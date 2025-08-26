#!/bin/bash

echo "🎯 RTSP Audio Latency Test"
echo "=========================="
echo
echo "This will play the RTSP stream with minimal buffering."
echo "To test latency:"
echo "1. Make a sharp sound (clap, snap, or tap the mic)"
echo "2. Listen for the delay in your speakers/headphones"
echo "3. Press Ctrl+C to stop"
echo
echo "Expected latency with current settings: 50-200ms"
echo

# Force low audio latency at the system level
export SDL_AUDIODRIVER=pulse
export PULSE_LATENCY_MSEC=10

# Play with absolute minimal buffering - window will show audio visualization
ffplay \
  -fflags nobuffer \
  -flags low_delay \
  -probesize 32 \
  -analyzeduration 0 \
  -rtsp_transport udp \
  -vn \
  -sync audio \
  -window_title "RTSP Audio Latency Test - Press Q to quit" \
  -i rtsp://127.0.0.1:8554/mic
