import httpx
import pytest

from glaux.http import (
    MAX_ATTEMPTS,
    MAX_CONSECUTIVE_FAILURES,
    PoliteClient,
    Refused,
    RequestFailed,
    TooManyFailures,
    backoff_delay,
    parse_retry_after,
)


class FakeTime:
    def __init__(self):
        self.now = 1000.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def make_client(handler, delay_s=1.0):
    t = FakeTime()
    client = PoliteClient(
        "https://example.test/api/",
        "glaux/test (contact: test)",
        delay_s,
        transport=httpx.MockTransport(handler),
        sleep=t.sleep,
        clock=t.clock,
        epoch=lambda: 0.0,
        rng=lambda: 0.0,
    )
    return client, t


def responder(*statuses, headers=None):
    """A handler that answers with the given statuses in order, then 200 forever."""
    queue = list(statuses)
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        status = queue.pop(0) if queue else 200
        return httpx.Response(status, json={"ok": status}, headers=headers or {})

    return handler, seen


def test_sends_user_agent_and_returns_success():
    handler, seen = responder(200)
    client, _ = make_client(handler)
    response = client.get("search", params={"size": 10})
    assert response.json() == {"ok": 200}
    assert seen[0].headers["User-Agent"] == "glaux/test (contact: test)"
    assert str(seen[0].url) == "https://example.test/api/search?size=10"
    assert client.stats.requests == 1
    assert client.stats.bytes > 0


def test_waits_between_requests():
    handler, _ = responder()
    client, t = make_client(handler, delay_s=1.5)
    client.get("a")
    client.get("b")
    client.get("c")
    assert t.sleeps == [1.5, 1.5]


def test_retries_transient_errors_with_backoff():
    handler, seen = responder(503, 502, 200)
    client, t = make_client(handler, delay_s=0.0)
    assert client.get("x").status_code == 200
    assert len(seen) == 3
    assert t.sleeps == [backoff_delay(1, 0.0), backoff_delay(2, 0.0)]
    assert client.stats.retries == 2
    assert client.stats.failures == 2


def test_gives_up_after_max_attempts():
    handler, seen = responder(*([500] * MAX_ATTEMPTS))
    client, _ = make_client(handler, delay_s=0.0)
    with pytest.raises(RequestFailed):
        client.get("x")
    assert len(seen) == MAX_ATTEMPTS


@pytest.mark.parametrize("status", [401, 403])
def test_stops_immediately_when_refused(status):
    handler, seen = responder(status)
    client, _ = make_client(handler)
    with pytest.raises(Refused):
        client.get("x")
    assert len(seen) == 1


def test_client_errors_fail_without_retry_or_failure_count():
    handler, seen = responder(404)
    client, _ = make_client(handler)
    with pytest.raises(RequestFailed) as exc:
        client.get("x")
    assert exc.value.response.status_code == 404
    assert len(seen) == 1
    assert client.stats.failures == 0


def test_honours_retry_after():
    handler, _ = responder(429, headers={"Retry-After": "30"})
    client, t = make_client(handler, delay_s=0.0)
    client.get("x")
    assert t.sleeps == [30.0]


def test_long_retry_after_stops_the_run():
    handler, _ = responder(429, headers={"Retry-After": "3600"})
    client, _ = make_client(handler, delay_s=0.0)
    with pytest.raises(Refused, match="wait"):
        client.get("x")


def test_consecutive_failures_across_requests_stop_the_run():
    handler, _ = responder(*([503] * (MAX_CONSECUTIVE_FAILURES + 5)))
    client, _ = make_client(handler, delay_s=0.0)
    with pytest.raises(RequestFailed):
        client.get("a")  # 5 failures
    with pytest.raises(TooManyFailures):
        client.get("b")  # 5 more reach the limit


def test_transport_errors_are_retried():
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            raise httpx.ConnectTimeout("slow", request=request)
        return httpx.Response(200)

    client, _ = make_client(handler, delay_s=0.0)
    assert client.get("x").status_code == 200
    assert len(calls) == 2


def test_tls_verification_failure_is_refused_not_retried():
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] bad cert", request=request)

    client, _ = make_client(handler)
    with pytest.raises(Refused, match="TLS"):
        client.get("x")
    assert len(calls) == 1


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("", None),
        ("120", 120.0),
        ("Thu, 01 Jan 1970 00:01:40 GMT", 100.0),
        ("soon", None),
    ],
)
def test_parse_retry_after(value, expected):
    assert parse_retry_after(value, now_epoch=0.0) == expected


def test_backoff_grows_and_is_capped():
    delays = [backoff_delay(n, 0.0) for n in range(1, 10)]
    assert delays[:4] == [2.0, 4.0, 8.0, 16.0]
    assert max(delays) == 120.0
    assert backoff_delay(1, 0.999) < 3.0
