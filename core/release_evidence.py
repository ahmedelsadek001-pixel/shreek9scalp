"""Provenance-bound release evidence for SHREEK V5.1.

Evidence is accepted only when every required release control has exactly one
provenance record. This layer remains advisory and has no broker authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Mapping

from core.release_gate import ReleaseDecision, ReleaseEvidence, evaluate_release
from core.robustness import RobustnessReport


_REQUIRED_NAMES = (
    "ci_green", "tests_green", "data_integrity_validated", "walk_forward_passed",
    "robustness_passed", "paper_trading_validated", "security_reviewed",
    "execution_reconciled", "shadow_validated", "recovery_validated",
)


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
        if self.name not in _REQUIRED_NAMES:
            raise ValueError(f"unsupported evidence name: {self.name}")
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
        names = [record.name for record in records]
        if len(names) != len(set(names)):
            raise ValueError("duplicate evidence names are not allowed")
        canonical = "\n".join(
            f"{r.name}|{r.passed}|{r.source}|{r.run_id}|{r.recorded_at.astimezone(timezone.utc).isoformat()}"
            for r in sorted(records, key=lambda item: item.name)
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
    """Evaluate only provenance-backed values and enforce the required policy."""
    if not isinstance(bundle, ReleaseEvidenceBundle):
        raise TypeError("bundle must be ReleaseEvidenceBundle")
    if not isinstance(required, ReleaseEvidence):
        raise TypeError("required must be ReleaseEvidence")
    values = bundle.as_map()
    missing = tuple(name for name in _REQUIRED_NAMES if name not in values)
    if missing:
        return ReleaseDecision(False, tuple(f"missing evidence provenance: {name}" for name in missing))
    evidence = ReleaseEvidence(**{name: values[name] for name in _REQUIRED_NAMES})
    required_values = {name: getattr(required, name) for name in _REQUIRED_NAMES}
    for name, expected in required_values.items():
        if type(expected) is not bool:
            return ReleaseDecision(False, (f"required policy contains non-boolean value: {name}",))
        if expected and not evidence.__getattribute__(name):
            return ReleaseDecision(False, (f"required evidence failed: {name}",))
    return evaluate_release(evidence)
