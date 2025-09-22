#!/usr/bin/env bash
set -e
DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
SCRIPTS_DIR="$DIR"
SERVER="${RTSP_SERVER_IP:-127.0.0.1}"
exec python3 "$SCRIPTS_DIR/rtsp_mic_client.py" --server "$SERVER" --list-devices
