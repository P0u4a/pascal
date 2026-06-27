#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HUB_DIR="$ROOT_DIR/modules/hub"
ENV_FILE="$ROOT_DIR/.env"
SERVER_PID=""

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
else
  echo "Missing .env at repo root. Copy .env.example to .env and edit it." >&2
  exit 1
fi

export HUB_BIND_ADDR="${HUB_BIND_ADDR:-0.0.0.0:8080}"

server_url() {
  printf 'http://%s\n' "$HUB_BIND_ADDR"
}

wait_for_server() {
  local url
  url="$(server_url)"

  for _ in {1..120}; do
    if curl -fsS "$url/health" >/dev/null 2>&1; then
      echo "Health check passed: $url/health"
      return 0
    fi

    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
      wait "$SERVER_PID"
      return $?
    fi

    sleep 0.25
  done

  echo "Pascal hub did not become healthy at $url/health" >&2
  return 1
}

stop_server() {
  if [[ -z "$SERVER_PID" ]] || ! kill -0 "$SERVER_PID" 2>/dev/null; then
    return
  fi

  echo
  echo "Stopping Pascal hub..."
  kill -TERM "$SERVER_PID" 2>/dev/null || true
  wait "$SERVER_PID" 2>/dev/null || true
}

cleanup() {
  local status=$?
  trap - EXIT INT TERM
  stop_server
  exit "$status"
}

trap cleanup EXIT INT TERM

(
  cd "$HUB_DIR"
  uv sync
  exec uv run hub-server
) &
SERVER_PID=$!

echo "Pascal hub PID: $SERVER_PID"
wait_for_server

url="$(server_url)"
echo
echo "Pascal hub is running with only:"
echo "  MCP endpoint:       $url/mcp"
echo "  WebRTC offer URL:   $url/v1/webrtc/offer"
echo "  ESP log URL:        $url/v1/logs"
echo "  Health check:       $url/health"
echo "  Snapshot file:      ${HUB_SNAPSHOT_PATH:-${HUB_DATA_DIR:-/tmp/pascal}/latest.jpg}"
echo
echo "The Swift app should use HUB_IOS_SERVER_URL=$url, or another LAN-reachable URL."
echo "Press Ctrl-C to stop."

wait "$SERVER_PID"
