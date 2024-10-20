# main.py

import logging
from collections import deque
from datetime import datetime
import asyncio
import queue
import re
import numpy as np
import sounddevice as sd
import json
import torch
import time
from faster_whisper import WhisperModel
from argparse import ArgumentParser
from generator import run_inference
from audio import (
    log_available_audio_devices,
    audio_callback,
    play_tts_response,
    play_wake_sound,
    play_sleep_sound,
)
from action import execute_commands, is_in_cooldown
from search import is_similar, run_search
from transcribe import transcribe_audio, init_transcription_model
from reflection import reflect
from rapidfuzz import fuzz  # Added for fuzzy matching

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("twin")

# Suppress logging from other libraries
for name in logging.root.manager.loggerDict:
    if name != "twin":
        logging.getLogger(name).setLevel(logging.ERROR)

# Suppress Whisper logs to ERROR level
logging.getLogger("faster_whisper").setLevel(logging.ERROR)

# Configuration Parameters
REFLECTION_INTERVAL = 3000  # Set the reflection interval in seconds
DEVICE_TYPE = "cuda" if torch.cuda.is_available() else "cpu"
COMPUTE_TYPE = "float16" if DEVICE_TYPE == "cuda" else "float32"
SAMPLE_RATE = 16000
BUFFER_DURATION = 3  # seconds
BUFFER_SIZE = SAMPLE_RATE * BUFFER_DURATION
SMALL_BUFFER_DURATION = 0.2  # 200 milliseconds for the small buffer
SMALL_BUFFER_SIZE = int(SAMPLE_RATE * SMALL_BUFFER_DURATION)
LANGUAGE = "en"
SIMILARITY_THRESHOLD = 85
COOLDOWN_PERIOD = 0  # seconds
RISK_THRESHOLD = 0.5  # Risk threshold for command execution
HISTORY_BUFFER_SIZE = 10  # Number of recent transcriptions to keep in history
HISTORY_MAX_CHARS = 4000  # Maximum number of characters to send to the LLM
WAKE_TIMEOUT = 16  # Time in seconds for how long the system remains "awake" after detecting the wake phrase
SILENCE_THRESHOLD = 0.0001  # Threshold for determining if the audio buffer contains silence
CHANNELS = 1
CHUNK_SIZE = 1024

# Define the missing constants
AMY_DISTANCE_THRESHOLD = 0.7
NA_DISTANCE_THRESHOLD = 1.4
HIP_DISTANCE_THRESHOLD = 1.1
WAKE_DISTANCE_THRESHOLD = 0.30

# TTS configuration
TTS_PYTHON_PATH = "/home/andy/venvs/tts-env/bin/python"
TTS_SCRIPT_PATH = "/home/andy/scripts/tts/tts.py"

# Wake and Sleep Sound Configuration
WAKE_SOUND_FILE = "/media/mass/scripts/twin/wake.wav"  # Ensure this file exists
SLEEP_SOUND_FILE = "/media/mass/scripts/twin/sleep.wav"  # Ensure this file exists

# Define the wake phrases and similarity threshold
WAKE_PHRASES = ["Hey computer.", "Hey twin"]
FUZZY_SIMILARITY_THRESHOLD = 60

# Parse command-line arguments
parser = ArgumentParser(description="Live transcription with flexible inference and embedding options.")
parser.add_argument('-e', '--execute', action='store_true', help="Execute the commands returned by the inference model")
parser.add_argument('--remote-inference', help="Use remote inference. Specify the full URL for the inference server.")
parser.add_argument('--remote-store', help="Specify the URL for the vector store server.")
parser.add_argument('-s', '--silent', action='store_true', help="Disable TTS playback")
parser.add_argument('--source', default=None, help="Manually set the audio source (index or name)")
parser.add_argument('--whisper-model', default="tiny.en", help="Specify the Whisper model size (default: tiny.en)")
parser.add_argument('--remote-transcribe', help="Use remote transcription. Specify the URL for the transcription server.")
args = parser.parse_args()

