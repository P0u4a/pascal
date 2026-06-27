from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable

from schemas import WebRtcSessionDescription

logger = logging.getLogger("pascal.webrtc")

VideoFrameHandler = Callable[[Any], Awaitable[None]]


async def create_media_answer(
    offer: WebRtcSessionDescription,
    peer_connections: set[Any],
    on_video_frame: VideoFrameHandler,
) -> WebRtcSessionDescription:
    try:
        from aiortc import RTCPeerConnection, RTCSessionDescription
    except ImportError as exc:
        raise RuntimeError("aiortc is not installed; run uv sync for the Pascal server") from exc

    pc = RTCPeerConnection()
    peer_connections.add(pc)

    @pc.on("connectionstatechange")
    async def on_connectionstatechange() -> None:
        logger.info("webrtc connection state=%s", pc.connectionState)
        if pc.connectionState in {"failed", "closed", "disconnected"}:
            peer_connections.discard(pc)
            await pc.close()

    @pc.on("track")
    def on_track(track: Any) -> None:
        logger.info("webrtc track received kind=%s", track.kind)
        if track.kind == "video":
            asyncio.create_task(_consume_video(track, on_video_frame))
        elif track.kind == "audio":
            asyncio.create_task(_consume_audio(track))

    await pc.setRemoteDescription(RTCSessionDescription(sdp=offer.sdp, type=offer.type))
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)
    await _wait_for_ice_gathering(pc)
    if pc.localDescription is None:
        raise RuntimeError("WebRTC local description was not created")
    return WebRtcSessionDescription(sdp=pc.localDescription.sdp, type=pc.localDescription.type)


async def close_peer_connections(peer_connections: set[Any]) -> None:
    if not peer_connections:
        return
    await asyncio.gather(*(pc.close() for pc in list(peer_connections)), return_exceptions=True)
    peer_connections.clear()


async def _consume_video(track: Any, on_video_frame: VideoFrameHandler) -> None:
    frame_count = 0
    while True:
        try:
            frame = await track.recv()
        except Exception as exc:
            logger.info("video track ended after %s frames: %s", frame_count, exc)
            return

        frame_count += 1
        image = frame.to_image()
        await on_video_frame(image)


async def _consume_audio(track: Any) -> None:
    frame_count = 0
    while True:
        try:
            await track.recv()
        except Exception as exc:
            logger.info("audio track ended after %s frames: %s", frame_count, exc)
            return
        frame_count += 1


async def _wait_for_ice_gathering(pc: Any) -> None:
    if pc.iceGatheringState == "complete":
        return
    complete = asyncio.Event()

    @pc.on("icegatheringstatechange")
    def on_icegatheringstatechange() -> None:
        if pc.iceGatheringState == "complete":
            complete.set()

    try:
        await asyncio.wait_for(complete.wait(), timeout=5.0)
    except TimeoutError:
        logger.warning("webrtc ICE gathering timed out; returning current local SDP")
