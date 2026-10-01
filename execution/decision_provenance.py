"""In-process provenance for execution approvals; copies and edits fail closed.

This is a local consistency guard, not a cryptographic authority or a broker
credential. Only decisions issued and retained in this process can pass it.
"""
from __future__ import annotations

from typing import Any
from weakref import ReferenceType, ref


class IssuedDecisionRegistry:
    """Track decision identity and the fields that were issued originally."""

    def __init__(self) -> None:
        self._records: dict[int, tuple[ReferenceType[Any], tuple[Any, ...]]] = {}

    def issue(self, decision: object, state: tuple[Any, ...]) -> None:
        key = id(decision)

        def forget(reference: ReferenceType[Any]) -> None:
            current = self._records.get(key)
            if current is not None and current[0] is reference:
                del self._records[key]

        self._records[key] = (ref(decision, forget), state)

    def is_issued(self, decision: object, state: tuple[Any, ...]) -> bool:
        original = self._records.get(id(decision))
        return (original is not None and original[0]() is decision
                and original[1] == state)
