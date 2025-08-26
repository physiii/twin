#!/bin/bash

echo "📦 Installing RTSP Microphone Service"
echo "===================================="

# Check if running as root
if [ "$EUID" -eq 0 ]; then
    echo "❌ Please run this script as a regular user (not root)"
    echo "   The script will ask for sudo when needed"
    exit 1
fi

# Check if scripts exist
if [ ! -f "start_rtsp_mic.sh" ]; then
    echo "❌ start_rtsp_mic.sh not found in current directory"
    exit 1
fi

if [ ! -f "service/rtsp-mic.service" ]; then
    echo "❌ service/rtsp-mic.service not found"
    exit 1
fi

echo "🔧 Making scripts executable..."
chmod +x start_rtsp_mic.sh
chmod +x test_mic_latency.sh
chmod +x scripts/rtsp_mic_client.py

echo "📋 Installing systemd service..."
sudo cp service/rtsp-mic.service /etc/systemd/system/
sudo systemctl daemon-reload

echo "🎤 Testing audio device access..."
python3 scripts/rtsp_mic_client.py --list-devices

echo ""
echo "✅ Service installed successfully!"
echo ""
echo "📖 Usage Commands:"
echo "  sudo systemctl start rtsp-mic     # Start the service"
echo "  sudo systemctl stop rtsp-mic      # Stop the service"
echo "  sudo systemctl enable rtsp-mic    # Auto-start on boot"
echo "  sudo systemctl status rtsp-mic    # Check service status"
echo "  journalctl -u rtsp-mic -f         # View live logs"
echo ""
echo "🧪 Manual Testing:"
echo "  ./start_rtsp_mic.sh               # Run manually"
echo "  ./test_mic_latency.sh             # Test latency"
echo ""
echo "🎯 Stream URL: rtsp://$(hostname -I | awk '{print $1}'):8554/mic"