# Store the remote URLs
REMOTE_STORE_URL = args.remote_store
REMOTE_INFERENCE_URL = args.remote_inference
REMOTE_TRANSCRIBE_URL = args.remote_transcribe

# Circular buffer for audio data
audio_buffer = deque(maxlen=BUFFER_SIZE)
small_audio_buffer = deque(maxlen=SMALL_BUFFER_SIZE)  # Smaller buffer for threshold detection
audio_queue = queue.Queue()  # Initialize audio_queue
recent_transcriptions = deque(maxlen=10)  # Buffer for recent transcriptions
history_buffer = deque(maxlen=HISTORY_BUFFER_SIZE)  # Buffer for extended history
running_log = []  # Running log to capture all events

is_awake = False
wake_start_time = None
is_processing = False  # Flag to indicate if the system is processing

# Flag to track if any inference was done during the awake period
did_inference = False

def get_timestamp():
    USE_TIMESTAMP = False
    if USE_TIMESTAMP:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    else:
        return ""

def get_history_text():
    history_text = " ".join(history_buffer)
    if len(history_text) > HISTORY_MAX_CHARS:
        history_text = history_text[-HISTORY_MAX_CHARS:]
        # Trim to the nearest word
        history_text = history_text[history_text.index(' ') + 1:]
    return history_text

def calculate_rms(audio_data):
    """Calculate the Root Mean Square (RMS) of the audio data."""
    if len(audio_data) == 0:
        return np.nan  # Return np.nan if the buffer is empty
    return np.sqrt(np.mean(np.square(audio_data)))

