#!/usr/bin/env bash
set -euo pipefail

# Usage: publish_mic.sh [RTSP_PORT] [PATH_NAME]
# Publishes a local microphone to rtsp://127.0.0.1:$RTSP_PORT/$PATH_NAME

RTSP_PORT=${1:-554}
PATH_NAME=${2:-mic}

audio_format="pulse"
audio_device="default"

if command -v pactl >/dev/null 2>&1 && pactl info >/dev/null 2>&1; then
  audio_format="pulse"
  audio_device="${PULSE_SOURCE:-default}"
else
  audio_format="alsa"
  # Try to find a sane capture device via ALSA
  if command -v arecord >/dev/null 2>&1; then
    # Pick first card that has device 0
    first_card=$(arecord -l 2>/dev/null | awk '
      /^card [0-9]+: / { gsub(",", "", $3); last_card=$3 }
      /device 0:/ { if (last_card != "") { print last_card; exit } }
    ' || true)
    if [[ -n "${first_card:-}" ]]; then
      audio_device="plughw:CARD=${first_card},DEV=0"
    else
      audio_device="default"
    fi
  fi
fi

exec ffmpeg -hide_banner -nostdin -loglevel error \
  -f "${audio_format}" -i "${audio_device}" \
  -c:a aac -b:a 96k -ar 16000 -ac 1 \
  -f rtsp -rtsp_transport tcp "rtsp://127.0.0.1:${RTSP_PORT}/${PATH_NAME}"


