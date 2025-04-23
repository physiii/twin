from collections import deque
from datetime import datetime
import asyncio
import queue
import numpy as np
import sounddevice as sd
import json
import torch
import time
import subprocess
from argparse import ArgumentParser
from audio import (
    log_available_audio_devices,
    audio_callback,
    play_wake_sound,
    play_sleep_sound,
)
from rtsp_audio import create_rtsp_audio_stream
from transcribe import transcribe_audio, init_transcription_model
from generator import process_user_text
from quality_control import generate_quality_control_report
from webserver import start_webserver
from command import execute_commands
import uuid
import os
import logging
import config

# Instead of a custom filter, we'll use standard logging format attributes
os.makedirs('logs', exist_ok=True)
log_file = config.LOG_FILE
handlers = [
    logging.FileHandler(log_file, mode='a'),
    logging.StreamHandler()
]
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] [%(levelname)s] [%(filename)s] %(message)s",
    handlers=handlers
)

# Remove the custom filter
logger = logging.getLogger("twin")
logging.getLogger("faster_whisper").setLevel(logging.ERROR)
# Explicitly set the level for the twin logger
logger.setLevel(logging.INFO)

# Load configuration from config.py
DEVICE_TYPE = config.DEVICE_TYPE
COMPUTE_TYPE = config.COMPUTE_TYPE
SAMPLE_RATE = config.SAMPLE_RATE
BUFFER_DURATION = config.BUFFER_DURATION
BUFFER_SIZE = int(SAMPLE_RATE * BUFFER_DURATION)
SMALL_BUFFER_DURATION = config.SMALL_BUFFER_DURATION
SMALL_BUFFER_SIZE = int(SAMPLE_RATE * SMALL_BUFFER_DURATION)
LANGUAGE = config.LANGUAGE
SIMILARITY_THRESHOLD = config.SIMILARITY_THRESHOLD
COOLDOWN_PERIOD = config.COOLDOWN_PERIOD
RISK_THRESHOLD = config.RISK_THRESHOLD
HISTORY_BUFFER_SIZE = config.HISTORY_BUFFER_SIZE
HISTORY_MAX_CHARS = config.HISTORY_MAX_CHARS
WAKE_TIMEOUT = config.WAKE_TIMEOUT
SILENCE_THRESHOLD = config.SILENCE_THRESHOLD
CHANNELS = config.CHANNELS
CHUNK_SIZE = config.CHUNK_SIZE
HISTORY_INCLUDE_CHUNKS = config.HISTORY_INCLUDE_CHUNKS
TTS_PYTHON_PATH = config.TTS_PYTHON_PATH
TTS_SCRIPT_PATH = config.TTS_SCRIPT_PATH
WAKE_SOUND_FILE = config.WAKE_SOUND_FILE
SLEEP_SOUND_FILE = config.SLEEP_SOUND_FILE

parser = ArgumentParser(description="Live transcription with flexible inference and embedding options.")
parser.add_argument("-e", "--execute", action="store_true", help="Execute the commands returned by the inference model")
parser.add_argument("--remote-inference", help="Use remote inference. Specify the full URL for the inference server.")
parser.add_argument("--remote-store", help="Specify the URL for the vector store server.")
parser.add_argument("-s", "--silent", action="store_true", help="Disable TTS playback")
parser.add_argument("--source", default=None, help="Manually set the audio source (index or name)")
parser.add_argument("--whisper-model", default=config.WHISPER_MODEL, help="Specify the Whisper model size")
parser.add_argument("--remote-transcribe", help="Use remote transcription. Specify the URL for the transcription server.")
args = parser.parse_args()

# Use config values as defaults, command line args override them
REMOTE_STORE_URL = args.remote_store or config.REMOTE_STORE_URL
REMOTE_INFERENCE_URL = args.remote_inference or config.REMOTE_INFERENCE_URL
REMOTE_TRANSCRIBE_URL = args.remote_transcribe or config.REMOTE_TRANSCRIBE_URL

audio_buffer = deque(maxlen=BUFFER_SIZE)
small_audio_buffer = deque(maxlen=SMALL_BUFFER_SIZE)
audio_queue = queue.Queue()
recent_transcriptions = deque(maxlen=10)
history_buffer = deque(maxlen=HISTORY_BUFFER_SIZE)
running_log = deque(maxlen=1000)

is_awake = False
wake_start_time = None
did_inference = False

command_queue = asyncio.Queue()

def get_timestamp():
    USE_TIMESTAMP = False
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S") if USE_TIMESTAMP else ""

