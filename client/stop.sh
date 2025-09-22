#!/usr/bin/env bash
set -e
systemctl --user stop rtsp-mic-client.service || true
