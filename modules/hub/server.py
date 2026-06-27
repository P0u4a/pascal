from __future__ import annotations

import asyncio
import base64
import json
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated, Any, AsyncIterator

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.tools import ToolResult
from mcp.types import ImageContent, TextContent
from pydantic import Field

from config import Config
from movement import Move, MovementClient
from schemas import ApiStatus, ClientLog, Ingested, WebRtcSessionDescription
from webrtc import close_peer_connections, create_media_answer

logger = logging.getLogger("pascal.hub")


@dataclass
class AppState:
    config: Config
    movement: MovementClient | None
    peer_connections: set[Any]
    snapshot_lock: asyncio.Lock
    latest_video_id: int = 0


_state: AppState | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global _state
    config = Config.from_env()
    config.data_dir.mkdir(parents=True, exist_ok=True)
    _state = AppState(
        config=config,
        movement=MovementClient(config.esp_http_url, config.movement_step_ms)
        if config.esp_http_url
        else None,
        peer_connections=set(),
        snapshot_lock=asyncio.Lock(),
    )
    app.state.hub = _state
    try:
        yield
    finally:
        await close_peer_connections(_state.peer_connections)
        _state = None


def create_app() -> FastAPI:
    configure_logging()
    mcp_app = create_mcp().http_app(path="/mcp", json_response=True, stateless_http=True)
    app = FastAPI(title="Pascal Hub", lifespan=combined_lifespan(mcp_app))

    @app.get("/health", response_model=ApiStatus)
    async def health(request: Request) -> ApiStatus:
        state = get_state(request)
        return ApiStatus(service="hub", latest_video_id=state.latest_video_id)

    @app.post("/v1/webrtc/offer", response_model=WebRtcSessionDescription)
    async def webrtc_offer(
        request: Request,
        offer: WebRtcSessionDescription,
    ) -> WebRtcSessionDescription:
        state = get_state(request)
        try:
            return await create_media_answer(
                offer,
                state.peer_connections,
                on_video_frame=lambda image: save_snapshot(request, image),
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/v1/logs", response_model=Ingested)
    async def client_log(log: ClientLog) -> Ingested:
        target = f"pascal.{log.subsystem}" if log.subsystem else "pascal.hub.client"
        logging.getLogger(target).log(log_level(log.level), log.message)
        return Ingested(accepted=True)

    app.mount("/", mcp_app)

    return app


def combined_lifespan(mcp_app: Any) -> Any:
    @asynccontextmanager
    async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with lifespan(app):
            async with mcp_app.lifespan(mcp_app):
                yield

    return _lifespan


def create_mcp() -> FastMCP:
    mcp = FastMCP(name="pascal", version="0.1.0")

    @mcp.tool(title="Move Robot")
    async def move_robot(moves: Annotated[list[Move], Field(min_length=1)]) -> ToolResult:
        """
        Move Pascal with F (go forward), B (go backwards), L (turn left), R (turn right) commands and return the latest robot POV image.
        Each move is one step and can be chained to run continuously. 
        """
        return await move_robot_tool(moves)

    @mcp.tool(title="Get Snapshot")
    async def get_snapshot() -> ToolResult:
        """Return the current robot POV image."""
        return await snapshot_result(
            {"snapshot": True},
            missing_message="no snapshot available",
        )

    return mcp


async def move_robot_tool(moves: list[Move]) -> ToolResult:
    state = require_state()
    if state.movement is None:
        raise ToolError("ESP_HTTP_URL is not configured")

    executed = await state.movement.send_moves(moves)
    return await snapshot_result(
        {"executed": executed},
        missing_message="no snapshot available after movement",
    )


async def snapshot_result(
    status: dict[str, Any],
    *,
    missing_message: str,
) -> ToolResult:
    state = require_state()
    async with state.snapshot_lock:
        snapshot_path = state.config.snapshot_path
        if not snapshot_path.exists():
            raise ToolError(missing_message)
        image_bytes = snapshot_path.read_bytes()

    status["snapshot_bytes"] = len(image_bytes)
    status["latest_video_id"] = state.latest_video_id
    return ToolResult(
        content=[
            TextContent(type="text", text=json.dumps(status, separators=(",", ":"))),
            ImageContent(
                type="image",
                data=base64.b64encode(image_bytes).decode("ascii"),
                mimeType="image/jpeg",
            ),
        ],
        structured_content=status,
    )


async def save_snapshot(request: Request, image: Any) -> None:
    state = get_state(request)
    state.latest_video_id += 1
    async with state.snapshot_lock:
        image.save(state.config.snapshot_path, format="JPEG", quality=80)
    if state.latest_video_id == 1 or state.latest_video_id % 60 == 0:
        logger.info("snapshot updated frame_id=%s path=%s", state.latest_video_id, state.config.snapshot_path)


def get_state(request: Request) -> AppState:
    return request.app.state.hub


def require_state() -> AppState:
    if _state is None:
        raise ToolError("hub is not ready")
    return _state


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def log_level(level: str | None) -> int:
    return {
        "error": logging.ERROR,
        "warn": logging.WARNING,
        "warning": logging.WARNING,
    }.get(level or "info", logging.INFO)


def main() -> None:
    config = Config.from_env()
    uvicorn.run(
        "server:create_app",
        factory=True,
        host=config.bind_host,
        port=config.bind_port,
    )


if __name__ == "__main__":
    main()
