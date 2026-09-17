import pytest

from core.research_provenance import (
    ResearchProvenance,
    build_provenance,
    fingerprint_mapping,
    validate_provenance,
)


def test_mapping_fingerprint_is_deterministic_and_order_independent():
    assert fingerprint_mapping({"b": 2, "a": 1}) == fingerprint_mapping({"a": 1, "b": 2})
    assert fingerprint_mapping({"a": 1}) != fingerprint_mapping({"a": 2})


def test_build_provenance_requires_code_revision():
    provenance = build_provenance(data={"bars": 10}, config={"risk": 0.01}, code_revision="abc123")
    validate_provenance(provenance)
    assert len(provenance.data_fingerprint) == 64
    assert len(provenance.config_fingerprint) == 64


def test_invalid_provenance_fails_closed():
    with pytest.raises(ValueError, match="provenance"):
        validate_provenance(object())
    with pytest.raises(ValueError, match="code revision"):
        validate_provenance(ResearchProvenance("data", "config", ""))


def test_fingerprint_rejects_non_mapping():
    with pytest.raises(ValueError, match="mapping"):
        fingerprint_mapping([("a", 1)])


def test_fingerprint_rejects_ambiguous_object_values():
    with pytest.raises(ValueError, match="unsupported value type"):
        fingerprint_mapping({"data": object()})


def test_fingerprint_rejects_non_string_keys():
    with pytest.raises(ValueError, match="non-string mapping key"):
        fingerprint_mapping({1: "bar"})


def test_fingerprint_rejects_non_finite_numbers():
    with pytest.raises(ValueError, match="non-finite"):
        fingerprint_mapping({"nan": float("nan")})
    with pytest.raises(ValueError, match="non-finite"):
        fingerprint_mapping({"inf": float("inf")})


def test_nested_json_like_values_are_canonicalized():
    left = {"bars": [{"close": 1.0, "symbol": "XAUUSD"}, {"close": 2.0}]}
    right = {"bars": [{"symbol": "XAUUSD", "close": 1.0}, {"close": 2.0}]}
    assert fingerprint_mapping(left) == fingerprint_mapping(right)
