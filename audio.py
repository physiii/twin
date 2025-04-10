import logging
import sounddevice as sd
from collections import deque
import asyncio
import time
import numpy as np

logger = logging.getLogger("twin")

def log_available_audio_devices():
    devices = sd.query_devices()
    logger.info("Available audio devices:")
    for i, device in enumerate(devices):
        logger.info(f"{i}: {device['name']}, Default Sample Rate: {device['default_samplerate']}, Max Input Channels: {device['max_input_channels']}")

def audio_callback(indata, frames, time_info, status, audio_queue, audio_buffer, small_audio_buffer):
    if status:
        logger.error(f"Audio callback error: {status}")
    
    # Add debug logging
    debug_interval = 50  # Only log once per 50 callbacks to avoid flooding
    if id(indata) % debug_interval == 0:
        if indata.size > 0:
            max_val = np.max(np.abs(indata))
            mean_val = np.mean(np.abs(indata))
            logger.debug(f"Audio callback received data: shape={indata.shape}, max={max_val:.6f}, mean={mean_val:.6f}")
        else:
            logger.debug("Audio callback received empty data")
    
    audio_data = indata[:, 0] if indata.shape[1] > 1 else indata.flatten()
    audio_queue.put(audio_data.copy())
    audio_buffer.extend(audio_data)
    small_audio_buffer.extend(audio_data)  # Add this line to handle the small buffer

async def play_tts_response(response_text, max_words=15, tts_python_path=None, tts_script_path=None, silent=False):
    if silent:
        return 0
    
    start_time = time.time()
    try:
        words = response_text.split()
        truncated_response = ' '.join(words[:max_words]) + '...' if len(words) > max_words else response_text
        proc = await asyncio.create_subprocess_exec(
            tts_python_path, tts_script_path, truncated_response,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()
    except Exception as e:
        logger.error(f"Failed to execute TTS script: {e}")
    return time.time() - start_time

# **Function to Play Wake Sound**
async def play_wake_sound(sound_file):
    try:
        proc = await asyncio.create_subprocess_exec(
            'paplay', sound_file,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()
    except Exception as e:
        logger.error(f"Failed to play wake sound: {e}")

# **Function to Play Sleep Sound**
async def play_sleep_sound(sound_file):
    try:
        proc = await asyncio.create_subprocess_exec(
            'paplay', sound_file,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()
    except Exception as e:
        logger.error(f"Failed to play sleep sound: {e}")
