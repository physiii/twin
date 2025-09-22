#!/usr/bin/env bash
set -e
journalctl --user -u rtsp-mic-client.service -f | cat
