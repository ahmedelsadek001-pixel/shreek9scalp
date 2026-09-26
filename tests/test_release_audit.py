from core.release_audit import REQUIRED_PATHS, audit_tree, require_release_tree


def test_complete_tree_passes():
    result = audit_tree(REQUIRED_PATHS)
    assert result.passed
    assert result.missing_paths == ()


def test_v53_execution_safety_layers_are_release_required():
    required = set(REQUIRED_PATHS)
    assert {
        "core/promotion_gate.py",
        "execution/broker_outcome.py",
        "execution/execution_journal.py",
        "execution/execution_lifecycle.py",
        "execution/guarded_adapter.py",
        "execution/idempotency.py",
        "execution/quote_safety.py",
        "execution/restart_recovery.py",
        "execution/safety_gate.py",
    } <= required


def test_missing_required_path_blocks():
    result = audit_tree(REQUIRED_PATHS[:-1])
    assert not result.passed
    assert REQUIRED_PATHS[-1] in result.missing_paths


def test_runtime_order_send_is_flagged():
    result = audit_tree(REQUIRED_PATHS, production_sources=(("execution/live.py", "broker.order_send(order)"),))
    assert not result.passed
    assert result.forbidden_runtime_files == ("execution/live.py",)


def test_non_python_files_are_ignored_for_runtime_scan():
    result = audit_tree(REQUIRED_PATHS, production_sources=(("docs/example.txt", "order_send"),))
    assert result.passed


def test_require_release_tree_raises_on_failure():
    result = audit_tree(())
    try:
        require_release_tree(result)
    except RuntimeError as exc:
        assert "release tree audit failed" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")
