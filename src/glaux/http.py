"""A polite HTTP client for public services.

Implements the "Polite client rules" in docs/build-spec.md: one request at a time, a fixed pause
between requests, retries with backoff for transient failures, and a hard stop when the service
refuses us. Never disables TLS verification.
"""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from email.utils import parsedate_to_datetime

import httpx

log = logging.getLogger(__name__)

TIMEOUT_S = 30.0
MAX_ATTEMPTS = 5
MAX_CONSECUTIVE_FAILURES = 10
BACKOFF_BASE_S = 2.0
BACKOFF_CAP_S = 120.0
# A service asking us to wait longer than this is asking us to stop for now.
MAX_RETRY_AFTER_S = 300.0

RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
REFUSED_STATUSES = frozenset({401, 403})


class Refused(Exception):
    """The service refused us or asked us to back off for a long time. Stop the run and report."""


class TooManyFailures(Exception):
    """Too many failures in a row. Stop the run and report."""


class RequestFailed(Exception):
    """One request failed for good (a 4xx, or retries ran out). The run may continue."""

    def __init__(self, message: str, response: httpx.Response | None = None):
        super().__init__(message)
        self.response = response


@dataclass
class Stats:
    requests: int = 0
    retries: int = 0
    failures: int = 0
    bytes: int = 0


def parse_retry_after(value: str | None, now_epoch: float) -> float | None:
    """Seconds to wait from a Retry-After header, which is either seconds or an HTTP date."""
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        return float(value)
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, when.timestamp() - now_epoch)


def backoff_delay(attempt: int, jitter: float, retry_after: float | None = None) -> float:
    """Delay before retry number `attempt` (1 for the first retry). `jitter` is in [0, 1)."""
    delay = min(BACKOFF_CAP_S, BACKOFF_BASE_S * 2 ** (attempt - 1)) * (1.0 + 0.5 * jitter)
    if retry_after is not None:
        delay = max(delay, retry_after)
    return delay


def _is_tls_failure(exc: Exception) -> bool:
    text = f"{exc} {exc.__cause__} {exc.__context__}".upper()
    return "CERTIFICATE_VERIFY_FAILED" in text or ("SSL" in text and "VERIFY" in text)


class PoliteClient:
    def __init__(
        self,
        base_url: str,
        user_agent: str,
        delay_s: float,
        *,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        epoch: Callable[[], float] = time.time,
        rng: Callable[[], float] = random.random,
    ):
        self._http = httpx.Client(
            base_url=base_url,
            headers={"User-Agent": user_agent},
            timeout=TIMEOUT_S,
            follow_redirects=True,
            transport=transport,
        )
        self._delay_s = delay_s
        self._sleep = sleep
        self._clock = clock
        self._epoch = epoch
        self._rng = rng
        self._last_done: float | None = None
        self._consecutive_failures = 0
        self.stats = Stats()

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> PoliteClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _wait_turn(self) -> None:
        if self._last_done is None:
            return
        remaining = self._delay_s - (self._clock() - self._last_done)
        if remaining > 0:
            self._sleep(remaining)

    def _record_failure(self, reason: str) -> None:
        self.stats.failures += 1
        self._consecutive_failures += 1
        if self._consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
            raise TooManyFailures(f"{self._consecutive_failures} failures in a row, last: {reason}")

    def get(
        self,
        url: str,
        params: Mapping[str, str | int] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            self._wait_turn()
            started = self._clock()
            response: httpx.Response | None = None
            try:
                response = self._http.get(url, params=params, headers=headers)
                reason = f"HTTP {response.status_code}"
            except httpx.TransportError as exc:
                if _is_tls_failure(exc):
                    raise Refused(f"TLS verification failed for {url}: {exc}") from exc
                reason = f"{exc.__class__.__name__}: {exc}"
            finally:
                self._last_done = self._clock()
                self.stats.requests += 1

            elapsed = self._last_done - started
            if response is not None:
                self.stats.bytes += len(response.content)
                log.debug(
                    "GET %s %s %d bytes %.2fs",
                    response.request.url,
                    response.status_code,
                    len(response.content),
                    elapsed,
                )
                status = response.status_code
                if status < 400:
                    self._consecutive_failures = 0
                    return response
                if status in REFUSED_STATUSES:
                    raise Refused(f"{url} answered HTTP {status}. Stopping, do not work around it.")
                if status not in RETRY_STATUSES:
                    # A client error such as 400 or 404 says nothing about the service's health.
                    raise RequestFailed(f"{url} answered HTTP {status}", response)
            else:
                log.debug("GET %s failed after %.2fs: %s", url, elapsed, reason)

            self._record_failure(reason)
            if attempt == MAX_ATTEMPTS:
                raise RequestFailed(f"{url} failed {MAX_ATTEMPTS} times, last: {reason}", response)

            retry_after = None
            if response is not None:
                retry_after = parse_retry_after(response.headers.get("Retry-After"), self._epoch())
                if retry_after is not None and retry_after > MAX_RETRY_AFTER_S:
                    raise Refused(f"{url} asked us to wait {retry_after:.0f}s. Stopping for now.")
            delay = backoff_delay(attempt, self._rng(), retry_after)
            log.info("retrying %s in %.1fs after %s", url, delay, reason)
            self.stats.retries += 1
            self._sleep(delay)

        raise AssertionError("unreachable")
