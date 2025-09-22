#!/usr/bin/env bash
set -euo pipefail
DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
BIN="$DIR/mediamtx"
PORT=554
SYS_UNIT_FILE="/etc/systemd/system/rtsp-server.service"

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

echo "Install complete. Use $DIR/run.py for a foreground run."

echo "\nConfiguring system service (requires sudo): $SYS_UNIT_FILE"
sudo bash -c "cat > '$SYS_UNIT_FILE'" <<EOU
[Unit]
Description=MediaMTX RTSP Server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$DIR
ExecStart=$BIN $DIR/mediamtx.yml
Restart=always
RestartSec=3
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOU

# Disable any lingering user service with same name
systemctl --user disable --now rtsp-server.service 2>/dev/null || true

sudo systemctl daemon-reload
sudo systemctl enable --now rtsp-server.service
echo "System service enabled. Use: sudo systemctl status rtsp-server.service"
