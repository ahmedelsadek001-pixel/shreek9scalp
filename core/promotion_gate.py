"""Fail-closed V5.2-to-V5.3 promotion boundary.

Research approval and execution safety are separate decisions. This module
combines them only to decide whether the paper/shadow V5.3 stage may begin;
it never grants live or MT5 authority.
"""
from __future__ import annotations

from dataclasses import dataclass

from execution.safety_gate import ExecutionSafetyEvidence, evaluate_execution_safety
from research.research_release_gate import (
    ResearchReleaseDecision,
    ResearchReleasePackage,
    evaluate_research_release_package,
)


@dataclass(frozen=True)
class V53PromotionDecision:
    ready: bool
    failures: tuple[str, ...]


def evaluate_v53_promotion(
    research: ResearchReleasePackage | ResearchReleaseDecision,
    execution: ExecutionSafetyEvidence,
) -> V53PromotionDecision:
    """Require artifact-bound V5.2 evidence before admitting the paper/shadow stage.

    A legacy failed decision may still convey its diagnostic failures, but a
    bare successful decision cannot authorize promotion: it can be created
    solely from caller-supplied booleans without any research artifact.
    """
    if not isinstance(research, (ResearchReleasePackage, ResearchReleaseDecision)):
        raise TypeError("research must be ResearchReleasePackage or ResearchReleaseDecision")
    if not isinstance(execution, ExecutionSafetyEvidence):
        raise TypeError("execution must be ExecutionSafetyEvidence")

    failures: list[str] = []
    if isinstance(research, ResearchReleasePackage):
        decision = evaluate_research_release_package(research)
    else:
        decision = research
        if decision.ready is True:
            failures.append("V5.2 promotion requires a validated research release package")

    if not isinstance(decision.failures, tuple) or any(
        type(item) is not str or not item for item in decision.failures
    ):
        failures.append("V5.2 research failure list is malformed")
    if type(decision.ready) is not bool:
        failures.append("V5.2 research decision is malformed")
    elif decision.ready and decision.failures:
        failures.append("V5.2 research decision is inconsistent")
    elif not decision.ready:
        if isinstance(decision.failures, tuple):
            failures.extend(
                f"V5.2 promotion blocked: {reason}" for reason in decision.failures
                if type(reason) is str and reason
            )
        if not decision.failures:
            failures.append("V5.2 research decision rejected without reason")

    execution_decision = evaluate_execution_safety(execution)
    failures.extend(f"V5.3 execution safety blocked: {reason}" for reason in execution_decision.failures)
    return V53PromotionDecision(not failures, tuple(failures))
