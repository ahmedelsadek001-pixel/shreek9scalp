import pytest

from core.setup_quality import SetupQualityInput, score_setup


def test_empty_setup_is_blocked():
    result = score_setup(SetupQualityInput())
    assert result.score == 0
    assert result.grade == "BLOCKED"
    assert not result.tradable


def test_score_weights_sum_to_100():
    result = score_setup(SetupQualityInput(True, True, True, True, True, True, True, True, True))
    assert result.score == 100
    assert result.grade == "A+"
    assert result.tradable


def test_boundary_grades():
    assert score_setup(SetupQualityInput(htf_structure=True, liquidity_sweep=True, fvg=True, order_block=True)).score == 60
    assert score_setup(SetupQualityInput(htf_structure=True, liquidity_sweep=True, fvg=True, order_block=True, m15_confirmation=True)).score == 75


def test_only_boolean_inputs_are_scored():
    result = score_setup(SetupQualityInput(htf_structure=True, m15_confirmation=True, rr_valid=True, session_valid=True))
    assert result.score == 45
    assert not result.tradable


def test_wrong_type_rejected():
    with pytest.raises(TypeError):
        score_setup(None)
