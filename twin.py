import logging
from collections import deque
from datetime import datetime, timedelta
import re
import asyncio
import concurrent.futures
import queue
import numpy as np
import sounddevice as sd
import shlex
import json
import torch
import requests
import time
import aiohttp
from faster_whisper import WhisperModel
from pymilvus import connections, Collection
from sentence_transformers import SentenceTransformer
from fuzzywuzzy import fuzz
from prompt import SYSTEM_PROMPT, PROMPT
from argparse import ArgumentParser

# Import inference functions
from inference import gpt4o_inference, ollama_inference, clean_gpt_response

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
MODEL_SIZE = "small.en"
DEVICE_TYPE = "cuda" if torch.cuda.is_available() else "cpu"
COMPUTE_TYPE = "float16" if DEVICE_TYPE == "cuda" else "float32"
SAMPLE_RATE = 16000
BUFFER_DURATION = 8  # seconds
BUFFER_SIZE = SAMPLE_RATE * BUFFER_DURATION
LANGUAGE = "en"
AMY_DISTANCE_THRESHOLD = 1.0
NA_DISTANCE_THRESHOLD = 1.2
HIP_DISTANCE_THRESHOLD = 1.1
SIMILARITY_THRESHOLD = 85  # Similarity threshold for fuzzy matching
COOLDOWN_PERIOD = 0  # seconds
RISK_THRESHOLD = 0.2

# New constants for extended history
HISTORY_BUFFER_SIZE = 5  # Number of recent transcriptions to keep in history
HISTORY_MAX_CHARS = 200  # Maximum number of characters to send to the LLM

# Audio parameters
CHANNELS = 1
CHUNK_SIZE = 1024

# TTS configuration
TTS_PYTHON_PATH = "/home/andy/venvs/tts-env/bin/python"
TTS_SCRIPT_PATH = "/home/andy/scripts/tts/tts.py"

# Initialize models
model = WhisperModel(MODEL_SIZE, device=DEVICE_TYPE, compute_type=COMPUTE_TYPE)
if DEVICE_TYPE == "cuda":
    torch.cuda.synchronize()

# Parse command-line arguments
parser = ArgumentParser(description="Live transcription with flexible inference and embedding options.")
parser.add_argument('-e', '--execute', action='store_true', help="Execute the commands returned by the inference model")
parser.add_argument('--local-embed', action='store_true', help="Use gte-Qwen2-1.5B-instruct for local embeddings")
parser.add_argument('--local-inference', action='store_true', help="Use local Ollama for inference")
parser.add_argument('-s', '--silent', action='store_true', help="Disable TTS playback")
parser.add_argument('--store-ip', default="localhost", help="Milvus host IP address (default: localhost)")
args = parser.parse_args()

# Milvus configuration
MILVUS_HOST = args.store_ip
MILVUS_PORT = "19530"

# Initialize local embedding model if --local-embed is set
local_embedding_model = SentenceTransformer("Alibaba-NLP/gte-Qwen2-1.5B-instruct", trust_remote_code=True) if args.local_embed else None

# Connect to Milvus
connections.connect("default", host=MILVUS_HOST, port=MILVUS_PORT)

# Circular buffer for audio data
audio_buffer = deque(maxlen=BUFFER_SIZE)
audio_queue = queue.Queue()
recent_transcriptions = deque(maxlen=10)  # Buffer for recent transcriptions
history_buffer = deque(maxlen=HISTORY_BUFFER_SIZE)  # New buffer for extended history
last_executed_commands = {}  # Dictionary to store the timestamp of last command executions

def log_available_audio_devices():
    devices = sd.query_devices()
    logger.info("Available audio devices:")
    for i, device in enumerate(devices):
        logger.info(f"{i}: {device['name']}, Default Sample Rate: {device['default_samplerate']}, Max Input Channels: {device['max_input_channels']}")

