#!/usr/bin/env bash
set -e
UNIT_FILE="$HOME/.config/systemd/user/rtsp-mic-client.service"
ENV_FILE="$HOME/.config/rtsp-mic-client.env"

systemctl --user disable --now rtsp-mic-client.service || true
systemctl --user daemon-reload || true
rm -f "$UNIT_FILE"
# Keep env file by default; delete if --purge
if [[ "$1" == "--purge" ]]; then
  rm -f "$ENV_FILE"
fi

echo "Removed user service."
