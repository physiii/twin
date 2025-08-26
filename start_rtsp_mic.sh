#!/bin/bash

echo "🎤 Starting Low-Latency RTSP Microphone Stream"
echo "=============================================="
echo ""

# Kill any existing processes
echo "Cleaning up existing processes..."
killall mediamtx 2>/dev/null
sleep 1

# Start MediaMTX server
echo "Starting MediaMTX RTSP server..."
cd scripts
./mediamtx mediamtx.yml &
MEDIAMTX_PID=$!
cd ..

# Wait for server to start
sleep 3

# Start microphone streaming
echo "Starting microphone stream..."
echo "Device: alsa_input.usb-Focusrite_Scarlett_2i2_4th_Gen_S2ZPP0Y3A939A9-00.analog-surround-40"
echo "Stream URL: rtsp://127.0.0.1:8554/mic"
echo ""
echo "Press Ctrl+C to stop everything"
echo ""

cd scripts
python3 rtsp_mic_client.py \
  --server 127.0.0.1 \
  --sample-rate 8000 \
  --device "alsa_input.usb-Focusrite_Scarlett_2i2_4th_Gen_S2ZPP0Y3A939A9-00.analog-surround-40"

# Cleanup when script exits
echo ""
echo "Stopping MediaMTX..."
kill $MEDIAMTX_PID 2>/dev/null
wait $MEDIAMTX_PID 2>/dev/null
echo "✅ All processes stopped"
