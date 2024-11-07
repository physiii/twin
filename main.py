# main.py

import logging
from collections import deque
from datetime import datetime
import asyncio
import queue
import numpy as np
import sounddevice as sd
import json
import torch
import time
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
from reflection import reflect
from rapidfuzz import fuzz

from webserver import start_webserver  # Import the webserver module
from command_processor import (
    process_command_text,
    process_mqtt_event_data,
)  # Import the command processor

import aiomqtt  # Import aiomqtt for MQTT functionality

# Initialize logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("twin")

# Suppress Whisper logs to ERROR level
logging.getLogger("faster_whisper").setLevel(logging.ERROR)

# Configuration Parameters
REFLECTION_INTERVAL = 3000  # Reflection interval in seconds
DEVICE_TYPE = "cuda" if torch.cuda.is_available() else "cpu"
COMPUTE_TYPE = "float16" if DEVICE_TYPE == "cuda" else "float32"
SAMPLE_RATE = 16000
BUFFER_DURATION = 3  # For responsiveness
BUFFER_SIZE = SAMPLE_RATE * BUFFER_DURATION
SMALL_BUFFER_DURATION = 0.2  # 200 milliseconds
SMALL_BUFFER_SIZE = int(SAMPLE_RATE * SMALL_BUFFER_DURATION)
LANGUAGE = "en"
SIMILARITY_THRESHOLD = 85
COOLDOWN_PERIOD = 0  # seconds
RISK_THRESHOLD = 0.5  # Risk threshold for command execution
HISTORY_BUFFER_SIZE = 4  # Number of recent transcriptions to keep
HISTORY_MAX_CHARS = 4000  # Max chars to send to the LLM
WAKE_TIMEOUT = 24  # Time in seconds the system remains "awake" after wake phrase
SILENCE_THRESHOLD = 0.0001  # Threshold for silence detection
CHANNELS = 1
CHUNK_SIZE = 1024

# Define thresholds
AMY_DISTANCE_THRESHOLD = 1.0
NA_DISTANCE_THRESHOLD = 1.4
HIP_DISTANCE_THRESHOLD = 1.1
WAKE_DISTANCE_THRESHOLD = 0.30
CONDITIONS_DISTANCE_THRESHOLD = 1.0
MODES_DISTANCE_THRESHOLD = 1.0

# TTS configuration
TTS_PYTHON_PATH = "/home/andy/venvs/tts-env/bin/python"
TTS_SCRIPT_PATH = "/home/andy/scripts/tts/tts.py"

# Wake and Sleep Sound Configuration
WAKE_SOUND_FILE = "/media/mass/scripts/twin/wake.wav"
SLEEP_SOUND_FILE = "/media/mass/scripts/twin/sleep.wav"

# Define the wake phrases and similarity threshold
WAKE_PHRASES = ["Hey computer.", "Hey twin"]
FUZZY_SIMILARITY_THRESHOLD = 60

# MQTT Configuration
MQTT_BROKER_HOST = "192.168.1.42"
MQTT_BROKER_PORT = 1883
MQTT_USERNAME = "andy"
MQTT_PASSWORD = "qscwdvpk"
MQTT_TOPICS = ["radar"]

# Parse command-line arguments
parser = ArgumentParser(
    description="Live transcription with flexible inference and embedding options."
)
parser.add_argument(
    "-e",
    "--execute",
    action="store_true",
    help="Execute the commands returned by the inference model",
)
parser.add_argument(
    "--remote-inference",
    help="Use remote inference. Specify the full URL for the inference server.",
)
parser.add_argument(
    "--remote-store", help="Specify the URL for the vector store server."
)
parser.add_argument(
    "-s", "--silent", action="store_true", help="Disable TTS playback"
)
parser.add_argument(
    "--source", default=None, help="Manually set the audio source (index or name)"
)
parser.add_argument(
    "--whisper-model",
    default="tiny.en",
    help="Specify the Whisper model size (default: tiny.en)",
)
parser.add_argument(
    "--remote-transcribe",
    help="Use remote transcription. Specify the URL for the transcription server.",
)
args = parser.parse_args()

# Store the remote URLs
REMOTE_STORE_URL = args.remote_store
REMOTE_INFERENCE_URL = args.remote_inference
REMOTE_TRANSCRIBE_URL = args.remote_transcribe

