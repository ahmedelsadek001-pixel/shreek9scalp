"""Causal backtest engine with deterministic partial-exit lifecycle support."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from math import isfinite, sqrt
from typing import Iterable, Optional, Sequence
from core.enums import Direction
from core.models import ExecutionLevels

@dataclass(frozen=True)
class BacktestBar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    spread: float = 0.0
    def valid(self)->bool:
        v=(self.open,self.high,self.low,self.close,self.spread)
        return all(isfinite(float(x)) for x in v) and self.low<=self.high and self.spread>=0

@dataclass(frozen=True)
class BacktestOrder:
    signal_time: datetime
    direction: Direction
    levels: ExecutionLevels
    volume: float=1.0
    tag: str=""

@dataclass(frozen=True)
class BacktestTrade:
    signal_time: datetime
    entry_time: datetime
    exit_time: datetime
    direction: Direction
    entry: float
    exit: float
    volume: float
    gross_pnl: float
    costs: float
    net_pnl: float
    exit_reason: str
    tag: str=""

@dataclass(frozen=True)
class BacktestStats:
    starting_equity: float
    ending_equity: float
    net_pnl: float
    return_pct: float
    trades: int
    wins: int
    losses: int
    win_rate: float
    profit_factor: float
    expectancy: float
    max_drawdown: float
    max_drawdown_pct: float
    sharpe: float

@dataclass(frozen=True)
class BacktestResult:
    trades: tuple[BacktestTrade,...]
    equity_curve: tuple[float,...]
    stats: BacktestStats

@dataclass(frozen=True)
class CostModel:
    slippage: float=0.0
    point_value: float=1.0
    commission_per_volume: float=0.0
    def valid(self)->bool:
        v=(self.slippage,self.point_value,self.commission_per_volume)
        return all(isfinite(float(x)) for x in v) and self.slippage>=0 and self.point_value>0 and self.commission_per_volume>=0

def _validate_levels(direction:Direction,levels:ExecutionLevels)->None:
    values=(levels.entry,levels.sl,levels.tp1,levels.tp2,levels.tp3,levels.risk)
    if not all(isfinite(float(x)) and float(x)>0 for x in values): raise ValueError("execution levels must be finite and positive")
    if direction==Direction.BUY: valid=levels.sl<levels.entry<levels.tp1<=levels.tp2<=levels.tp3
    elif direction==Direction.SELL: valid=levels.sl>levels.entry>levels.tp1>=levels.tp2>=levels.tp3
    else: valid=False
    if not valid or abs(abs(levels.entry-levels.sl)-levels.risk)>max(1e-9,levels.risk*1e-6): raise ValueError("execution levels are inconsistent with order direction")

def _fill_price(bar:BacktestBar,direction:Direction,slippage:float)->float:
    half=bar.spread/2
    return bar.open+half+slippage if direction==Direction.BUY else bar.open-half-slippage

def _exit_hit(bar:BacktestBar,direction:Direction,sl:float,tp:float)->tuple[Optional[float],str]:
    stop,target=(bar.low<=sl,bar.high>=tp) if direction==Direction.BUY else (bar.high>=sl,bar.low<=tp)
    if stop:return sl,"SL"
    if target:return tp,"TP3"
    return None,""

def _stats(start:float,equity:Sequence[float],trades:Sequence[BacktestTrade])->BacktestStats:
    end=equity[-1] if equity else start; net=end-start; wins=sum(t.net_pnl>0 for t in trades); losses=sum(t.net_pnl<0 for t in trades)
    gp=sum(max(t.net_pnl,0) for t in trades); gl=sum(-min(t.net_pnl,0) for t in trades); pf=gp/gl if gl else (float("inf") if gp else 0)
    peak=start; dd=0
    for x in equity: peak=max(peak,x); dd=max(dd,peak-x)
    rs=[]; prev=start
    for x in equity:
        if prev: rs.append((x-prev)/prev)
        prev=x
    mean=sum(rs)/len(rs) if rs else 0; var=sum((r-mean)**2 for r in rs)/(len(rs)-1) if len(rs)>1 else 0
    sharpe=mean/sqrt(var)*sqrt(252) if var>0 else 0
    return BacktestStats(start,end,net,net/start*100,len(trades),wins,losses,wins/len(trades)*100 if trades else 0,pf,net/len(trades) if trades else 0,dd,dd/start*100,sharpe)

def run_backtest(bars:Iterable[BacktestBar],orders:Iterable[BacktestOrder],starting_equity:float=10000.0,costs:CostModel=CostModel(),force_close_at_end:bool=True)->BacktestResult:
    if not isfinite(starting_equity) or starting_equity<=0 or not costs.valid(): raise ValueError("invalid backtest configuration")
    series=list(bars)
    if not series or any(not b.valid() for b in series): raise ValueError("invalid or empty bar series")
    if any(series[i].timestamp>=series[i+1].timestamp for i in range(len(series)-1)): raise ValueError("bars must be strictly chronological")
    by_time={b.timestamp:i for i,b in enumerate(series)}; pending=sorted(orders,key=lambda o:o.signal_time)
    for o in pending:
        if o.signal_time not in by_time: raise ValueError("every order must reference an existing signal bar")
        if o.direction not in (Direction.BUY,Direction.SELL): raise ValueError("backtest orders must be BUY or SELL")
        if not isfinite(o.volume) or o.volume<=0: raise ValueError("order volume must be positive and finite")
        _validate_levels(o.direction,o.levels)
    trades=[]; equity=[starting_equity]; occupied=-1
    for o in pending:
        si=by_time[o.signal_time]; ei=si+1
        if ei>=len(series) or ei<=occupied: continue
        eb=series[ei]; entry=_fill_price(eb,o.direction,costs.slippage)
        if (o.direction==Direction.BUY and entry<=o.levels.sl) or (o.direction==Direction.SELL and entry>=o.levels.sl): continue
        exit_price=None; reason=""; xi=None
        for i in range(ei,len(series)):
            hit,why=_exit_hit(series[i],o.direction,o.levels.sl,o.levels.tp3)
            if hit is not None: exit_price,reason,xi=hit,why,i; break
        if exit_price is None:
            if not force_close_at_end: continue
            xi=len(series)-1; exit_price,reason=series[-1].close,"EOD"
        half=series[xi].spread/2
        adverse=exit_price-costs.slippage-half if o.direction==Direction.BUY else exit_price+costs.slippage+half
        gross=((adverse-entry) if o.direction==Direction.BUY else (entry-adverse))*o.volume*costs.point_value
        commission=costs.commission_per_volume*o.volume; net=gross-commission
        trades.append(BacktestTrade(o.signal_time,eb.timestamp,series[xi].timestamp,o.direction,entry,adverse,o.volume,gross,commission,net,reason,o.tag))
        equity.append(equity[-1]+net); occupied=xi
    return BacktestResult(tuple(trades),tuple(equity),_stats(starting_equity,equity,trades))
