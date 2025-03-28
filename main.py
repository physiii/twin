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
from transcribe import transcribe_audio, init_transcription_model
from generator import process_user_text
from quality_control import generate_quality_control_report
from webserver import start_webserver
import uuid
import os
import logging

# Instead of a custom filter, we'll use standard logging format attributes
os.makedirs('logs', exist_ok=True)
log_file = 'logs/continuous.log'
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

DEVICE_TYPE = "cuda" if torch.cuda.is_available() else "cpu"
COMPUTE_TYPE = "float16" if DEVICE_TYPE == "cuda" else "float32"
SAMPLE_RATE = 16000
BUFFER_DURATION = 3
BUFFER_SIZE = SAMPLE_RATE * BUFFER_DURATION
SMALL_BUFFER_DURATION = 0.2
SMALL_BUFFER_SIZE = int(SAMPLE_RATE * SMALL_BUFFER_DURATION)
LANGUAGE = "en"
SIMILARITY_THRESHOLD = 85
COOLDOWN_PERIOD = 0
RISK_THRESHOLD = 0.5
HISTORY_BUFFER_SIZE = 4
HISTORY_MAX_CHARS = 4000
WAKE_TIMEOUT = 24
SILENCE_THRESHOLD = 0.00005
CHANNELS = 1
CHUNK_SIZE = 1024

# How many transcription chunks to prepend for the current inference:
HISTORY_INCLUDE_CHUNKS = 6

TTS_PYTHON_PATH = "/home/andy/venvs/tts-env/bin/python"
TTS_SCRIPT_PATH = "/home/andy/scripts/tts/tts.py"

WAKE_SOUND_FILE = "/media/mass/scripts/twin/wake.wav"
SLEEP_SOUND_FILE = "/media/mass/scripts/twin/sleep.wav"

parser = ArgumentParser(description="Live transcription with flexible inference and embedding options.")
parser.add_argument("-e", "--execute", action="store_true", help="Execute the commands returned by the inference model")
parser.add_argument("--remote-inference", help="Use remote inference. Specify the full URL for the inference server.")
parser.add_argument("--remote-store", help="Specify the URL for the vector store server.")
parser.add_argument("-s", "--silent", action="store_true", help="Disable TTS playback")
parser.add_argument("--source", default=None, help="Manually set the audio source (index or name)")
parser.add_argument("--whisper-model", default="turbo", help="Specify the Whisper model size")
parser.add_argument("--remote-transcribe", help="Use remote transcription. Specify the URL for the transcription server.")
args = parser.parse_args()

REMOTE_STORE_URL = args.remote_store
REMOTE_INFERENCE_URL = args.remote_inference
REMOTE_TRANSCRIBE_URL = args.remote_transcribe

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
    Pauses media playback using playerctl.
    If VLC is running and recognized by playerctl, it will also be paused.
    """
    loop = asyncio.get_running_loop()
    try:
        # 1. Pause any default player if it's currently playing
        status_result = await loop.run_in_executor(
            None, 
            lambda: subprocess.run(['playerctl', 'status'], capture_output=True, text=True)
        )
        if status_result.stdout.strip() == 'Playing':
            await loop.run_in_executor(
                None, 
                lambda: subprocess.run(['playerctl', 'pause'])
            )

        # 2. Check if VLC is recognized by playerctl, and if so, pause it if it's playing
        players_result = await loop.run_in_executor(
            None, 
            lambda: subprocess.run(['playerctl', '-l'], capture_output=True, text=True)
        )
        players = players_result.stdout.strip().split('\n')
        if 'vlc' in players:
            vlc_status_result = await loop.run_in_executor(
                None, 
                lambda: subprocess.run(
                    ['playerctl', '-p', 'vlc', 'status'], 
                    capture_output=True, 
                    text=True
                )
            )
            if vlc_status_result.stdout.strip() == 'Playing':
                await loop.run_in_executor(
                    None, 
                    lambda: subprocess.run(['playerctl', '-p', 'vlc', 'pause'])
                )

    except Exception as e:
        logger.error(f"Error pausing media players: {e}")

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

    if small_rms < SILENCE_THRESHOLD and not is_awake:
        return

    audio_data = np.array(list(audio_buffer), dtype=np.float32)
    if len(audio_data) == 0:
        return

    rms = calculate_rms(audio_data)
    if rms < SILENCE_THRESHOLD:
        return

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

        # Send to inference
        result = await process_user_text(
            combined_text,
            context,
            is_awake=is_awake,
            force_awake=False
        )

        # If a wake phrase is detected now
        if result["woke_up"]:
            is_awake = True
            wake_start_time = time.time()
            await pause_media_players()
            asyncio.create_task(play_wake_sound(WAKE_SOUND_FILE))
            context['session_data'] = {
                "session_id": str(uuid.uuid4()),
                "start_time": datetime.now().isoformat(),
                "wake_phrase": text,
                "before_transcriptions": list(recent_transcriptions),
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
                logger.info("[Wake] Timeout reset due to command execution")
                if 'session_data' in context and context['session_data']:
                    context['session_data']['source_commands'].append({
                        "timestamp": datetime.now().isoformat(),
                        "command_text": text,
                        "inference_response": result["inference_response"],
                    })

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
    log_available_audio_devices()
    devices = sd.query_devices()
    input_device = ""

    if args.source:
        if args.source.isdigit():
            input_device = int(args.source)
        else:
            for i, device in enumerate(devices):
                if args.source.lower() in device["name"].lower():
                    input_device = i
                    break
        if input_device == "":
            logger.error(f"Specified audio source '{args.source}' not found.")
            return

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
        "AMY_DISTANCE_THRESHOLD": 1.1,
        "NA_DISTANCE_THRESHOLD": 1.2,
        "HIP_DISTANCE_THRESHOLD": 1.1,
        "command_queue": command_queue,
        "session_data": None,
        "QC_REPORT_DIR": "reports",
        "GENERAL_REPORT_FILE": "general_report.txt",
    }

    os.makedirs(context['QC_REPORT_DIR'], exist_ok=True)
    runner = await start_webserver(context)

    try:
        with sd.InputStream(
            callback=lambda indata, frames, time_info, status: audio_callback(
                indata, frames, time_info, status, audio_queue, audio_buffer, small_audio_buffer
            ),
            channels=CHANNELS,
            samplerate=SAMPLE_RATE,
            blocksize=CHUNK_SIZE,
            device=input_device,
            dtype="float32",
        ):
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
        await runner.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
