#!/usr/bin/env bash
set -euo pipefail
DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
BIN="$DIR/mediamtx"
PORT=554

echo "Installing dependencies..."
sudo apt update
sudo apt install -y ffmpeg pulseaudio-utils lsof

echo "Attempting to allow $BIN to bind to privileged ports (setcap)..."
if command -v setcap >/dev/null 2>&1; then
	sudo setcap 'cap_net_bind_service=+ep' "$BIN" || echo "setcap failed; start.sh will use sudo"
else
	echo "setcap not available; start.sh will use sudo"
fi

echo "Validating binary and config..."
[[ -x "$BIN" ]] || { echo "Missing or non-executable $BIN"; exit 1; }
[[ -f "$DIR/mediamtx.yml" ]] || { echo "Missing $DIR/mediamtx.yml"; exit 1; }

echo "Ensuring no process is listening on $PORT..."
if lsof -i :$PORT -sTCP:LISTEN -Pn >/dev/null 2>&1; then
	echo "Killing existing process on $PORT"
	sudo fuser -k ${PORT}/tcp || true
fi

echo "Install complete. Use $DIR/start.sh to start the server."
