#!/usr/bin/env bash
set -euo pipefail
PORT=554
# Try graceful stop
sudo pkill -f '/media/mass/scripts/twin/client/mediamtx' || true
sleep 1
# Ensure ports are free (TCP 554 and legacy UDP 8000/8001 if enabled elsewhere)
if lsof -i :$PORT -sTCP:LISTEN -Pn >/dev/null 2>&1; then
	echo "Port $PORT still in use, forcing..."
	sudo fuser -k ${PORT}/tcp || true
	sleep 1
fi
sudo fuser -k 8000/udp 2>/dev/null || true
sudo fuser -k 8001/udp 2>/dev/null || true
sleep 0.3
if lsof -i :$PORT -sTCP:LISTEN -Pn >/dev/null 2>&1; then
	echo "Failed to stop server (port still listening)" >&2
	exit 1
fi
echo "Server stopped."
