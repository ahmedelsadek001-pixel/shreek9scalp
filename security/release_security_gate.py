"""Static security gate for SHREEK V5.1 release validation.

This gate is intentionally conservative: it blocks release when source text
contains common credential material or direct live-order authority markers.
It does not claim to replace secret scanners or a human security review.
"""
from __future__ import annotations

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
_LIVE_MARKERS = (
    "order_send(",
    "mt5.order_send(",
    "MetaTrader5.order_send(",
)


def scan_source(path: str, content: str) -> tuple[SecurityFinding, ...]:
    """Return conservative findings for one source file."""
    if not path.strip():
        raise ValueError("path is required")
    if not isinstance(content, str):
        raise TypeError("content must be str")
    findings: list[SecurityFinding] = []
    for rule, pattern in _SECRET_PATTERNS:
        if pattern.search(content):
            findings.append(SecurityFinding(rule, path, "credential-like material detected"))
    for marker in _LIVE_MARKERS:
        if marker in content:
            findings.append(SecurityFinding("live-order-authority", path, f"live execution marker: {marker}"))
    return tuple(findings)


def evaluate_tree(files: Iterable[tuple[str, str]]) -> tuple[bool, tuple[SecurityFinding, ...]]:
    """Fail closed when any scanned source contains a security finding."""
    findings: list[SecurityFinding] = []
    for path, content in files:
        findings.extend(scan_source(path, content))
    return not findings, tuple(findings)