def get_history_text():
    """
    Returns the joined text from history_buffer (up to HISTORY_MAX_CHARS).
    We handle chunk-based slicing elsewhere, so this is the full buffer joined.
    """
    history_text = " ".join(history_buffer)
    if len(history_text) > HISTORY_MAX_CHARS:
        history_text = history_text[-HISTORY_MAX_CHARS:]
        # Trim to avoid cutting mid-word
        if " " in history_text:
            history_text = history_text[history_text.index(" ") + 1:]
    return history_text

def calculate_rms(audio_data):
    if len(audio_data) == 0:
        return np.nan
    return np.sqrt(np.mean(np.square(audio_data)))

async def pause_media_players():
    """
    Pauses media playback using playerctl, potentially remotely via SSH.
    If VLC is running and recognized by playerctl, it will also be paused.
    """
    loop = asyncio.get_running_loop()
    ssh_target = config.SSH_HOST_TARGET
    logger.debug(f"pause_media_players: SSH_HOST_TARGET from config = '{ssh_target}'")
    
    # Function to run playerctl command (potentially remotely)
    async def run_playerctl(*args):
        playerctl_cmd_parts = ['playerctl'] + list(args)
        final_command = []
        
        if ssh_target:
            # Construct the remote command string including DISPLAY export
            remote_command_str = f"export DISPLAY=:0; {' '.join(playerctl_cmd_parts)}"
            final_command = ['ssh', '-o', 'StrictHostKeyChecking=no', ssh_target, remote_command_str]
        else:
            final_command = playerctl_cmd_parts

        logger.debug(f"Attempting to execute playerctl command: {' '.join(final_command)}")
        try:
            # Add timeout for safety
            result = await asyncio.wait_for(loop.run_in_executor(
                None, 
                lambda: subprocess.run(final_command, capture_output=True, text=True, check=False)
            ), timeout=10.0)
            
            stdout_decoded = result.stdout.strip()
            stderr_decoded = result.stderr.strip()
            
            if result.returncode != 0:
                # Don't log error if code is 1 (playerctl often exits 1 if no players found/running)
                if result.returncode == 1 and not stderr_decoded:
                     logger.debug(f"playerctl command exited 1 (likely no players): {' '.join(final_command)}")
                else:
                     logger.warning(f"playerctl command failed (Code: {result.returncode}): {' '.join(final_command)} - Stderr: {stderr_decoded}")
                return None # Indicate failure or non-existence
            else:
                logger.debug(f"playerctl command successful: {' '.join(final_command)} - Stdout: {stdout_decoded}")
                return stdout_decoded # Return stdout on success
                
        except asyncio.TimeoutError:
             logger.error(f"Timeout executing playerctl command: {' '.join(final_command)}. SSH connection issue?")
             return None
        except FileNotFoundError:
             # Handle potential FileNotFoundError for both ssh and playerctl
             cmd_name = final_command[0] 
             logger.error(f"playerctl/ssh command failed: '{cmd_name}' not found. Is it installed and in PATH?")
             return None
        except Exception as e:
             logger.error(f"Error executing command {' '.join(final_command)}: {e}", exc_info=True)
             return None

    # --- Main logic using run_playerctl --- 
    if ssh_target:
        logger.info("Attempting to pause media players remotely via SSH")
    else:
        logger.info("Attempting to pause local media players")

    try:
        # 1. Pause any default player if it's currently playing
        status = await run_playerctl('status')
        if status == 'Playing':
            await run_playerctl('pause')
            logger.info("Pause command sent to default player.")
        elif status is not None: # Check if status command succeeded but wasn't 'Playing'
            logger.info(f"Default player status: {status}")

        # 2. Check if VLC is recognized by playerctl, and pause if playing
        players_output = await run_playerctl('-l')
        if players_output is not None:
            players = players_output.split('\n')
            if 'vlc' in players:
                vlc_status = await run_playerctl('-p', 'vlc', 'status')
                if vlc_status == 'Playing':
                    await run_playerctl('-p', 'vlc', 'pause')
                    logger.info("Pause command sent to VLC player.")
                elif vlc_status is not None:
                    logger.info(f"VLC player found but not playing (Status: {vlc_status}).")
            else:
                 logger.info("VLC player not found by playerctl.")
        else:
            logger.info("Could not list players via playerctl (or no players running/error occurred).")
            
    except Exception as e:
        # Catch any broader errors in the main logic using run_playerctl
        logger.error(f"Unexpected error in pause_media_players logic: {e}", exc_info=True)