def audio_callback(indata, frames, time, status):
    if status:
        logger.error(f"Audio callback error: {status}")
    audio_data = indata[:, 0] if indata.shape[1] > 1 else indata.flatten()
    audio_queue.put(audio_data.copy())
    audio_buffer.extend(audio_data)

def get_timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def clean_text(text):
    text = re.sub(r'\[.*?\]|\(.*?\)|\*.*?\*|\{.*?\}', '', text)
    return text.strip()

def is_similar(text, buffer):
    clean_text_val = clean_text(text)
    for recent_text in buffer:
        clean_recent_text = clean_text(recent_text)
        similarity = fuzz.ratio(clean_text_val, clean_recent_text)
        if similarity > SIMILARITY_THRESHOLD:
            return True
    return False

def is_in_cooldown(command):
    now = datetime.now()
    if command in last_executed_commands:
        last_execution_time = last_executed_commands[command]
        if now - last_execution_time < timedelta(seconds=COOLDOWN_PERIOD):
            return True
    last_executed_commands[command] = now
    return False

async def run_search(text, collection_name):
    start_time = time.time()
    if args.local_embed:
        query_embedding = local_embedding_model.encode([text], prompt_name="query")[0].tolist()
        collection = Collection(collection_name)
        search_params = {
            "metric_type": "L2",
            "params": {"nprobe": 10},
        }
        try:
            results = collection.search(
                data=[query_embedding],
                anns_field="vector",
                param=search_params,
                limit=5,
                output_fields=["snippet"]
            )
            result = [(hit.entity.get('snippet'), hit.distance) for hit in results[0]]
        except Exception as e:
            logger.error(f"Error in Milvus search: {str(e)}")
            result = []
    else:
        search_command = f'python /media/mass/scripts/vectorstore/search.py "{text}" --collection {collection_name} --ip-address {MILVUS_HOST}'
        try:
            proc = await asyncio.create_subprocess_shell(
                search_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode == 0:
                search_results = json.loads(stdout)
                result = [(r['snippet'], round(r['distance'], 2)) for r in search_results]
            else:
                logger.error(f"Error running search: {stderr.decode()}")
                result = []
        except Exception as e:
            logger.error(f"Error in search process: {str(e)}")
            result = []
    return result, time.time() - start_time

async def execute_commands(commands):
    start_time = time.time()
    for command in commands:
        if is_in_cooldown(command):
            print(f"[Cooldown] {get_timestamp()} Command '{command}' skipped due to cooldown.")
            continue
        try:
            if command.lower().startswith('echo '):
                message = command[5:].strip()
                if (message.startswith('"') and message.endswith('"')) or (message.startswith("'") and message.endswith("'")):
                    message = message[1:-1]
                full_command = f'echo "{message}" >> /home/andy/Documents/notes.txt'
                proc = await asyncio.create_subprocess_shell(
                    full_command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await proc.communicate()
                if proc.returncode == 0:
                    print(f"[Executed] {get_timestamp()} Command: {full_command}")
                else:
                    logger.error(f"Command failed: {full_command}")
                    logger.error(f"Error message: {stderr.decode()}")
            elif command.lower().startswith('i played') or command.lower().startswith('playing'):
                print(f"[Simulated] {get_timestamp()} {command}")
            else:
                args = shlex.split(command)
                proc = await asyncio.create_subprocess_exec(
                    *args,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await proc.communicate()
                if proc.returncode == 0:
                    print(f"[Executed] {get_timestamp()} Command: {command}")
                    print(f"[Output] {get_timestamp()} {stdout.decode()}")
                else:
                    logger.error(f"Command failed: {command}")
                    logger.error(f"Error message: {stderr.decode()}")
        except Exception as e:
            logger.error(f"Error executing command '{command}': {str(e)}")
    return time.time() - start_time

async def play_tts_response(response_text, max_words=15):
    if args.silent:
        return 0
    
    start_time = time.time()
    try:
        words = response_text.split()
        truncated_response = ' '.join(words[:max_words]) + '...' if len(words) > max_words else response_text
        proc = await asyncio.create_subprocess_exec(
            TTS_PYTHON_PATH, TTS_SCRIPT_PATH, truncated_response,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()
    except Exception as e:
        logger.error(f"Failed to execute TTS script: {e}")
    return time.time() - start_time

def get_history_text():
    history_text = " ".join(history_buffer)
    if len(history_text) > HISTORY_MAX_CHARS:
        history_text = history_text[-HISTORY_MAX_CHARS:]
        # Trim to the nearest word
        history_text = history_text[history_text.index(' ')+1:]
    return history_text

async def process_buffer():
    process_start = time.time()
    audio_data = np.array(list(audio_buffer), dtype=np.float32)
    if len(audio_data) == 0:
        return

    transcription_start = time.time()
    segments, _ = model.transcribe(audio_data, language=LANGUAGE, suppress_tokens=[2, 3], suppress_blank=True, condition_on_previous_text=False, no_speech_threshold=0.5)
    transcription_time = time.time() - transcription_start
    
    for segment in segments:
        text = segment.text.strip()
        clean_text_val = clean_text(text)
        if not clean_text_val or is_similar(clean_text_val, recent_transcriptions):
            continue

        recent_transcriptions.append(clean_text_val)
        history_buffer.append(clean_text_val)
        logger.info(f"[Source] {get_timestamp()} {clean_text_val}")

        amygdala_results, amygdala_time = await run_search(clean_text_val, 'amygdala')
        accumbens_results, accumbens_time = await run_search(clean_text_val, 'na')
        hippocampus_results, hippocampus_time = await run_search(clean_text_val, 'hippocampus')
        
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
                    inference_response, inference_time = await ollama_inference(history_text, combined_commands)
                    inference_type = "Ollama"
                else:
                    inference_response, inference_time = await gpt4o_inference(history_text, combined_commands)
                    inference_type = "GPT-4o"
                
                audio_buffer.clear()
                with audio_queue.mutex:
                    audio_queue.queue.clear()

                if inference_response:
                    logger.info(f"[{inference_type}] {get_timestamp()} {json.dumps(inference_response, indent=2)}")
                    
                    execution_time = 0
                    if args.execute:
                        if inference_response['risk'] <= RISK_THRESHOLD or (inference_response['risk'] > RISK_THRESHOLD and inference_response.get('confirmed', False)):
                            execution_time = await execute_commands(inference_response['commands'])
                        else:
                            logger.warning(f"[Warning] {get_timestamp()} Commands not executed. Risk: {inference_response['risk']}. Confirmation required.")
                    
                    tts_time = await play_tts_response(inference_response['response'])
                    
                    total_time = time.time() - process_start
                    logger.info(f"[Timing] {get_timestamp()} Total: {total_time:.4f}s, Transcription: {transcription_time:.4f}s, Search: {max(amygdala_time, accumbens_time, hippocampus_time):.4f}s, Inference: {inference_time:.4f}s, Execution: {execution_time:.4f}s, TTS: {tts_time:.4f}s")
                else:
                    logger.error(f"Unable to get or parse {inference_type} inference.")

async def main():
    log_available_audio_devices()
    input_device = sd.default.device[0]
    try:
        with sd.InputStream(callback=audio_callback, channels=CHANNELS, samplerate=SAMPLE_RATE, 
                            blocksize=CHUNK_SIZE, device=input_device, dtype='float32'):
            print(f"{get_timestamp()} Streaming started... Press Ctrl+C to stop.")
            print(f"Using {'local' if args.local_embed else 'remote'} embeddings and {'local Ollama' if args.local_inference else 'GPT-4o'} for inference.")
            print(f"TTS playback is {'disabled' if args.silent else 'enabled'}.")
            
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
