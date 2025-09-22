#!/usr/bin/env bash
set -euo pipefail
DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
cd "$DIR"
CONF="$DIR/mediamtx.yml"
BIN="$DIR/mediamtx"
if [[ ! -x "$BIN" ]]; then echo "mediamtx binary missing at $BIN"; exit 1; fi
if [[ ! -f "$CONF" ]]; then echo "mediamtx.yml missing at $CONF"; exit 1; fi
if [[ $EUID -ne 0 ]]; then
  if ! sudo -n true 2>/dev/null; then echo "This will start RTSP on port 554 and needs sudo."; fi
  exec sudo "$BIN" "$CONF"
else
  exec "$BIN" "$CONF"
fi
