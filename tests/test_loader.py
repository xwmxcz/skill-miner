from pathlib import Path

from skill_miner.loader import load_session

FIXTURE = Path(__file__).parent / "fixtures" / "sample.jsonl"


def test_load_session_returns_user_and_assistant_events():
    s = load_session(FIXTURE)
    assert s is not None
    assert s.session_id == "fixture-session-1"
    types = [e.type for e in s.events]
    assert types.count("user") == 3
    assert types.count("assistant") == 3


def test_load_session_missing_file(tmp_path):
    assert load_session(tmp_path / "nope.jsonl") is None
