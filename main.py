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
    play_tts_response,
    play_wake_sound,
    play_sleep_sound,
)
from search import run_search
from transcribe import transcribe_audio, init_transcription_model
from rapidfuzz import fuzz
from webserver import start_webserver
from command import process_command_text
import uuid
import os
from quality_control import generate_quality_control_report

import logging
from logging.handlers import RotatingFileHandler
from logger import setup_logging

setup_logging()
logger = logging.getLogger('twin')

os.makedirs('logs', exist_ok=True)
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_filename = f'logs/twin_{timestamp}.log'
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        RotatingFileHandler(log_filename, maxBytes=5*1024*1024, backupCount=5)
    ]
)
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
SILENCE_THRESHOLD = 0.0001
CHANNELS = 1
CHUNK_SIZE = 1024

AMY_DISTANCE_THRESHOLD = 1.1
NA_DISTANCE_THRESHOLD = 1.2
HIP_DISTANCE_THRESHOLD = 1.1
WAKE_DISTANCE_THRESHOLD = 0.30

TTS_PYTHON_PATH = "/home/andy/venvs/tts-env/bin/python"
TTS_SCRIPT_PATH = "/home/andy/scripts/tts/tts.py"

WAKE_SOUND_FILE = "/media/mass/scripts/twin/wake.wav"
SLEEP_SOUND_FILE = "/media/mass/scripts/twin/sleep.wav"

WAKE_PHRASES = ["Hey computer.", "Hey twin"]
FUZZY_SIMILARITY_THRESHOLD = 60

parser = ArgumentParser(description="Live transcription with flexible inference and embedding options.")
parser.add_argument("-e", "--execute", action="store_true", help="Execute the commands returned by the inference model")
parser.add_argument("--remote-inference", help="Use remote inference. Specify the full URL for the inference server.")
parser.add_argument("--remote-store", help="Specify the URL for the vector store server.")
parser.add_argument("-s", "--silent", action="store_true", help="Disable TTS playback")
parser.add_argument("--source", default=None, help="Manually set the audio source (index or name)")
parser.add_argument("--whisper-model", default="tiny.en", help="Specify the Whisper model size (default: tiny.en)")
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
running_log = deque(maxlen=1000)  # Limit to last 1000 entries

is_awake = False
wake_start_time = None
is_processing = False
did_inference = False

command_queue = asyncio.Queue()

def get_timestamp():
    USE_TIMESTAMP = False
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S") if USE_TIMESTAMP else ""

def get_history_text():
    history_text = " ".join(history_buffer)
    if len(history_text) > HISTORY_MAX_CHARS:
        history_text = history_text[-HISTORY_MAX_CHARS:]
        history_text = history_text[history_text.index(" ") + 1 :]
    return history_text

def calculate_rms(audio_data):
    if len(audio_data) == 0:
        return np.nan
    return np.sqrt(np.mean(np.square(audio_data)))

async def pause_media_players():
    loop = asyncio.get_running_loop()

    try:
        result = await loop.run_in_executor(None, lambda: subprocess.run(['playerctl', 'status'], capture_output=True, text=True))
        if result.stdout.strip() == 'Playing':
            await loop.run_in_executor(None, lambda: subprocess.run(['playerctl', 'pause']))
    except Exception as e:
        logger.error(f"Error checking or pausing playerctl: {e}")

    try:
        result = await loop.run_in_executor(None, lambda: subprocess.run(['ps', '-C', 'vlc', '-o', 'state'], capture_output=True, text=True))
        states = result.stdout.strip().split('\n')[1:]
        if 'S' in states:
            await loop.run_in_executor(None, lambda: subprocess.run(['pkill', '-STOP', 'vlc']))
    except Exception as e:
        logger.error(f"Error checking or pausing vlc: {e}")

