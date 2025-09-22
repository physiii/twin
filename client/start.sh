#!/usr/bin/env bash
set -euo pipefail
DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
BIN="$DIR/mediamtx"
CONF="$DIR/mediamtx.yml"
PORT=554
if [[ ! -x "$BIN" ]]; then echo "Missing mediamtx at $BIN"; exit 1; fi
if [[ ! -f "$CONF" ]]; then echo "Missing config at $CONF"; exit 1; fi
if ! grep -q "^rtspAddress: :$PORT$" "$CONF"; then echo "Updating rtspAddress to :$PORT"; sed -i "s/^rtspAddress: :.*/rtspAddress: :$PORT/" "$CONF"; fi
if lsof -i :$PORT -sTCP:LISTEN -Pn >/dev/null 2>&1; then
	echo "MediaMTX already running on port $PORT"
	exit 0
fi
echo "Starting MediaMTX on port $PORT with $CONF"
exec sudo "$BIN" "$CONF"
