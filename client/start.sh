#!/usr/bin/env bash
set -e
DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
SCRIPTS_DIR="$DIR"
exec python3 "$SCRIPTS_DIR/rtsp_mic_client.py" --server "${RTSP_SERVER_IP:-192.168.1.40}" --path "${RTSP_PATH:-mic}" "$@"
