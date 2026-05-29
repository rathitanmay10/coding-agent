from __future__ import annotations

import time


from coding_agent.session_log import (
    SessionLogger,
    TurnRecord,
    latest_session,
    load_session,
)


def _make_turn(
    user: str,
    output: str,
    error=None,
    duration_s=1.5,
    input_tokens=10,
    output_tokens=20,
    requests=1,
) -> TurnRecord:
    return TurnRecord(
        user=user,
        output=output,
        error=error,
        duration_s=duration_s,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        requests=requests,
    )


def test_round_trip_two_turns(tmp_path):
    logger = SessionLogger(tmp_path, "test:model")
    t1 = _make_turn("hello", "world", input_tokens=11, output_tokens=22, requests=2)
    t2 = _make_turn(
        "foo",
        "bar",
        error="oops",
        duration_s=3.0,
        input_tokens=33,
        output_tokens=44,
        requests=3,
    )
    logger.log_turn(t1)
    logger.log_turn(t2)

    records = load_session(logger.path)
    assert len(records) == 2

    r1 = records[0]
    assert r1.user == "hello"
    assert r1.output == "world"
    assert r1.error is None
    assert r1.duration_s == 1.5
    assert r1.input_tokens == 11
    assert r1.output_tokens == 22
    assert r1.requests == 2

    r2 = records[1]
    assert r2.user == "foo"
    assert r2.output == "bar"
    assert r2.error == "oops"
    assert r2.duration_s == 3.0
    assert r2.input_tokens == 33
    assert r2.output_tokens == 44
    assert r2.requests == 3


def test_session_start_line_skipped(tmp_path):
    logger = SessionLogger(tmp_path, "test:model")
    logger.log_turn(_make_turn("u", "o"))
    logger.log_turn(_make_turn("u2", "o2"))

    records = load_session(logger.path)
    assert len(records) == 2


def test_load_session_nonexistent_returns_empty(tmp_path):
    result = load_session(tmp_path / "does_not_exist.jsonl")
    assert result == []


def test_load_session_skips_malformed_line(tmp_path):
    logger = SessionLogger(tmp_path, "test:model")
    logger.log_turn(_make_turn("a", "b"))
    logger.log_turn(_make_turn("c", "d"))

    with logger.path.open("a", encoding="utf-8") as f:
        f.write("not json\n")

    records = load_session(logger.path)
    assert len(records) == 2
    assert records[0].user == "a"
    assert records[1].user == "c"


def test_latest_session_returns_logger_path(tmp_path):
    logger = SessionLogger(tmp_path, "test:model")
    result = latest_session(tmp_path)
    assert result == logger.path


def test_latest_session_no_logs_returns_none(tmp_path):
    assert latest_session(tmp_path) is None


def test_latest_session_returns_newest_by_name(tmp_path):
    logger1 = SessionLogger(tmp_path, "test:model")
    # Sleep 1s only if both share same timestamp; use name comparison instead.
    # Create second logger; if names differ, max wins; if same second, either is valid.
    time.sleep(1)
    logger2 = SessionLogger(tmp_path, "test:model")

    result = latest_session(tmp_path)
    # max by name: either logger2.path if timestamps differ, or one of them if equal
    candidates = {logger1.path, logger2.path}
    assert result in candidates
    assert result == max(candidates, key=lambda p: p.name)