async def process_buffer(transcription_model, use_remote_transcription, remote_transcribe_url):
    global is_awake, wake_start_time, is_processing, did_inference
    process_start = time.time()

    # Convert small buffer to a NumPy array and calculate RMS
    small_audio_data = np.array(list(small_audio_buffer), dtype=np.float32)
    small_rms = calculate_rms(small_audio_data)

    if small_rms < SILENCE_THRESHOLD and not is_awake:
        return  # Skip processing if below the silence threshold and not awake

    # Now use the larger buffer for transcription
    audio_data = np.array(list(audio_buffer), dtype=np.float32)
    if len(audio_data) == 0:
        return

    rms = calculate_rms(audio_data)

    if rms < SILENCE_THRESHOLD:
        return

    # Transcription
    transcription_start = time.time()
    transcriptions, _ = await transcribe_audio(
        model=transcription_model,
        audio_data=audio_data,
        language=LANGUAGE,
        similarity_threshold=SIMILARITY_THRESHOLD,
        recent_transcriptions=recent_transcriptions,
        history_buffer=history_buffer,
        history_max_chars=HISTORY_MAX_CHARS,
        use_remote=use_remote_transcription,
        remote_url=remote_transcribe_url
    )
    transcription_end = time.time()
    transcription_time = transcription_end - transcription_start

    for text in transcriptions:
        logger.info(f"[Source] {get_timestamp()} {text}")
        running_log.append(f"{get_timestamp()} [Transcription] {text}")

        # Iterate through the entire transcription with a sliding window
        words = text.strip().split()
        window_size = min(len(words), 2)  # Adjusted to match the wake phrases

        wake_detected = False  # Flag to indicate if wake phrase is detected in this transcription

        for i in range(len(words) - window_size + 1):
            window = ' '.join(words[i:i+window_size])

            # Wake Phrase Search using vector search
            wake_results, wake_time = await run_search(window, 'wake', remote_store_url=REMOTE_STORE_URL)
            relevant_wake = [r for r in wake_results if r[1] < WAKE_DISTANCE_THRESHOLD]

            # Fuzzy Match using RapidFuzz for all wake phrases
            fuzzy_matches = []
            for phrase in WAKE_PHRASES:
                similarity = fuzz.token_set_ratio(window, phrase)
                if similarity >= FUZZY_SIMILARITY_THRESHOLD:
                    fuzzy_matches.append((phrase, similarity))

            if relevant_wake:
                if is_awake:
                    break

                is_awake = True

                if not fuzzy_matches:
                    break
                    
                wake_start_time = time.time()
                did_inference = False  # Reset did_inference when system wakes up

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

                wake_detected = True  # Mark that wake has been detected
                break  # Exit the loop after detecting wake phrase

        if wake_detected:
            continue  # Skip further processing for this transcription as wake has been handled

        if is_awake and ((time.time() - wake_start_time) <= WAKE_TIMEOUT or is_processing):

            # Search
            search_start = time.time()
            amygdala_results, _ = await run_search(text, 'amygdala', remote_store_url=REMOTE_STORE_URL)
            accumbens_results, _ = await run_search(text, 'na', remote_store_url=REMOTE_STORE_URL)
            hippocampus_results, _ = await run_search(text, 'hippocampus', remote_store_url=REMOTE_STORE_URL)
            search_end = time.time()
            search_time = search_end - search_start

            relevant_amygdala = [r for r in amygdala_results if r[1] < AMY_DISTANCE_THRESHOLD]
            relevant_accumbens = [r for r in accumbens_results if r[1] < NA_DISTANCE_THRESHOLD]
            relevant_hippocampus = [r for r in hippocampus_results if r[1] < HIP_DISTANCE_THRESHOLD]

            if relevant_amygdala and relevant_accumbens:
                # Start processing
                wake_start_time = time.time()  # Reset the wake start time
                is_processing = True

                for snippet, distance in relevant_amygdala:
                    logger.info(f"[Amygdala] {get_timestamp()} {snippet} | {distance}")

                accumbens_commands = [snippet for snippet, _ in relevant_accumbens]

                for snippet, distance in relevant_accumbens:
                    logger.info(f"[Accumbens] {get_timestamp()} {snippet} | {distance}")

                if relevant_hippocampus:
                    hippocampus_commands = [snippet for snippet, _ in relevant_hippocampus]
                    for snippet, distance in relevant_hippocampus:
                        logger.info(f"[Hippocampus] {get_timestamp()} {snippet} | {distance}")
                else:
                    hippocampus_commands = []

                combined_commands = accumbens_commands + hippocampus_commands

                # Use the extended history for inference
                history_text = get_history_text()
                prompt_text = f"{get_timestamp()} [Prompt] {history_text}"
                running_log.append(prompt_text)

                # Inference
                inference_start = time.time()
                if REMOTE_INFERENCE_URL:
                    logger.info(f"Using remote inference: {REMOTE_INFERENCE_URL}")
                    inference_response, _ = await run_inference(
                        history_text,
                        combined_commands,
                        use_remote_inference=True,
                        inference_url=REMOTE_INFERENCE_URL,
                    )
                    inference_type = f"Remote Inference ({REMOTE_INFERENCE_URL})"
                else:
                    logger.info("Using GPT-4o for inference.")
                    inference_response, _ = await run_inference(history_text, combined_commands)
                    inference_type = "GPT-4o"
                inference_end = time.time()
                inference_time = inference_end - inference_start

                running_log.append(f"{get_timestamp()} [Response] {json.dumps(inference_response, indent=2)}")

                # Clear the audio buffer after processing
                audio_buffer.clear()

                # Ensure the audio_queue is also cleared
                with audio_queue.mutex:
                    audio_queue.queue.clear()

                if inference_response:
                    logger.info(f"[{inference_type}] {json.dumps(inference_response, indent=2)}")
                    did_inference = True  # Set did_inference to True since an inference was done

                    # Execution
                    execution_start = time.time()
                    execution_time = 0
                    if args.execute:
                        if inference_response['risk'] <= RISK_THRESHOLD or (
                            inference_response['risk'] > RISK_THRESHOLD and inference_response.get('confirmed', False)
                        ):
                            execution_time = await execute_commands(inference_response['commands'], COOLDOWN_PERIOD)
                            running_log.append(f"{get_timestamp()} [Command] {inference_response['commands']}")
                        else:
                            logger.warning(
                                f"[Warning] {get_timestamp()} Commands not executed. Risk: {inference_response['risk']}. "
                                f"Confirmation required."
                            )
                    execution_end = time.time()
                    execution_time = execution_end - execution_start

                    # TTS
                    tts_start = time.time()
                    # Uncomment the following lines if TTS is required
                    # tts_time = await play_tts_response(
                    #     inference_response['response'],
                    #     tts_python_path=TTS_PYTHON_PATH,
                    #     tts_script_path=TTS_SCRIPT_PATH,
                    #     silent=args.silent,
                    # )
                    tts_end = time.time()
                    tts_time = tts_end - tts_start

                    total_time = time.time() - process_start
                    logger.info(
                        f"[Timing] {get_timestamp()} Total: {total_time:.4f}s, Transcription: {transcription_time:.4f}s, "
                        f"Search: {search_time:.4f}s, Inference: {inference_time:.4f}s, "
                        f"Execution: {execution_time:.4f}s, TTS: {tts_time:.4f}s"
                    )
                else:
                    logger.error(f"Unable to get or parse {inference_type} inference.")

                # Processing complete
                is_processing = False
            else:
                logger.debug(
                    f"Thresholds not met. Amygdala: {bool(relevant_amygdala)}, Accumbens: {bool(relevant_accumbens)}"
                )
                is_processing = False  # Ensure processing flag is reset
        else:
            is_processing = False  # Ensure processing flag is reset

    # Reset awake state after timeout if not processing
    if not is_processing and wake_start_time and (time.time() - wake_start_time) > WAKE_TIMEOUT:
        if is_awake:
            logger.info(f"[Wake] System asleep after {WAKE_TIMEOUT} seconds.")
            if not did_inference:
                # Play Sleep Sound Asynchronously
                asyncio.create_task(play_sleep_sound(SLEEP_SOUND_FILE))
        is_awake = False
        did_inference = False  # Reset did_inference for next awake cycle

