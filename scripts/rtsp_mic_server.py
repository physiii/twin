#!/usr/bin/env python3
"""
Audio Streaming Server for Twin Voice Assistant

This script captures audio from the local microphone using PipeWire/PulseAudio
and streams it via HTTP or UDP for consumption by Twin's voice processing system.

Usage:
    python rtsp_mic_server.py [options]

Requirements:
    - FFmpeg with HTTP/UDP support
    - PipeWire or PulseAudio
    - Python 3.6+
"""

import subprocess
import sys
import os
import time
import signal
import argparse
import logging
from typing import Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class AudioStreamingServer:
    def __init__(self, port: int = 8554, audio_device: str = "default", 
                 sample_rate: int = 16000, channels: int = 1, use_udp: bool = False):
        self.port = port
        self.audio_device = audio_device
        self.sample_rate = sample_rate
        self.channels = channels
        self.use_udp = use_udp
        self.ffmpeg_process: Optional[subprocess.Popen] = None
        self.running = False
        
    def check_dependencies(self) -> bool:
        """Check if required dependencies are available"""
        try:
            # Check FFmpeg
            result = subprocess.run(['ffmpeg', '-version'], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode != 0:
                logger.error("FFmpeg not found or not working")
                return False
            logger.info(f"✅ FFmpeg found: {result.stdout.split()[2]}")
            
            # Check audio system
            audio_systems = ['pipewire', 'pulseaudio']
            audio_found = False
            
            for system in audio_systems:
                try:
                    result = subprocess.run(['which', system], 
                                          capture_output=True, timeout=5)
                    if result.returncode == 0:
                        logger.info(f"✅ Audio system found: {system}")
                        audio_found = True
                        break
                except subprocess.TimeoutExpired:
                    continue
            
            if not audio_found:
                logger.warning("⚠️ No audio system detected, but continuing anyway")
            
            return True
            
        except subprocess.TimeoutExpired:
            logger.error("❌ Dependency check timed out")
            return False
        except Exception as e:
            logger.error(f"❌ Error checking dependencies: {e}")
            return False
    
    def check_audio_device(self) -> bool:
        """Check if the specified audio device exists"""
        if self.audio_device == "default":
            return True  # "default" should always work
        
        try:
            # Test by trying to open the device briefly
            test_cmd = [
                'ffmpeg', '-f', 'pulse', '-i', self.audio_device,
                '-t', '0.1', '-f', 'null', '-'
            ]
            
            result = subprocess.run(test_cmd, capture_output=True, text=True, timeout=5)
            
            # If FFmpeg can read from the device for even 0.1 seconds, it exists
            if result.returncode == 0:
                return True
            
            # Check the error message for device-related issues
            if "No such file or directory" in result.stderr or "does not exist" in result.stderr:
                logger.error(f"❌ Audio device '{self.audio_device}' not found")
                self.list_audio_devices()
                return False
            
            # Other errors might be temporary, so we'll proceed
            logger.warning(f"⚠️ Audio device test failed but continuing: {result.stderr}")
            return True
            
        except subprocess.TimeoutExpired:
            logger.warning("⚠️ Audio device test timed out, continuing anyway")
            return True
        except Exception as e:
            logger.warning(f"⚠️ Could not test audio device, continuing anyway: {e}")
            return True

    def list_audio_devices(self) -> None:
        """List available audio input devices"""
        logger.info("🎤 Available audio input devices:")
        
        try:
            # Try PipeWire/PulseAudio first
            result = subprocess.run(['pactl', 'list', 'short', 'sources'], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0 and result.stdout.strip():
                logger.info("PulseAudio/PipeWire sources:")
                for line in result.stdout.strip().split('\n'):
                    parts = line.split('\t')
                    if len(parts) >= 2:
                        logger.info(f"  📱 {parts[1]}")
        except:
            pass
        
        try:
            # Also try FFmpeg device listing
            result = subprocess.run(['ffmpeg', '-f', 'pulse', '-list_devices', 'true', '-i', 'dummy'], 
                                  capture_output=True, text=True, timeout=10)
            if "Input devices:" in result.stderr:
                logger.info("FFmpeg PulseAudio devices:")
                lines = result.stderr.split('\n')
                in_input_section = False
                for line in lines:
                    if "Input devices:" in line:
                        in_input_section = True
                        continue
                    elif "Output devices:" in line:
                        break
                    elif in_input_section and "[pulse]" in line:
                        logger.info(f"  🎙️  {line.strip()}")
        except:
            pass
    
    def build_ffmpeg_command(self) -> list:
        """Build the FFmpeg command for audio streaming"""
        if self.use_udp:
            # Simple UDP streaming - direct raw audio
            cmd = [
                'ffmpeg',
                '-f', 'pulse',  # Use PulseAudio/PipeWire input
                '-i', self.audio_device,  # Audio device
                '-acodec', 'pcm_s16le',  # Audio codec
                '-ar', str(self.sample_rate),  # Sample rate
                '-ac', str(self.channels),  # Number of channels
                '-f', 'wav',  # WAV format for compatibility
                f'udp://0.0.0.0:{self.port}'  # UDP streaming
            ]
        else:
            # HTTP Live Streaming (HLS) - more reliable than RTSP
            cmd = [
                'ffmpeg',
                '-f', 'pulse',  # Use PulseAudio/PipeWire input
                '-i', self.audio_device,  # Audio device
                '-acodec', 'pcm_s16le',  # Audio codec
                '-ar', str(self.sample_rate),  # Sample rate
                '-ac', str(self.channels),  # Number of channels
                '-f', 'wav',  # WAV format
                '-listen', '1',  # Listen for HTTP connections
                f'http://0.0.0.0:{self.port}/audio.wav'  # HTTP URL
            ]
        
        return cmd
    
    def start_server(self) -> bool:
        """Start the audio streaming server"""
        if self.running:
            logger.warning("Server is already running")
            return False
        
        # Check audio device first
        if not self.check_audio_device():
            return False
        
        protocol = "UDP" if self.use_udp else "HTTP"
        logger.info(f"🚀 Starting {protocol} audio streaming server on port {self.port}")
        
        if self.use_udp:
            logger.info(f"📡 Stream URL: udp://localhost:{self.port}")
        else:
            logger.info(f"📡 Stream URL: http://localhost:{self.port}/audio.wav")
            
        logger.info(f"🎤 Audio device: {self.audio_device}")
        logger.info(f"📊 Sample rate: {self.sample_rate}Hz, Channels: {self.channels}")
        
        cmd = self.build_ffmpeg_command()
        logger.debug(f"FFmpeg command: {' '.join(cmd)}")
        
        try:
            self.ffmpeg_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            
            # Give FFmpeg a moment to start
            time.sleep(2)
            
            # Check if process is still running
            if self.ffmpeg_process.poll() is None:
                self.running = True
                logger.info(f"✅ {protocol} audio server started successfully")
                
                if self.use_udp:
                    logger.info(f"🔗 Connect Twin with: --source udp://your_ip:{self.port}")
                else:
                    logger.info(f"🔗 Connect Twin with: --source http://your_ip:{self.port}/audio.wav")
                return True
            else:
                stdout, stderr = self.ffmpeg_process.communicate()
                logger.error("❌ FFmpeg failed to start")
                logger.error(f"Stdout: {stdout}")
                logger.error(f"Stderr: {stderr}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error starting server: {e}")
            return False
    
    def stop_server(self) -> None:
        """Stop the audio streaming server"""
        if not self.running:
            return
        
        logger.info("🛑 Stopping audio streaming server...")
        
        if self.ffmpeg_process:
            try:
                self.ffmpeg_process.terminate()
                
                # Wait for graceful shutdown
                try:
                    self.ffmpeg_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    logger.warning("FFmpeg didn't terminate gracefully, forcing kill")
                    self.ffmpeg_process.kill()
                    self.ffmpeg_process.wait()
                
                logger.info("✅ Audio streaming server stopped")
            except Exception as e:
                logger.error(f"Error stopping server: {e}")
        
        self.running = False
        self.ffmpeg_process = None
    
    def run(self) -> None:
        """Run the server with signal handling"""
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}")
            self.stop_server()
            sys.exit(0)
        
        # Set up signal handlers
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        if not self.check_dependencies():
            logger.error("❌ Dependency check failed")
            sys.exit(1)
        
        if not self.start_server():
            logger.error("❌ Failed to start server")
            sys.exit(1)
        
        try:
            # Monitor the FFmpeg process
            while self.running:
                if self.ffmpeg_process and self.ffmpeg_process.poll() is not None:
                    stdout, stderr = self.ffmpeg_process.communicate()
                    logger.error("❌ FFmpeg process died unexpectedly")
                    logger.error(f"Stdout: {stdout}")
                    logger.error(f"Stderr: {stderr}")
                    break
                
                time.sleep(1)
        
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        finally:
            self.stop_server()

def main():
    parser = argparse.ArgumentParser(
        description="Audio Streaming Server for Twin Voice Assistant",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python rtsp_mic_server.py                    # Use defaults (HTTP)
  python rtsp_mic_server.py --port 8555        # Custom port
  python rtsp_mic_server.py --device pulse     # Specific device
  python rtsp_mic_server.py --udp              # Use UDP streaming
  python rtsp_mic_server.py --list-devices     # List audio devices
  
Connect to Twin:
  python main.py --source http://localhost:8554/audio.wav
  python main.py --source udp://localhost:8554  # for UDP mode
        """
    )
    
    parser.add_argument(
        '--port', '-p',
        type=int,
        default=8554,
        help='Audio streaming server port (default: 8554)'
    )
    
    parser.add_argument(
        '--device', '-d',
        type=str,
        default='default',
        help='Audio input device (default: "default")'
    )
    
    parser.add_argument(
        '--sample-rate', '-r',
        type=int,
        default=16000,
        help='Audio sample rate (default: 16000)'
    )
    
    parser.add_argument(
        '--channels', '-c',
        type=int,
        default=1,
        help='Number of audio channels (default: 1)'
    )
    
    parser.add_argument(
        '--list-devices', '-l',
        action='store_true',
        help='List available audio devices and exit'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    
    parser.add_argument(
        '--udp', '-u',
        action='store_true',
        help='Use UDP streaming instead of HTTP streaming'
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Create server instance
    server = AudioStreamingServer(
        port=args.port,
        audio_device=args.device,
        sample_rate=args.sample_rate,
        channels=args.channels,
        use_udp=args.udp
    )
    
    if args.list_devices:
        server.list_audio_devices()
        return
    
    logger.info("🤖 Twin Audio Streaming Server")
    logger.info("=" * 40)
    
    server.run()

if __name__ == "__main__":
    main() 