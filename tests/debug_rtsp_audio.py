import numpy as np
import os
import time
import logging
import subprocess
import json
import asyncio
from collections import deque
import config
import argparse
import soundfile as sf
import rtsp_audio
from audio import audio_callback as orig_audio_callback

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] [%(levelname)s] [%(filename)s] %(message)s")
logger = logging.getLogger("debug_rtsp")

# Create test directories
os.makedirs("debug_audio", exist_ok=True)

class DebugAudioCapture:
    """Debug wrapper for RTSP audio capture that saves intermediate files"""
    
    def __init__(self, duration=10, interval=1):
        self.duration = duration
        self.interval = interval
        self.sample_rate = config.SAMPLE_RATE
        self.channels = config.CHANNELS
        self.rtsp_url = config.RTSP_URL
        self.latency_flags = config.RTSP_LATENCY_FLAGS
        self.raw_buffer = deque(maxlen=int(self.sample_rate * self.duration))
        self.processed_buffer = deque(maxlen=int(self.sample_rate * self.duration))
        self.last_save_time = 0
        
    def debug_audio_callback(self, indata, frames, time_info, status):
        """Custom callback that saves the raw input data"""
        # Save raw input data
        audio_data = indata.copy()
        flattened = indata[:, 0] if indata.shape[1] > 1 else indata.flatten()
        
        # Add to raw buffer
        for sample in flattened:
            self.raw_buffer.append(sample)
            
        # Call original callback with a mock audio queue and buffers
        mock_audio_queue = deque(maxlen=1000)
        mock_audio_buffer = deque(maxlen=int(self.sample_rate * 3))
        mock_small_buffer = deque(maxlen=int(self.sample_rate * 0.2))
        
        orig_audio_callback(indata, frames, time_info, status, 
                           mock_audio_queue, mock_audio_buffer, mock_small_buffer)
        
        # Save the processed data
        for item in mock_audio_buffer:
            self.processed_buffer.append(item)
            
        # Periodically save snapshots
        current_time = time.time()
        if current_time - self.last_save_time >= self.interval:
            self.save_snapshots()
            self.last_save_time = current_time
    
    def save_snapshots(self):
        """Save snapshots of the raw and processed audio buffers"""
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        
        # Save raw audio
        if self.raw_buffer:
            raw_data = np.array(list(self.raw_buffer), dtype=np.float32)
            raw_file = f"debug_audio/raw_{timestamp}.wav"
            sf.write(raw_file, raw_data, self.sample_rate)
            logger.info(f"Saved raw audio: {raw_file}")
            
            # Calculate stats
            rms = np.sqrt(np.mean(np.square(raw_data)))
            logger.info(f"Raw audio stats: min={np.min(raw_data):.4f}, max={np.max(raw_data):.4f}, mean={np.mean(raw_data):.4f}, rms={rms:.6f}")
        
        # Save processed audio
        if self.processed_buffer:
            proc_data = np.array(list(self.processed_buffer), dtype=np.float32)
            proc_file = f"debug_audio/processed_{timestamp}.wav"
            sf.write(proc_file, proc_data, self.sample_rate)
            logger.info(f"Saved processed audio: {proc_file}")
            
            # Calculate stats
            rms = np.sqrt(np.mean(np.square(proc_data)))
            logger.info(f"Processed audio stats: min={np.min(proc_data):.4f}, max={np.max(proc_data):.4f}, mean={np.mean(proc_data):.4f}, rms={rms:.6f}")
    
    def save_ffmpeg_direct(self, duration):
        """Save audio directly from FFmpeg for comparison"""
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        output_file = f"debug_audio/ffmpeg_direct_{timestamp}.wav"
        
        cmd = ['ffmpeg']
        
        # Add low-latency flags if specified
        if isinstance(self.latency_flags, str):
            for flag in self.latency_flags.split():
                cmd.append(flag)
        elif isinstance(self.latency_flags, list):
            cmd.extend(self.latency_flags)
            
        # Input URL
        cmd.extend(['-i', self.rtsp_url])
        
        # Output format settings - save directly to WAV
        cmd.extend([
            '-vn',                          # No video
            '-acodec', 'pcm_s16le',         # 16-bit PCM for WAV
            '-ar', str(self.sample_rate),   # Sample rate
            '-ac', str(self.channels),      # Number of channels
            '-t', str(duration),            # Duration
            '-y',                           # Overwrite output file
            output_file                     # Output file
        ])
        
        logger.info(f"Running direct FFmpeg capture: {' '.join(cmd)}")
        try:
            subprocess.run(cmd, check=True)
            logger.info(f"Direct FFmpeg audio saved to: {output_file}")
            
            # Load and analyze the file
            try:
                audio_data, _ = sf.read(output_file)
                rms = np.sqrt(np.mean(np.square(audio_data)))
                logger.info(f"Direct FFmpeg audio stats: min={np.min(audio_data):.4f}, max={np.max(audio_data):.4f}, mean={np.mean(audio_data):.4f}, rms={rms:.6f}")
            except Exception as e:
                logger.error(f"Error analyzing direct FFmpeg file: {e}")
                
        except subprocess.CalledProcessError as e:
            logger.error(f"Error running direct FFmpeg capture: {e}")

async def main():
    parser = argparse.ArgumentParser(description="Debug RTSP audio capture")
    parser.add_argument("--duration", type=int, default=30, help="Recording duration in seconds")
    parser.add_argument("--interval", type=int, default=5, help="Interval between saving snapshots")
    parser.add_argument("--ffmpeg", action="store_true", help="Also save direct FFmpeg capture")
    args = parser.parse_args()
    
    # Create the debug capturer
    debug_capture = DebugAudioCapture(duration=args.duration, interval=args.interval)
    
    # If requested, do a direct FFmpeg capture first
    if args.ffmpeg:
        debug_capture.save_ffmpeg_direct(min(args.duration, 5))  # Cap at 5 seconds
    
    # Create the RTSP audio capturer
    stream = rtsp_audio.RTSPAudioCapture(
        rtsp_url=debug_capture.rtsp_url,
        sample_rate=debug_capture.sample_rate,
        channels=debug_capture.channels,
        chunk_size=config.CHUNK_SIZE,
        latency_flags=debug_capture.latency_flags
    )
    
    # Start with our debug callback
    stream.start(debug_capture.debug_audio_callback)
    
    # Wait for the specified duration
    try:
        logger.info(f"Running debug capture for {args.duration} seconds...")
        for i in range(args.duration):
            print(f"Capturing... {i+1}/{args.duration}", end="\r")
            await asyncio.sleep(1)
            
        # Save final snapshots
        debug_capture.save_snapshots()
        
    except KeyboardInterrupt:
        logger.info("\nInterrupted by user")
    finally:
        # Stop the stream
        stream.stop()
        logger.info("Debug capture complete")
        
        # Create a summary file with config info
        summary = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "rtsp_url": debug_capture.rtsp_url,
            "sample_rate": debug_capture.sample_rate,
            "channels": debug_capture.channels,
            "latency_flags": str(debug_capture.latency_flags),
            "buffer_duration": config.BUFFER_DURATION,
            "small_buffer_duration": config.SMALL_BUFFER_DURATION,
            "silence_threshold": config.SILENCE_THRESHOLD,
        }
        
        with open("debug_audio/summary.json", "w") as f:
            json.dump(summary, f, indent=2)
            
        logger.info("Summary saved to debug_audio/summary.json")

if __name__ == "__main__":
    asyncio.run(main()) 