async def reflection_loop():
    while True:
        await asyncio.sleep(REFLECTION_INTERVAL)
        if running_log:  # Reflect only if there is something in the log
            reflection_data = await reflect(running_log)
            logger.info(f"Reflection report: {json.dumps(reflection_data, indent=2)}")
            running_log.clear()  # Clear the log after reflection

async def main():
    log_available_audio_devices()
    devices = sd.query_devices()
    input_device = ""

    if args.source:
        if args.source.isdigit():
            input_device = int(args.source)
        else:
            for i, device in enumerate(devices):
                if args.source.lower() in device['name'].lower():
                    input_device = i
                    break
        if input_device == "":
            logger.error(f"Specified audio source '{args.source}' not found.")
            return

    use_remote_transcription = args.remote_transcribe is not None
    transcription_model = None if use_remote_transcription else init_transcription_model(
        args.whisper_model, DEVICE_TYPE, COMPUTE_TYPE
    )

    try:
        with sd.InputStream(
            callback=lambda indata, frames, time, status: audio_callback(
                indata, frames, time, status, audio_queue, audio_buffer, small_audio_buffer
            ),
            channels=CHANNELS,
            samplerate=SAMPLE_RATE,
            blocksize=CHUNK_SIZE,
            device=input_device,
            dtype='float32',
        ):
            print(f"{get_timestamp()} Streaming started... Press Ctrl+C to stop.")
            inference_type = f"remote inference ({REMOTE_INFERENCE_URL})" if REMOTE_INFERENCE_URL else "GPT-4o"
            transcription_type = (
                f"remote ({REMOTE_TRANSCRIBE_URL})" if use_remote_transcription else f"local ({args.whisper_model})"
            )
            print(f"Using {inference_type} for inference, and {transcription_type} for transcription.")
            print(f"TTS playback is {'disabled' if args.silent else 'enabled'}.")
    
            reflection_task = asyncio.create_task(reflection_loop())
    
            while True:
                await process_buffer(transcription_model, use_remote_transcription, REMOTE_TRANSCRIBE_URL)
                await asyncio.sleep(0.1)
    except KeyboardInterrupt:
        print(f"{get_timestamp()} Streaming stopped.")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {str(e)}")
        logger.exception("An error occurred during execution.")
    finally:
        pass  # Cleanup if necessary

if __name__ == "__main__":
    asyncio.run(main())
