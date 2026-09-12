from __future__ import annotations
import os
from dataclasses import dataclass, field, fields
from typing import Optional
from config import constants as C
import MetaTrader5 as mt5

@dataclass
class TimeframeSpec:
    mt5_constant: int
    bars_to_fetch: int
    swing_window: int

@dataclass
class Settings:
    model_name: str = field(default_factory=lambda: os.environ.get("MODEL_NAME", "openai/gpt-4o-mini"))
    ai_cache_minutes: int = 5
    confluence_threshold: int = 10
    atr_sl_buffer: float = C.DEFAULT_ATR_SL_BUFFER
    min_rr_to_draw: float = C.DEFAULT_MIN_RR_TO_DRAW
    ob_min_body_atr: float = C.OB_MIN_BODY_ATR_RATIO_DEFAULT
    fvg_max_age_bars: int = 50
    pd_array_lookback: int = 60
    news_filter_hours: int = 1
    m15_entry_mode: bool = True
    m15_candle_confirmation: bool = True
    m15_bos_required: bool = True
    m15_fvg_entry: bool = True
    m15_ob_entry: bool = True
    m15_sweep_confirmation: bool = True
    m5_entry_mode: bool = True
    m3_entry_mode: bool = True
    m3_fvg_failure_required: bool = False
    trail_stop_atr_mult: float = C.DEFAULT_TRAIL_STOP_ATR_MULT
    breakeven_at_rr: float = C.DEFAULT_BREAKEVEN_AT_RR
    partial_close_at_tp1: float = C.DEFAULT_PARTIAL_CLOSE_TP1
    partial_close_at_tp2: float = C.DEFAULT_PARTIAL_CLOSE_TP2
    full_close_at_tp3: bool = True
    bos_break_threshold_atr: float = 0.1
    ranging_atr_factor: float = 0.5
    daily_loss_limit_pct: float = C.DEFAULT_DAILY_LOSS_LIMIT_PCT
    weekly_loss_limit_pct: float = 0.10
    max_drawdown_pct: float = 0.15
    max_consecutive_losses: int = 3
    swing_window: dict[str,int] = field(default_factory=lambda:{"D1":5,"H4":5,"H1":8,"M15":10,"M5":12,"M3":15})
    def set_field(self,key:str,raw_value:str)->tuple[bool,str]:
        if key not in {f.name for f in fields(self)}: return False,f"Unknown setting: {key}"
        current=getattr(self,key)
        try:
            if isinstance(current,bool): coerced=raw_value.strip().lower() in ("1","true","on","yes")
            elif isinstance(current,int): coerced=int(raw_value)
            elif isinstance(current,float): coerced=float(raw_value)
            else: coerced=raw_value
        except ValueError: return False,f"Invalid value '{raw_value}' for {key}"
        setattr(self,key,coerced); return True,f"{key} -> {coerced}"

TIMEFRAMES={
 "D1":TimeframeSpec(mt5.TIMEFRAME_D1,150,5),"H4":TimeframeSpec(mt5.TIMEFRAME_H4,200,5),
 "H1":TimeframeSpec(mt5.TIMEFRAME_H1,250,8),"M15":TimeframeSpec(mt5.TIMEFRAME_M15,300,10),
 "M5":TimeframeSpec(mt5.TIMEFRAME_M5,400,12),"M3":TimeframeSpec(mt5.TIMEFRAME_M3,400,15)}
SYMBOL_CATEGORIES={"Metals":["XAUUSD","XAGUSD"],"Majors":["EURUSD","GBPUSD","USDJPY","USDCHF","AUDUSD","USDCAD","NZDUSD"],"Crypto":["BTCUSD","ETHUSD"],"Indices":["US30","US500","NAS100","GER40","UK100"]}
def _parse_allowed_ids(raw:Optional[str])->frozenset[int]:
    if not raw:return frozenset()
    return frozenset(int(x.strip()) for x in raw.split(",") if x.strip().isdigit())
ALLOWED_TELEGRAM_USER_IDS=_parse_allowed_ids(os.environ.get("ALLOWED_TELEGRAM_USER_IDS"))
SETTINGS=Settings()
