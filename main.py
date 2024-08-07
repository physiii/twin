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
from pymilvus import connections, Collection
from argparse import ArgumentParser

# Import inference functions
from inference import run_inference

# Import audio utility functions
from audio import log_available_audio_devices, audio_callback, play_tts_response

# Import command utility functions
from command import execute_commands, is_in_cooldown

# Import search utility functions
from search import is_similar, run_search

# Logging configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("twin")

# Suppress logging from all libraries
for name in logging.root.manager.loggerDict:
    logging.info("log name: " + name)
    if name != "twin":
        logging.getLogger(name).setLevel(logging.ERROR)

logging.getLogger("faster_whisper").setLevel(logging.ERROR)

# Parameters
DEVICE_TYPE = "cuda" if torch.cuda.is_available() else "cpu"
COMPUTE_TYPE = "float16" if DEVICE_TYPE == "cuda" else "float32"
SAMPLE_RATE = 16000
BUFFER_DURATION = 8  # seconds
BUFFER_SIZE = SAMPLE_RATE * BUFFER_DURATION
LANGUAGE = "en"
AMY_DISTANCE_THRESHOLD = 1.0
NA_DISTANCE_THRESHOLD = 1.5
HIP_DISTANCE_THRESHOLD = 1.1
SIMILARITY_THRESHOLD = 85  # Similarity threshold for fuzzy matching
COOLDOWN_PERIOD = 0  # seconds
RISK_THRESHOLD = 0.2

# New constants for extended history
HISTORY_BUFFER_SIZE = 5  # Number of recent transcriptions to keep in history
HISTORY_MAX_CHARS = 400  # Maximum number of characters to send to the LLM

# Audio parameters
CHANNELS = 1
CHUNK_SIZE = 1024

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
args = parser.parse_args()

# Initialize models
model = WhisperModel(args.whisper_model, device=DEVICE_TYPE, compute_type=COMPUTE_TYPE)
if DEVICE_TYPE == "cuda":
    torch.cuda.synchronize()

# Milvus configuration
MILVUS_HOST = args.store_ip
MILVUS_PORT = "19530"

# Connect to Milvus
connections.connect("default", host=MILVUS_HOST, port=MILVUS_PORT)

# Circular buffer for audio data
audio_buffer = deque(maxlen=BUFFER_SIZE)
audio_queue = queue.Queue()
recent_transcriptions = deque(maxlen=10)  # Buffer for recent transcriptions
history_buffer = deque(maxlen=HISTORY_BUFFER_SIZE)  # New buffer for extended history

def get_timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def get_history_text():
    history_text = " ".join(history_buffer)
    if len(history_text) > HISTORY_MAX_CHARS:
        history_text = history_text[-HISTORY_MAX_CHARS:]
        # Trim to the nearest word
        history_text = history_text[history_text.index(' ')+1:]
    return history_text

def clean_transcription(text):
    text = re.sub(r'\[.*?\]', '', text)
    text = re.sub(r'\(.*?\)', '', text)
    return text.strip()