async def process_buffer(transcription_model, use_remote_transcription, remote_transcribe_url, context):
    await asyncio.sleep(0.1)
    global is_awake, wake_start_time, is_processing, did_inference

    # Log sizes of data structures
    logger.info(f"running_log size: {len(running_log)}")
    logger.info(f"audio_buffer size: {len(audio_buffer)}")
    logger.info(f"small_audio_buffer size: {len(small_audio_buffer)}")
    logger.info(f"history_buffer size: {len(history_buffer)}")

    if not command_queue.empty():
        command_text = await command_queue.get()
        logger.info(f"[Command] Received external command: {command_text}")
        is_awake = True
        wake_start_time = time.time()
        did_inference = False

        inference_response = await process_command_text(command_text, context)
        if inference_response:
            did_inference = True
            # Reset timeout when a command was actually executed
            if inference_response.get('commands') and context['args'].execute:
                wake_start_time = time.time()
        logger.info(f"[Inference] {inference_response}")
        return

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

    transcriptions, _ = await transcribe_audio(
        model=transcription_model,
        audio_data=audio_data,
        language=LANGUAGE,
        similarity_threshold=SIMILARITY_THRESHOLD,
        recent_transcriptions=recent_transcriptions,
        history_buffer=history_buffer,
        history_max_chars=HISTORY_MAX_CHARS,
        use_remote=use_remote_transcription,
        remote_url=remote_transcribe_url,
    )

    for text in transcriptions:
        logger.info(f"[Source] {get_timestamp()} {text}")
        running_log.append(f"{get_timestamp()} [Transcription] {text}")

        if is_awake and 'session_data' in context and context['session_data']:
            context['session_data']['after_transcriptions'].append(text)
            history_buffer.append(text)
        else:
            recent_transcriptions.append(text)

        words = text.strip().split()
        window_size = min(len(words), 2)

        wake_detected = False

        for i in range(len(words) - window_size + 1):
            window = " ".join(words[i : i + window_size])

            wake_results, _ = await run_search(window, "wake", remote_store_url=REMOTE_STORE_URL)
            relevant_wake = [r for r in wake_results if r[1] < WAKE_DISTANCE_THRESHOLD]

            fuzzy_matches = []
            for phrase in WAKE_PHRASES:
                similarity = fuzz.token_set_ratio(window, phrase)
                if similarity >= FUZZY_SIMILARITY_THRESHOLD:
                    fuzzy_matches.append((phrase, similarity))

            if relevant_wake and fuzzy_matches:
                if is_awake:
                    break

                is_awake = True
                wake_start_time = time.time()
                did_inference = False

                await pause_media_players()

                log_message = "[Wake] System awakened by phrase(s): "
                if relevant_wake:
                    for match in relevant_wake:
                        log_message += f"'{match[0]}' with distance: {match[1]}, "
                if fuzzy_matches:
                    for match in fuzzy_matches:
                        log_message += f"'{match[0]}' with similarity: {match[1]}, "
                log_message += f"(source text: '{window}')"

                logger.info(log_message)

                asyncio.create_task(play_wake_sound(WAKE_SOUND_FILE))

                context['session_data'] = {
                    "session_id": str(uuid.uuid4()),
                    "start_time": datetime.now().isoformat(),
                    "wake_phrase": window,
                    "before_transcriptions": list(recent_transcriptions),
                    "after_transcriptions": [],
                    "inferences": [],
                    "commands_executed": [],
                    "vectorstore_results": [],
                    "user_feedback": [],
                    "complete_transcription": "",
                    "source_commands": [],
                }

                wake_detected = True
                break

        if is_awake and ((time.time() - wake_start_time) <= WAKE_TIMEOUT or is_processing):
            amygdala_results, _ = await run_search(text, "amygdala", remote_store_url=REMOTE_STORE_URL)
            accumbens_results, _ = await run_search(text, "na", remote_store_url=REMOTE_STORE_URL)
            hippocampus_results, _ = await run_search(text, "hippocampus", remote_store_url=REMOTE_STORE_URL)

            relevant_amygdala = [r for r in amygdala_results if r[1] < AMY_DISTANCE_THRESHOLD]
            relevant_accumbens = [r for r in accumbens_results if r[1] < NA_DISTANCE_THRESHOLD]
            relevant_hippocampus = [r for r in hippocampus_results if r[1] < HIP_DISTANCE_THRESHOLD]

            context['session_data']['vectorstore_results'].append({
                "timestamp": datetime.now().isoformat(),
                "transcription": text,
                "amygdala_results": amygdala_results,
                "accumbens_results": accumbens_results,
                "hippocampus_results": hippocampus_results,
            })

            if relevant_amygdala and relevant_accumbens:
                is_processing = True

                history_text = get_history_text()
                prompt_text = f"{get_timestamp()} [Prompt] {history_text}"
                running_log.append(prompt_text)

                inference_response = await process_command_text(history_text, context)
                if inference_response:
                    did_inference = True
                    # Reset timeout when a command was actually executed
                    if inference_response.get('commands') and context['args'].execute:
                        wake_start_time = time.time()
                        logger.info("[Wake] Timeout reset due to command execution")
                    context['session_data']['source_commands'].append({
                        "timestamp": datetime.now().isoformat(),
                        "command_text": history_text,
                        "inference_response": inference_response,
                    })
                logger.info(f"[Inference] {inference_response}")
                is_processing = False
            else:
                logger.debug(f"Thresholds not met. Amygdala: {bool(relevant_amygdala)}, Accumbens: {bool(relevant_accumbens)}")
                is_processing = False
        else:
            is_processing = False

    if not is_processing and wake_start_time and (time.time() - wake_start_time) > WAKE_TIMEOUT:
        if is_awake:
            logger.info(f"[Wake] System asleep after {WAKE_TIMEOUT} seconds of inactivity.")
            if not did_inference:
                asyncio.create_task(play_sleep_sound(SLEEP_SOUND_FILE))
            context['session_data']['end_time'] = datetime.now().isoformat()
            context['session_data']['duration'] = time.time() - wake_start_time
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

    with open("/media/mass/scripts/twin/na.txt", "r") as f:
        na_commands = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    context = {
        "REMOTE_STORE_URL": REMOTE_STORE_URL,
        "REMOTE_INFERENCE_URL": REMOTE_INFERENCE_URL,
        "args": args,
        "RISK_THRESHOLD": RISK_THRESHOLD,
        "COOLDOWN_PERIOD": COOLDOWN_PERIOD,
        "TTS_PYTHON_PATH": TTS_PYTHON_PATH,
        "TTS_SCRIPT_PATH": TTS_SCRIPT_PATH,
        "running_log": running_log,
        "AMY_DISTANCE_THRESHOLD": AMY_DISTANCE_THRESHOLD,
        "NA_DISTANCE_THRESHOLD": NA_DISTANCE_THRESHOLD,
        "HIP_DISTANCE_THRESHOLD": HIP_DISTANCE_THRESHOLD,
        "command_queue": command_queue,
        "available_commands": na_commands,
        "session_data": None,
        "QC_REPORT_DIR": "reports",
        "GENERAL_REPORT_FILE": "general_report.txt",  # Added for general report tracking
    }

    os.makedirs(context['QC_REPORT_DIR'], exist_ok=True)

    runner = await start_webserver(context)

    try:
        with sd.InputStream(
            callback=lambda indata, frames, time, status: audio_callback(
                indata, frames, time, status, audio_queue, audio_buffer, small_audio_buffer
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
            logger.info(f"Using {inference_type} for inference, and {transcription_type} for transcription.")

            while True:
                await process_buffer(
                    transcription_model,
                    use_remote_transcription,
                    REMOTE_TRANSCRIBE_URL,
                    context,
                )
    except KeyboardInterrupt:
        logger.info(f"Streaming stopped.")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {str(e)}")
        logger.exception("An error occurred during execution.")
    finally:
        await runner.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
