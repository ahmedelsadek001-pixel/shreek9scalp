from datetime import datetime, timezone

from core.enums import Direction
from execution.shadow_pipeline import PaperShadowBridge
from paper_trading.engine import PaperFill, PaperOrder


def _order() -> PaperOrder:
    return PaperOrder(
        "XAUUSD", Direction.BUY, 2500.0, 2495.0, 0.03,
        datetime(2026, 9, 12, 10, 0, tzinfo=timezone.utc),
    )


def test_paper_order_can_be_reconciled_through_shadow_bridge():
    bridge = PaperShadowBridge()
    order = _order()
    bridge.register_paper_order("paper-001", order)
    fill = PaperFill(order, 2501.0, 0.03, datetime(2026, 9, 12, 10, 1, tzinfo=timezone.utc), "TP")
    result = bridge.reconcile_paper_fill("paper-001", fill)
    assert result.reconciled
    assert result.reasons == ()


def test_bridge_keeps_unknown_fill_blocked():
    bridge = PaperShadowBridge()
    order = _order()
    fill = PaperFill(order, 2501.0, 0.03, datetime(2026, 9, 12, 10, 1, tzinfo=timezone.utc), "TP")
    result = bridge.reconcile_paper_fill("unknown", fill)
    assert not result.reconciled
    assert result.reasons == ("unknown order identity",)
