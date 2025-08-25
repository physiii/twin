#!/usr/bin/env python3
"""
HTTP Audio Streaming Server for Twin

This creates an HTTP audio stream from the microphone using FFmpeg.
"""

import subprocess
import sys
import argparse
import signal
import socket

def signal_handler(signum, frame):
    print(f"\nReceived signal {signum}, stopping...")
    sys.exit(0)

def get_ip_address():
    """Get the primary IP address of this machine"""
    try:
        # Connect to a remote address to determine the local IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"

def main():
    parser = argparse.ArgumentParser(description="HTTP Audio Streaming Server for Twin")
    parser.add_argument('--port', '-p', type=int, default=8555, help='HTTP port')
    parser.add_argument('--device', '-d', default='default', help='Audio device')
    
    args = parser.parse_args()
    
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    ip_addr = get_ip_address()
    
    print("🎤 Twin HTTP Audio Streaming Server")
    print("=" * 40)
    print(f"📡 Starting HTTP server on port {args.port}")
    print(f"🎙️  Audio device: {args.device}")
    print(f"🌐 Stream URL: http://{ip_addr}:{args.port}")
    print("-" * 40)
    print(f"🔗 Connect Twin with:")
    print(f"   python main.py --source http://{ip_addr}:{args.port}")
    print("-" * 40)
    print("Press Ctrl+C to stop")
    print()
    
    # FFmpeg command for HTTP streaming
    cmd = [
        'ffmpeg',
        '-f', 'pulse',
        '-i', args.device,
        '-acodec', 'pcm_s16le',
        '-ar', '16000',
        '-ac', '1',
        '-f', 'wav',
        '-listen', '1',
        f'http://0.0.0.0:{args.port}'
    ]
    
    print(f"🔧 Starting FFmpeg...")
    
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