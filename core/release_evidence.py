"""Provenance-bound release evidence for SHREEK V5.1.

The release gate must consume evidence produced by validated pipeline stages,
not caller-supplied booleans with no provenance. This module remains advisory
and has no broker/execution authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Mapping

from core.release_gate import ReleaseDecision, ReleaseEvidence, evaluate_release
from core.robustness import RobustnessReport


@dataclass(frozen=True)
class EvidenceRecord:
    name: str
    passed: bool
    source: str
    run_id: str
    recorded_at: datetime

    def validate(self) -> None:
        if not self.name.strip() or not self.source.strip() or not self.run_id.strip():
            raise ValueError("evidence identity fields are required")
        if type(self.passed) is not bool:
            raise TypeError("evidence passed must be bool")
        if self.recorded_at.tzinfo is None:
            raise ValueError("recorded_at must be timezone-aware")


@dataclass(frozen=True)
class ReleaseEvidenceBundle:
    records: tuple[EvidenceRecord, ...]
    bundle_id: str

    @classmethod
    def from_records(cls, records: tuple[EvidenceRecord, ...]) -> "ReleaseEvidenceBundle":
        if not records:
            raise ValueError("at least one evidence record is required")
        for record in records:
            record.validate()
        canonical = "\n".join(
            f"{r.name}|{r.passed}|{r.source}|{r.run_id}|{r.recorded_at.isoformat()}" for r in records
        )
        return cls(records, sha256(canonical.encode("utf-8")).hexdigest())

    def as_map(self) -> Mapping[str, bool]:
        return {record.name: record.passed for record in self.records}


def build_robustness_evidence(report: RobustnessReport, run_id: str) -> EvidenceRecord:
    """Convert an actual robustness report into immutable release evidence."""
    if not isinstance(report, RobustnessReport):
        raise TypeError("report must be RobustnessReport")
    if not run_id.strip():
        raise ValueError("run_id is required")
    return EvidenceRecord(
        name="robustness_passed",
        passed=report.passed,
        source="core.robustness.build_robustness_report",
        run_id=run_id,
        recorded_at=datetime.now(timezone.utc),
    )


def evaluate_evidence_bundle(bundle: ReleaseEvidenceBundle, required: ReleaseEvidence) -> ReleaseDecision:
    """Require provenance for every release flag before evaluating readiness."""
    if not isinstance(bundle, ReleaseEvidenceBundle):
        raise TypeError("bundle must be ReleaseEvidenceBundle")
    if not isinstance(required, ReleaseEvidence):
        raise TypeError("required must be ReleaseEvidence")
    values = bundle.as_map()
    required_names = (
        "ci_green", "tests_green", "data_integrity_validated", "walk_forward_passed",
        "robustness_passed", "paper_trading_validated", "security_reviewed",
        "execution_reconciled", "shadow_validated", "recovery_validated",
    )
    missing = tuple(name for name in required_names if name not in values)
    if missing:
        return ReleaseDecision(False, tuple(f"missing evidence provenance: {name}" for name in missing))
    if any(type(values[name]) is not bool for name in required_names):
        return ReleaseDecision(False, ("release evidence contains non-boolean values",))
    evidence = ReleaseEvidence(**{name: values[name] for name in required_names})
    return evaluate_release(evidence)
