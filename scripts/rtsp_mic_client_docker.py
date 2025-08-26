#!/usr/bin/env python3
"""
RTSP Microphone Client - Docker Optimized Version
Streams microphone audio to RTSP server from within Docker containers
"""

import subprocess
import os
import time
import signal
import sys
import logging
import socket

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class DockerRTSPMicClient:
    def __init__(self):
        # Get configuration from environment variables
        self.rtsp_server_ip = os.getenv('RTSP_SERVER_IP', '127.0.0.1')
        self.rtsp_server_port = int(os.getenv('RTSP_SERVER_PORT', '8554'))
        self.stream_path = os.getenv('STREAM_PATH', 'mic')
        self.audio_device = os.getenv('AUDIO_DEVICE', 'default')
        self.sample_rate = int(os.getenv('SAMPLE_RATE', '16000'))
        self.channels = int(os.getenv('CHANNELS', '1'))
        
        self.ffmpeg_process = None
        self.running = False
        
        # Signal handling for clean shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        # Resolve default PulseAudio source to an explicit device name when possible
        self.audio_device = self._resolve_pulseaudio_source(self.audio_device)

    def _resolve_pulseaudio_source(self, desired_device: str) -> str:
        """Resolve 'default' to the actual PulseAudio default source name if available."""
        try:
            # If user provided a specific device, keep it
            if desired_device and desired_device != 'default':
                return desired_device

            # Query default source name
            result = subprocess.run(['pactl', 'get-default-source'], capture_output=True, text=True, timeout=3)
            if result.returncode == 0:
                name = result.stdout.strip()
                if name:
                    logger.info(f"✅ Using PulseAudio default source: {name}")
                    return name
        except Exception as e:
            logger.debug(f"Could not resolve default PulseAudio source: {e}")
        # Fallback
        logger.info("ℹ️ Using PulseAudio source: default")
        return desired_device
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        logger.info(f"Received signal {signum}, shutting down...")
        self.stop()
        sys.exit(0)
    
    def check_audio_system(self) -> bool:
        """Check if the audio system is accessible"""
        try:
            # Check if PulseAudio is running
            result = subprocess.run(
                ['pactl', 'info'],
                capture_output=True, text=True, timeout=5
            )
            
            if result.returncode == 0:
                logger.info("✅ PulseAudio is accessible")
                return True
            else:
                logger.error("❌ PulseAudio not accessible")
                return False
                
        except subprocess.TimeoutExpired:
            logger.error("Timeout checking audio system")
            return False
        except FileNotFoundError:
            logger.error("pactl not found")
            return False
        except Exception as e:
            logger.error(f"Error checking audio system: {e}")
            return False
    
    def list_audio_devices(self):
        """List available audio devices"""
        try:
            result = subprocess.run(
                ['pactl', 'list', 'short', 'sources'],
                capture_output=True, text=True, timeout=5
            )
            
            if result.returncode == 0:
                logger.info("Available audio sources:")
                sources = result.stdout.strip().split('\n')
                for source in sources:
                    if source.strip():
                        logger.info(f"  {source}")
                
                # Check if our device exists
                for source in sources:
                    if self.audio_device in source:
                        logger.info(f"✅ Audio device '{self.audio_device}' found")
                        return True
                
                logger.warning(f"⚠️  Audio device '{self.audio_device}' not found")
                return False
            else:
                logger.error("Failed to list audio sources")
                return False
                
        except Exception as e:
            logger.error(f"Error listing audio devices: {e}")
            return False
    
    def build_ffmpeg_command(self) -> list:
        """Build the FFmpeg command for streaming audio to RTSP server"""
        # Capture from PulseAudio source. If user provided a '.monitor' device, use it as-is.
        # Otherwise, use the device name directly (e.g., 'default' or 'alsa_input.*').
        pulse_input = self.audio_device if self.audio_device.endswith('.monitor') else self.audio_device

        # Prefer G.711 mu-law at 8kHz for near-zero codec delay; fall back to PCM if a different
        # sample rate is requested.
        use_mulaw = self.sample_rate == 8000 and self.channels == 1

        cmd = [
            'ffmpeg',
            # Input: PulseAudio source with a small queue to avoid input-side backpressure
            '-f', 'pulse',
            '-thread_queue_size', '1024',
            '-i', pulse_input,
            # Audio settings
            '-ac', str(self.channels),
            '-ar', str(self.sample_rate),
            '-c:a', 'pcm_mulaw' if use_mulaw else 'pcm_s16le',
            # Minimize internal buffering and use wallclock timestamps
            '-use_wallclock_as_timestamps', '1',
            '-reorder_queue_size', '0',
            '-max_delay', '0',
            '-probesize', '32',
            '-analyzeduration', '0',
            # Output: RTSP over UDP with low-latency flags
            '-f', 'rtsp',
            '-rtsp_transport', 'udp',
            '-flags', 'low_delay',
            '-flush_packets', '1',
            '-max_interleave_delta', '0',
            '-loglevel', 'error',
            f'rtsp://{self.rtsp_server_ip}:{self.rtsp_server_port}/{self.stream_path}'
        ]
        
        return cmd
    
    def test_rtsp_connection(self) -> bool:
        """Test connectivity to RTSP server"""
        try:
            # Try to connect to the RTSP server
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex((self.rtsp_server_ip, self.rtsp_server_port))
            sock.close()
            
            if result == 0:
                logger.info(f"✅ RTSP server {self.rtsp_server_ip}:{self.rtsp_server_port} is reachable")
                return True
            else:
                logger.error(f"❌ Cannot connect to RTSP server {self.rtsp_server_ip}:{self.rtsp_server_port}")
                return False
                
        except Exception as e:
            logger.error(f"Error testing RTSP connection: {e}")
            return False
    
    def start_streaming(self) -> bool:
        """Start the audio streaming client"""
        if self.running:
            logger.warning("Client is already running")
            return False
        
        logger.info(f"🎤 Starting Docker RTSP microphone client...")
        logger.info(f"   RTSP Server: {self.rtsp_server_ip}:{self.rtsp_server_port}")
        logger.info(f"   Stream path: {self.stream_path}")
        logger.info(f"   Audio device: {self.audio_device}")
        logger.info(f"   Sample rate: {self.sample_rate}Hz")
        logger.info(f"   Channels: {self.channels}")
        
        # Check audio system
        if not self.check_audio_system():
            logger.error("Audio system check failed")
            return False
        
        # List audio devices
        if not self.list_audio_devices():
            logger.warning("Audio device not found, but continuing...")
        
        # Test RTSP connection
        if not self.test_rtsp_connection():
            logger.error("RTSP connection test failed")
            return False
        
        logger.info("-" * 50)
        logger.info(f"✅ Streaming to: rtsp://{self.rtsp_server_ip}:{self.rtsp_server_port}/{self.stream_path}")
        logger.info("-" * 50)
        
        # Debug: Log the actual FFmpeg command
        ffmpeg_cmd = self.build_ffmpeg_command()
        logger.info(f"🔧 FFmpeg command: {' '.join(ffmpeg_cmd)}")
        
        try:
            self.ffmpeg_process = subprocess.Popen(
                ffmpeg_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            
            # Wait a moment to see if FFmpeg starts successfully
            time.sleep(3)
            
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

def main():
    logger.info("🐳 Docker RTSP Microphone Client Starting...")
    
    # Create and start client
    client = DockerRTSPMicClient()
    
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
