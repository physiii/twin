#!/bin/bash

echo "🎤 RTSP Microphone Service Status"
echo "================================="
echo ""

# Check service status
SERVICE_STATUS=$(systemctl is-active rtsp-mic)
SERVICE_ENABLED=$(systemctl is-enabled rtsp-mic)

echo "📋 Service Status:"
echo "  Active: $SERVICE_STATUS"
echo "  Enabled: $SERVICE_ENABLED"
echo ""

if [ "$SERVICE_STATUS" = "active" ]; then
    echo "✅ Service is running!"
    
    # Check if stream is accessible
    echo ""
    echo "🔍 Testing stream accessibility..."
    if timeout 3s ffprobe rtsp://127.0.0.1:8554/mic >/dev/null 2>&1; then
        echo "✅ Stream is accessible at rtsp://127.0.0.1:8554/mic"
        
        # Get stream details
        echo ""
        echo "📊 Stream Details:"
        ffprobe rtsp://127.0.0.1:8554/mic 2>&1 | grep -E "(Stream|Duration|bitrate)" | head -3
        
    else
        echo "❌ Stream not accessible (may be starting up...)"
    fi
    
else
    echo "❌ Service is not running"
    echo ""
    echo "🔧 To start manually:"
    echo "   sudo systemctl start rtsp-mic"
fi

echo ""
echo "📖 Management Commands:"
echo "  sudo systemctl status rtsp-mic    # Check detailed status"
echo "  sudo systemctl restart rtsp-mic   # Restart service"
echo "  journalctl -u rtsp-mic -f         # View live logs"
echo "  ./test_mic_latency.sh             # Test latency"
