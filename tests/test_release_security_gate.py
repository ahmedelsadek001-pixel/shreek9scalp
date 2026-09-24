import pytest
from pathlib import Path

from security.release_security_gate import evaluate_paths, evaluate_tree, scan_source


def test_clean_source_passes():
    passed, findings = evaluate_tree((("core/example.py", "def f():\n    return 1\n"),))
    assert passed
    assert not findings


def test_api_key_literal_is_blocked():
    passed, findings = evaluate_tree((("bad.py", "API_KEY = '12345678901234567890'\n"),))
    assert not passed
    assert findings[0].rule == "generic-api-key"


def test_live_order_marker_is_blocked():
    findings = scan_source("bad.py", "result = mt5.order_send(request)\n")
    assert any(f.rule == "live-order-authority" for f in findings)


@pytest.mark.parametrize("function_name", ["positions_send", "trade_transaction", "send_order", "place_order", "submit_order"])
def test_alternate_transport_markers_are_blocked(function_name):
    findings = scan_source("bad.py", f"result = broker.{function_name}(request)\n")
    assert any(f.rule == "live-order-authority" for f in findings)


def test_dynamic_transport_dispatch_is_blocked():
    findings = scan_source("bad.py", 'result = getattr(broker, "order_send")(request)\n')
    assert any(f.rule == "live-order-authority" for f in findings)


def test_subscript_transport_dispatch_is_blocked():
    findings = scan_source("bad.py", 'result = broker["order_send"](request)\n')
    assert any(f.rule == "live-order-authority" for f in findings)


def test_malformed_source_is_blocked_fail_closed():
    passed, findings = evaluate_tree((("broken.py", "def incomplete(:\n"),))
    assert not passed
    assert any(f.rule == "syntax-error" for f in findings)


def test_invalid_inputs_fail_explicitly():
    with pytest.raises(ValueError):
        scan_source("", "x")
    with pytest.raises(TypeError):
        scan_source("x.py", 123)


def test_path_scan_fails_closed_on_read_error(tmp_path):
    missing = tmp_path / "missing.py"
    passed, findings = evaluate_paths((missing,))
    assert not passed
    assert any(f.rule == "read-error" for f in findings)


def test_path_scan_excludes_test_and_security_trees(tmp_path):
    test_file = tmp_path / "tests" / "fixture.py"
    security_file = tmp_path / "security" / "fixture.py"
    test_file.parent.mkdir()
    security_file.parent.mkdir()
    test_file.write_text("broker.order_send(request)\n", encoding="utf-8")
    security_file.write_text("broker.order_send(request)\n", encoding="utf-8")
    passed, findings = evaluate_paths((test_file, security_file))
    assert passed
    assert findings == ()

