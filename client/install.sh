#!/usr/bin/env bash
set -e
DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_DIR=$(cd "$DIR/.." && pwd)
SCRIPTS_DIR="$REPO_DIR/client"

# Ensure required tools
command -v python3 >/dev/null || { echo "python3 is required"; exit 1; }

# Create user systemd directory
UNIT_DIR="$HOME/.config/systemd/user"
mkdir -p "$UNIT_DIR"

# Write environment file if not exists
ENV_FILE="$HOME/.config/rtsp-mic-client.env"
if [[ ! -f "$ENV_FILE" ]]; then
  cat > "$ENV_FILE" << EOV
# RTSP mic client configuration
RTSP_SERVER_IP=${RTSP_SERVER_IP:-192.168.1.40}
RTSP_SERVER_PORT=${RTSP_SERVER_PORT:-554}
RTSP_PATH=${RTSP_PATH:-mic}
RTSP_DEVICE=${RTSP_DEVICE:-default}
RTSP_SAMPLE_RATE=${RTSP_SAMPLE_RATE:-16000}
RTSP_CHANNELS=${RTSP_CHANNELS:-1}
EOV
  echo "Wrote $ENV_FILE"
else
  echo "Using existing $ENV_FILE"
fi

# Create user service file
UNIT_FILE="$UNIT_DIR/rtsp-mic-client.service"
cat > "$UNIT_FILE" << EOU
[Unit]
Description=RTSP Microphone Client (user)
After=default.target

[Service]
Type=simple
WorkingDirectory=$SCRIPTS_DIR
EnvironmentFile=%h/.config/rtsp-mic-client.env
ExecStart=/usr/bin/python3 $SCRIPTS_DIR/rtsp_mic_client.py --server ${RTSP_SERVER_IP} --port ${RTSP_SERVER_PORT} --path ${RTSP_PATH} --device ${RTSP_DEVICE} --sample-rate ${RTSP_SAMPLE_RATE} --channels ${RTSP_CHANNELS}
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
EOU

echo "Wrote $UNIT_FILE"

# Enable lingering so user services run at boot (optional)
if command -v loginctl >/dev/null 2>&1; then
  if loginctl show-user "$USER" | grep -q "Linger=no"; then
    echo "Enabling user lingering (so service can run at boot)"
    sudo loginctl enable-linger "$USER" || true
  fi
fi

systemctl --user daemon-reload
systemctl --user enable --now rtsp-mic-client.service
systemctl --user status rtsp-mic-client.service --no-pager | sed -n '1,15p'
