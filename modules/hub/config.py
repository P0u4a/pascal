from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    bind_host: str
    bind_port: int
    esp_http_url: str | None
    movement_step_ms: int
    data_dir: Path
    snapshot_path: Path

    @classmethod
    def from_env(cls) -> "Config":
        bind_host, bind_port = parse_bind_addr(os.getenv("HUB_BIND_ADDR", "0.0.0.0:8080"))
        data_dir = Path(
            os.getenv(
                "HUB_DATA_DIR",
                str(Path(tempfile.gettempdir()) / "pascal"),
            )
        )
        return cls(
            bind_host=bind_host,
            bind_port=bind_port,
            esp_http_url=non_empty_env("ESP_HTTP_URL"),
            movement_step_ms=int(os.getenv("ESP_MOVE_STEP_MS", "700")),
            data_dir=data_dir,
            snapshot_path=Path(os.getenv("HUB_SNAPSHOT_PATH", str(data_dir / "latest.jpg"))),
        )


def parse_bind_addr(value: str) -> tuple[str, int]:
    host, sep, port_text = value.rpartition(":")
    if not sep or not host:
        raise ValueError("HUB_BIND_ADDR must be shaped like host:port")
    return host, int(port_text)


def non_empty_env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None or value == "":
        return None
    return value
