import numpy as np
import os
import time
import logging
import queue
import threading
import soundfile as sf
import asyncio
from collections import deque
import config
import argparse
from rtsp_audio import RTSPAudioCapture
from transcribe import transcribe_audio, init_transcription_model
import io

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
    
    # Log audio stats occasionally
    if frames % 50 == 0:  # Only log every 50th frame
        if audio_data.size > 0:
            max_val = np.max(np.abs(audio_data))
            mean_val = np.mean(np.abs(audio_data))
            logger.info(f"Audio: shape={indata.shape}, max={max_val:.6f}, mean={mean_val:.6f}")
    
    # Put data in queue for processing
    sample_queue.put(audio_data.copy())

async def main():
    parser = argparse.ArgumentParser(description="Test RTSP audio and transcription")
    parser.add_argument("--duration", type=int, default=10, help="Recording duration in seconds")
    parser.add_argument("--remote-transcribe", help="Use remote transcription with this URL")
    parser.add_argument("--whisper-model", default=config.WHISPER_MODEL, help="Whisper model to use")
    args = parser.parse_args()
    
    # Create output directory
    os.makedirs("test_audio", exist_ok=True)
    
    # Create RTSP audio capture
    rtsp_url = config.RTSP_URL
    sample_rate = config.SAMPLE_RATE
    channels = config.CHANNELS
    chunk_size = config.CHUNK_SIZE
    latency_flags = config.RTSP_LATENCY_FLAGS
    
    logger.info(f"Creating RTSP audio capture with URL: {rtsp_url}")
    logger.info(f"Using latency flags: {latency_flags}")
    
    # Initialize transcription model if not using remote
    use_remote_transcription = args.remote_transcribe is not None
    transcription_model = None
    if not use_remote_transcription:
        logger.info(f"Initializing local transcription model: {args.whisper_model}")
        transcription_model = init_transcription_model(args.whisper_model, config.DEVICE_TYPE, config.COMPUTE_TYPE)
    else:
        logger.info(f"Using remote transcription: {args.remote_transcribe}")
    
    # Start the RTSP stream
    stream = RTSPAudioCapture(
        rtsp_url=rtsp_url,
        sample_rate=sample_rate,
        channels=channels,
        chunk_size=chunk_size,
        latency_flags=latency_flags
    )
    
    stream.start(audio_callback)
    
    # Process for specified duration
    try:
        logger.info(f"Capturing audio for {args.duration} seconds...")
        for i in range(args.duration):
            logger.info(f"Capturing... {i+1}/{args.duration}")
            await asyncio.sleep(1)
        
        # Save the buffer to a WAV file for debugging/verification
        audio_data = np.array(list(audio_buffer), dtype=np.float32)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        output_file = f"test_audio/rtsp_audio_{timestamp}.wav"
        
        logger.info(f"Saving {len(audio_data)} samples to {output_file}")
        sf.write(output_file, audio_data, sample_rate)
        logger.info(f"Audio saved to {output_file}")
        
        # Print audio statistics
        if len(audio_data) > 0:
            logger.info(f"Audio stats: min={np.min(audio_data):.4f}, max={np.max(audio_data):.4f}, mean={np.mean(audio_data):.4f}")
            rms = np.sqrt(np.mean(np.square(audio_data)))
            logger.info(f"Audio RMS (volume): {rms:.6f}")
            if rms < 0.001:
                logger.warning("Audio may be silence or very quiet - check your RTSP stream.")
        else:
            logger.error("No audio data captured!")
        
        # Transcribe the audio directly from the in-memory numpy array
        logger.info("Transcribing the captured audio...")
        recent_transcriptions = deque(maxlen=10)
        history_buffer = deque(maxlen=config.HISTORY_BUFFER_SIZE)
        transcriptions, _ = await transcribe_audio(
            model=transcription_model,
            audio_data=audio_data, # Pass the numpy array directly
            audio_buffer=None, # Don't pass the buffer
            language="en",
            similarity_threshold=config.SIMILARITY_THRESHOLD,
            recent_transcriptions=recent_transcriptions,
            history_buffer=history_buffer,
            history_max_chars=config.HISTORY_MAX_CHARS,
            use_remote=use_remote_transcription,
            remote_url=args.remote_transcribe,
            sample_rate=config.SAMPLE_RATE 
        )
        
        if transcriptions:
            logger.info("Transcription results:")
            for i, text in enumerate(transcriptions):
                logger.info(f"  {i+1}: {text}")
        else:
            logger.warning("No transcription results returned!")
        
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        # Stop the stream
        stream.stop()
        logger.info("RTSP audio capture stopped")

if __name__ == "__main__":
    asyncio.run(main()) 