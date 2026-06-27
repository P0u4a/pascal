#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  send-motion.sh <esp8266-ip-or-url> <motion> [motion ...]

Examples:
  send-motion.sh <esp-ip> forward
  send-motion.sh http://<esp-ip>/motion forward left stop
  send-motion.sh "$ESP_HTTP_URL" F L R

Motions:
  stop, s, 0
  forward, f
  backward, back, b
  left, rotate-left, l
  right, rotate-right, r
EOF
}

if [[ $# -lt 2 ]]; then
  usage >&2
  exit 2
fi

target=$1
shift
motions=("$@")

if [[ "$target" != http://* ]]; then
  target="http://${target}"
fi

target="${target%/}"
if [[ "$target" != */motion ]]; then
  target="${target}/motion"
fi

payload=$(mktemp "${TMPDIR:-/tmp}/pascal-motion.XXXXXX")
trap 'rm -f "$payload"' EXIT

for motion in "${motions[@]}"; do
  motion_lc=$(printf '%s' "$motion" | tr '[:upper:]' '[:lower:]')
  case "$motion_lc" in
    stop|s|0)
      printf '\x00' >>"$payload"
      ;;
    forward|f)
      printf '\x01' >>"$payload"
      ;;
    backward|back|b)
      printf '\x02' >>"$payload"
      ;;
    left|rotate-left|rotate_left|l)
      printf '\x03' >>"$payload"
      ;;
    right|rotate-right|rotate_right|r)
      printf '\x04' >>"$payload"
      ;;
    *)
      printf 'unknown motion: %s\n\n' "$motion" >&2
      usage >&2
      exit 2
      ;;
  esac
done

curl -fsS -X POST \
  -H 'content-type: application/octet-stream' \
  --data-binary "@${payload}" \
  "$target"
printf '\n'
