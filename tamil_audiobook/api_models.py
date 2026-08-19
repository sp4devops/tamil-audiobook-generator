from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BookEditRequest(StrictRequest):
    title: str | None = Field(default=None, max_length=500)
    author: str | None = Field(default=None, max_length=500)
    series: str | None = Field(default=None, max_length=500)


class ProgressRequest(StrictRequest):
    seconds: float = Field(default=0.0, ge=0.0, allow_inf_nan=False)
    duration: float = Field(default=0.0, ge=0.0, allow_inf_nan=False)


class PreferencesRequest(StrictRequest):
    playback_rate: float | None = Field(default=None, ge=0.5, le=3.0, allow_inf_nan=False)
    focus_mode: bool | None = None
    focus_minutes: int | None = Field(default=None, ge=1, le=180)
    break_minutes: int | None = Field(default=None, ge=1, le=180)
    reduce_motion: bool | None = None
    large_text: bool | None = None
    eq_preset: Literal["flat", "voice", "warm", "bright"] | None = None
    ambience: Literal["off", "rain", "brown"] | None = None
    theme: Literal["midnight", "graphite", "paper", "ocean"] | None = None
    repeat_mode: Literal["off", "all", "one"] | None = None
    shuffle: bool | None = None
    skip_seconds: int | None = Field(default=None, ge=1, le=300)
    generation_mode: Literal["fast", "balanced", "cool"] | None = None


class PlaylistCreateRequest(StrictRequest):
    name: str = Field(min_length=1, max_length=500)


class PlaylistUpdateRequest(StrictRequest):
    name: str | None = Field(default=None, max_length=500)
    books: list[str] | None = Field(default=None, max_length=10_000)


class FollowRequest(StrictRequest):
    kind: Literal["authors", "series"]
    value: str = Field(min_length=1, max_length=500)
    follow: bool = True


class ResetRequest(StrictRequest):
    confirmation: Literal["DELETE ALL LOCAL DATA"]