# Circular buffers for audio data and transcriptions
audio_buffer = deque(maxlen=BUFFER_SIZE)
small_audio_buffer = deque(maxlen=SMALL_BUFFER_SIZE)
audio_queue = queue.Queue()
recent_transcriptions = deque(maxlen=10)
history_buffer = deque(maxlen=HISTORY_BUFFER_SIZE)
running_log = []

# Global state variables
is_awake = False
wake_start_time = None
is_processing = False
did_inference = False

# Command queue for external commands
command_queue = asyncio.Queue()

def get_timestamp():
    """Returns the current timestamp as a string."""
    USE_TIMESTAMP = False
    if USE_TIMESTAMP:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    else:
        return ""

def get_history_text():
    """Retrieves and trims the history text for inference."""
    history_text = " ".join(history_buffer)
    if len(history_text) > HISTORY_MAX_CHARS:
        history_text = history_text[-HISTORY_MAX_CHARS:]
        history_text = history_text[history_text.index(" ") + 1 :]
    return history_text

def calculate_rms(audio_data):
    """Calculates the root mean square of the audio data."""
    if len(audio_data) == 0:
        return np.nan
    return np.sqrt(np.mean(np.square(audio_data)))

async def mqtt_event_loop(context):
    """Handles MQTT events asynchronously."""
    try:
        logger.info("[MQTT] Connecting to MQTT broker...")
        # Connect to the MQTT broker with authentication
        async with aiomqtt.Client(
            hostname=MQTT_BROKER_HOST,
            port=MQTT_BROKER_PORT,
            username=MQTT_USERNAME,
            password=MQTT_PASSWORD,
        ) as client:
            logger.info("[MQTT] Connected to MQTT broker.")
            # Subscribe to the specified topics
            for topic in MQTT_TOPICS:
                await client.subscribe(topic)
                logger.info(f"[MQTT] Subscribed to MQTT topic: '{topic}'")

            # Use client.messages as an async iterator
            async for message in client.messages:
                topic = message.topic.value  # Use .value to get the topic string
                payload = message.payload.decode()
                logger.info(f"[MQTT] Received MQTT message on topic '{topic}': {payload}")
                try:
                    event_data = json.loads(payload)
                    await process_mqtt_event_data(event_data, context)
                except json.JSONDecodeError:
                    logger.error(f"[MQTT] Invalid JSON in MQTT message payload: {payload}")
                except Exception as e:
                    logger.exception(f"[MQTT] Error processing MQTT message: {e}")
    except aiomqtt.MQTTException as error:
        logger.error(f"[MQTT] MQTT connection error: {error}")
    except Exception as e:
        logger.exception(f"[MQTT] Unexpected error in MQTT event loop: {e}")