async def process_buffer(transcription_model, use_remote_transcription, remote_transcribe_url, context):
    """
    Periodically transcribes audio from audio_buffer and dispatches the text
    to process_user_text, with optional history-based context if awake.
    """
    await asyncio.sleep(0.1)
    global is_awake, wake_start_time, did_inference

    # Process any queued external commands first
    if not command_queue.empty():
        command_text = await command_queue.get()
        logger.info(f"[Command] Received external command: {command_text}")
        # Force awake for external commands
        result = await process_user_text(command_text, context, is_awake=True, force_awake=True)
        if result["woke_up"]:
            is_awake = True
            wake_start_time = time.time()
            await pause_media_players()
            asyncio.create_task(play_wake_sound(WAKE_SOUND_FILE))
            context['session_data'] = {
                "session_id": str(uuid.uuid4()),
                "start_time": datetime.now().isoformat(),
                "before_transcriptions": [],
                "after_transcriptions": [],
                "inferences": [],
                "commands_executed": [],
                "vectorstore_results": [],
                "user_feedback": [],
                "complete_transcription": "",
                "source_commands": [],
            }
        if result["inference_response"]:
            did_inference = True
            if result["inference_response"].get('commands') and context['args'].execute:
                wake_start_time = time.time()
        return

    # Read small buffer to gauge silence
    small_audio_data = np.array(list(small_audio_buffer), dtype=np.float32)
    small_rms = calculate_rms(small_audio_data)
    
    # Debug logging for audio levels
    if len(small_audio_buffer) > 0 and time.time() % 5 < 0.2:  # Log every ~5 seconds
        logger.debug(f"Small buffer RMS: {small_rms}, threshold: {SILENCE_THRESHOLD}, small buffer size: {len(small_audio_buffer)}")

    audio_data = np.array(list(audio_buffer), dtype=np.float32)
    if len(audio_data) == 0:
        return

    rms = calculate_rms(audio_data)
    
    # Debug logging for main buffer
    if time.time() % 5 < 0.2:  # Log every ~5 seconds
        logger.debug(f"Main buffer RMS: {rms}, main buffer size: {len(audio_buffer)}")

    # --- Silence Check --- 
    # Only transcribe if audio level is above the threshold
    if rms < SILENCE_THRESHOLD:
        return # Skip transcription if below silence threshold
    
    # --- Proceed with Transcription --- 
    # Transcribe the current chunk
    transcriptions, _ = await transcribe_audio(
        model=transcription_model,
        audio_data=audio_data,
        language="en",
        similarity_threshold=SIMILARITY_THRESHOLD,
        recent_transcriptions=recent_transcriptions,
        history_buffer=history_buffer,
        history_max_chars=HISTORY_MAX_CHARS,
        use_remote=use_remote_transcription,
        remote_url=remote_transcribe_url,
        sample_rate=config.SAMPLE_RATE
    )

    # Process each recognized utterance
    for text in transcriptions:
        logger.info(f"[Source] {get_timestamp()} {text}")
        running_log.append(f"{get_timestamp()} [Transcription] {text}")

        if is_awake and 'session_data' in context and context['session_data']:
            context['session_data']['after_transcriptions'].append(text)
            history_buffer.append(text)
        else:
            recent_transcriptions.append(text)

        # If we're awake, build a chunk-based history string
        if is_awake:
            # Slice the last N chunks from history_buffer
            last_chunks = list(history_buffer)[-HISTORY_INCLUDE_CHUNKS:]
            hist_text = " ".join(last_chunks)
            combined_text = (hist_text + " " + text).strip()
        else:
            # If not awake, just use the raw text
            combined_text = text

        # Send to inference *before* checking wake status for this text
        text_to_process = text if is_awake else combined_text
        result = await process_user_text(
            text_to_process,
            context,
            is_awake=is_awake, # Pass current awake state
            force_awake=False
        )

        # Now, handle state changes and potential command execution

        # --- Wake Up Logic --- 
        if result["woke_up"] and not is_awake:
            is_awake = True # Set awake *now*
            wake_start_time = time.time()
            await pause_media_players()
            asyncio.create_task(play_wake_sound(WAKE_SOUND_FILE))
            # Initialize session data on wake-up
            context['session_data'] = {
                "session_id": str(uuid.uuid4()),
                "start_time": datetime.now().isoformat(),
                "before_transcriptions": list(recent_transcriptions), # Capture history before wake
                "after_transcriptions": [],
                "inferences": [],
                "commands_executed": [],
                "vectorstore_results": [],
                "user_feedback": [],
                "complete_transcription": "",
                "source_commands": [],
            }
            recent_transcriptions.clear() # Clear noise buffer after wake
            logger.info("[Wake] System awake.")
            # If we just woke up, don't process inference from the wake phrase itself
            # Skip directly to the next buffer cycle
            continue 

        # --- Inference & Command Execution Logic (Only if awake) --- 
        if is_awake: # Check if we are (or just became) awake
            if result["inference_response"]:
                did_inference = True
                inference_data = result["inference_response"]
                # Add inference details to session data
                if 'session_data' in context and context['session_data'] is not None:
                    context['session_data']['inferences'].append({
                        "timestamp": datetime.now().isoformat(),
                        "transcription_used": text_to_process,
                        "raw_inference_output": inference_data.get("raw_output", ""), # Assuming raw output is stored
                        "processed_inference_output": inference_data,
                    })

                # --> IMMEDIATE COMMAND EXECUTION <--
                if inference_data.get('commands') and context['args'].execute:
                    logger.info(f"[Execute] Running commands immediately: {inference_data['commands']}")
                    await execute_commands(
                        commands=inference_data['commands'],
                        context_or_cooldown=context,
                        requires_confirmation=inference_data.get('confirmed', False),
                        risk_level=inference_data.get('risk', 0.5),
                        self_text=result.get("self_text", "")
                    )
                    # Add executed commands to session data
                    if 'session_data' in context and context['session_data'] is not None:
                        context['session_data']['commands_executed'].append({
                            "timestamp": datetime.now().isoformat(),
                            "commands": inference_data['commands'],
                            "triggering_transcription": text_to_process,
                        })

                # Reset timer only if inference happened while awake
                wake_start_time = time.time()
            # else: No inference response while awake, but still reset timer because user spoke
            else:
                 wake_start_time = time.time()
                 logger.debug("[Wake] Timer reset due to non-command transcription while awake.")

    # Check if we should sleep
    if is_awake and wake_start_time and (time.time() - wake_start_time) > WAKE_TIMEOUT:
        logger.info(f"[Wake] System asleep after {WAKE_TIMEOUT} seconds of inactivity.")
        if not did_inference:
            asyncio.create_task(play_sleep_sound(SLEEP_SOUND_FILE))
        if context['session_data']:
            context['session_data']['end_time'] = datetime.now().isoformat()
            context['session_data']['duration'] = time.time() - wake_start_time
            # Save the entire buffer as final transcript
            context['session_data']['complete_transcription'] = " ".join(history_buffer)
            await generate_quality_control_report(context['session_data'], context)
            context['session_data'] = None
        is_awake = False
        did_inference = False

