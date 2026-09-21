from datetime import datetime,timedelta,timezone
from core.enums import Direction
from execution.execution_gate import evaluate_execution_gate
from execution.guarded_adapter import GuardedExecutionAdapter
from execution.quote_safety import evaluate_quote_safety,QuoteSafetyDecision
from execution.reconciliation import OrderIntent
from execution.recovery import RecoveryDecision,RecoveryState

def gate(): return evaluate_execution_gate(operational=(True,()),broker=(True,()),recovery=RecoveryDecision(RecoveryState.CONNECTED,True,"ready"),kill_switch_active=False)
def intent(): return OrderIntent("Q-1","XAUUSD",Direction.BUY,0.03,2500.0)

def test_stale_quote_never_reaches_transport():
    calls=[]; now=datetime.now(timezone.utc)
    q=evaluate_quote_safety(quote_time=now-timedelta(seconds=5),now=now,intended_price=2500,market_price=2500,max_age_seconds=2,max_deviation_points=3,point_size=.1)
    r=GuardedExecutionAdapter(lambda x:calls.append(x)).execute_intent(gate(),intent(),q)
    assert not r.executed and calls==[] and "quote safety" in r.reasons[0]

def test_fresh_quote_reaches_transport_once():
    calls=[]; now=datetime.now(timezone.utc)
    q=evaluate_quote_safety(quote_time=now,now=now,intended_price=2500,market_price=2500.1,max_age_seconds=2,max_deviation_points=3,point_size=.1)
    r=GuardedExecutionAdapter(lambda x:calls.append(x.order_id) or "sent").execute_intent(gate(),intent(),q)
    assert r.executed and calls==["Q-1"]

def test_fabricated_malformed_quote_decision_fails_closed():
    calls=[]
    r=GuardedExecutionAdapter(lambda x:calls.append(x)).execute_intent(gate(),intent(),object())
    assert not r.executed and calls==[]