async def process_buffer(transcription_model, use_remote_transcription, remote_transcribe_url, context):
    """Processes the audio buffer for transcription and inference."""
    await asyncio.sleep(0.1)
    global is_awake, wake_start_time, is_processing, did_inference
    process_start = time.time()

    # Check for external commands in the command queue
    if not command_queue.empty():
        command_text = await command_queue.get()
        logger.info(f"[Command] Received external command: {command_text}")
        is_awake = True
        wake_start_time = time.time()
        did_inference = False

        inference_response = await process_command_text(command_text, context)
        logger.info(f"[Inference] {inference_response}")
        if inference_response:
            did_inference = True
        return

    # Audio processing
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

    # Transcription
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

        words = text.strip().split()
        window_size = min(len(words), 2)

        wake_detected = False

        for i in range(len(words) - window_size + 1):
            window = " ".join(words[i : i + window_size])

            # Wake Phrase Search using vector search
            wake_results, _ = await run_search(
                window, "wake", remote_store_url=REMOTE_STORE_URL
            )
            relevant_wake = [r for r in wake_results if r[1] < WAKE_DISTANCE_THRESHOLD]

            # Fuzzy Match using RapidFuzz for all wake phrases
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

                # Build the log message
                log_message = "[Wake] System awakened by phrase(s): "
                if relevant_wake:
                    for match in relevant_wake:
                        log_message += f"'{match[0]}' with distance: {match[1]}, "
                if fuzzy_matches:
                    for match in fuzzy_matches:
                        log_message += f"'{match[0]}' with similarity: {match[1]}, "
                log_message += f"(source text: '{window}')"

                logger.info(log_message)

                # Play Wake Sound Asynchronously
                asyncio.create_task(play_wake_sound(WAKE_SOUND_FILE))

                wake_detected = True
                break

        if is_awake and ((time.time() - wake_start_time) <= WAKE_TIMEOUT or is_processing):

            # Search
            amygdala_results, _ = await run_search(text, "amygdala", remote_store_url=REMOTE_STORE_URL)
            accumbens_results, _ = await run_search(text, "na", remote_store_url=REMOTE_STORE_URL)
            hippocampus_results, _ = await run_search(text, "hippocampus", remote_store_url=REMOTE_STORE_URL)
            conditions_results, _ = await run_search(text, "conditions", remote_store_url=REMOTE_STORE_URL)
            modes_results, _ = await run_search(text, "modes", remote_store_url=REMOTE_STORE_URL)

            relevant_amygdala = [r for r in amygdala_results if r[1] < AMY_DISTANCE_THRESHOLD]
            relevant_accumbens = [r for r in accumbens_results if r[1] < NA_DISTANCE_THRESHOLD]
            relevant_hippocampus = [r for r in hippocampus_results if r[1] < HIP_DISTANCE_THRESHOLD]
            relevant_conditions = [r for r in conditions_results if r[1] < CONDITIONS_DISTANCE_THRESHOLD]
            relevant_modes = [r for r in modes_results if r[1] < MODES_DISTANCE_THRESHOLD]

            if relevant_amygdala and relevant_accumbens:
                wake_start_time = time.time()
                is_processing = True

                history_text = get_history_text()
                prompt_text = f"{get_timestamp()} [Prompt] {history_text}"
                running_log.append(prompt_text)

                inference_response = await process_command_text(history_text, context)
                logger.info(f"[Inference] {inference_response}")
                if inference_response:
                    did_inference = True
                is_processing = False
            else:
                logger.debug(
                    f"Thresholds not met. Amygdala: {bool(relevant_amygdala)}, Accumbens: {bool(relevant_accumbens)}"
                )
                is_processing = False
        else:
            is_processing = False

    # Reset awake state after timeout if not processing
    if not is_processing and wake_start_time and (time.time() - wake_start_time) > WAKE_TIMEOUT:
        if is_awake:
            logger.info(f"[Wake] System asleep after {WAKE_TIMEOUT} seconds.")
            if not did_inference:
                asyncio.create_task(play_sleep_sound(SLEEP_SOUND_FILE))
        is_awake = False
        did_inference = False

async def reflection_loop():
    """Periodically performs reflection based on the running log."""
    while True:
        await asyncio.sleep(REFLECTION_INTERVAL)
        if running_log:
            reflection_data = await reflect(running_log)
            logger.info(f"Reflection report: {json.dumps(reflection_data, indent=2)}")
            running_log.clear()

async def main():
    """Main function to start the voice assistant."""
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

    # Load commands from na.txt to build the commands vector store
    with open("/media/mass/scripts/twin/na.txt", "r") as f:
        na_commands = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    # Create context for shared variables
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
        "CONDITIONS_DISTANCE_THRESHOLD": CONDITIONS_DISTANCE_THRESHOLD,
        "MODES_DISTANCE_THRESHOLD": MODES_DISTANCE_THRESHOLD,
        "command_queue": command_queue,
        "current_mode": "Wake Mode",
        "available_commands": na_commands,
    }

    # Initialize web server
    runner = await start_webserver(context)

    # Start MQTT event loop
    mqtt_task = asyncio.create_task(mqtt_event_loop(context))

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
            print(f"{get_timestamp()} Streaming started... Press Ctrl+C to stop.")
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
            print(f"Using {inference_type} for inference, and {transcription_type} for transcription.")
            print(f"TTS playback is {'disabled' if args.silent else 'enabled'}.")

            reflection_task = asyncio.create_task(reflection_loop())

            while True:
                await process_buffer(
                    transcription_model,
                    use_remote_transcription,
                    REMOTE_TRANSCRIBE_URL,
                    context,
                )
    except KeyboardInterrupt:
        print(f"{get_timestamp()} Streaming stopped.")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {str(e)}")
        logger.exception("An error occurred during execution.")
    finally:
        await runner.cleanup()
        mqtt_task.cancel()

if __name__ == "__main__":
    asyncio.run(main())
