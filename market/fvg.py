"""Fair Value Gap detection using closed candles only."""
from __future__ import annotations
import pandas as pd
from core.enums import Direction
from core.models import FairValueGap, OrderBlock

def _fvg_is_untouched(kind: str, top: float, bottom: float, df: pd.DataFrame, formed_at: int) -> bool:
    subsequent = df.iloc[formed_at + 1:]
    if kind == "bullish":
        return not (subsequent["low"] <= bottom).any()
    return not (subsequent["high"] >= top).any()

def find_fvgs(df: pd.DataFrame, lookback: int = 40) -> list[FairValueGap]:
    subset = df.iloc[-lookback:].reset_index(drop=True)
    if len(subset) < 3: return []
    highs, lows = subset["high"].to_numpy(), subset["low"].to_numpy()
    out=[]
    for i in range(2,len(subset)):
        if highs[i-2] < lows[i]:
            bottom, top = float(highs[i-2]), float(lows[i])
            if _fvg_is_untouched("bullish",top,bottom,subset,i): out.append(FairValueGap(kind="bullish",top=top,bottom=bottom,formed_at=i))
        elif lows[i-2] > highs[i]:
            bottom, top = float(highs[i]), float(lows[i-2])
            if _fvg_is_untouched("bearish",top,bottom,subset,i): out.append(FairValueGap(kind="bearish",top=top,bottom=bottom,formed_at=i))
    return out

def nearest_fvg(fvgs,current_price,direction):
    wanted="bullish" if direction==Direction.BUY else "bearish"
    return min((f for f in fvgs if f.kind==wanted),key=lambda f:abs(current_price-f.midpoint),default=None)

def fvg_overlaps_ob(fvg: FairValueGap, ob: OrderBlock) -> bool:
    return fvg.overlaps(ob)
