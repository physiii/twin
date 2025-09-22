#!/usr/bin/env bash
set -euo pipefail

SERVER=${1:-127.0.0.1}
PATH_NAME=${2:-mic}
DUR=${DUR:-5}

# Resolve PulseAudio source
if command -v pactl >/dev/null 2>&1; then
  SOURCE=$(pactl get-default-source 2>/dev/null || true)
  if [[ -z "${SOURCE:-}" ]]; then
    SOURCE=$(pactl list short sources 2>/dev/null | awk '$2 ~ /^alsa_input\./ {print $2; exit}')
  fi
else
  echo "pactl not found; please install pulseaudio-utils" >&2
  exit 1
fi

if [[ -z "${SOURCE:-}" ]]; then
  echo "No PulseAudio source found" >&2
  exit 1
fi

echo "Using PulseAudio source: $SOURCE"
echo "Testing publish to rtsp://$SERVER:554/$PATH_NAME for $DUR seconds"

if timeout $((DUR+3)) ffmpeg -hide_banner -loglevel error \
  -f pulse -i "$SOURCE" -t "$DUR" \
  -c:a aac -b:a 128k -ar 16000 -ac 1 \
  -f rtsp -rtsp_transport tcp "rtsp://$SERVER:554/$PATH_NAME"; then
  echo "Publish OK"
else
  echo "Publish FAIL"
  exit 1
fi

echo "Playing back locally with ffplay to verify audio..."
timeout $((DUR+5)) ffplay -loglevel warning -autoexit -nodisp "rtsp://127.0.0.1:554/$PATH_NAME" || true

LAN_IP=$(hostname -I | awk '{print $1}')
if [[ -n "${LAN_IP:-}" ]]; then
  echo "Playing back via LAN IP $LAN_IP with ffplay..."
  timeout $((DUR+5)) ffplay -loglevel warning -autoexit -nodisp "rtsp://$LAN_IP:554/$PATH_NAME" || true
fi
