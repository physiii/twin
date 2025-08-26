#!/bin/bash

echo "🎧 Testing RTSP Microphone Latency"
echo "=================================="
echo ""
echo "This will play audio from the RTSP stream."
echo "Make sounds to test the delay!"
echo "Press 'q' to quit."
echo ""

# Use the lowest latency ffplay settings
ffplay \
  -fflags nobuffer \
  -flags low_delay \
  -probesize 32 \
  -analyzeduration 0 \
  -rtsp_transport udp \
  -sync audio \
  -vn \
  -nodisp \
  -window_title "RTSP Latency Test - Press Q to quit" \
  rtsp://127.0.0.1:8554/mic
