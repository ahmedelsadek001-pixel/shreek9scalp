import pytest

from research.instrument_specs import ResearchInstrumentSpec, XAUUSD_RESEARCH_SPEC


def test_xauusd_research_spec_is_explicit_and_valid():
    XAUUSD_RESEARCH_SPEC.validate()
    assert XAUUSD_RESEARCH_SPEC.symbol == "XAUUSD"
    assert XAUUSD_RESEARCH_SPEC.pip_size == pytest.approx(0.10)
    assert XAUUSD_RESEARCH_SPEC.price_decimals == 2


def test_invalid_instrument_spec_is_rejected():
    with pytest.raises(ValueError):
        ResearchInstrumentSpec("XAUUSD", 0.0, 2).validate()
    with pytest.raises(ValueError):
        ResearchInstrumentSpec("XAUUSD", 0.10, 2.5).validate()
