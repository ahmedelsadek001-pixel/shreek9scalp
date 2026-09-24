"""Static security gate for SHREEK V5.1 release validation.

The gate detects credential-like literals and actual live-order call sites.
Test fixtures may contain intentionally dangerous examples and are excluded
by the CI tree policy; the scanner itself remains useful for targeted checks.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
import re
from typing import Iterable


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


def _has_live_order_call(content: str) -> bool:
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            function = node.func
            if isinstance(function, ast.Name) and function.id in _LIVE_FUNCTIONS:
                return True
            if isinstance(function, ast.Attribute) and function.attr in _LIVE_FUNCTIONS:
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
    if _has_live_order_call(content):
        findings.append(SecurityFinding("live-order-authority", path, "live broker transport call detected"))
    return tuple(findings)


def evaluate_tree(files: Iterable[tuple[str, str]]) -> tuple[bool, tuple[SecurityFinding, ...]]:
    """Fail closed when any scanned source contains a security finding."""
    findings: list[SecurityFinding] = []
    for path, content in files:
        findings.extend(scan_source(path, content))
    return not findings, tuple(findings)