async def main():
    # Debug the SSH target value as read from config
    logger.info(f"*** STARTUP INFO: SSH_HOST_TARGET = '{config.SSH_HOST_TARGET}' ***")
    
    log_available_audio_devices()
    devices = sd.query_devices()
    input_device = None  # Changed from empty string to None

    # Skip device detection if using RTSP
    if config.AUDIO_SOURCE.lower() == 'rtsp':
        logger.info(f"Using RTSP audio source: {config.RTSP_URL}")
    else:
        # Try to find the specified input device
        if args.source:
            if args.source.isdigit():
                input_device = int(args.source)
            else:
                for i, device in enumerate(devices):
                    if args.source.lower() in device["name"].lower():
                        input_device = i
                        break
                
                # If device name not found and we're looking for pulse, try to find it by number
                if input_device is None and args.source.lower() == "pulse":
                    for i, device in enumerate(devices):
                        if "pulse" in device["name"].lower() or (device.get("name", "").lower() == "pulse"):
                            input_device = i
                            logger.info(f"Found PulseAudio device at index {i}")
                            break
                
                # If still not found, try device 13 (common pulse index)
                if input_device is None and args.source.lower() == "pulse":
                    try:
                        # Find the device with pulse in the name
                        for i, device in enumerate(devices):
                            if i == 13 and device.get("max_input_channels", 0) > 0:
                                input_device = 13
                                logger.info("Using default PulseAudio device (13)")
                                break
                    except Exception as e:
                        logger.error(f"Error finding pulse device: {e}")
            
            # If input_device is still None, try to find any working device
            if input_device is None:
                logger.warning(f"Specified audio source '{args.source}' not found. Trying fallback devices.")
                
                # Try common device indices for input
                for test_id in [13, 14, 0, "default"]:
                    try:
                        logger.info(f"Testing audio device {test_id}")
                        with sd.InputStream(device=test_id, channels=1, samplerate=SAMPLE_RATE, blocksize=CHUNK_SIZE, dtype="float32"):
                            logger.info(f"Found working audio device: {test_id}")
                            input_device = test_id
                            break
                    except Exception as e:
                        logger.warning(f"Device {test_id} failed: {e}")
                
                # If still no device, try to find any with input channels
                if input_device is None:
                    for i, device in enumerate(devices):
                        try:
                            if device.get("max_input_channels", 0) > 0:
                                logger.info(f"Trying device {i}: {device.get('name', 'Unknown')} with {device.get('max_input_channels')} input channels")
                                with sd.InputStream(device=i, channels=1, samplerate=SAMPLE_RATE, blocksize=CHUNK_SIZE, dtype="float32"):
                                    logger.info(f"Found working audio device: {i}")
                                    input_device = i
                                    break
                        except Exception as e:
                            logger.warning(f"Device {i} failed: {e}")
        
        if input_device is None and config.AUDIO_SOURCE.lower() != 'rtsp':
            logger.error("No suitable audio device found. Exiting.")
            return

        logger.info(f"Using audio input device: {input_device}")
    
    use_remote_transcription = args.remote_transcribe is not None
    transcription_model = (
        None
        if use_remote_transcription
        else init_transcription_model(args.whisper_model, DEVICE_TYPE, COMPUTE_TYPE)
    )

    context = {
        "REMOTE_STORE_URL": REMOTE_STORE_URL,
        "REMOTE_INFERENCE_URL": REMOTE_INFERENCE_URL,
        "args": args,
        "RISK_THRESHOLD": RISK_THRESHOLD,
        "COOLDOWN_PERIOD": COOLDOWN_PERIOD,
        "TTS_PYTHON_PATH": TTS_PYTHON_PATH,
        "TTS_SCRIPT_PATH": TTS_SCRIPT_PATH,
        "running_log": running_log,
        "AMY_DISTANCE_THRESHOLD": config.AMY_DISTANCE_THRESHOLD,
        "NA_DISTANCE_THRESHOLD": config.NA_DISTANCE_THRESHOLD,
        "HIP_DISTANCE_THRESHOLD": config.HIP_DISTANCE_THRESHOLD,
        "command_queue": command_queue,
        "session_data": None,
        "QC_REPORT_DIR": config.QC_REPORT_DIR,
        "GENERAL_REPORT_FILE": config.GENERAL_REPORT_FILE,
    }

    os.makedirs(context['QC_REPORT_DIR'], exist_ok=True)
    runner = await start_webserver(context)

    try:
        # Choose audio source based on configuration
        if config.AUDIO_SOURCE.lower() == 'rtsp':
            logger.info(f"Using RTSP audio source: {config.RTSP_URL}")
            # Create RTSP audio stream with the same callback interface
            audio_stream = create_rtsp_audio_stream(
                lambda indata, frames, time_info, status: audio_callback(
                    indata, frames, time_info, status, audio_queue, audio_buffer, small_audio_buffer
                )
            )
            # No need for a context manager with the RTSP stream
        else:
            # Use traditional microphone input with sounddevice
            logger.info(f"Using microphone audio input device: {input_device}")
            audio_stream = sd.InputStream(
                callback=lambda indata, frames, time_info, status: audio_callback(
                    indata, frames, time_info, status, audio_queue, audio_buffer, small_audio_buffer
                ),
                channels=CHANNELS,
                samplerate=SAMPLE_RATE,
                blocksize=CHUNK_SIZE,
                device=input_device,
                dtype="float32",
            )
            audio_stream.start()

        # Log active configuration
        inference_type = (
            f"remote inference ({REMOTE_INFERENCE_URL})"
            if REMOTE_INFERENCE_URL
            else "Local inference"
        )
        transcription_type = (
            f"remote ({REMOTE_TRANSCRIBE_URL})"
            if use_remote_transcription
            else f"local ({args.whisper_model})"
        )
        logger.info(
            f"Using {inference_type} for inference, and {transcription_type} for transcription."
        )
        while True:
            await process_buffer(
                transcription_model,
                use_remote_transcription,
                REMOTE_TRANSCRIBE_URL,
                context,
            )
    except KeyboardInterrupt:
        logger.info("Streaming stopped.")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {str(e)}")
        logger.exception("An error occurred during execution.")
    finally:
        # Clean up audio stream
        if audio_stream:
            if hasattr(audio_stream, 'stop'):
                audio_stream.stop()
            elif hasattr(audio_stream, 'close'):
                audio_stream.close()
                
        # Clean up web server
        await runner.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
