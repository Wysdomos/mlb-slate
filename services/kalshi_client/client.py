"""Typed Kalshi public market-data client.

The client intentionally uses public REST endpoints only. Kalshi's public
market-data endpoints require no credentials, so this module never sends auth
headers, secrets, or API keys.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, Iterable, Mapping, Optional, Tuple, Union

KALSHI_BASE_URL = "https://external-api.kalshi.com/trade-api/v2"
DEFAULT_USER_AGENT = "TheDailySlate-KalshiClient/1.0"
JsonObject = Dict[str, Any]
Params = Mapping[str, Union[str, int, float, bool, None]]
Transport = Callable[[str, Mapping[str, str], int], Tuple[JsonObject, Mapping[str, str]]]


class KalshiApiError(Exception):
    """Raised for Kalshi API transport, HTTP, or payload errors."""

    def __init__(
        self,
        message: str,
        *,
        status: Optional[int] = None,
        code: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code


class KalshiApiRateLimitError(KalshiApiError):
    """Raised when Kalshi rate-limits longer than the retry budget."""


class KalshiApiPayloadError(KalshiApiError):
    """Raised when Kalshi returns an unexpected payload shape."""


def _default_transport(
    url: str,
    headers: Mapping[str, str],
    timeout: int,
) -> Tuple[JsonObject, Mapping[str, str]]:
    req = urllib.request.Request(url, headers=dict(headers), method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            return payload, {k.lower(): v for k, v in resp.headers.items()}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        code = None
        message = body or f"Kalshi API returned HTTP {exc.code}"
        try:
            payload = json.loads(body)
            code = str(payload.get("code") or payload.get("error") or "") or None
            message = str(payload.get("message") or payload.get("detail") or message)
        except json.JSONDecodeError:
            pass
        if exc.code == 429:
            raise KalshiApiRateLimitError(message, status=exc.code, code=code) from exc
        raise KalshiApiError(message, status=exc.code, code=code) from exc
    except urllib.error.URLError as exc:
        raise KalshiApiError(f"Could not reach Kalshi API: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise KalshiApiPayloadError("Kalshi API returned non-JSON payload") from exc


class KalshiClient:
    """Small stdlib client for Kalshi public REST market data."""

    def __init__(
        self,
        *,
        base_url: str = KALSHI_BASE_URL,
        timeout: Optional[int] = None,
        min_gap: Optional[float] = None,
        transport: Optional[Transport] = None,
        user_agent: str = DEFAULT_USER_AGENT,
        retries: int = 3,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        if self.base_url != KALSHI_BASE_URL:
            raise ValueError("KalshiClient supports exactly one pinned public base URL")
        self.timeout = timeout if timeout is not None else _env_int("KALSHI_TIMEOUT", 20)
        self.min_gap = min_gap if min_gap is not None else _env_float("KALSHI_MIN_REQUEST_GAP", 0.25)
        self._transport = transport or _default_transport
        self.user_agent = user_agent
        self.retries = retries
        self._last_call = 0.0
        self.request_count = 0

    def series(self, *, category: Optional[str] = None, tags: Optional[str] = None, limit: int = 200) -> JsonObject:
        return self._get("/series", {"category": category, "tags": tags, "limit": limit})

    def series_detail(self, series_ticker: str) -> JsonObject:
        return self._get(f"/series/{series_ticker}", {})

    def events(
        self,
        *,
        series_ticker: Optional[str] = None,
        cursor: Optional[str] = None,
        limit: int = 200,
    ) -> JsonObject:
        return self._get("/events", {"series_ticker": series_ticker, "cursor": cursor, "limit": limit})

    def markets(
        self,
        *,
        series_ticker: Optional[str] = None,
        event_ticker: Optional[str] = None,
        cursor: Optional[str] = None,
        limit: int = 200,
    ) -> JsonObject:
        return self._get(
            "/markets",
            {
                "series_ticker": series_ticker,
                "event_ticker": event_ticker,
                "cursor": cursor,
                "limit": limit,
            },
        )

    def market(self, ticker: str) -> JsonObject:
        return self._get(f"/markets/{ticker}", {})

    def orderbook(self, ticker: str) -> JsonObject:
        return self._get(f"/markets/{ticker}/orderbook", {})

    def paged_events(
        self,
        *,
        series_ticker: str,
        max_pages: Optional[int] = None,
        limit: int = 200,
    ) -> list[JsonObject]:
        return list(
            self._paged(
                lambda cursor: self.events(series_ticker=series_ticker, cursor=cursor, limit=limit),
                key="events",
                max_pages=max_pages,
            )
        )

    def paged_markets(
        self,
        *,
        event_ticker: str,
        series_ticker: Optional[str] = None,
        max_pages: Optional[int] = None,
        limit: int = 200,
    ) -> list[JsonObject]:
        return list(
            self._paged(
                lambda cursor: self.markets(
                    series_ticker=series_ticker,
                    event_ticker=event_ticker,
                    cursor=cursor,
                    limit=limit,
                ),
                key="markets",
                max_pages=max_pages,
            )
        )

    def _paged(
        self,
        getter: Callable[[Optional[str]], JsonObject],
        *,
        key: str,
        max_pages: Optional[int],
    ) -> Iterable[JsonObject]:
        cursor = None
        pages = 0
        while True:
            if max_pages is not None and pages >= max_pages:
                return
            payload = getter(cursor)
            pages += 1
            rows = payload.get(key)
            if not isinstance(rows, list):
                raise KalshiApiPayloadError(f"Kalshi payload missing list key: {key}")
            for row in rows:
                if isinstance(row, dict):
                    yield row
            cursor = payload.get("cursor")
            if not cursor:
                return

    def _get(self, path: str, params: Params) -> JsonObject:
        clean_params = _clean_params(params)
        url = self._url(path, clean_params)
        headers = {"Accept": "application/json", "User-Agent": self.user_agent}
        last_err: Optional[Exception] = None
        for attempt in range(self.retries + 1):
            self._pace()
            try:
                self.request_count += 1
                response, _headers = self._transport(url, headers, self.timeout)
                if not isinstance(response, dict):
                    raise KalshiApiPayloadError("Kalshi API returned a non-object payload")
                return response
            except KalshiApiRateLimitError as exc:
                last_err = exc
                if attempt >= self.retries:
                    break
                time.sleep(_retry_delay(attempt, exc))
            except KalshiApiError as exc:
                last_err = exc
                if exc.status not in (408, 425, 429, 500, 502, 503, 504) or attempt >= self.retries:
                    break
                time.sleep(_retry_delay(attempt, exc))
        if isinstance(last_err, KalshiApiError):
            raise last_err
        raise KalshiApiError(f"Kalshi request failed: {last_err}")

    def _url(self, path: str, params: Mapping[str, str]) -> str:
        url = f"{self.base_url}{path}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        return url

    def _pace(self) -> None:
        if self.min_gap <= 0:
            return
        now = time.time()
        wait = self.min_gap - (now - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.time()


def _clean_params(params: Params) -> Dict[str, str]:
    clean = {}
    for key, value in params.items():
        if value is None:
            continue
        clean[key] = str(value)
    return dict(sorted(clean.items()))


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value < 0:
        raise ValueError(f"{name} must be >= 0")
    return value


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a float") from exc
    if value < 0:
        raise ValueError(f"{name} must be >= 0")
    return value


def _retry_delay(attempt: int, exc: KalshiApiError) -> float:
    return min(2.0 * (attempt + 1), 8.0)
