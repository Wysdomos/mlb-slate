"""Typed Ballpark Pal API v1 client.

The client intentionally uses X-API-Key header auth only. The deprecated
query-param key form is never emitted.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date as date_type
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional, Tuple, Union

BPP_BASE_URL = "https://www.ballparkpal.com/api/v1"
DEFAULT_CACHE_DIR = Path(__file__).resolve().parent / "cache"
DEFAULT_USER_AGENT = "TheDailySlate-BPPClient/1.0"
JsonObject = Dict[str, Any]
Params = Mapping[str, Union[str, int, bool, None]]
Transport = Callable[[str, Mapping[str, str], int], Tuple[JsonObject, Mapping[str, str]]]


class BppApiError(Exception):
    """Raised for Ballpark Pal API transport, HTTP, or envelope errors."""

    def __init__(
        self,
        message: str,
        *,
        status: Optional[int] = None,
        code: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.request_id = request_id


class BppApiAuthError(BppApiError):
    """Raised when an authenticated endpoint is called without an API key."""


@dataclass(frozen=True)
class CacheEntry:
    fetched_at: float
    url: str
    response: JsonObject


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
        request_id = None
        code = None
        message = body or f"Ballpark Pal API returned HTTP {exc.code}"
        try:
            payload = json.loads(body)
            err = payload.get("error") or {}
            request_id = err.get("requestId")
            code = err.get("code")
            message = err.get("message") or message
        except json.JSONDecodeError:
            pass
        raise BppApiError(
            message,
            status=exc.code,
            code=code,
            request_id=request_id,
        ) from exc
    except urllib.error.URLError as exc:
        raise BppApiError(f"Could not reach Ballpark Pal API: {exc.reason}") from exc


class BppClient:
    """Small stdlib client for the Ballpark Pal API v1 surface."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        base_url: str = BPP_BASE_URL,
        cache_dir: Union[str, Path] = DEFAULT_CACHE_DIR,
        use_cache: bool = True,
        timeout: int = 30,
        min_gap: float = 0.0,
        transport: Optional[Transport] = None,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.environ.get("BPP_API_KEY")
        self.base_url = base_url.rstrip("/")
        self.cache_dir = Path(cache_dir)
        self.use_cache = use_cache
        self.timeout = timeout
        self.min_gap = min_gap
        self._transport = transport or _default_transport
        self.user_agent = user_agent
        self._last_call = 0.0

    def health(self, *, force_refresh: bool = False) -> JsonObject:
        return self._get(
            "/health",
            {},
            auth_required=bool(self.api_key),
            force_refresh=force_refresh,
        )

    def markets(self, *, force_refresh: bool = False) -> JsonObject:
        return self._get("/markets", {}, force_refresh=force_refresh)

    def teams(self, *, force_refresh: bool = False) -> JsonObject:
        return self._get("/teams", {}, force_refresh=force_refresh)

    def players(
        self,
        *,
        team_id: Optional[int] = None,
        q: Optional[str] = None,
        force_refresh: bool = False,
    ) -> JsonObject:
        return self._get(
            "/players",
            {"teamId": team_id, "q": q},
            force_refresh=force_refresh,
        )

    def games(
        self,
        *,
        date: Optional[Union[str, date_type]] = None,
        game_id: Optional[int] = None,
        force_refresh: bool = False,
    ) -> JsonObject:
        if date is None and game_id is None:
            raise ValueError("games requires date or game_id")
        return self._get(
            "/games",
            {"date": _date_str(date), "gameId": game_id},
            force_refresh=force_refresh,
        )

    def game(self, game_id: int, *, force_refresh: bool = False) -> JsonObject:
        return self._get(f"/games/{game_id}", {}, force_refresh=force_refresh)

    def projection_probabilities(
        self,
        game_id: int,
        *,
        force_refresh: bool = False,
    ) -> JsonObject:
        return self._get(
            "/projections/probabilities",
            {"gameId": game_id},
            force_refresh=force_refresh,
        )

    def projection_averages(
        self,
        game_id: int,
        *,
        force_refresh: bool = False,
    ) -> JsonObject:
        return self._get(
            "/projections/averages",
            {"gameId": game_id},
            force_refresh=force_refresh,
        )

    def parkfactors(
        self,
        date: Union[str, date_type],
        *,
        force_refresh: bool = False,
    ) -> JsonObject:
        return self._get(
            "/parkfactors",
            {"date": _date_str(date)},
            force_refresh=force_refresh,
        )

    def hitter_parkfactors(
        self,
        *,
        date: Optional[Union[str, date_type]] = None,
        game_id: Optional[int] = None,
        force_refresh: bool = False,
    ) -> JsonObject:
        if date is None and game_id is None:
            raise ValueError("hitter_parkfactors requires date or game_id")
        return self._get(
            "/parkfactors/hitters",
            {"date": _date_str(date), "gameId": game_id},
            force_refresh=force_refresh,
        )

    def matchups(
        self,
        date: Union[str, date_type],
        *,
        starters: bool = False,
        force_refresh: bool = False,
    ) -> JsonObject:
        return self._get(
            "/matchups",
            {"date": _date_str(date), "starters": "true" if starters else None},
            force_refresh=force_refresh,
        )

    def predict_matchup(
        self,
        *,
        batter_id: int,
        pitcher_id: int,
        force_refresh: bool = False,
    ) -> JsonObject:
        return self._get(
            "/matchups/predict",
            {"batterId": batter_id, "pitcherId": pitcher_id},
            force_refresh=force_refresh,
        )

    def _get(
        self,
        path: str,
        params: Params,
        *,
        auth_required: bool = True,
        force_refresh: bool = False,
    ) -> JsonObject:
        clean_params = _clean_params(params)
        url = self._url(path, clean_params)
        cache_path = self._cache_path(path, clean_params)

        if self.use_cache and not force_refresh:
            cached = self._read_cache(cache_path)
            if cached is not None:
                return cached

        headers = {"Accept": "application/json", "User-Agent": self.user_agent}
        if auth_required:
            if not self.api_key:
                raise BppApiAuthError("BPP_API_KEY is required for this endpoint")
            headers["X-API-Key"] = self.api_key

        self._pace()
        response, _headers = self._transport(url, headers, self.timeout)
        self._raise_for_error_envelope(response)

        if self.use_cache:
            self._write_cache(cache_path, CacheEntry(time.time(), url, response))
        return response

    def _url(self, path: str, params: Mapping[str, str]) -> str:
        url = f"{self.base_url}{path}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        return url

    def _cache_path(self, path: str, params: Mapping[str, str]) -> Path:
        payload = json.dumps(
            {"base_url": self.base_url, "path": path, "params": params},
            sort_keys=True,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
        stem = path.strip("/").replace("/", "_") or "root"
        return self.cache_dir / f"{stem}_{digest}.json"

    def _read_cache(self, cache_path: Path) -> Optional[JsonObject]:
        try:
            with cache_path.open("r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except FileNotFoundError:
            return None
        except (OSError, json.JSONDecodeError):
            return None

        response = raw.get("response") if isinstance(raw, dict) else None
        return response if isinstance(response, dict) else None

    def _write_cache(self, cache_path: Path, entry: CacheEntry) -> None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "fetchedAt": entry.fetched_at,
            "url": entry.url,
            "response": entry.response,
        }
        tmp = cache_path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
            fh.write("\n")
        tmp.replace(cache_path)

    def _pace(self) -> None:
        if self.min_gap <= 0:
            return
        now = time.time()
        wait = self.min_gap - (now - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.time()

    def _raise_for_error_envelope(self, response: JsonObject) -> None:
        err = response.get("error")
        if not isinstance(err, dict):
            return
        raise BppApiError(
            err.get("message") or "Ballpark Pal API error",
            code=err.get("code"),
            request_id=err.get("requestId"),
        )


def _clean_params(params: Params) -> Dict[str, str]:
    clean = {}
    for key, value in params.items():
        if value is None:
            continue
        clean[key] = str(value)
    return dict(sorted(clean.items()))


def _date_str(value: Optional[Union[str, date_type]]) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, date_type):
        return value.isoformat()
    return value
