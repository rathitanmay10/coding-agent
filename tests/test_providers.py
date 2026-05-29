from __future__ import annotations

import httpx
import pytest

from coding_agent.providers import with_retry


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr("coding_agent.providers.time.sleep", lambda *_: None)


def test_success_first_try():
    calls = []

    def fn():
        calls.append(1)
        return "ok"

    result = with_retry(fn, attempts=3)
    assert result == "ok"
    assert len(calls) == 1


def test_transient_transport_error_retries_then_succeeds():
    calls = []

    def fn():
        calls.append(1)
        if len(calls) < 3:
            raise httpx.ConnectError("boom")
        return "success"

    result = with_retry(fn, attempts=3)
    assert result == "success"
    assert len(calls) == 3


def test_transient_http_status_error_retries_then_succeeds():
    calls = []
    req = httpx.Request("GET", "http://x")
    resp = httpx.Response(503, request=req)

    def fn():
        calls.append(1)
        if len(calls) < 3:
            raise httpx.HTTPStatusError("x", request=req, response=resp)
        return "done"

    result = with_retry(fn, attempts=3)
    assert result == "done"
    assert len(calls) == 3


def test_always_transient_exhausts_attempts():
    calls = []

    def fn():
        calls.append(1)
        raise httpx.ConnectError("always fail")

    with pytest.raises(httpx.ConnectError):
        with_retry(fn, attempts=3)

    assert len(calls) == 3


def test_non_transient_raises_immediately():
    calls = []

    def fn():
        calls.append(1)
        raise ValueError("not transient")

    with pytest.raises(ValueError, match="not transient"):
        with_retry(fn, attempts=3)

    assert len(calls) == 1


def test_http_status_non_transient_raises_immediately():
    calls = []
    req = httpx.Request("GET", "http://x")
    resp = httpx.Response(400, request=req)

    def fn():
        calls.append(1)
        raise httpx.HTTPStatusError("bad request", request=req, response=resp)

    with pytest.raises(httpx.HTTPStatusError):
        with_retry(fn, attempts=3)

    assert len(calls) == 1


def test_generic_exception_with_transient_status_code_retries():
    calls = []

    class FakeAPIError(Exception):
        def __init__(self, msg, status_code):
            super().__init__(msg)
            self.status_code = status_code

    def fn():
        calls.append(1)
        if len(calls) < 3:
            raise FakeAPIError("rate limited", 503)
        return "recovered"

    result = with_retry(fn, attempts=3)
    assert result == "recovered"
    assert len(calls) == 3


def test_generic_exception_with_non_transient_status_code_raises_immediately():
    calls = []

    class FakeAPIError(Exception):
        def __init__(self, msg, status_code):
            super().__init__(msg)
            self.status_code = status_code

    def fn():
        calls.append(1)
        raise FakeAPIError("bad request", 400)

    with pytest.raises(FakeAPIError):
        with_retry(fn, attempts=3)

    assert len(calls) == 1
