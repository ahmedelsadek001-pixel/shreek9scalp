"""Reproduce an audited, research-only XAUUSD study from an explicit JSON spec."""
from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import asdict, fields
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping, Sequence

from research.dataset_runner import run_audited_xauusd_breakout_retest_research
from research.research_run_artifact import (
    fingerprint_research_run_artifact,
    serialize_research_run_artifact,
)
from research.xauusd_source_manifest import XAUUSDSourceManifest


SCHEMA = "shreek.xauusd-study.v1"
RUN_CONTROLS = frozenset({
    "train_size", "test_size", "purge_size", "step", "starting_equity",
    "simulations", "seed", "slippage_multiplier", "spread_multiplier",
    "bootstrap_block_size", "bootstrap_simulations", "label_horizon",
})


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant: {value}")


def _read_spec(path: Path) -> tuple[XAUUSDSourceManifest, tuple[dict[str, Any], ...], float, float, str, dict[str, Any], str]:
    """Require an explicit reproducible specification, without arbitrary hooks."""
    spec = json.loads(path.read_text(encoding="utf-8"), parse_constant=_reject_constant)
    required = {"schema", "strategy_version", "source_manifest", "parameter_sets",
                "pip_size", "volume", "run"}
    if not isinstance(spec, dict) or set(spec) != required or spec["schema"] != SCHEMA:
        raise ValueError("study spec schema or fields are invalid")
    manifest_fields = {field.name for field in fields(XAUUSDSourceManifest)}
    raw_manifest = spec["source_manifest"]
    if not isinstance(raw_manifest, dict) or set(raw_manifest) != manifest_fields:
        raise ValueError("study source manifest fields are invalid")
    manifest = XAUUSDSourceManifest(**raw_manifest)
    manifest.validate()
    parameters = spec["parameter_sets"]
    if not isinstance(parameters, list) or not parameters or any(
        not isinstance(candidate, dict) for candidate in parameters
    ):
        raise ValueError("parameter_sets must contain candidate objects")
    version = spec["strategy_version"]
    if type(version) is not str or not version.strip() or version != version.strip():
        raise ValueError("strategy_version must be a non-empty, trimmed string")
    controls = spec["run"]
    if not isinstance(controls, dict) or set(controls) != RUN_CONTROLS:
        raise ValueError("study run controls must be complete and exact")
    if type(controls["seed"]) is not int:
        raise ValueError("a fixed integer seed is required for reproducible research")
    normalized = json.dumps(spec, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return (manifest, tuple(parameters), spec["pip_size"], spec["volume"],
            version, controls, sha256(normalized.encode("utf-8")).hexdigest())


def _repo_revision() -> str:
    repo = Path(__file__).resolve().parent.parent
    try:
        command = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True, check=True, text=True,
        )
        status = subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain"],
            capture_output=True, check=True, text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ValueError("cannot bind research to a Git revision") from exc
    revision = command.stdout.strip()
    if len(revision) != 40 or any(char not in "0123456789abcdef" for char in revision):
        raise ValueError("Git revision must be a full SHA-1 commit")
    if status.stdout.strip():
        raise ValueError("Git tree must be clean before research")
    return revision


def run_study(
    spec_path: Path, paths: Mapping[str, Path], output: Path,
) -> dict[str, Any]:
    """Write a complete read-only result once; a failed study is still evidence."""
    manifest, parameters, pip_size, volume, version, controls, spec_hash = _read_spec(spec_path)
    revision = _repo_revision()
    result = run_audited_xauusd_breakout_retest_research(
        paths, parameters, source_manifest=manifest, pip_size=pip_size,
        volume=volume, artifact_metadata={
            "strategy_id": "breakout-retest",
            "strategy_version": version,
            "code_revision": revision,
            "study_spec_sha256": spec_hash,
        }, **controls,
    )
    artifact = result.research.artifact
    export = json.loads(artifact.evidence_export)
    stats = export["statistical_evidence"]
    summary = {
        "code_revision": revision,
        "study_spec_sha256": spec_hash,
        "research_artifact_sha256": fingerprint_research_run_artifact(artifact),
        "dataset_quality_passed": result.audit.quality.passed,
        "oos_trades": export["evidence"]["oos_trade_count"],
        "oos_expectancy": export["evidence"]["oos_expectancy"],
        "ruin_rate_pct": export["evidence"]["ruin_rate_pct"],
        "oos_gate": export["gate"],
        "certification": stats["certification"],
        "confidence_interval": stats["confidence_interval"],
        "block_bootstrap": stats["block_bootstrap"],
    }
    bundle = {
        "schema": "shreek.xauusd-study-result.v1",
        "summary": summary,
        "dataset_audit": asdict(result.audit),
        "research_artifact": json.loads(serialize_research_run_artifact(artifact)),
        "limitations": [
            "Broker export provenance and cost assumptions require external verification.",
            "Stress is a P&L proxy, not historical bid/ask execution replay.",
            "This study grants neither V5.2 promotion nor live order authority.",
        ],
    }
    # Exclusive creation avoids replacing an earlier immutable study result.
    encoded = json.dumps(bundle, sort_keys=True, indent=2, allow_nan=False) + "\n"
    with output.open("x", encoding="utf-8") as destination:
        destination.write(encoded)
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only, audited XAUUSD research study")
    for name in ("spec", "m5", "m15", "h1", "output"):
        parser.add_argument(f"--{name}", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        summary = run_study(args.spec, {"5m": args.m5, "15m": args.m15,
                                       "1h": args.h1}, args.output)
    except (ValueError, OSError, UnicodeError, TypeError, KeyError) as exc:
        parser.error(str(exc))
    print(json.dumps(summary, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
