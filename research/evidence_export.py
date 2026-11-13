"""Deterministic JSON export for SHREEK V5.2 research evidence."""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from hashlib import sha256
from math import isclose, isfinite
from typing import Any, Mapping

from research.backtest_wfo import BacktestWFOResult

from research.dataset_provenance import DatasetProvenance
from research.evidence_pipeline import EvidencePipelineResult
from research.evidence_gate import evaluate_oos_evidence
from core.execution_cost_stress import stress_backtest_trades


EXPORT_SCHEMA_VERSION = "3"


def _canonical_selected_parameters(parameters: tuple[Mapping[str, Any], ...]) -> list[dict[str, Any]]:
    """Return JSON-native selected parameters without lossy string coercion."""
    canonical: list[dict[str, Any]] = []
    for params in parameters:
        if not isinstance(params, Mapping) or any(type(key) is not str or not key for key in params):
            raise ValueError("selected WFO parameters must use non-empty string keys")
        row = dict(sorted(params.items()))
        try:
            json.dumps(row, sort_keys=True, separators=(",", ":"), allow_nan=False)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("selected WFO parameters must be strict JSON values") from exc
        canonical.append(row)
    return canonical


def _build_wfo_evidence(wfo: BacktestWFOResult, expected_windows: int) -> dict[str, Any]:
    """Archive exact WFO geometry, scores, and train-selected parameters."""
    validation = wfo.validation
    count = len(validation.windows)
    if not (
        count
        == len(validation.train_scores)
        == len(validation.test_scores)
        == len(validation.selected_parameters)
        == len(wfo.train_metrics)
        == len(wfo.train_results)
        == len(wfo.oos_metrics)
        == len(wfo.oos_results)
        == expected_windows
    ):
        raise ValueError("WFO evidence cardinality does not match OOS report")
    if wfo.window_timestamps and len(wfo.window_timestamps) != count:
        raise ValueError("WFO timestamp evidence cardinality does not match windows")
    for window in validation.windows:
        if not (
            type(window.train_start) is int
            and type(window.train_end) is int
            and type(window.purge_start) is int
            and type(window.purge_end) is int
            and type(window.test_start) is int
            and type(window.test_end) is int
            and 0 <= window.train_start < window.train_end
            and window.train_end == window.purge_start
            and window.purge_start <= window.purge_end
            and window.purge_end == window.test_start
            and window.test_start < window.test_end
        ):
            raise ValueError("WFO window geometry is invalid")
    scores = (*validation.train_scores, *validation.test_scores)
    if any(type(score) not in (int, float) or not isfinite(float(score)) for score in scores):
        raise ValueError("WFO scores must be finite numbers")
    evidence = {
        "windows": [asdict(window) for window in validation.windows],
        "train_scores": list(validation.train_scores),
        "test_scores": list(validation.test_scores),
        "selected_parameters": _canonical_selected_parameters(validation.selected_parameters),
    }
    if wfo.window_timestamps:
        previous_train_first = None
        previous_test_first = None
        previous_test_last = None
        for row in wfo.window_timestamps:
            values = {name: getattr(row, name) for name in (
                "train_first", "train_last", "purge_first", "purge_last", "test_first", "test_last"
            )}
            parsed = {}
            for name, value in values.items():
                if value is None and name in {"purge_first", "purge_last"}:
                    parsed[name] = None
                    continue
                if type(value) is not str or not value:
                    raise ValueError("WFO timestamps must be non-empty ISO datetime strings")
                try:
                    parsed[name] = datetime.fromisoformat(value)
                except ValueError as exc:
                    raise ValueError("WFO timestamps must be valid ISO datetimes") from exc
                if parsed[name].tzinfo is None or parsed[name].utcoffset() is None:
                    raise ValueError("WFO timestamps must be timezone-aware")
            if (parsed["purge_first"] is None) != (parsed["purge_last"] is None):
                raise ValueError("WFO purge timestamps must both be present or absent")
            if not parsed["train_first"] <= parsed["train_last"] < parsed["test_first"] <= parsed["test_last"]:
                raise ValueError("WFO timestamp chronology is invalid")
            if parsed["purge_first"] is not None and not (
                parsed["train_last"] < parsed["purge_first"] <= parsed["purge_last"] < parsed["test_first"]
            ):
                raise ValueError("WFO purge timestamp chronology is invalid")
            if previous_train_first is not None and parsed["train_first"] <= previous_train_first:
                raise ValueError("WFO training timestamps must be chronological")
            if previous_test_first is not None and parsed["test_first"] <= previous_test_first:
                raise ValueError("WFO OOS starts must be chronological")
            if previous_test_last is not None and parsed["test_first"] <= previous_test_last:
                raise ValueError("WFO OOS timestamps must not overlap")
            previous_train_first = parsed["train_first"]
            previous_test_first = parsed["test_first"]
            previous_test_last = parsed["test_last"]
        evidence["window_timestamps"] = [asdict(window) for window in wfo.window_timestamps]
    return evidence



