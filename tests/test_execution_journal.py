import json,pytest
from hashlib import sha256
from execution.execution_journal import JournalSnapshot,build_snapshot,deserialize_snapshot,serialize_snapshot
from execution.idempotency import SubmissionRecord,SubmissionState

def _records(): return (SubmissionRecord("A",SubmissionState.UNKNOWN,1),SubmissionRecord("B",SubmissionState.ACCEPTED,1))

def test_journal_round_trip_is_deterministic_and_verified():
    s=build_snapshot(_records()); raw=serialize_snapshot(s)
    assert deserialize_snapshot(raw)==s
    assert serialize_snapshot(deserialize_snapshot(raw))==raw

def test_tampered_state_fails_checksum():
    raw=serialize_snapshot(build_snapshot(_records())); d=json.loads(raw)
    d["records"][0]["state"]="accepted"
    with pytest.raises(ValueError,match="checksum"): deserialize_snapshot(json.dumps(d))

def test_duplicate_identity_fails_closed():
    r=SubmissionRecord("A",SubmissionState.UNKNOWN,1)
    with pytest.raises(ValueError,match="duplicate"): build_snapshot((r,r))

def test_journal_rejects_malformed_record_fields():
    with pytest.raises(ValueError, match="order identity"):
        build_snapshot((SubmissionRecord(" A", SubmissionState.ACCEPTED, 1),))
    malformed = SubmissionRecord("A", SubmissionState.ACCEPTED, 1)
    object.__setattr__(malformed, "state", "accepted")
    with pytest.raises(ValueError, match="submission state"):
        build_snapshot((malformed,))

@pytest.mark.parametrize("raw",["","[]","{}",'{"records":[],"checksum":1}',"not-json"])
def test_malformed_journal_fails_closed(raw):
    with pytest.raises(ValueError): deserialize_snapshot(raw)


@pytest.mark.parametrize("boundary", ["build", "serialize", "deserialize"])
def test_new_state_is_invalid_even_with_a_matching_journal_checksum(boundary):
    records = (SubmissionRecord("A", SubmissionState.NEW, 1),)
    payload = [{"order_id": "A", "state": "new", "attempts": 1}]
    checksum = sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    snapshot = JournalSnapshot(records, checksum)
    raw = json.dumps({"records": payload, "checksum": checksum})
    with pytest.raises(ValueError, match="submission state"):
        if boundary == "build":
            build_snapshot(records)
        elif boundary == "serialize":
            serialize_snapshot(snapshot)
        else:
            deserialize_snapshot(raw)
