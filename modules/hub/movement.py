from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlparse

import httpx

Move = Literal["F", "B", "L", "R"]


@dataclass(frozen=True)
class MotionCommand:
    label: str
    byte: int


class MovementClient:
    def __init__(self, base_url: str, step_duration_ms: int) -> None:
        parsed = urlparse(base_url)
        if parsed.scheme != "http" or not parsed.netloc:
            raise ValueError("ESP_HTTP_URL must start with http:// and include a host")
        self._url = base_url
        self._health_url = f"http://{parsed.netloc}/health"
        self._step_duration = step_duration_ms / 1000.0

    @property
    def target(self) -> str:
        return self._url

    async def send_moves(self, moves: list[Move]) -> list[str]:
        body = bytearray()
        executed: list[str] = []
        for requested in moves:
            command = parse_motion_command(requested)
            body.append(command.byte)
            executed.append(command.label)

        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.post(
                self._url,
                content=bytes(body),
                headers={"content-type": "application/octet-stream"},
            )
            response.raise_for_status()
        await asyncio.sleep(self._step_duration * len(moves))
        return executed

    async def health(self) -> str:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(self._health_url)
            response.raise_for_status()
            return f"HTTP/{response.http_version} {response.status_code} {response.reason_phrase}"


def parse_motion_command(value: Move) -> MotionCommand:
    match value:
        case "F":
            return MotionCommand("F", 0x01)
        case "B":
            return MotionCommand("B", 0x02)
        case "L":
            return MotionCommand("L", 0x03)
        case "R":
            return MotionCommand("R", 0x04)
        case other:
            raise ValueError(f"unknown movement command '{other}', expected F, B, L, or R")
