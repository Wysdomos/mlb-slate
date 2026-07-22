"""Response models for the local PyBaseball API."""

from typing import Any

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "daily-slate-pybaseball-api"
    mode: str = "local-read-only"
    cache_enabled: bool
    backend_loaded: bool


class DatasetResponse(BaseModel):
    source: str = "pybaseball"
    query: dict[str, Any]
    row_count: int = Field(ge=0)
    total_rows: int = Field(ge=0)
    offset: int = Field(ge=0)
    next_offset: int | None = Field(default=None, ge=1)
    truncated: bool
    records: list[dict[str, Any]]


class ErrorResponse(BaseModel):
    detail: str
