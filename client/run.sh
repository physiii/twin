#!/usr/bin/env bash
set -euo pipefail

# RTSP audio server publisher using MediaMTX and FFmpeg
# - Listens on RTSP port 554 (requires sudo to bind <1024)
# - Publishes default PulseAudio/PIPEWIRE mic to path /mic

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_MTX="$SCRIPT_DIR/mediamtx"
CONF_PATH="$SCRIPT_DIR/mediamtx_554.yml"

RTSP_PORT=554
RTSP_PATH="mic"
RTSP_URL="rtsp://127.0.0.1:${RTSP_PORT}/${RTSP_PATH}"

# Determine target user (for audio session access)
TARGET_USER="${SUDO_USER:-$(id -un)}"
TARGET_UID=$(id -u "$TARGET_USER")
RUN_AS_USER_PREFIX=(sudo -u "$TARGET_USER" XDG_RUNTIME_DIR="/run/user/${TARGET_UID}")

cleanup() {
  set +e
  if [[ -n "${FFMPEG_PID:-}" ]] && kill -0 "$FFMPEG_PID" 2>/dev/null; then
    kill "$FFMPEG_PID" 2>/dev/null || true
    wait "$FFMPEG_PID" 2>/dev/null || true
  fi
  if [[ -n "${MTX_PID:-}" ]] && kill -0 "$MTX_PID" 2>/dev/null; then
    sudo kill "$MTX_PID" 2>/dev/null || true
    wait "$MTX_PID" 2>/dev/null || true
  fi
  rm -f "$CONF_PATH" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# Dependency checks
for cmd in sudo ffmpeg ffprobe lsof hostname; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "Missing dependency: $cmd" >&2; exit 1; }
  
done

if [[ ! -x "$BIN_MTX" ]]; then
  echo "Missing or non-executable MediaMTX binary at $BIN_MTX" >&2
  echo "Place the 'mediamtx' binary in $SCRIPT_DIR and make it executable." >&2
  exit 1
fi

detect_audio_input() {
  # Try PulseAudio/ PipeWire via pactl in the user's session
  if command -v pactl >/dev/null 2>&1; then
    if "${RUN_AS_USER_PREFIX[@]}" pactl info >/dev/null 2>&1; then
      local src
      src=$(("${RUN_AS_USER_PREFIX[@]}" pactl get-default-source 2>/dev/null) | tr -d '\n' || true)
      if [[ -z "$src" ]]; then
        src=$(("${RUN_AS_USER_PREFIX[@]}" bash -lc "pactl list short sources | awk 'NR==1{print \\$2}'") 2>/dev/null | tr -d '\n' || true)
      fi
      if [[ -n "$src" ]]; then
        AUDIO_FORMAT="pulse"
        AUDIO_INPUT="$src"
        return 0
      fi
    fi
  fi
  # Fallback to ALSA default
  AUDIO_FORMAT="alsa"
  AUDIO_INPUT="default"
}

detect_audio_input
echo "Using audio: format=$AUDIO_FORMAT input=$AUDIO_INPUT (as $TARGET_USER)"

# Quick validation of audio input (1s dry run to null)
if ! "${RUN_AS_USER_PREFIX[@]}" ffmpeg -hide_banner -nostdin -loglevel error -f "$AUDIO_FORMAT" -i "$AUDIO_INPUT" -t 1 -f null - >/dev/null 2>&1; then
  echo "WARNING: Could not read from $AUDIO_FORMAT:$AUDIO_INPUT. If PulseAudio fails, try setting a working default mic or ensure PipeWire/Pulse is running. Falling back may still work." >&2
fi

# Write minimal config to force RTSP on :554
cat > "$CONF_PATH" <<EOF
rtspAddress: :${RTSP_PORT}
paths:
  mic:
    source: publisher
EOF

# Start MediaMTX using the config; run in background under sudo (keep logs visible)
echo "Starting MediaMTX (RTSP :$RTSP_PORT) with $CONF_PATH ..."
sudo -E "$BIN_MTX" "$CONF_PATH" &
MTX_PID=$!

# Wait for RTSP port to be listening
echo -n "Waiting for RTSP port $RTSP_PORT to be ready"
for _ in {1..50}; do
  if lsof -i :"$RTSP_PORT" -sTCP:LISTEN -Pn >/dev/null 2>&1; then
    echo " ... ready"
    break
  fi
  echo -n "."
  sleep 0.2
done
if ! lsof -i :"$RTSP_PORT" -sTCP:LISTEN -Pn >/dev/null 2>&1; then
  echo "\nERROR: MediaMTX did not start listening on port $RTSP_PORT" >&2
  # If it accidentally bound to 8554, hint to the user
  if lsof -i :8554 -sTCP:LISTEN -Pn >/dev/null 2>&1; then
    echo "Hint: Server appears to be listening on 8554 instead. Check logs above for config parsing issues." >&2
  fi
  exit 1
fi

# Publish mic audio to RTSP
echo "Starting FFmpeg publisher -> $RTSP_URL"
"${RUN_AS_USER_PREFIX[@]}" ffmpeg -hide_banner -nostdin -loglevel error \
  -f "$AUDIO_FORMAT" -i "$AUDIO_INPUT" \
  -c:a aac -b:a 128k -ar 48000 -ac 1 \
  -f rtsp -rtsp_transport tcp "$RTSP_URL" &
FFMPEG_PID=$!

# Show connection hints
LAN_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || true)
echo "RTSP feed is live:"
echo "  Local:   rtsp://127.0.0.1:${RTSP_PORT}/${RTSP_PATH}"
if [[ -n "$LAN_IP" ]]; then
  echo "  LAN:     rtsp://${LAN_IP}:${RTSP_PORT}/${RTSP_PATH}"
fi
echo "Connect with your client (e.g., VLC, ffplay)."

# Keep the script running until interrupted
wait


