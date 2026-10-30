"""Optional OpenAI advisory layer for SHREEK V5.1.

AI is strictly advisory: it can explain and summarize deterministic strategy
outputs, but it cannot authorize, size, or execute a trade.
Credentials are read only from OPENAI_API_KEY at runtime.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping, Optional


@dataclass(frozen=True)
class AIAdvice:
    summary: str
    risk_notes: tuple[str, ...] = ()
    model: str = ""


class OpenAIAdvisor:
    """Thin, fail-closed adapter around the OpenAI Responses API."""

    def __init__(self, model: str = "gpt-5-mini", api_key: Optional[str] = None) -> None:
        self.model = model
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def explain_signal(self, signal: Mapping[str, Any]) -> AIAdvice:
        """Explain a deterministic signal without granting execution authority."""
        if not self.enabled:
            return AIAdvice("OpenAI advisor disabled: OPENAI_API_KEY is not configured.")
        try:
            from openai import OpenAI
        except ImportError:
            return AIAdvice("OpenAI advisor unavailable: install the OpenAI SDK.")

        client = OpenAI(api_key=self.api_key)
        prompt = (
            "You are a trading research assistant. Explain the supplied deterministic "
            "signal and identify risks. Do not recommend or authorize an order. "
            "Never override risk gates. Return concise research notes.\n\n"
            f"Signal data: {dict(signal)}"
        )
        try:
            response = client.responses.create(model=self.model, input=prompt)
            text = getattr(response, "output_text", "").strip()
        except Exception as exc:
            return AIAdvice(f"OpenAI advisor failed closed: {type(exc).__name__}.")
        return AIAdvice(text or "OpenAI returned no advisory text.", model=self.model)
