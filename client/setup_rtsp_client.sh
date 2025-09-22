#!/bin/bash

# RTSP Client Setup Script for Ubuntu
# Installs dependencies and configures microphone streaming

set -e

echo "🔧 RTSP Microphone Client Setup"
echo "================================"

# Check if running as root
if [[ $EUID -eq 0 ]]; then
   echo "❌ This script should not be run as root"
   echo "   Run as a regular user instead"
   exit 1
fi

# Check Ubuntu version
if ! command -v lsb_release &> /dev/null; then
    echo "⚠️  Not running Ubuntu, some commands may not work"
else
    UBUNTU_VERSION=$(lsb_release -rs)
    echo "✅ Ubuntu $UBUNTU_VERSION detected"
fi

echo ""
echo "📦 Installing dependencies..."

# Update package list
sudo apt update

# Install required packages
PACKAGES=(
    "ffmpeg"
    "pulseaudio-utils"
    "python3"
    "python3-pip"
)

for package in "${PACKAGES[@]}"; do
    if dpkg -l | grep -q "^ii  $package "; then
        echo "✅ $package already installed"
    else
        echo "📥 Installing $package..."
        sudo apt install -y "$package"
    fi
done

# Install Python dependencies
echo ""
echo "🐍 Installing Python dependencies..."
pip3 install --user requests

echo ""
echo "🎤 Checking audio system..."

# Check if PulseAudio/PipeWire is running
if pgrep -x "pulseaudio" > /dev/null || pgrep -x "pipewire" > /dev/null; then
    echo "✅ Audio system (PulseAudio/PipeWire) is running"
else
    echo "⚠️  Audio system not running, starting PulseAudio..."
    pulseaudio --start --log-level=4
fi

# List available audio devices
echo ""
echo "🔍 Available audio devices:"
python3 "$(dirname "$0")/rtsp_mic_client.py" --list-devices

echo ""
echo "✅ Setup complete!"
echo ""
echo "🚀 Usage examples:"
echo "   # List audio devices"
echo "   python3 $(dirname "$0")/rtsp_mic_client.py --list-devices"
echo ""
echo "   # Stream to RTSP server (replace IP with your server)"
echo "   python3 $(dirname "$0")/rtsp_mic_client.py --server 192.168.1.40"
echo ""
echo "   # Stream to specific room"
echo "   python3 $(dirname "$0")/rtsp_mic_client.py --server 192.168.1.40 --path office"
echo ""
echo "   # Use specific microphone device"
echo "   python3 $(dirname "$0")/rtsp_mic_client.py --server 192.168.1.40 --device 'USB Microphone'"
echo ""
echo "📝 Note: This client uses monitor sources, so other apps can still use the microphone"
echo "   without interference. The audio is copied, not captured exclusively."

