"""Mechanical release-tree audit for SHREEK V5.2/V5.3/V6.0.

This audit checks that the candidate contains the required safety, research,
and release-control layers. It does not claim that empirical evidence exists
and it has no broker/execution authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Iterable

REQUIRED_PATHS = (
    "core/admission_firewall.py",
    "core/backtest_engine.py",
    "core/duplicate_guard.py",
    "core/integration_gate.py",
    "core/paper_trade_pipeline.py",
    "core/release_certification.py",
    "core/release_evidence.py",
    "core/release_gate.py",
    "core/release_manifest.py",
    "core/live_authorization.py",
    "core/scanner.py",
    "core/setup_quality.py",
    "core/trade_orchestrator.py",
    "core/walk_forward.py",
    "execution/broker_safety.py",
    "execution/operational_guard.py",
    "execution/reconciliation.py",
    "execution/recovery.py",
    "execution/shadow.py",
    "execution/shadow_pipeline.py",
    "market/data_integrity.py",
    "risk/daily_risk_ledger.py",
    "risk/news_firewall.py",
    "risk/pre_trade_risk_gate.py",
    "risk/risk_state.py",
    "core/robustness.py",
    "core/risk_simulation.py",
    "research/advanced_wfo.py",
    "research/edge_matrix.py",
    "research/edge_selection.py",
    "research/excursion_stats.py",
    "research/execution_quality.py",
    "research/mae_mfe.py",
    "research/performance_metrics.py",
    "research/regime.py",
    "research/regime_attribution.py",
    "research/research_evidence.py",
    "research/research_release_gate.py",
    "research/selection_score.py",
    "research/strategy_attribution.py",
    "docs/V5_1_RELEASE_CHECKLIST.md",
    ".github/workflows/python-package.yml",
)

FORBIDDEN_RUNTIME_NAMES = (
    "order_send",
    "positions_send",
    "trade_transaction",
)


@dataclass(frozen=True)
class ReleaseAudit:
    passed: bool
    missing_paths: tuple[str, ...]
    forbidden_runtime_files: tuple[str, ...]


def audit_tree(paths: Iterable[str], *, production_sources: Iterable[tuple[str, str]] = ()) -> ReleaseAudit:
    """Audit a release tree from paths and production source text.

    ``production_sources`` is an iterable of ``(path, source)`` pairs. The
    lexical check is deliberately a second line of defense; the dedicated
    AST-level security gate remains authoritative.
    """
    normalized = {str(PurePosixPath(path)) for path in paths}
    missing = tuple(path for path in REQUIRED_PATHS if path not in normalized)

    forbidden: list[str] = []
    for path, source in production_sources:
        if not path.endswith(".py"):
            continue
        if any(name in source for name in FORBIDDEN_RUNTIME_NAMES):
            forbidden.append(path)

    return ReleaseAudit(
        passed=not missing and not forbidden,
        missing_paths=missing,
        forbidden_runtime_files=tuple(sorted(set(forbidden))),
    )


def require_release_tree(audit: ReleaseAudit) -> None:
    """Raise when the release tree fails the mechanical audit."""
    if not audit.passed:
        details = []
        if audit.missing_paths:
            details.append("missing: " + ", ".join(audit.missing_paths))
        if audit.forbidden_runtime_files:
            details.append("forbidden runtime names: " + ", ".join(audit.forbidden_runtime_files))
        raise RuntimeError("release tree audit failed; " + "; ".join(details))
