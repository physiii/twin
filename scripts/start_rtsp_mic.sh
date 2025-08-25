#!/bin/bash
# Quick launcher for Twin RTSP Microphone Server

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RTSP_SCRIPT="$SCRIPT_DIR/rtsp_mic_server.py"

echo -e "${BLUE}🤖 Twin RTSP Microphone Server Launcher${NC}"
echo "========================================"
echo

# Check if the main script exists
if [[ ! -f "$RTSP_SCRIPT" ]]; then
    echo "❌ RTSP server script not found: $RTSP_SCRIPT"
    exit 1
fi

# Function to start with specific configuration
start_server() {
    local port=$1
    local device=$2
    local description=$3
    
    echo -e "${GREEN}🚀 Starting: $description${NC}"
    echo "   Port: $port"
    echo "   Device: $device"
    echo "   URL: rtsp://$(hostname -I | awk '{print $1}'):$port/audio"
    echo
    
    exec python3 "$RTSP_SCRIPT" --port "$port" --device "$device"
}

# Menu options
echo "Select configuration:"
echo
echo "1) Default microphone (port 8554)"
echo "2) Office setup (port 8554, specific device)"
echo "3) Kitchen setup (port 8555)" 
echo "4) Living room setup (port 8556)"
echo "5) Custom configuration"
echo "6) List audio devices"
echo "7) Test existing stream"
echo
read -p "Choice [1-7]: " choice

case $choice in
    1)
        start_server 8554 "default" "Default microphone"
        ;;
    2)
        echo "Available devices:"
        python3 "$RTSP_SCRIPT" --list-devices
        echo
        read -p "Enter device name for office: " office_device
        start_server 8554 "$office_device" "Office microphone"
        ;;
    3)
        echo "Available devices:"
        python3 "$RTSP_SCRIPT" --list-devices
        echo
        read -p "Enter device name for kitchen: " kitchen_device
        start_server 8555 "$kitchen_device" "Kitchen microphone"
        ;;
    4)
        echo "Available devices:"
        python3 "$RTSP_SCRIPT" --list-devices
        echo
        read -p "Enter device name for living room: " living_device
        start_server 8556 "$living_device" "Living room microphone"
        ;;
    5)
        read -p "Port [8554]: " custom_port
        custom_port=${custom_port:-8554}
        
        echo "Available devices:"
        python3 "$RTSP_SCRIPT" --list-devices
        echo
        read -p "Device [default]: " custom_device
        custom_device=${custom_device:-default}
        
        start_server "$custom_port" "$custom_device" "Custom configuration"
        ;;
    6)
        echo "Available audio devices:"
        python3 "$RTSP_SCRIPT" --list-devices
        ;;
    7)
        read -p "RTSP URL to test [rtsp://localhost:8554/audio]: " test_url
        test_url=${test_url:-rtsp://localhost:8554/audio}
        
        echo "Testing stream: $test_url"
        echo "Press Ctrl+C to stop"
        echo
        
        if command -v ffplay &> /dev/null; then
            ffplay "$test_url"
        elif command -v vlc &> /dev/null; then
            vlc "$test_url"
        else
            echo "No media player found. Install ffplay or vlc to test streams."
        fi
        ;;
    *)
        echo "Invalid choice"
        exit 1
        ;;
esac 