#!/usr/bin/env bash
set -euo pipefail
echo Installing dependencies and capabilities...
sudo apt update
sudo apt install -y ffmpeg pulseaudio-utils
echo Setting CAP_NET_BIND_SERVICE so mediamtx can bind port 554 without sudo...
sudo setcap "cap_net_bind_service=+ep" "$PWD/client/mediamtx" || { echo "setcap failed; will require sudo to run server"; }
echo Done.
