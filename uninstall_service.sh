#!/bin/bash

echo "🗑️  Uninstalling RTSP Microphone Service"
echo "======================================="

# Stop and disable service
echo "⏹️  Stopping service..."
sudo systemctl stop rtsp-mic 2>/dev/null || true
sudo systemctl disable rtsp-mic 2>/dev/null || true

# Remove service file
echo "📄 Removing service file..."
sudo rm -f /etc/systemd/system/rtsp-mic.service

# Reload systemd
echo "🔄 Reloading systemd..."
sudo systemctl daemon-reload

# Kill any running processes
echo "🔌 Stopping any running processes..."
killall python3 2>/dev/null || true
killall mediamtx 2>/dev/null || true

echo ""
echo "✅ Service uninstalled successfully!"
echo ""
echo "ℹ️  The script files remain in this directory:"
echo "   - start_rtsp_mic.sh (manual start)"
echo "   - test_mic_latency.sh (test latency)"
