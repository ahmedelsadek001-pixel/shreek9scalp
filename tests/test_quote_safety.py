from datetime import datetime,timedelta,timezone
import pytest
from execution.quote_safety import evaluate_quote_safety
NOW=datetime(2026,9,21,19,0,tzinfo=timezone.utc)

def q(**kw):
    x=dict(quote_time=NOW,now=NOW,intended_price=2500.0,market_price=2500.2,max_age_seconds=2.0,max_deviation_points=3.0,point_size=0.1); x.update(kw); return evaluate_quote_safety(**x)

def test_fresh_quote_within_deviation_passes(): assert q().allowed
def test_stale_quote_fails_closed(): assert not q(quote_time=NOW-timedelta(seconds=3)).allowed
def test_future_quote_fails_closed(): assert not q(quote_time=NOW+timedelta(seconds=1)).allowed
def test_excessive_deviation_fails_closed(): assert not q(market_price=2500.4).allowed
@pytest.mark.parametrize("field",["intended_price","market_price","max_age_seconds","max_deviation_points","point_size"])
def test_boolean_numeric_inputs_fail_closed(field): assert not q(**{field:True}).allowed
def test_naive_timestamp_fails_closed(): assert not q(quote_time=NOW.replace(tzinfo=None)).allowed