def _build_execution_cost_evidence(wfo: BacktestWFOResult, spread_multiplier: float, slippage_multiplier: float) -> dict[str, Any]:
    """Build a canonical, per-trade OOS cost ledger and a separate additive stress diagnostic."""
    rows: list[dict[str, Any]] = []
    trades = []
    for window_index, result in enumerate(wfo.oos_results):
        for trade_index, trade in enumerate(result.trades):
            values = {
                "entry": trade.entry,
                "exit": trade.exit,
                "volume": trade.volume,
                "gross_pnl": trade.gross_pnl,
                "spread_cost": trade.spread_cost,
                "slippage_cost": trade.slippage_cost,
                "commission_cost": trade.commission_cost,
                "costs": trade.costs,
                "net_pnl": trade.net_pnl,
            }
            if any(type(value) not in (int, float) or not isfinite(float(value)) for value in values.values()):
                raise ValueError("OOS execution-cost ledger values must be finite real numbers")
            if any(values[name] < 0 for name in ("volume", "spread_cost", "slippage_cost", "commission_cost", "costs")):
                raise ValueError("OOS execution costs and volume must be non-negative")
            component_total = trade.spread_cost + trade.slippage_cost + trade.commission_cost
            if not isclose(float(trade.costs), float(component_total), rel_tol=1e-12, abs_tol=1e-12):
                raise ValueError("OOS trade total costs do not reconcile to cost components")
            if not isclose(float(trade.net_pnl), float(trade.gross_pnl - component_total), rel_tol=1e-12, abs_tol=1e-12):
                raise ValueError("OOS trade net P&L does not reconcile to gross P&L and costs")
            direction = getattr(trade.direction, "value", trade.direction)
            if type(direction) is not str or not direction:
                raise ValueError("OOS trade direction must be a non-empty string")
            timestamps = {}
            for name in ("signal_time", "entry_time", "exit_time"):
                value = getattr(trade, name, None)
                if not isinstance(value, datetime):
                    raise ValueError("OOS cost ledger trades must expose datetime timestamps")
                timestamps[name] = value.isoformat()
            if trade.entry_time < trade.signal_time or trade.exit_time < trade.entry_time:
                raise ValueError("OOS cost ledger trade timestamps are not chronological")
            rows.append({
                "window_index": window_index,
                "trade_index": trade_index,
                **timestamps,
                "direction": direction,
                **values,
            })
            trades.append(trade)
    if not rows:
        raise ValueError("OOS execution-cost ledger requires realized trades")
    canonical_rows = json.dumps(rows, sort_keys=True, separators=(",", ":"), allow_nan=False)
    stress = stress_backtest_trades(
        trades,
        spread_multiplier=spread_multiplier,
        slippage_multiplier=slippage_multiplier,
    )
    totals = {
        "gross_pnl": stress.total_gross_pnl,
        "spread_cost": stress.total_spread_cost,
        "slippage_cost": stress.total_slippage_cost,
        "commission_cost": stress.total_commission,
        "baseline_net_pnl": stress.total_baseline_net_pnl,
        "cost_stressed_net_pnl": stress.total_stressed_net_pnl,
    }
    return {
        "schema": "shreek.oos-execution-cost-ledger.v1",
        "trade_count": len(rows),
        "rows": rows,
        "ledger_sha256": sha256(canonical_rows.encode("utf-8")).hexdigest(),
        "stress": {
            "method": "additive_spread_slippage_only",
            "spread_multiplier": stress.spread_multiplier,
            "slippage_multiplier": stress.slippage_multiplier,
            "commission_unchanged": True,
            "totals": totals,
        },
    }



