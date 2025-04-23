import numpy as np
import os
import time
import logging
import queue
import threading
import soundfile as sf
from collections import deque
import config
from rtsp_audio import RTSPAudioCapture

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] [%(levelname)s] [%(filename)s] %(message)s")
logger = logging.getLogger("test_rtsp")

# Audio buffer and sample queue
audio_buffer = deque(maxlen=int(config.SAMPLE_RATE * 10))  # 10 seconds buffer
sample_queue = queue.Queue()

def audio_callback(indata, frames, time_info, status):
    """Callback for audio data from RTSP stream"""
    if status:
        logger.error(f"Audio callback error: {status}")
    
    # Get the audio data
    audio_data = indata[:, 0] if indata.shape[1] > 1 else indata.flatten()
    
    # Add to buffer
    for sample in audio_data:
        audio_buffer.append(sample)
    
    # Log audio stats
    if audio_data.size > 0:
        max_val = np.max(np.abs(audio_data))
        mean_val = np.mean(np.abs(audio_data))
        logger.info(f"Audio: shape={indata.shape}, max={max_val:.6f}, mean={mean_val:.6f}")
    
    # Put data in queue for processing
    sample_queue.put(audio_data.copy())

def main():
    # Create output directory
    os.makedirs("test_audio", exist_ok=True)
    
    # Create RTSP audio capture
    rtsp_url = config.RTSP_URL
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
    
    # Start the stream
    stream.start(audio_callback)
    
    # Process for a few seconds
    try:
        logger.info("Capturing audio for 5 seconds...")
        time.sleep(5)
        
        # Save the buffer to a WAV file
        audio_data = np.array(list(audio_buffer), dtype=np.float32)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        output_file = f"test_audio/rtsp_audio_{timestamp}.wav"
        
        logger.info(f"Saving {len(audio_data)} samples to {output_file}")
        sf.write(output_file, audio_data, sample_rate)
        logger.info(f"Audio saved to {output_file}")
        
        # Print audio statistics
        if len(audio_data) > 0:
            logger.info(f"Audio stats: min={np.min(audio_data):.4f}, max={np.max(audio_data):.4f}, mean={np.mean(audio_data):.4f}")
            # Calculate RMS (volume)
            rms = np.sqrt(np.mean(np.square(audio_data)))
            logger.info(f"Audio RMS (volume): {rms:.6f}")
            # Check if audio might be silence
            if rms < 0.001:
                logger.warning("Audio may be silence or very quiet - check your RTSP stream.")
        else:
            logger.error("No audio data captured!")
        
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        # Stop the stream
        stream.stop()
        logger.info("RTSP audio capture stopped")

if __name__ == "__main__":
    main() 