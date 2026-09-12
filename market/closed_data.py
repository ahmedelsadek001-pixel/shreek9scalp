"""Helpers that make closed-candle usage explicit and testable."""
from __future__ import annotations
import pandas as pd

def closed_bars(df: pd.DataFrame) -> pd.DataFrame:
    """Return only completed bars; never allow an in-progress final row."""
    if len(df) < 2:
        return df.iloc[0:0].copy()
    out = df.iloc[:-1].copy()
    return out.reset_index(drop=True)

def last_closed_time(df: pd.DataFrame):
    if len(df) < 2 or "time" not in df.columns:
        return None
    return df.iloc[-2]["time"]
