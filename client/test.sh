#!/usr/bin/env bash
set -e
DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
SCRIPTS_DIR="$DIR/../scripts"
SERVER=${1:-192.168.1.40}
PATH_NAME=${2:-mic}
echo "Testing stream to rtsp://$SERVER:8554/$PATH_NAME for 5 seconds"
timeout 7 ffmpeg -hide_banner -loglevel error -f pulse -i default.monitor -t 5 -f rtsp -rtsp_transport tcp rtsp://$SERVER:8554/$PATH_NAME && echo "OK" || echo "FAIL"
