#!/usr/bin/env bash
set -euo pipefail

# Test script for RTSP audio server
# Steps:
# 1) Check deps (ffprobe, ffplay)
# 2) Probe local and LAN URLs
# 3) Attempt short record via ffmpeg
# 4) Launch ffplay for interactive listen

RTSP_PORT=554
RTSP_PATH="mic"

for cmd in ffprobe ffplay ffmpeg; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "Missing dependency: $cmd" >&2; exit 1; }
done

LAN_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || true)
URLS=("rtsp://127.0.0.1:${RTSP_PORT}/${RTSP_PATH}")
if [[ -n "$LAN_IP" ]]; then
  URLS+=("rtsp://${LAN_IP}:${RTSP_PORT}/${RTSP_PATH}")
fi

OUT_DIR="$(pwd)/test_audio"
mkdir -p "$OUT_DIR"

overall_pass=true

for url in "${URLS[@]}"; do
  echo "\n=== Testing $url ==="

  echo "Probing stream..."
  if ffprobe -v error -rtsp_transport tcp -select_streams a:0 -show_streams -of compact=p=0:nk=1 "$url" >/dev/null 2>&1; then
    echo "PROBE: PASS"
  else
    echo "PROBE: FAIL"
    overall_pass=false
  fi

  echo "Recording 3 seconds to file..."
  out_file="$OUT_DIR/$(echo "$url" | tr '/:' '_')_sample.aac"
  if ffmpeg -hide_banner -loglevel error -rtsp_transport tcp -t 3 -i "$url" -vn -acodec copy "$out_file"; then
    echo "RECORD: PASS ($out_file)"
  else
    echo "RECORD: FAIL"
    overall_pass=false
  fi
done

echo "\nLaunching ffplay for local URL so you can listen (Ctrl+C to exit)..."
ffplay -loglevel warning -rtsp_transport tcp -autoexit "rtsp://127.0.0.1:${RTSP_PORT}/${RTSP_PATH}"

if $overall_pass; then
  echo "\nRESULT: PASS"
else
  echo "\nRESULT: FAIL"
fi


