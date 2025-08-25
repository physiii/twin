#!/usr/bin/env python3
"""
RTSP Microphone Client - Streams microphone audio to RTSP server
Runs on Ubuntu machines to provide room-specific audio feeds
"""

import subprocess
import argparse
import socket
import time
import signal
import sys
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class RTSPMicClient:
    def __init__(self, rtsp_server_ip: str, rtsp_server_port: int = 8554, 
                 stream_path: str = "mic", audio_device: str = "default",
                 sample_rate: int = 16000, channels: int = 1):
        self.rtsp_server_ip = rtsp_server_ip
        self.rtsp_server_port = rtsp_server_port
        self.stream_path = stream_path
        self.audio_device = audio_device
        self.sample_rate = sample_rate
        self.channels = channels
        
        self.ffmpeg_process = None
        self.running = False
        
        # Signal handling for clean shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        logger.info(f"Received signal {signum}, shutting down...")
        self.stop()
        sys.exit(0)
    
    def check_audio_device(self) -> bool:
        """Check if the specified audio device is available"""
        try:
            # Use pactl to list audio devices (PipeWire/PulseAudio)
            result = subprocess.run(
                ['pactl', 'list', 'short', 'sources'],
                capture_output=True, text=True, timeout=5
            )
            
            if result.returncode == 0:
                sources = result.stdout.strip().split('\n')
                logger.info("Available audio sources:")
                for source in sources:
                    if source.strip():
                        logger.info(f"  {source}")
                
                # Check if our device exists
                for source in sources:
                    if self.audio_device in source:
                        logger.info(f"✅ Audio device '{self.audio_device}' found")
                        return True
                
                logger.warning(f"⚠️  Audio device '{self.audio_device}' not found")
                logger.info("Available devices:")
                for source in sources:
                    if source.strip():
                        parts = source.split('\t')
                        if len(parts) >= 2:
                            logger.info(f"  {parts[1]}")
                return False
            else:
                logger.error("Failed to list audio sources")
                return False
                
        except subprocess.TimeoutExpired:
            logger.error("Timeout checking audio devices")
            return False
        except FileNotFoundError:
            logger.error("pactl not found. Install pulseaudio-utils or use different audio system")
            return False
        except Exception as e:
            logger.error(f"Error checking audio devices: {e}")
            return False
    
    def build_ffmpeg_command(self) -> list:
        """Build the FFmpeg command for streaming audio to RTSP server"""
        # Use pulseaudio input with monitor source to avoid blocking other apps
        # This creates a copy of the audio stream without interfering with the original
        
        # First, try to find a monitor source for our device
        monitor_source = f"{self.audio_device}.monitor"
        
        cmd = [
            'ffmpeg',
            '-f', 'pulse',
            '-i', monitor_source,  # Use monitor source to avoid blocking
            '-acodec', 'pcm_s16le',  # PCM 16-bit little-endian
            '-ar', str(self.sample_rate),  # Sample rate
            '-ac', str(self.channels),  # Number of channels
            '-f', 'rtsp',
            '-rtsp_transport', 'tcp',  # Use TCP for better reliability
            '-loglevel', 'error',  # Reduce log noise
            f'rtsp://{self.rtsp_server_ip}:{self.rtsp_server_port}/{self.stream_path}'
        ]
        
        return cmd
    
    def start_streaming(self) -> bool:
        """Start the audio streaming client"""
        if self.running:
            logger.warning("Client is already running")
            return False
        
        # Check audio device first
        if not self.check_audio_device():
            logger.error("Audio device check failed")
            return False
        
        # Get local IP address for logging
        try:
            # Get primary IP address
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
        except Exception:
            local_ip = "127.0.0.1"
        
        logger.info(f"🎤 Starting microphone streaming client...")
        logger.info(f"   Local IP: {local_ip}")
        logger.info(f"   Audio device: {self.audio_device}")
        logger.info(f"   RTSP Server: {self.rtsp_server_ip}:{self.rtsp_server_port}")
        logger.info(f"   Stream path: {self.stream_path}")
        logger.info(f"   Sample rate: {self.sample_rate}Hz")
        logger.info(f"   Channels: {self.channels}")
        logger.info("-" * 50)
        logger.info(f"✅ Streaming to: rtsp://{self.rtsp_server_ip}:{self.rtsp_server_port}/{self.stream_path}")
        logger.info("-" * 50)
        logger.info("ℹ️  This client uses monitor sources, so other apps can still use the microphone")
        
        try:
            self.ffmpeg_process = subprocess.Popen(
                self.build_ffmpeg_command(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            
            # Wait a moment to see if FFmpeg starts successfully
            time.sleep(2)
            
            if self.ffmpeg_process.poll() is None:
                self.running = True
                logger.info("✅ Streaming started successfully")
                
                # Start monitoring thread
                self._monitor_stream()
                return True
            else:
                # FFmpeg process exited
                stdout, stderr = self.ffmpeg_process.communicate()
                logger.error(f"FFmpeg process failed to start")
                logger.error(f"stdout: {stdout}")
                logger.error(f"stderr: {stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to start streaming: {e}")
            return False
    
    def _monitor_stream(self):
        """Monitor the streaming process"""
        try:
            while self.running and self.ffmpeg_process:
                if self.ffmpeg_process.poll() is not None:
                    logger.warning("FFmpeg process stopped unexpectedly")
                    self.running = False
                    break
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Monitoring interrupted")
        finally:
            self.stop()
    
    def stop(self):
        """Stop the streaming client"""
        if not self.running:
            return
        
        logger.info("Stopping streaming client...")
        self.running = False
        
        if self.ffmpeg_process:
            try:
                self.ffmpeg_process.terminate()
                self.ffmpeg_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning("FFmpeg process didn't terminate gracefully, forcing...")
                self.ffmpeg_process.kill()
            except Exception as e:
                logger.error(f"Error stopping FFmpeg: {e}")
            finally:
                self.ffmpeg_process = None
        
        logger.info("Streaming client stopped")

def list_audio_devices():
    """List available audio devices"""
    try:
        result = subprocess.run(
            ['pactl', 'list', 'short', 'sources'],
            capture_output=True, text=True, timeout=5
        )
        
        if result.returncode == 0:
            print("\n🎤 Available Audio Sources:")
            print("=" * 50)
            sources = result.stdout.strip().split('\n')
            for i, source in enumerate(sources):
                if source.strip():
                    parts = source.split('\t')
                    if len(parts) >= 2:
                        device_id = parts[0]
                        device_name = parts[1]
                        print(f"{i+1:2d}. {device_name} (ID: {device_id})")
                        # Show monitor source if available
                        monitor_name = f"{device_name}.monitor"
                        print(f"    Monitor: {monitor_name}")
            print()
        else:
            print("❌ Failed to list audio sources")
            
    except Exception as e:
        print(f"❌ Error listing audio devices: {e}")

def main():
    parser = argparse.ArgumentParser(
        description="RTSP Microphone Client - Stream microphone audio to RTSP server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Stream to default RTSP server
  python3 rtsp_mic_client.py --server 192.168.1.40

  # Stream to specific room with custom device
  python3 rtsp_mic_client.py --server 192.168.1.40 --device "USB Microphone" --path office

  # List available audio devices
  python3 rtsp_mic_client.py --list-devices

  # Stream with custom audio settings
  python3 rtsp_mic_client.py --server 192.168.1.40 --sample-rate 44100 --channels 2
        """
    )
    
    parser.add_argument(
        '--server', '-s',
        required=True,
        help='RTSP server IP address'
    )
    
    parser.add_argument(
        '--port', '-p',
        type=int,
        default=8554,
        help='RTSP server port (default: 8554)'
    )
    
    parser.add_argument(
        '--path', '-P',
        default='mic',
        help='Stream path on RTSP server (default: mic)'
    )
    
    parser.add_argument(
        '--device', '-d',
        default='default',
        help='Audio device name (default: default)'
    )
    
    parser.add_argument(
        '--sample-rate', '-r',
        type=int,
        default=16000,
        help='Audio sample rate in Hz (default: 16000)'
    )
    
    parser.add_argument(
        '--channels', '-c',
        type=int,
        default=1,
        choices=[1, 2],
        help='Number of audio channels (default: 1)'
    )
    
    parser.add_argument(
        '--list-devices', '-l',
        action='store_true',
        help='List available audio devices and exit'
    )
    
    args = parser.parse_args()
    
    if args.list_devices:
        list_audio_devices()
        return
    
    # Validate arguments
    if args.sample_rate not in [8000, 16000, 22050, 44100, 48000]:
        logger.warning(f"Sample rate {args.sample_rate}Hz may not be optimal. Recommended: 16000Hz")
    
    if args.channels == 2 and args.sample_rate > 22050:
        logger.warning(f"High sample rate ({args.sample_rate}Hz) with stereo may cause high bandwidth usage")
    
    # Create and start client
    client = RTSPMicClient(
        rtsp_server_ip=args.server,
        rtsp_server_port=args.port,
        stream_path=args.path,
        audio_device=args.device,
        sample_rate=args.sample_rate,
        channels=args.channels
    )
    
    try:
        if client.start_streaming():
            logger.info("Client running. Press Ctrl+C to stop.")
            # Keep main thread alive
            while client.running:
                time.sleep(1)
        else:
            logger.error("Failed to start client")
            sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        client.stop()

if __name__ == "__main__":
    main()

