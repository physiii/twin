#!/usr/bin/env bash
set -e
systemctl --user status rtsp-mic-client.service --no-pager | cat
