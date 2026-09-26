from dataclasses import replace
from datetime import datetime,timedelta,timezone
from core.enums import Direction
from execution.execution_gate import evaluate_environment_gate
from execution.broker_safety import BrokerSafetyPolicy
from execution.operational_guard import OperationalPolicy, OperationalSnapshot
from execution.guarded_adapter import GuardedExecutionAdapter
from execution.quote_safety import evaluate_quote_safety,QuoteSafetyDecision
from execution.reconciliation import OrderIntent
from execution.recovery import RecoveryDecision,RecoveryState
from execution.idempotency import IdempotencyLedger

def gate():
    now=datetime.now(timezone.utc)
    return evaluate_environment_gate(
        operational_policy=OperationalPolicy(),
        operational_snapshot=OperationalSnapshot(now,now,now,True,True),
        broker_policy=BrokerSafetyPolicy(frozenset({"XAUUSD"}),1.0,.01,1.0,.5),
        symbol="XAUUSD",spread=.2,volume=.03,slippage=.1,
        recovery=RecoveryDecision(RecoveryState.CONNECTED,True,"ready"),
        kill_switch_active=False,
    )
def intent(): return OrderIntent("Q-1","XAUUSD",Direction.BUY,0.03,2500.0)

def test_stale_quote_never_reaches_transport():
    calls=[]; now=datetime.now(timezone.utc)
    q=evaluate_quote_safety(quote_time=now-timedelta(seconds=5),now=now,intended_price=2500,market_price=2500,max_age_seconds=2,max_deviation_points=3,point_size=.1)
    r=GuardedExecutionAdapter(lambda x:calls.append(x)).execute_intent(gate(),intent(),q)
    assert not r.executed and calls==[] and "quote safety" in r.reasons[0]

def test_fresh_quote_reaches_transport_once():
    calls=[]; now=datetime.now(timezone.utc)
    q=evaluate_quote_safety(quote_time=now,now=now,intended_price=2500,market_price=2500.1,max_age_seconds=2,max_deviation_points=3,point_size=.1)
    r=GuardedExecutionAdapter(lambda x:calls.append(x.order_id) or "sent",IdempotencyLedger()).execute_intent(gate(),intent(),q)
    assert r.executed and calls==["Q-1"]

def test_fabricated_malformed_quote_decision_fails_closed():
    calls=[]
    r=GuardedExecutionAdapter(lambda x:calls.append(x)).execute_intent(gate(),intent(),object())
    assert not r.executed and calls==[]

def test_strict_boundary_rejects_missing_quote_before_transport():
    calls=[]
    r=GuardedExecutionAdapter(lambda x:calls.append(x)).execute_intent_strict(gate(),intent(),None)
    assert not r.executed and calls==[] and r.reasons==("quote safety decision required",)

def test_strict_boundary_accepts_only_explicit_fresh_quote():
    calls=[]; now=datetime.now(timezone.utc)
    q=evaluate_quote_safety(quote_time=now,now=now,intended_price=2500,market_price=2500,max_age_seconds=2,max_deviation_points=3,point_size=.1)
    r=GuardedExecutionAdapter(lambda x:calls.append(x.order_id) or "sent",IdempotencyLedger()).execute_intent_strict(gate(),intent(),q)
    assert r.executed and calls==["Q-1"]

def test_missing_quote_is_blocked_on_both_submission_methods():
    calls=[]; adapter=GuardedExecutionAdapter(lambda x:calls.append(x))
    assert adapter.execute_intent(gate(),intent()).reasons==("quote safety decision required",)
    assert adapter.execute_intent_strict(gate(),intent(),None).reasons==("quote safety decision required",)
    assert calls==[]

def test_forged_positive_quote_and_mismatched_price_never_reach_transport():
    calls=[]; adapter=GuardedExecutionAdapter(lambda x:calls.append(x))
    forged=QuoteSafetyDecision(True,"accepted",2500.0)
    assert "not issued" in adapter.execute_intent(gate(),intent(),forged).reasons[0]
    now=datetime.now(timezone.utc)
    wrong=evaluate_quote_safety(quote_time=now,now=now,intended_price=2501.0,
                                market_price=2501.0,max_age_seconds=2,
                                max_deviation_points=3,point_size=.1)
    assert "does not match intent" in adapter.execute_intent(gate(),intent(),wrong).reasons[0]
    assert calls==[]

def test_cloned_or_mutated_issued_quote_cannot_change_intended_price():
    calls=[]; now=datetime.now(timezone.utc)
    issued=evaluate_quote_safety(quote_time=now,now=now,intended_price=2501.0,
                                 market_price=2501.0,max_age_seconds=2,
                                 max_deviation_points=3,point_size=.1)
    adapter=GuardedExecutionAdapter(lambda x:calls.append(x),IdempotencyLedger())
    copied=replace(issued,intended_price=2500.0)
    assert "not issued" in adapter.execute_intent(gate(),intent(),copied).reasons[0]
    object.__setattr__(issued,"intended_price",2500.0)
    assert "not issued" in adapter.execute_intent(gate(),intent(),issued).reasons[0]
    assert calls==[]

def test_quote_expires_between_evaluation_and_submission(monkeypatch):
    from execution import guarded_adapter

    calls=[]; now=datetime.now(timezone.utc)
    quote=evaluate_quote_safety(quote_time=now,now=now,intended_price=2500.0,
                                market_price=2500.0,max_age_seconds=2,
                                max_deviation_points=3,point_size=.1)
    monkeypatch.setattr(guarded_adapter,"utc_now",lambda: now+timedelta(seconds=3))
    adapter=GuardedExecutionAdapter(lambda x:calls.append(x),IdempotencyLedger())
    result=adapter.execute_intent(gate(),intent(),quote)
    assert not result.executed
    assert result.reasons==("quote expired before submission",)
    assert calls==[]
