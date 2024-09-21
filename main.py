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
from pymilvus import connections
from argparse import ArgumentParser
from generator import run_inference
from audio import log_available_audio_devices, audio_callback, play_tts_response
from action import execute_commands, is_in_cooldown
from search import is_similar, run_search
from transcribe import transcribe_audio, init_transcription_model
from reflection import reflect

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
BUFFER_DURATION = 6  # seconds
BUFFER_SIZE = SAMPLE_RATE * BUFFER_DURATION
SMALL_BUFFER_DURATION = 0.2  # 200 milliseconds for the small buffer
SMALL_BUFFER_SIZE = int(SAMPLE_RATE * SMALL_BUFFER_DURATION)
LANGUAGE = "en"
SIMILARITY_THRESHOLD = 85  # Similarity threshold for fuzzy matching
COOLDOWN_PERIOD = 0  # seconds
RISK_THRESHOLD = 0.5  # Risk threshold for command execution
HISTORY_BUFFER_SIZE = 10  # Number of recent transcriptions to keep in history
HISTORY_MAX_CHARS = 4000  # Maximum number of characters to send to the LLM
WAKE_TIMEOUT = 20  # Time in seconds for how long the system remains "awake" after detecting the wake phrase
SILENCE_THRESHOLD = 0.0001  # Threshold for determining if the audio buffer contains silence
CHANNELS = 1
CHUNK_SIZE = 1024

# Define the missing constants
AMY_DISTANCE_THRESHOLD = 0.7
NA_DISTANCE_THRESHOLD = 1.5
HIP_DISTANCE_THRESHOLD = 1.1
WAKE_DISTANCE_THRESHOLD = 0.65

# TTS configuration
TTS_PYTHON_PATH = "/home/andy/venvs/tts-env/bin/python"
TTS_SCRIPT_PATH = "/home/andy/scripts/tts/tts.py"

# Parse command-line arguments
parser = ArgumentParser(description="Live transcription with flexible inference and embedding options.")
parser.add_argument('-e', '--execute', action='store_true', help="Execute the commands returned by the inference model")
parser.add_argument('--local-embed', nargs='?', const='local', help="Use local embeddings. Optionally specify an IP for remote embeddings.")
parser.add_argument('--local-inference', nargs='?', const='127.0.0.1:11434', help="Use local Ollama for inference. Optionally specify an IP:PORT for remote Ollama.")
parser.add_argument('-s', '--silent', action='store_true', help="Disable TTS playback")
parser.add_argument('--store-ip', default="localhost", help="Milvus host IP address (default: localhost)")
parser.add_argument('--source', default=None, help="Manually set the audio source (index or name)")
parser.add_argument('--whisper-model', default="tiny.en", help="Specify the Whisper model size (default: tiny.en)")
parser.add_argument('--remote-transcribe', help="Use remote transcription. Specify the URL for the transcription server.")
args = parser.parse_args()

# Milvus configuration
MILVUS_HOST = args.store_ip
MILVUS_PORT = "19530"

