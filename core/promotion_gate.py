"""Fail-closed V5.2-to-V5.3 promotion boundary.

Research approval and execution safety are separate decisions. This module
combines them only to decide whether the paper/shadow V5.3 stage may begin;
it never grants live or MT5 authority.
"""
from __future__ import annotations

from dataclasses import dataclass

from execution.safety_gate import ExecutionSafetyEvidence, evaluate_execution_safety
from research.research_release_gate import ResearchReleaseDecision


@dataclass(frozen=True)
class V53PromotionDecision:
    ready: bool
    failures: tuple[str, ...]


def evaluate_v53_promotion(
    research: ResearchReleaseDecision,
    execution: ExecutionSafetyEvidence,
) -> V53PromotionDecision:
    """Allow V5.3 only when V5.2 and execution-safety decisions both pass."""
    if not isinstance(research, ResearchReleaseDecision):
        raise TypeError("research must be ResearchReleaseDecision")
    if not isinstance(execution, ExecutionSafetyEvidence):
        raise TypeError("execution must be ExecutionSafetyEvidence")

    failures: list[str] = []
    if type(research.ready) is not bool:
        failures.append("V5.2 research decision is malformed")
    elif not research.ready:
        failures.extend(f"V5.2 promotion blocked: {reason}" for reason in research.failures)
    if not isinstance(research.failures, tuple) or any(not isinstance(item, str) for item in research.failures):
        failures.append("V5.2 research failure list is malformed")

    execution_decision = evaluate_execution_safety(execution)
    failures.extend(f"V5.3 execution safety blocked: {reason}" for reason in execution_decision.failures)
    return V53PromotionDecision(not failures, tuple(failures))
