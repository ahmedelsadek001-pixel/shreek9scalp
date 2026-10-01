from datetime import datetime, timezone

from core.enums import Direction, SetupType, SignalStatus, Timeframe
from core.models import TradeSignal
from core.release_gate import ReleaseEvidence, evaluate_release
from core.setup_quality import SetupQualityInput
from core.trade_orchestrator import TradeOrchestrator
from execution.reconciliation import OrderIntent
from execution.recovery import RecoveryState, ShadowRecovery
from execution.shadow import ShadowExecution
from execution.shadow_pipeline import PaperShadowBridge
from paper_trading.engine import PaperTradingEngine
from risk.risk_budget import RiskBudget


TIMESTAMP = datetime(2026, 9, 12, 10, 2, tzinfo=timezone.utc)


def _bars():
    return [
        {
            "timestamp": datetime(2026, 9, 12, 10, i, tzinfo=timezone.utc),
            "open": 99.0,
            "high": 101.0,
            "low": 98.0,
            "close": 100.0,
        }
        for i in range(3)
    ]


def _setup():
    return SetupQualityInput(
        htf_structure=True,
        liquidity_sweep=True,
        fvg=True,
        order_block=True,
        m15_confirmation=True,
        m5_confirmation=True,
        m3_confirmation=True,
        rr_valid=True,
        session_valid=True,
    )


def _signal():
    return TradeSignal(
        status=SignalStatus.VALID,
        setup_type=SetupType.COMBINED,
        frame=Timeframe.M15,
        direction=Direction.BUY,
        entry_price=100.0,
        sl_price=99.0,
        confidence=0.9,
        aligned=True,
    )


def test_full_paper_shadow_recovery_release_chain():
    engine = PaperTradingEngine(1000, 0.05)
    orchestrator = TradeOrchestrator(engine, RiskBudget(1000, risk_pct=0.01))

    decision = orchestrator.evaluate_and_submit(
        _signal(), _bars(), _setup(), timestamp=TIMESTAMP,
        symbol="XAUUSD", setup_min_score=70,
    )
    assert decision.allowed
    assert engine.open_order is not None

    shadow = ShadowExecution()
    bridge = PaperShadowBridge(shadow)
    order = engine.open_order
    bridge.register_paper_order("paper-chain-001", order)
    fill = engine.close(
        101.0,
        datetime(2026, 9, 12, 10, 5, tzinfo=timezone.utc),
        "TP",
    )
    validation = bridge.reconcile_paper_fill("paper-chain-001", fill)
    assert validation.reconciled
    assert shadow.pending_order_ids() == ()

    recovery = ShadowRecovery(shadow)
    assert recovery.disconnect().state is RecoveryState.DISCONNECTED
    assert recovery.begin_recovery().state is RecoveryState.RECOVERING
    recovered = recovery.complete_recovery()
    assert recovered.state is RecoveryState.CONNECTED
    assert recovered.can_submit

    evidence = ReleaseEvidence(
        ci_green=True,
        tests_green=True,
        data_integrity_validated=True,
        walk_forward_passed=True,
        robustness_passed=True,
        paper_trading_validated=True,
        security_reviewed=True,
        execution_reconciled=True,
        shadow_validated=validation.reconciled,
        recovery_validated=recovered.can_submit,
    )
    release = evaluate_release(evidence)
    assert release.ready
    assert release.failures == ()


def test_recovery_blocks_release_when_shadow_order_remains_pending():
    shadow = ShadowExecution()
    recovery = ShadowRecovery(shadow)
    shadow.submit_intent(OrderIntent("pending-001", "XAUUSD", Direction.BUY, 0.03, 2500.0))
    recovery.disconnect()
    recovery.begin_recovery()
    blocked = recovery.complete_recovery()
    assert not blocked.can_submit
    assert blocked.state is RecoveryState.RECOVERING

    evidence = ReleaseEvidence(
        ci_green=True,
        tests_green=True,
        data_integrity_validated=True,
        walk_forward_passed=True,
        robustness_passed=True,
        paper_trading_validated=True,
        security_reviewed=True,
        execution_reconciled=True,
        shadow_validated=True,
        recovery_validated=blocked.can_submit,
    )
    release = evaluate_release(evidence)
    assert not release.ready
    assert "disconnect recovery has not been validated" in release.failures
