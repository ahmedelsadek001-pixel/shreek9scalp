"""Premium/discount and PD-array confluence for closed-bar data."""
from __future__ import annotations

import pandas as pd

from config.settings import Settings
from core.enums import Direction, Timeframe
from core.models import PDArrayZone
from market.fvg import find_fvgs
from market.order_blocks import find_order_block
from market.structure import determine_structure


def compute_pd_array_zone(
    df_h4: pd.DataFrame,
    settings: Settings,
    lookback: int = 60,
) -> PDArrayZone:
    """Build a PD zone using only confirmed H4 structure and closed data."""
    if df_h4 is None or len(df_h4) < 3:
        return PDArrayZone(zone_top=None, zone_bottom=None, equilibrium=None)

    atr = float(df_h4["atr"].iloc[-1]) if "atr" in df_h4.columns else None
    if atr is None or not pd.notna(atr) or atr <= 0:
        return PDArrayZone(zone_top=None, zone_bottom=None, equilibrium=None)

    struct = determine_structure(
        df_h4,
        Timeframe.H4,
        atr=atr,
        threshold_atr=settings.bos_break_threshold_atr,
        confirmation_bars=settings.swing_window["H4"],
    )
    sh, sl = struct.last_swing_high, struct.last_swing_low
    if sh is None or sl is None or sh <= sl:
        return PDArrayZone(zone_top=None, zone_bottom=None, equilibrium=None)

    zone_top, zone_bottom = float(sh), float(sl)
    equilibrium = (zone_top + zone_bottom) / 2.0
    ob_bull = find_order_block(df_h4, Direction.BUY, equilibrium, sh, sl, settings.ob_min_body_atr, lookback=lookback)
    ob_bear = find_order_block(df_h4, Direction.SELL, equilibrium, sh, sl, settings.ob_min_body_atr, lookback=lookback)
    ob = ob_bull or ob_bear

    fvgs = find_fvgs(df_h4, lookback=min(lookback, settings.fvg_max_age_bars))
    fvg = min(fvgs, key=lambda item: abs(equilibrium - item.midpoint)) if fvgs else None

    if ob is not None:
        zone_top, zone_bottom = max(zone_top, ob.high), min(zone_bottom, ob.low)
    if fvg is not None:
        zone_top, zone_bottom = max(zone_top, fvg.top), min(zone_bottom, fvg.bottom)

    equilibrium = (zone_top + zone_bottom) / 2.0
    return PDArrayZone(
        zone_top=zone_top,
        zone_bottom=zone_bottom,
        equilibrium=equilibrium,
        order_block=ob,
        fvg=fvg,
        swing_high=sh,
        swing_low=sl,
    )


def price_in_pd_zone(pd_zone: PDArrayZone, current_price: float, direction: Direction) -> dict:
    """Return deterministic location/confluence information for current price."""
    if not pd_zone.is_valid or not pd.notna(current_price):
        return {"in_zone": False, "sub_zone": "UNKNOWN", "pct": 50.0, "correct_zone": False}
    zt, zb, eq = pd_zone.zone_top, pd_zone.zone_bottom, pd_zone.equilibrium
    if current_price < zb or current_price > zt:
        return {"in_zone": False, "sub_zone": "OUTSIDE", "pct": 0.0, "correct_zone": False}
    width = zt - zb
    pct = (current_price - zb) / width * 100 if width else 50.0
    if direction == Direction.BUY:
        sub_zone = "DISCOUNT" if current_price <= eq else "PREMIUM"
        correct = current_price <= eq
    elif direction == Direction.SELL:
        sub_zone = "PREMIUM" if current_price >= eq else "DISCOUNT"
        correct = current_price >= eq
    else:
        sub_zone, correct = "UNKNOWN", False
    return {
        "in_zone": True,
        "sub_zone": sub_zone,
        "pct": round(pct, 1),
        "correct_zone": correct,
        "distance_to_eq": abs(current_price - eq),
        "distance_to_zone_edge": min(abs(current_price - zt), abs(current_price - zb)),
    }
