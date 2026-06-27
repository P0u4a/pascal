from __future__ import annotations

from pydantic import BaseModel


class ApiStatus(BaseModel):
    service: str
    latest_video_id: int


class ClientLog(BaseModel):
    level: str | None = None
    subsystem: str | None = None
    message: str


class Ingested(BaseModel):
    accepted: bool


class WebRtcSessionDescription(BaseModel):
    sdp: str
    type: str
