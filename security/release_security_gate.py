"""Static security gate for SHREEK V5.1 release validation.

The gate detects credential-like literals and actual live-order call sites.
Test fixtures may contain intentionally dangerous examples and are excluded
by the CI tree policy; the scanner itself remains useful for targeted checks.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import re
from typing import Iterable, Union


@dataclass(frozen=True)
class SecurityFinding:
    rule: str
    path: str
    detail: str


_SECRET_PATTERNS = (
    ("generic-api-key", re.compile(r"(?i)(api[_-]?key|secret|token)\s*[:=]\s*[\"'][^\"']{12,}[\"']")),
    ("telegram-bot-token", re.compile(r"\b\d{8,12}:[A-Za-z0-9_-]{30,}\b")),
    ("openai-key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
)
_LIVE_FUNCTIONS = {
    # MT5/native broker transport names.
    "order_send",
    "positions_send",
    "trade_transaction",
    # Generic transport aliases that must remain behind the guarded adapter.
    "send_order",
    "place_order",
    "submit_order",
}
DEFAULT_EXCLUDED_PARTS = frozenset({".git", ".venv", "venv", "__pycache__", "tests", "security"})
# The sole broker send call is constrained to a reviewed DEMO-only module.
# Any change to it breaks the release gate until its new bytes are reviewed.
_DEMO_TRANSPORT_SHA256 = "d19f1ed5ea256fd5bda2af7565a6a447a8a11d75447c843f0002f151e19a32ef"


def _reviewed_demo_transport(path: str, content: str) -> bool:
    normalized = path.replace("\\", "/")
    return (normalized == "execution/mt5_demo_transport.py"
            or normalized.endswith("/execution/mt5_demo_transport.py")) and (
                sha256(content.encode("utf-8")).hexdigest() == _DEMO_TRANSPORT_SHA256
            )


def _has_live_order_call(content: str) -> bool:
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return False
    dangerous_aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
            value = node.value
            dangerous = False
            if isinstance(value, ast.Attribute) and value.attr in _LIVE_FUNCTIONS:
                dangerous = True
            elif (
                isinstance(value, ast.Subscript)
                and isinstance(value.slice, ast.Constant)
                and value.slice.value in _LIVE_FUNCTIONS
            ):
                dangerous = True
            elif (
                isinstance(value, ast.Call)
                and isinstance(value.func, ast.Name)
                and value.func.id == "getattr"
                and len(value.args) >= 2
                and isinstance(value.args[1], ast.Constant)
                and value.args[1].value in _LIVE_FUNCTIONS
            ):
                dangerous = True
            if dangerous:
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                dangerous_aliases.update(
                    target.id for target in targets if isinstance(target, ast.Name)
                )
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            function = node.func
            if isinstance(function, ast.Name) and (
                function.id in _LIVE_FUNCTIONS or function.id in dangerous_aliases
            ):
                return True
            if isinstance(function, ast.Attribute) and function.attr in _LIVE_FUNCTIONS:
                return True
            # Catch dynamic attribute dispatch such as
            # ``getattr(broker, "order_send")(request)``.
            if (
                isinstance(function, ast.Call)
                and isinstance(function.func, ast.Name)
                and function.func.id == "getattr"
                and len(function.args) >= 2
                and isinstance(function.args[1], ast.Constant)
                and function.args[1].value in _LIVE_FUNCTIONS
            ):
                return True
            # Catch mapping-style dynamic dispatch such as
            # ``broker["order_send"](request)``.
            if (
                isinstance(function, ast.Subscript)
                and isinstance(function.slice, ast.Constant)
                and function.slice.value in _LIVE_FUNCTIONS
            ):
                return True
    return False


def scan_source(path: str, content: str) -> tuple[SecurityFinding, ...]:
    """Return conservative findings for one source file."""
    if not path.strip():
        raise ValueError("path is required")
    if not isinstance(content, str):
        raise TypeError("content must be str")
    findings: list[SecurityFinding] = []
    # A security scanner must fail closed on unreadable production source.
    # ``compileall`` remains a separate CI check, but this keeps the gate safe
    # when it is called independently or from a release-review script.
    try:
        ast.parse(content, filename=path)
    except SyntaxError as exc:
        findings.append(SecurityFinding("syntax-error", path, f"source could not be parsed: {exc.msg}"))
        return tuple(findings)
    for rule, pattern in _SECRET_PATTERNS:
        if pattern.search(content):
            findings.append(SecurityFinding(rule, path, "credential-like material detected"))
    if _has_live_order_call(content) and not _reviewed_demo_transport(path, content):
        findings.append(SecurityFinding("live-order-authority", path, "live broker transport call detected"))
    return tuple(findings)


def evaluate_tree(files: Iterable[tuple[str, str]]) -> tuple[bool, tuple[SecurityFinding, ...]]:
    """Fail closed when any scanned source contains a security finding."""
    findings: list[SecurityFinding] = []
    for path, content in files:
        findings.extend(scan_source(path, content))
    return not findings, tuple(findings)


def evaluate_paths(
    paths: Iterable[Union[str, Path]],
    *,
    excluded_parts: Iterable[str] = DEFAULT_EXCLUDED_PARTS,
) -> tuple[bool, tuple[SecurityFinding, ...]]:
    """Scan Python files from a release tree and fail closed on read errors.

    Keeping file discovery and source scanning together prevents CI callers
    from silently skipping unreadable or malformed production files.
    """
    excluded = frozenset(excluded_parts)
    findings: list[SecurityFinding] = []
    for raw_path in paths:
        path = Path(raw_path)
        if path.suffix != ".py" or any(part in excluded for part in path.parts):
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            findings.append(SecurityFinding("read-error", str(path), f"source could not be read: {exc}"))
            continue
        findings.extend(scan_source(str(path), content))
    return not findings, tuple(findings)
