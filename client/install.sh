#!/usr/bin/env bash
set -euo pipefail
DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
BIN="$DIR/mediamtx"
PORT=554
UNIT_DIR="$HOME/.config/systemd/user"
UNIT_FILE="$UNIT_DIR/rtsp-server.service"

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
echo "\nConfiguring user-level systemd service (rtsp-server.service)..."
mkdir -p "$UNIT_DIR"
cat > "$UNIT_FILE" <<EOU
[Unit]
Description=MediaMTX RTSP Server (user)
After=default.target

[Service]
Type=simple
WorkingDirectory=$DIR
ExecStart=$BIN $DIR/mediamtx.yml
Restart=always
RestartSec=3
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
EOU

systemctl --user daemon-reload
systemctl --user enable --now rtsp-server.service
echo "Service enabled. Use: systemctl --user status rtsp-server.service"
