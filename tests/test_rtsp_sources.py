import numpy as np
import os
import time
import logging
import argparse
import asyncio
import soundfile as sf
from collections import deque
import config
from rtsp_audio import RTSPAudioCapture

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] [%(levelname)s] [%(filename)s] %(message)s")
logger = logging.getLogger("test_rtsp_sources")

class AudioTester:
    """Class to test audio from different RTSP sources"""
    
    def __init__(self, rtsp_url, duration=5, sample_rate=48000, channels=1, chunk_size=1024):
        self.rtsp_url = rtsp_url
        self.duration = duration
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_size = chunk_size
        self.audio_buffer = deque(maxlen=int(sample_rate * duration))
        self.latency_flags = config.RTSP_LATENCY_FLAGS
        
    def audio_callback(self, indata, frames, time_info, status):
        """Callback for audio data"""
        if status:
            logger.error(f"Audio callback error: {status}")
        
        # Get the audio data
        audio_data = indata[:, 0] if indata.shape[1] > 1 else indata.flatten()
        
        # Add to buffer
        for sample in audio_data:
            self.audio_buffer.append(sample)
        
        # Log occasional stats
        if len(self.audio_buffer) % 10000 == 0:
            logger.info(f"Buffer size: {len(self.audio_buffer)}/{self.audio_buffer.maxlen}")
    
    async def capture_and_save(self, output_file):
        """Capture audio and save to file"""
        logger.info(f"Testing RTSP URL: {self.rtsp_url}")
        
        # Create RTSP audio capture
        stream = RTSPAudioCapture(
            rtsp_url=self.rtsp_url,
            sample_rate=self.sample_rate,
            channels=self.channels,
            chunk_size=self.chunk_size,
            latency_flags=self.latency_flags
        )
        
        # Start the stream
        stream.start(self.audio_callback)
        
        # Wait for the specified duration
        for i in range(self.duration):
            logger.info(f"Capturing... {i+1}/{self.duration}")
            await asyncio.sleep(1)
        
        # Stop the stream
        stream.stop()
        
        # Save the captured audio
        audio_data = np.array(list(self.audio_buffer), dtype=np.float32)
        
        if len(audio_data) > 0:
            logger.info(f"Saving {len(audio_data)} samples to {output_file}")
            sf.write(output_file, audio_data, self.sample_rate)
            
            # Print audio statistics
            logger.info(f"Audio stats: min={np.min(audio_data):.4f}, max={np.max(audio_data):.4f}, mean={np.mean(audio_data):.4f}")
            rms = np.sqrt(np.mean(np.square(audio_data)))
            logger.info(f"Audio RMS (volume): {rms:.6f}")
            return rms
        else:
            logger.error("No audio data captured!")
            return 0.0

async def main():
    parser = argparse.ArgumentParser(description="Test multiple RTSP audio sources")
    parser.add_argument("--duration", type=int, default=5, help="Recording duration for each source in seconds")
    parser.add_argument("--urls", nargs="+", help="List of RTSP URLs to test")
    args = parser.parse_args()
    
    # Create output directory
    os.makedirs("test_audio", exist_ok=True)
    
    # Get the default URL from config if none provided
    rtsp_urls = args.urls or [config.RTSP_URL]
    
    # Test each URL
    results = []
    for i, url in enumerate(rtsp_urls):
        try:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            output_file = f"test_audio/source_{i}_{timestamp}.wav"
            
            tester = AudioTester(
                rtsp_url=url,
                duration=args.duration,
                sample_rate=config.SAMPLE_RATE,
                channels=config.CHANNELS,
                chunk_size=config.CHUNK_SIZE
            )
            
            rms = await tester.capture_and_save(output_file)
            results.append({
                "url": url,
                "file": output_file,
                "rms": rms
            })
            
            # Wait a bit between tests
            await asyncio.sleep(1)
            
        except Exception as e:
            logger.error(f"Error testing URL {url}: {e}")
    
    # Print summary
    logger.info("\n--- RTSP Source Test Results ---")
    for i, result in enumerate(results):
        logger.info(f"Source {i}: {result['url']}")
        logger.info(f"  - File: {result['file']}")
        logger.info(f"  - Volume (RMS): {result['rms']:.6f}")
        if result['rms'] < 0.001:
            logger.warning("  - Audio level very low or silent!")
        elif result['rms'] > 0.1:
            logger.info("  - Good audio level detected")

if __name__ == "__main__":
    asyncio.run(main()) 