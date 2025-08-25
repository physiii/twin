#!/bin/bash

# Simple RTSP Client Launcher
# Usage: ./launch_rtsp_client.sh

set -e

echo "🚀 Launching RTSP client"

# Set environment variables
# Default RTSP server IP to this machine's primary LAN IP if not provided
LOCAL_IP=$(hostname -I | awk '{print $1}')
export RTSP_SERVER_IP=${RTSP_SERVER_IP:-$LOCAL_IP}
export RTSP_SERVER_PORT=${RTSP_SERVER_PORT:-8554}

echo "📡 Configuration:"
echo "   RTSP Server: $RTSP_SERVER_IP:$RTSP_SERVER_PORT"
echo "   Stream Path: mic"

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker first."
    exit 1
fi

# Stop any existing containers
echo "🛑 Stopping any existing containers..."
docker compose down 2>/dev/null || true

# Build and start the service
echo "🔨 Building and starting RTSP client..."
docker compose up -d --build

echo ""
echo "✅ RTSP client started successfully!"
echo ""
echo "📊 Container status:"
docker compose ps

echo ""
echo "🎤 Streaming to: rtsp://$RTSP_SERVER_IP:$RTSP_SERVER_PORT/mic"
echo ""
echo "📝 Update your Twin config/source_locations.json with:"
echo "   \"rtsp://$(hostname -I | awk '{print $1}'):$RTSP_SERVER_PORT/mic\": \"office\"  # map in Twin"
echo ""
echo "📋 Useful commands:"
echo "   # View logs"
echo "   docker compose logs -f"
echo ""
echo "   # Stop service"
echo "   docker compose down"
echo ""
echo "   # Restart service"
echo "   docker compose restart"
