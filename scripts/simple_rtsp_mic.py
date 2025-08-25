#!/usr/bin/env python3
"""
Simple RTSP Microphone Server for Twin

This creates a simple RTSP stream from the microphone using FFmpeg's RTSP output.
"""

import subprocess
import sys
import argparse
import signal
import time

def signal_handler(signum, frame):
    print(f"\nReceived signal {signum}, stopping...")
    sys.exit(0)

def main():
    parser = argparse.ArgumentParser(description="Simple RTSP Microphone Server")
    parser.add_argument('--port', '-p', type=int, default=8554, help='RTSP port')
    parser.add_argument('--device', '-d', default='default', help='Audio device')
    
    args = parser.parse_args()
    
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    print(f"🎤 Starting simple RTSP microphone server on port {args.port}")
    print(f"📡 Stream URL: rtsp://192.168.1.150:{args.port}/live.sdp")
    print("Press Ctrl+C to stop")
    print("-" * 50)
    
    # Simple FFmpeg command that creates an RTSP stream
    cmd = [
        'ffmpeg',
        '-f', 'pulse',
        '-i', args.device,
        '-acodec', 'pcm_s16le',
        '-ar', '16000',
        '-ac', '1',
        '-f', 'rtsp',
        f'rtsp://0.0.0.0:{args.port}/live.sdp'
    ]
    
    print(f"🔧 FFmpeg command: {' '.join(cmd)}")
    print("-" * 50)
    
    try:
        # Run FFmpeg
        process = subprocess.run(cmd)
    except KeyboardInterrupt:
        print("\n✅ Stopped by user")
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 