# Connect to Milvus
connections.connect("default", host=MILVUS_HOST, port=MILVUS_PORT)

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
    global is_awake, wake_start_time, is_processing
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

        # Wake Phrase Search
        wake_results, wake_time = await run_search(text, 'wake', args, milvus_host=MILVUS_HOST)
        relevant_wake = [r for r in wake_results if r[1] < WAKE_DISTANCE_THRESHOLD]

        if relevant_wake:
            is_awake = True
            wake_start_time = time.time()
            logger.info(f"[Wake] System awakened by phrase: {relevant_wake[0][0]}")

        if is_awake and ((time.time() - wake_start_time) <= WAKE_TIMEOUT or is_processing):
            # Extend wake time when processing
            if not is_processing:
                wake_start_time = time.time()

            # Start processing
            is_processing = True

            # Search
            search_start = time.time()
            amygdala_results, _ = await run_search(text, 'amygdala', args, milvus_host=MILVUS_HOST)
            accumbens_results, _ = await run_search(text, 'na', args, milvus_host=MILVUS_HOST)
            hippocampus_results, _ = await run_search(text, 'hippocampus', args, milvus_host=MILVUS_HOST)
            search_end = time.time()
            search_time = search_end - search_start

            relevant_amygdala = [r for r in amygdala_results if r[1] < AMY_DISTANCE_THRESHOLD]
            relevant_accumbens = [r for r in accumbens_results if r[1] < NA_DISTANCE_THRESHOLD]
            relevant_hippocampus = [r for r in hippocampus_results if r[1] < HIP_DISTANCE_THRESHOLD]

            if relevant_amygdala and relevant_accumbens:
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
                if args.local_inference:
                    if args.local_inference == '127.0.0.1:11434':
                        logger.info("Using local Ollama for inference.")
                        inference_response, _ = await run_inference(history_text, combined_commands, use_local_inference=True)
                        inference_type = "Local Ollama"
                    else:
                        logger.info(f"Using remote Ollama for inference: {args.local_inference}")
                        inference_response, _ = await run_inference(history_text, combined_commands, use_local_inference=True, ollama_ip=args.local_inference)
                        inference_type = f"Remote Ollama ({args.local_inference})"
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

                    # Execution
                    execution_start = time.time()
                    execution_time = 0
                    if args.execute:
                        if inference_response['risk'] <= RISK_THRESHOLD or (inference_response['risk'] > RISK_THRESHOLD and inference_response.get('confirmed', False)):
                            execution_time = await execute_commands(inference_response['commands'], COOLDOWN_PERIOD)
                            running_log.append(f"{get_timestamp()} [Command] {inference_response['commands']}")
                        else:
                            logger.warning(f"[Warning] {get_timestamp()} Commands not executed. Risk: {inference_response['risk']}. Confirmation required.")
                    execution_end = time.time()
                    execution_time = execution_end - execution_start

                    # TTS
                    tts_start = time.time()
                    tts_time = await play_tts_response(inference_response['response'],
                                                       tts_python_path=TTS_PYTHON_PATH,
                                                       tts_script_path=TTS_SCRIPT_PATH,
                                                       silent=args.silent)
                    tts_end = time.time()
                    tts_time = tts_end - tts_start

                    total_time = time.time() - process_start
                    logger.info(f"[Timing] {get_timestamp()} Total: {total_time:.4f}s, Transcription: {transcription_time:.4f}s, Search: {search_time:.4f}s, Inference: {inference_time:.4f}s, Execution: {execution_time:.4f}s, TTS: {tts_time:.4f}s")
                else:
                    logger.error(f"Unable to get or parse {inference_type} inference.")

                # Processing complete
                is_processing = False
            else:
                logger.debug(f"Thresholds not met. Amygdala: {bool(relevant_amygdala)}, Accumbens: {bool(relevant_accumbens)}")
                is_processing = False  # Ensure processing flag is reset
        else:
            is_processing = False  # Ensure processing flag is reset

    # Reset awake state after timeout if not processing
    if not is_processing and wake_start_time and (time.time() - wake_start_time) > WAKE_TIMEOUT:
        is_awake = False

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
    transcription_model = None if use_remote_transcription else init_transcription_model(args.whisper_model, DEVICE_TYPE, COMPUTE_TYPE)

    try:
        with sd.InputStream(callback=lambda indata, frames, time, status: audio_callback(indata, frames, time, status, audio_queue, audio_buffer, small_audio_buffer),
                            channels=CHANNELS, samplerate=SAMPLE_RATE,
                            blocksize=CHUNK_SIZE, device=input_device, dtype='float32'):
            print(f"{get_timestamp()} Streaming started... Press Ctrl+C to stop.")
            embed_type = "local" if args.local_embed == 'local' else f"remote ({args.local_embed})" if args.local_embed else "remote"
            inference_type = "local Ollama" if args.local_inference == '127.0.0.1:11434' else f"remote Ollama ({args.local_inference})" if args.local_inference else "GPT-4o"
            transcription_type = f"remote ({args.remote_transcribe})" if use_remote_transcription else f"local ({args.whisper_model})"
            print(f"Using {embed_type} embeddings, {inference_type} for inference, and {transcription_type} for transcription.")
            print(f"TTS playback is {'disabled' if args.silent else 'enabled'}.")

            reflection_task = asyncio.create_task(reflection_loop())

            while True:
                await process_buffer(transcription_model, use_remote_transcription, args.remote_transcribe)
                await asyncio.sleep(0.1)
    except KeyboardInterrupt:
        print(f"{get_timestamp()} Streaming stopped.")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {str(e)}")
        logger.exception("An error occurred during execution.")
    finally:
        connections.disconnect("default")

if __name__ == "__main__":
    asyncio.run(main())
