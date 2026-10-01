from journal.decision_journal import DecisionJournal, DecisionRecord


def test_append_and_read_round_trip(tmp_path):
    path = tmp_path / "decisions.jsonl"
    journal = DecisionJournal(path)
    record = DecisionRecord.now(
        "XAUUSD", "ADMITTED", "BUY", "all gates passed",
        fingerprint="abc123", score=14, setup_type="COMBINED", frame="M5",
        entry=2500.0, sl=2495.0,
    )
    journal.append(record)
    loaded = journal.read()
    assert len(loaded) == 1
    assert loaded[0].symbol == "XAUUSD"
    assert loaded[0].decision == "ADMITTED"
    assert loaded[0].fingerprint == "abc123"
    assert loaded[0].entry == 2500.0


def test_missing_journal_is_empty(tmp_path):
    assert DecisionJournal(tmp_path / "missing.jsonl").read() == []
