"""Provenance-bound release evidence for SHREEK V5.1/V6.0."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Mapping

from core.live_authorization import REQUIRED_EVIDENCE
from core.release_gate import ReleaseDecision, ReleaseEvidence, evaluate_release
from core.robustness import RobustnessReport


_V51_RELEASE_NAMES = tuple(ReleaseEvidence.__dataclass_fields__)
_SUPPORTED_NAMES = REQUIRED_EVIDENCE
_REQUIRED_NAMES = _V51_RELEASE_NAMES


@dataclass(frozen=True)
class EvidenceRecord:
    name: str
    passed: bool
    source: str
    run_id: str
    recorded_at: datetime

    def validate(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("evidence name is required")
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("evidence source is required")
        if not isinstance(self.run_id, str) or not self.run_id.strip():
            raise ValueError("evidence run_id is required")
        if self.name not in _SUPPORTED_NAMES:
            raise ValueError(f"unsupported evidence name: {self.name}")
        if type(self.passed) is not bool:
            raise TypeError("evidence passed must be bool")
        if not isinstance(self.recorded_at, datetime) or self.recorded_at.tzinfo is None:
            raise ValueError("recorded_at must be timezone-aware")


@dataclass(frozen=True)
class ReleaseEvidenceBundle:
    records: tuple[EvidenceRecord, ...]
    bundle_id: str

    @staticmethod
    def _canonical(records: tuple[EvidenceRecord, ...]) -> str:
        return "\n".join(
            f"{r.name}|{r.passed}|{r.source}|{r.run_id}|{r.recorded_at.astimezone(timezone.utc).isoformat()}"
            for r in sorted(records, key=lambda item: item.name)
        )

    @classmethod
    def from_records(cls, records: tuple[EvidenceRecord, ...]) -> "ReleaseEvidenceBundle":
        if not isinstance(records, tuple) or not records:
            raise ValueError("non-empty tuple of evidence records is required")
        for record in records:
            if not isinstance(record, EvidenceRecord):
                raise TypeError("records must contain EvidenceRecord values")
            record.validate()
        names = [record.name for record in records]
        if len(names) != len(set(names)):
            raise ValueError("duplicate evidence names are not allowed")
        canonical = cls._canonical(records)
        return cls(records, sha256(canonical.encode("utf-8")).hexdigest())

    def validate(self) -> None:
        expected = sha256(self._canonical(self.records).encode("utf-8")).hexdigest()
        if self.bundle_id != expected:
            raise ValueError("bundle_id does not match evidence records")
        rebuilt = ReleaseEvidenceBundle.from_records(self.records)
        if rebuilt.bundle_id != self.bundle_id:
            raise ValueError("evidence bundle integrity validation failed")

    def as_map(self) -> Mapping[str, bool]:
        self.validate()
        return {record.name: record.passed for record in self.records}


def build_robustness_evidence(report: RobustnessReport, run_id: str) -> EvidenceRecord:
    """Convert an actual robustness report into immutable release evidence."""
    if not isinstance(report, RobustnessReport):
        raise TypeError("report must be RobustnessReport")
    if not isinstance(run_id, str) or not run_id.strip():
        raise ValueError("run_id is required")
    return EvidenceRecord(
        name="robustness_passed",
        passed=report.passed,
        source="core.robustness.build_robustness_report",
        run_id=run_id,
        recorded_at=datetime.now(timezone.utc),
    )


def evaluate_evidence_bundle(bundle: ReleaseEvidenceBundle, required: ReleaseEvidence) -> ReleaseDecision:
    """Evaluate only integrity- and provenance-validated V5.1 values."""
    if not isinstance(bundle, ReleaseEvidenceBundle):
        raise TypeError("bundle must be ReleaseEvidenceBundle")
    if not isinstance(required, ReleaseEvidence):
        raise TypeError("required must be ReleaseEvidence")
    try:
        values = bundle.as_map()
    except (TypeError, ValueError, OverflowError):
        return ReleaseDecision(False, ("evidence bundle integrity validation failed",))
    missing = tuple(name for name in _REQUIRED_NAMES if name not in values)
    if missing:
        return ReleaseDecision(False, tuple(f"missing evidence provenance: {name}" for name in missing))
    evidence = ReleaseEvidence(**{name: values[name] for name in _V51_RELEASE_NAMES})
    for name in _REQUIRED_NAMES:
        expected = getattr(required, name, False)
        if type(expected) is not bool:
            return ReleaseDecision(False, (f"required policy contains non-boolean value: {name}",))
        if expected and not values[name]:
            return ReleaseDecision(False, (f"required evidence failed: {name}",))
    return evaluate_release(evidence)
