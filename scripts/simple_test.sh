#!/bin/bash

echo "🎯 Simple RTSP Audio Test"
echo "========================="
echo
echo "This will play the RTSP stream with basic settings."
echo "To test latency, make a sharp sound and listen for delay."
echo "Press 'Q' to quit when done."
echo

# Simple playback with just UDP transport
ffplay -rtsp_transport udp rtsp://127.0.0.1:8554/mic
