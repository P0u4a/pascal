from __future__ import annotations

import argparse
import os
import select
import sys
import termios
import time
import tty
import http.client
from collections.abc import Iterator
from contextlib import contextmanager
from urllib.parse import urlparse


MOVE_INTERVAL_SECONDS = 0.25
HTTP_TIMEOUT_SECONDS = 1.0
INPUT_POLL_SECONDS = 0.05
INPUT_READ_BYTES = 32

ARROW_MOTIONS = {
    b"\x1b[A": 0x01,  # Up: forward
    b"\x1b[B": 0x02,  # Down: backward
    b"\x1b[C": 0x04,  # Right: rotate right
    b"\x1b[D": 0x03,  # Left: rotate left
}


def parse_args() -> str:
    parser = argparse.ArgumentParser(description="Drive Pascal with the arrow keys.")
    parser.add_argument(
        "--url",
        default=os.getenv("ESP_HTTP_URL"),
        help="ESP HTTP URL or host. Defaults to ESP_HTTP_URL.",
    )
    args = parser.parse_args()

    if not args.url:
        parser.error("provide --url or set ESP_HTTP_URL")

    return to_motion_url(args.url)


def to_motion_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("--url must be an ESP host or an HTTP URL")

    if parsed.path != "/motion":
        value = f"{value}/motion"
    return value


@contextmanager
def raw_terminal() -> Iterator[None]:
    if not sys.stdin.isatty():
        raise RuntimeError("controller input must be run from an interactive terminal")

    original_settings = termios.tcgetattr(sys.stdin)
    try:
        tty.setcbreak(sys.stdin.fileno())
        yield
    finally:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, original_settings)


def read_latest_motion(timeout: float) -> int | None:
    if not input_ready(timeout):
        return None

    buffer = read_input_buffer()
    return parse_latest_motion(buffer)


def read_input_buffer() -> bytes:
    buffer = bytearray(os.read(sys.stdin.fileno(), INPUT_READ_BYTES))
    while input_ready(0.0):
        buffer.extend(os.read(sys.stdin.fileno(), INPUT_READ_BYTES))

    while (buffer.endswith(b"\x1b") or buffer.endswith(b"\x1b[")):
        buffer.extend(os.read(sys.stdin.fileno(), INPUT_READ_BYTES))

    return bytes(buffer)


def parse_latest_motion(buffer: bytes) -> int | None:
    latest: int | None = None
    index = 0
    while index < len(buffer):
        sequence = bytes(buffer[index : index + 3])
        motion = ARROW_MOTIONS.get(sequence)
        if motion is None:
            index += 1
            continue
        latest = motion
        index += 3

    return latest


def input_ready(timeout: float) -> bool:
    readable, _, _ = select.select([sys.stdin], [], [], timeout)
    return bool(readable)


class MotionClient:
    def __init__(self, url: str) -> None:
        parsed = urlparse(url)
        connection = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
        self.connection = connection(parsed.netloc, timeout=HTTP_TIMEOUT_SECONDS)
        self.path = parsed.path

    def send(self, motion: int) -> None:
        self.connection.request(
            "POST",
            self.path,
            body=bytes([motion]),
            headers={
                "content-type": "application/octet-stream",
                "connection": "keep-alive",
            },
        )
        response = self.connection.getresponse()
        response.read()


def main() -> None:
    try:
        url = parse_args()
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    print(f"Driving Pascal at {url}")
    print("Arrow keys: up=forward down=backward left=rotate left right=rotate right")
    print("Hold an arrow key to repeat. Press Ctrl+C to stop.")

    client = MotionClient(url)
    next_send_at = 0.0

    try:
        with raw_terminal():
            while True:
                motion = read_latest_motion(INPUT_POLL_SECONDS)
                if motion is None:
                    continue

                now = time.monotonic()
                if now < next_send_at:
                    time.sleep(next_send_at - now)

                # Read immediately
                queued_motion = read_latest_motion(0.0)
                if queued_motion is not None:
                    motion = queued_motion

                started_at = time.monotonic()
                try:
                    client.send(motion)
                except (http.client.HTTPException, TimeoutError, OSError) as exc:
                    print(f"\nfailed to send motion: {exc}", file=sys.stderr)

                elapsed = time.monotonic() - started_at
                next_send_at = started_at + max(MOVE_INTERVAL_SECONDS, elapsed)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
