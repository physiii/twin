import logging
import sounddevice as sd
from collections import deque
import asyncio
import time
import numpy as np
import config # Make sure config is imported

logger = logging.getLogger("twin")

def log_available_audio_devices():
    try:
        devices = sd.query_devices()
        logger.info("Available audio devices:")
        if devices:
            for i, device in enumerate(devices):
                logger.info(f"{i}: {device['name']}, Default Sample Rate: {device['default_samplerate']}, Max Input Channels: {device['max_input_channels']}")
        else:
            logger.warning("No audio devices found, but this is fine if using RTSP source")
    except Exception as e:
        logger.warning(f"Could not query audio devices: {e}. This is acceptable if using RTSP source.")

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
    ssh_target = config.SSH_HOST_TARGET
    logger.debug(f"play_wake_sound: SSH_HOST_TARGET from config = '{ssh_target}'")
    local_command_parts = ['paplay', sound_file]
    final_command = []
    
    if ssh_target:
        # Construct the command string for SSH execution including DISPLAY export
        remote_command_str = f"export DISPLAY=:0; {' '.join(local_command_parts)}"
        final_command = ['ssh', '-o', 'StrictHostKeyChecking=no', ssh_target, remote_command_str]
        logger.info(f"Attempting remote wake sound via SSH: {' '.join(final_command)}")
    else:
        final_command = local_command_parts
        logger.info(f"Attempting local wake sound: {' '.join(final_command)}")
        
    try:
        proc = await asyncio.create_subprocess_exec(
            *final_command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        # Add a timeout to communicate to prevent hangs (e.g., 10 seconds)
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10.0)
        
        stdout_decoded = stdout.decode('utf-8', errors='replace').strip()
        stderr_decoded = stderr.decode('utf-8', errors='replace').strip()

        if proc.returncode != 0:
             logger.error(f"Failed to play wake sound (Code: {proc.returncode}) Command: {' '.join(final_command)}. Stderr: {stderr_decoded}")
        else:
             logger.debug(f"Wake sound command executed successfully. Stdout: {stdout_decoded}")
             
    except FileNotFoundError:
        cmd_name = final_command[0]
        logger.error(f"Failed to play wake sound: '{cmd_name}' command not found. Is it installed and in PATH?")
    except asyncio.TimeoutError:
        logger.error(f"Timeout executing wake sound command: {' '.join(final_command)}. SSH connection issue?")
        if proc:
            proc.kill() # Ensure the process is killed on timeout
            await proc.wait()
    except Exception as e:
        logger.error(f"Failed to play wake sound with command {' '.join(final_command)}: {e}", exc_info=True)

# **Function to Play Sleep Sound**
async def play_sleep_sound(sound_file):
    ssh_target = config.SSH_HOST_TARGET
    logger.debug(f"play_sleep_sound: SSH_HOST_TARGET from config = '{ssh_target}'")
    local_command_parts = ['paplay', sound_file]
    final_command = []
    
    if ssh_target:
        # Construct the command string for SSH execution including DISPLAY export
        remote_command_str = f"export DISPLAY=:0; {' '.join(local_command_parts)}"
        final_command = ['ssh', '-o', 'StrictHostKeyChecking=no', ssh_target, remote_command_str]
        logger.info(f"Attempting remote sleep sound via SSH: {' '.join(final_command)}")
    else:
        final_command = local_command_parts
        logger.info(f"Attempting local sleep sound: {' '.join(final_command)}")

    try:
        proc = await asyncio.create_subprocess_exec(
            *final_command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        # Add a timeout
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10.0)
        
        stdout_decoded = stdout.decode('utf-8', errors='replace').strip()
        stderr_decoded = stderr.decode('utf-8', errors='replace').strip()
        
        if proc.returncode != 0:
             logger.error(f"Failed to play sleep sound (Code: {proc.returncode}) Command: {' '.join(final_command)}. Stderr: {stderr_decoded}")
        else:
             logger.debug(f"Sleep sound command executed successfully. Stdout: {stdout_decoded}")
             
    except FileNotFoundError:
        cmd_name = final_command[0]
        logger.error(f"Failed to play sleep sound: '{cmd_name}' command not found. Is it installed and in PATH?")
    except asyncio.TimeoutError:
        logger.error(f"Timeout executing sleep sound command: {' '.join(final_command)}. SSH connection issue?")
        if proc:
            proc.kill()
            await proc.wait()
    except Exception as e:
        logger.error(f"Failed to play sleep sound with command {' '.join(final_command)}: {e}", exc_info=True)