def build_evidence_export(
    result: EvidencePipelineResult,
    provenance: DatasetProvenance,
) -> dict[str, Any]:
    """Build a JSON-safe, deterministic evidence payload with its exact gate policy."""
    if not isinstance(result, EvidencePipelineResult):
        raise ValueError("result must be an EvidencePipelineResult")
    if not isinstance(provenance, DatasetProvenance):
        raise ValueError("provenance must be DatasetProvenance")
    provenance.validate()
    result.report.validate()
    result.policy.validate()
    expected_gate = evaluate_oos_evidence(result.report, result.policy)
    if result.gate != expected_gate:
        raise ValueError("evidence gate result does not match report and policy")
    payload = {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "dataset": asdict(provenance),
        "evidence": asdict(result.report),
        "gate": asdict(result.gate),
        "gate_policy": {**asdict(result.policy), "max_worst_drawdown": (None if result.policy.max_worst_drawdown == float("inf") else result.policy.max_worst_drawdown)},
    }
    if isinstance(result.wfo, BacktestWFOResult):
        payload["wfo_evidence"] = _build_wfo_evidence(
            result.wfo, result.report.oos_window_count
        )
        if result.run_config is None:
            raise ValueError("real WFO evidence requires reproducible research run config")
        result.run_config.validate()
        config = asdict(result.run_config)
        config["candidate_parameters"] = _canonical_selected_parameters(
            result.run_config.candidate_parameters
        )
        if result.report.simulations != result.run_config.simulations:
            raise ValueError("research run simulation count does not match OOS report")
        if any(
            params not in config["candidate_parameters"]
            for params in payload["wfo_evidence"]["selected_parameters"]
        ):
            raise ValueError("selected WFO parameters are absent from candidate parameter grid")
        payload["research_config"] = config
        payload["execution_cost_evidence"] = _build_execution_cost_evidence(
            result.wfo,
            result.run_config.spread_multiplier,
            result.run_config.slippage_multiplier,
        )
    statistical = (result.interval, result.bootstrap, result.certification)
    if any(item is not None for item in statistical):
        if any(item is None for item in statistical):
            raise ValueError("statistical certification evidence must be complete")
        result.interval.validate()
        result.bootstrap.validate()
        result.certification.validate()
        if result.run_config is not None:
            if not isclose(result.interval.confidence, result.run_config.confidence, rel_tol=0.0, abs_tol=0.0):
                raise ValueError("confidence interval does not match research run config")
            if result.bootstrap.block_size != result.run_config.bootstrap_block_size:
                raise ValueError("bootstrap block size does not match research run config")
            if result.bootstrap.simulations != result.run_config.bootstrap_simulations:
                raise ValueError("bootstrap simulations do not match research run config")
            if not isclose(result.bootstrap.confidence, result.run_config.confidence, rel_tol=0.0, abs_tol=0.0):
                raise ValueError("bootstrap confidence does not match research run config")
        result.certification_policy.validate()
        certification = result.certification
        if certification.oos_trades != result.interval.samples:
            raise ValueError("certification OOS trade count does not match statistical evidence")
        if result.bootstrap.samples != result.interval.samples:
            raise ValueError("bootstrap sample count does not match confidence interval")
        if result.interval.samples != result.report.oos_trade_count:
            raise ValueError("statistical sample count does not match OOS report")
        if certification.oos_windows != result.report.oos_window_count:
            raise ValueError("certification OOS windows do not match OOS report")
        if not isclose(certification.oos_stability_pct, result.report.oos_stability_pct, rel_tol=1e-12, abs_tol=1e-12):
            raise ValueError("certification OOS stability does not match OOS report")
        if not isclose(result.interval.mean, result.report.oos_expectancy, rel_tol=1e-12, abs_tol=1e-12):
            raise ValueError("confidence interval mean does not match OOS report expectancy")
        if not isclose(result.bootstrap.observed_mean, result.report.oos_expectancy, rel_tol=1e-12, abs_tol=1e-12):
            raise ValueError("bootstrap observed mean does not match OOS report expectancy")
        expected_failures: list[str] = []
        cert_policy = result.certification_policy
        if certification.oos_trades < cert_policy.min_oos_trades:
            expected_failures.append("insufficient OOS trades")
        if certification.oos_windows < cert_policy.min_oos_windows:
            expected_failures.append("insufficient OOS windows")
        if certification.oos_stability_pct < cert_policy.min_oos_stability_pct:
            expected_failures.append("OOS stability below minimum")
        if result.report.oos_expectancy <= 0.0:
            expected_failures.append("OOS expectancy is not positive")
        if cert_policy.require_positive_ci_lower and result.interval.lower <= 0.0:
            expected_failures.append("confidence interval does not exclude non-positive expectancy")
        if cert_policy.require_positive_bootstrap_lower and result.bootstrap.lower_mean <= 0.0:
            expected_failures.append("block bootstrap lower bound is not positive")
        if result.bootstrap.non_positive_mean_rate_pct > cert_policy.max_bootstrap_non_positive_rate_pct:
            expected_failures.append("bootstrap non-positive expectancy rate above maximum")
        if result.report.ruin_rate_pct > cert_policy.max_ruin_rate_pct:
            expected_failures.append("Monte Carlo ruin rate above maximum")
        if certification.oos_expectancy_degradation_pct > cert_policy.max_oos_expectancy_degradation_pct:
            expected_failures.append("OOS expectancy degradation above maximum")
        if certification.parameter_stability_pct < cert_policy.min_parameter_stability_pct:
            expected_failures.append("parameter stability below minimum")
        if certification.failures != tuple(expected_failures):
            raise ValueError("certification result does not match archived statistical evidence and policy")
        payload["statistical_evidence"] = {
            "confidence_interval": asdict(result.interval),
            "block_bootstrap": asdict(result.bootstrap),
            "certification": asdict(result.certification),
            "certification_policy": asdict(result.certification_policy),
        }
    return payload


def serialize_evidence_export(
    result: EvidencePipelineResult,
    provenance: DatasetProvenance,
) -> str:
    """Serialize evidence deterministically for archival or comparison."""
    payload = build_evidence_export(result, provenance)
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str, allow_nan=False)


def fingerprint_evidence_export(
    result: EvidencePipelineResult,
    provenance: DatasetProvenance,
) -> str:
    """Return SHA-256 identity of the canonical evidence export."""
    canonical = serialize_evidence_export(result, provenance)
    return sha256(canonical.encode("utf-8")).hexdigest()
