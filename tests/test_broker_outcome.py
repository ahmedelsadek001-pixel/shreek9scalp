import pytest
from execution.broker_outcome import BrokerOutcome, classify_broker_outcome

def test_timeout_is_unknown_and_never_retryable():
    d=classify_broker_outcome(acknowledged=False,accepted=None)
    assert d.outcome is BrokerOutcome.UNKNOWN and not d.retry_allowed

@pytest.mark.parametrize("code",["PRICE_CHANGED","REQUOTE","MARKET_BUSY"])
def test_only_explicit_rejections_can_be_retryable(code):
    d=classify_broker_outcome(acknowledged=True,accepted=False,rejection_code=code)
    assert d.outcome is BrokerOutcome.REJECTED_RETRYABLE and d.retry_allowed

def test_unknown_rejection_is_final():
    d=classify_broker_outcome(acknowledged=True,accepted=False,rejection_code="OTHER")
    assert d.outcome is BrokerOutcome.REJECTED_FINAL and not d.retry_allowed

def test_accepted_with_rejection_code_fails_closed():
    with pytest.raises(ValueError): classify_broker_outcome(acknowledged=True,accepted=True,rejection_code="REQUOTE")
