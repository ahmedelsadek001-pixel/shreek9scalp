import csv
from datetime import date, timedelta
from hashlib import sha256
import json

from research.paper_account_audit import audit_paper_account, FILL_COLUMNS, INTENT_COLUMNS


def _write_csv(path, columns, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def _bundle(tmp_path, *, mode="DEMO", count=2):
    intents = tmp_path / "intents.csv"
    fills = tmp_path / "fills.csv"
    manifest = tmp_path / "manifest.json"
    intent_rows = []
    fill_rows = []
    for index in range(count):
        day = (date(2026, 9, 1) + timedelta(days=index)).isoformat()
        intent_rows.append(dict(intent_id=f"strategy-{index}", symbol="XAUUSD", side="BUY",
                                volume="0.01", requested_price="2500", sent_at=f"{day}T12:00:00+00:00"))
        fill_rows.append(dict(intent_id=f"strategy-{index}", broker_order_id=f"demo-{index}",
                              symbol="XAUUSD", side="BUY", volume="0.01", entry_price="2500.10",
                              exit_price="2501.10", commission="0.07", net_pnl="0.93",
                              filled_at=f"{day}T12:00:02+00:00", closed_at=f"{day}T12:10:00+00:00"))
    _write_csv(intents, INTENT_COLUMNS, intent_rows)
    _write_csv(fills, FILL_COLUMNS, fill_rows)
    manifest.write_text(json.dumps(dict(account_mode=mode, account_fingerprint="a" * 64,
        source="broker_export", symbol="XAUUSD", strategy_id="shreek", strategy_version="5.2",
        currency="USD", contract_size="100", intents_sha256=sha256(intents.read_bytes()).hexdigest(),
        fills_sha256=sha256(fills.read_bytes()).hexdigest())), encoding="utf-8")
    return manifest, intents, fills


def _audit(paths):
    return audit_paper_account(*paths, min_trades=2, min_days=2)


def test_reconciled_demo_requires_external_provenance_even_when_structurally_sound(tmp_path):
    report = _audit(_bundle(tmp_path))
    assert report.structurally_reconciled and report.eligible_for_external_review
    assert not report.paper_trading_validated
    assert report.net_pnl == "1.86"
    assert report.worst_entry_slippage == "0.10"


def test_real_account_is_rejected(tmp_path):
    report = _audit(_bundle(tmp_path, mode="REAL"))
    assert not report.eligible_for_external_review
    assert not report.paper_trading_validated


def test_missing_inputs_fail_closed(tmp_path):
    report = _audit((tmp_path / "missing.json", tmp_path / "missing.csv", tmp_path / "fills.csv"))
    assert not report.eligible_for_external_review


def test_export_mutation_fails_hash_pin(tmp_path):
    paths = _bundle(tmp_path)
    with paths[2].open("a", encoding="utf-8") as stream:
        stream.write("altered\n")
    assert "hash mismatch" in " ".join(_audit(paths).failures)


def test_duplicate_broker_order_rejected(tmp_path):
    paths = _bundle(tmp_path)
    rows = list(csv.DictReader(paths[2].open(encoding="utf-8")))
    rows[1]["broker_order_id"] = rows[0]["broker_order_id"]
    _write_csv(paths[2], FILL_COLUMNS, rows)
    manifest = json.loads(paths[0].read_text())
    manifest["fills_sha256"] = sha256(paths[2].read_bytes()).hexdigest()
    paths[0].write_text(json.dumps(manifest))
    assert "duplicate fill" in " ".join(_audit(paths).failures)


def test_bad_pnl_and_delayed_fills_rejected(tmp_path):
    paths = _bundle(tmp_path)
    rows = list(csv.DictReader(paths[2].open(encoding="utf-8")))
    rows[0]["net_pnl"] = "50.00"
    _write_csv(paths[2], FILL_COLUMNS, rows)
    manifest = json.loads(paths[0].read_text())
    manifest["fills_sha256"] = sha256(paths[2].read_bytes()).hexdigest()
    paths[0].write_text(json.dumps(manifest))
    assert "P&L" in " ".join(_audit(paths).failures)
    rows[0]["net_pnl"] = "0.93"
    rows[0]["filled_at"] = "2026-09-01T12:01:00+00:00"
    _write_csv(paths[2], FILL_COLUMNS, rows)
    manifest["fills_sha256"] = sha256(paths[2].read_bytes()).hexdigest()
    paths[0].write_text(json.dumps(manifest))
    assert "delay" in " ".join(_audit(paths).failures)


def test_partial_and_unfilled_intents_rejected(tmp_path):
    paths = _bundle(tmp_path)
    rows = list(csv.DictReader(paths[2].open(encoding="utf-8")))
    rows.pop()
    _write_csv(paths[2], FILL_COLUMNS, rows)
    manifest = json.loads(paths[0].read_text())
    manifest["fills_sha256"] = sha256(paths[2].read_bytes()).hexdigest()
    paths[0].write_text(json.dumps(manifest))
    assert "unfilled intents" in " ".join(_audit(paths).failures)


def test_timezone_and_order_identity_fail_closed(tmp_path):
    paths = _bundle(tmp_path)
    rows = list(csv.DictReader(paths[1].open(encoding="utf-8")))
    rows[0]["sent_at"] = "2026-09-01T12:00:00"
    _write_csv(paths[1], INTENT_COLUMNS, rows)
    manifest = json.loads(paths[0].read_text())
    manifest["intents_sha256"] = sha256(paths[1].read_bytes()).hexdigest()
    paths[0].write_text(json.dumps(manifest))
    assert "sent_at" in " ".join(_audit(paths).failures)

    rows[0]["sent_at"] = "2026-09-01T12:00:00+00:00"
    rows[1]["intent_id"] = rows[0]["intent_id"]
    _write_csv(paths[1], INTENT_COLUMNS, rows)
    manifest["intents_sha256"] = sha256(paths[1].read_bytes()).hexdigest()
    paths[0].write_text(json.dumps(manifest))
    assert "duplicate intent" in " ".join(_audit(paths).failures)


def test_policy_requires_coverage_and_limits_slippage(tmp_path):
    paths = _bundle(tmp_path)
    assert "insufficient" in " ".join(audit_paper_account(*paths).failures)
    assert "slippage" in " ".join(audit_paper_account(
        *paths, min_trades=2, min_days=2, max_slippage="0.05").failures)
