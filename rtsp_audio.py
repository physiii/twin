import subprocess
import numpy as np
import threading
import queue
import logging
import time
import os
import config
from collections import deque

logger = logging.getLogger("twin")

class RTSPAudioCapture:
    """
    Captures audio from an RTSP stream using FFmpeg
    and provides a callback-based interface similar to sounddevice
    """
    
    def __init__(
        self, 
        rtsp_url, 
        sample_rate=48000, 
        channels=1,
        chunk_size=1024,
        buffer_size=144000,  # 3 seconds at 48kHz
        latency_flags=None
    ):
        self.rtsp_url = rtsp_url
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_size = chunk_size
        self.buffer = deque(maxlen=buffer_size)
        self.audio_queue = queue.Queue()
        self.is_running = False
        self.process = None
        self.capture_thread = None
        self.callback_thread = None
        self.user_callback = None
        self.latency_flags = latency_flags or []
        
    def _build_ffmpeg_command(self):
        """Build the FFmpeg command to extract audio from RTSP stream"""
        cmd = ['ffmpeg']
        
        # Add low-latency flags if specified
        if isinstance(self.latency_flags, str):
            # If it's a string, split it into arguments
            for flag in self.latency_flags.split():
                cmd.append(flag)
        elif isinstance(self.latency_flags, list):
            # If it's already a list, extend with it
            cmd.extend(self.latency_flags)
            
        # Input URL
        cmd.extend(['-i', self.rtsp_url])
        
        # Output format settings
        cmd.extend([
            '-vn',  # No video
            '-acodec', 'pcm_f32le',  # 32-bit float PCM
            '-ar', str(self.sample_rate),  # Sample rate
            '-ac', str(self.channels),  # Number of channels
            '-f', 'f32le',  # 32-bit float format
            'pipe:1'  # Output to stdout
        ])
        
        logger.info(f"FFmpeg command: {' '.join(cmd)}")
        return cmd
        
    def _capture_audio(self):
        """Capture audio from FFmpeg and put in queue"""
        cmd = self._build_ffmpeg_command()
        
        try:
            logger.info(f"Starting FFmpeg process with command: {' '.join(cmd)}")
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=self.chunk_size * 4  # 4 bytes per float32 sample
            )
            
            logger.info("Started FFmpeg RTSP audio capture process")
            
            # Start a thread to log stderr from FFmpeg
            def log_stderr():
                for line in iter(self.process.stderr.readline, b''):
                    stderr_line = line.decode('utf-8', errors='replace').strip()
                    if stderr_line:
                        logger.debug(f"FFmpeg: {stderr_line}")
            
            stderr_thread = threading.Thread(target=log_stderr)
            stderr_thread.daemon = True
            stderr_thread.start()
            
            # Read audio data in chunks
            bytes_per_chunk = self.chunk_size * self.channels * 4  # 4 bytes per float32 sample
            
            while self.is_running:
                try:
                    # Read a chunk of audio data
                    audio_chunk = self.process.stdout.read(bytes_per_chunk)
                    
                    if not audio_chunk:
                        logger.warning("End of RTSP stream or error. Restarting in 2 seconds...")
                        # Log FFmpeg return code
                        if self.process.poll() is not None:
                            logger.error(f"FFmpeg process exited with code {self.process.poll()}")
                        time.sleep(2)
                        break
                    
                    # Convert to numpy array of float32
                    audio_array = np.frombuffer(audio_chunk, dtype=np.float32)
                    
                    # Log audio data stats occasionally
                    if hasattr(self, 'log_counter'):
                        self.log_counter += 1
                    else:
                        self.log_counter = 0
                        
                    # if self.log_counter % 100 == 0:  # Log every 100 chunks
                    #     logger.info(f"RTSP audio stats: min={np.min(audio_array):.4f}, max={np.max(audio_array):.4f}, mean={np.mean(audio_array):.4f}, shape={audio_array.shape}")
                    
                    # Put in the queue for the callback thread
                    self.audio_queue.put(audio_array)
                    
                except Exception as e:
                    logger.error(f"Error reading RTSP audio: {e}")
                    time.sleep(0.5)
                    
        except Exception as e:
            logger.error(f"Error starting FFmpeg process: {e}")
        finally:
            self._cleanup()
            
    def _callback_processor(self):
        """Process audio chunks and call the user callback"""
        while self.is_running:
            try:
                # Get audio chunk from queue
                audio_array = self.audio_queue.get(timeout=1)
                
                # Add to buffer
                for sample in audio_array:
                    self.buffer.append(sample)
                
                # If there's a callback, call it
                if self.user_callback:
                    # sounddevice callback format: callback(indata, frames, time, status)
                    indata = np.array(list(self.buffer)[-self.chunk_size:]).reshape(-1, self.channels)
                    self.user_callback(indata, self.chunk_size, {'current_time': time.time()}, None)
                    
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error in callback processor: {e}")
                
    def _cleanup(self):
        """Clean up resources"""
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except:
                try:
                    self.process.kill()
                except:
                    pass
                    
        self.process = None
        
    def start(self, callback):
        """Start audio capture with the given callback"""
        if self.is_running:
            return
            
        self.is_running = True
        self.user_callback = callback
        
        # Start the capture thread
        self.capture_thread = threading.Thread(target=self._capture_audio)
        self.capture_thread.daemon = True
        self.capture_thread.start()
        
        # Start the callback processor thread
        self.callback_thread = threading.Thread(target=self._callback_processor)
        self.callback_thread.daemon = True
        self.callback_thread.start()
        
        logger.info("RTSP audio capture started")
        
    def stop(self):
        """Stop audio capture"""
        self.is_running = False
        
        if self.capture_thread:
            self.capture_thread.join(timeout=2)
            self.capture_thread = None
            
        if self.callback_thread:
            self.callback_thread.join(timeout=2)
            self.callback_thread = None
            
        self._cleanup()
        logger.info("RTSP audio capture stopped")

def create_rtsp_audio_stream(callback_func, rtsp_url=None):
    """
    Create an RTSP audio stream with the specified callback.
    This mimics the sounddevice.InputStream interface for easy integration.
    """
    rtsp_url = rtsp_url or config.RTSP_URL
    sample_rate = config.SAMPLE_RATE
    channels = config.CHANNELS
    chunk_size = config.CHUNK_SIZE
    latency_flags = config.RTSP_LATENCY_FLAGS
    
    logger.info(f"Creating RTSP audio capture with URL: {rtsp_url}")
    
    stream = RTSPAudioCapture(
        rtsp_url=rtsp_url,
        sample_rate=sample_rate,
        channels=channels,
        chunk_size=chunk_size,
        latency_flags=latency_flags
    )
    
    stream.start(callback_func)
    return stream 