async def process_buffer():
    process_start = time.time()
    audio_data = np.array(list(audio_buffer), dtype=np.float32)
    if len(audio_data) == 0:
        return

    transcription_start = time.time()
    segments, _ = model.transcribe(audio_data, language=LANGUAGE, suppress_tokens=[2, 3], suppress_blank=True, condition_on_previous_text=True, no_speech_threshold=0.5)
    transcription_time = time.time() - transcription_start
    
    for segment in segments:
        text = clean_transcription(segment.text.strip())
        if not text or is_similar(text, recent_transcriptions, SIMILARITY_THRESHOLD):
            continue

        recent_transcriptions.append(text)
        history_buffer.append(text)
        logger.info(f"[Source] {get_timestamp()} {text}")

        amygdala_results, amygdala_time = await run_search(text, 'amygdala', args, milvus_host=MILVUS_HOST)
        accumbens_results, accumbens_time = await run_search(text, 'na', args, milvus_host=MILVUS_HOST)
        hippocampus_results, hippocampus_time = await run_search(text, 'hippocampus', args, milvus_host=MILVUS_HOST)
        
        relevant_amygdala = [r for r in amygdala_results if r[1] < AMY_DISTANCE_THRESHOLD]
        relevant_accumbens = [r for r in accumbens_results if r[1] < NA_DISTANCE_THRESHOLD]
        relevant_hippocampus = [r for r in hippocampus_results if r[1] < HIP_DISTANCE_THRESHOLD]
        
        if relevant_amygdala:
            for snippet, distance in relevant_amygdala:
                logger.info(f"[Amygdala] {get_timestamp()} {snippet} | {distance}")
            
            if relevant_accumbens or relevant_hippocampus:
                accumbens_commands = [snippet for snippet, _ in relevant_accumbens]
                hippocampus_commands = [snippet for snippet, _ in relevant_hippocampus]
                
                for snippet, distance in relevant_accumbens:
                    logger.info(f"[Accumbens] {get_timestamp()} {snippet} | {distance}")
                
                for snippet, distance in relevant_hippocampus:
                    logger.info(f"[Hippocampus] {get_timestamp()} {snippet} | {distance}")
                
                combined_commands = accumbens_commands
                
                # Use the extended history for inference
                history_text = get_history_text()
                
                if args.local_inference:
                    if args.local_inference == '127.0.0.1:11434':
                        inference_response, inference_time = await run_inference(history_text, combined_commands, use_local_inference=True)
                        inference_type = "Local Ollama"
                    else:
                        inference_response, inference_time = await run_inference(history_text, combined_commands, use_local_inference=True, ollama_ip=args.local_inference)
                        inference_type = f"Remote Ollama ({args.local_inference})"
                else:
                    inference_response, inference_time = await run_inference(history_text, combined_commands)
                    inference_type = "GPT-4o"
                
                audio_buffer.clear()
                with audio_queue.mutex:
                    audio_queue.queue.clear()

                if inference_response:
                    logger.info(f"[{inference_type}] {get_timestamp()} {json.dumps(inference_response, indent=2)}")
                    
                    execution_time = 0
                    if args.execute:
                        if inference_response['risk'] <= RISK_THRESHOLD or (inference_response['risk'] > RISK_THRESHOLD and inference_response.get('confirmed', False)):
                            execution_time = await execute_commands(inference_response['commands'], COOLDOWN_PERIOD)
                        else:
                            logger.warning(f"[Warning] {get_timestamp()} Commands not executed. Risk: {inference_response['risk']}. Confirmation required.")
                    
                    tts_time = await play_tts_response(inference_response['response'], 
                                                       tts_python_path=TTS_PYTHON_PATH, 
                                                       tts_script_path=TTS_SCRIPT_PATH, 
                                                       silent=args.silent)
                    
                    total_time = time.time() - process_start
                    logger.info(f"[Timing] {get_timestamp()} Total: {total_time:.4f}s, Transcription: {transcription_time:.4f}s, Search: {max(amygdala_time, accumbens_time, hippocampus_time):.4f}s, Inference: {inference_time:.4f}s, Execution: {execution_time:.4f}s, TTS: {tts_time:.4f}s")
                else:
                    logger.error(f"Unable to get or parse {inference_type} inference.")

async def main():
    log_available_audio_devices()
    devices = sd.query_devices()
    input_device = None
    
    if args.source:
        if args.source.isdigit():
            input_device = int(args.source)
        else:
            for i, device in enumerate(devices):
                if args.source.lower() in device['name'].lower():
                    input_device = i
                    break
        if input_device is None:
            logger.error(f"Specified audio source '{args.source}' not found.")
            return
    
    try:
        with sd.InputStream(callback=lambda indata, frames, time, status: audio_callback(indata, frames, time, status, audio_queue, audio_buffer),
                            channels=CHANNELS, samplerate=SAMPLE_RATE, 
                            blocksize=CHUNK_SIZE, device=input_device, dtype='float32'):
            print(f"{get_timestamp()} Streaming started... Press Ctrl+C to stop.")
            embed_type = "local" if args.local_embed == 'local' else f"remote ({args.local_embed})" if args.local_embed else "remote"
            inference_type = "local Ollama" if args.local_inference == '127.0.0.1:11434' else f"remote Ollama ({args.local_inference})" if args.local_inference else "GPT-4o"
            print(f"Using {embed_type} embeddings and {inference_type} for inference.")
            print(f"TTS playback is {'disabled' if args.silent else 'enabled'}.")
            print(f"Using Whisper model: {args.whisper_model}")
            
            while True:
                await process_buffer()
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
