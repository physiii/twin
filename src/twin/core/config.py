import os
import logging
from dotenv import load_dotenv
from pathlib import Path

# Load the .env file if it exists
env_path = Path('.') / '.env'
load_dotenv(dotenv_path=env_path)

# Set up logger
logger = logging.getLogger("twin")

# Debug output for .env loading
env_silence_threshold = os.getenv('SILENCE_THRESHOLD')
logger.warning(f"Loading SILENCE_THRESHOLD from .env: '{env_silence_threshold}'")

# Audio settings
SAMPLE_RATE = int(os.getenv('SAMPLE_RATE', '16000'))
BUFFER_DURATION = float(os.getenv('BUFFER_DURATION', '3'))
SMALL_BUFFER_DURATION = float(os.getenv('SMALL_BUFFER_DURATION', '0.2'))
CHANNELS = int(os.getenv('CHANNELS', '1'))
CHUNK_SIZE = int(os.getenv('CHUNK_SIZE', '1024'))
SILENCE_THRESHOLD = float(os.getenv('SILENCE_THRESHOLD', '0.01')) # Default to 0.01

# Debug output for loaded value
logger.warning(f"Final SILENCE_THRESHOLD: {SILENCE_THRESHOLD}")

# RTSP Stream settings
AUDIO_SOURCE = os.getenv('AUDIO_SOURCE', 'microphone')
RTSP_URL = os.getenv('RTSP_URL', '')
RTSP_LATENCY_FLAGS = os.getenv('RTSP_LATENCY_FLAGS', '')
RTSP_AUDIO_CODEC = os.getenv('RTSP_AUDIO_CODEC', 'aac')
RTSP_RECONNECT_INTERVAL = int(os.getenv('RTSP_RECONNECT_INTERVAL', '20'))  # seconds

# Transcription settings
LANGUAGE = os.getenv('LANGUAGE', 'en')
SIMILARITY_THRESHOLD = int(os.getenv('SIMILARITY_THRESHOLD', '85'))
WHISPER_MODEL = os.getenv('WHISPER_MODEL', 'turbo')

# Inference and command settings
RISK_THRESHOLD = float(os.getenv('RISK_THRESHOLD', '0.5'))
COOLDOWN_PERIOD = int(os.getenv('COOLDOWN_PERIOD', '0'))
HISTORY_BUFFER_SIZE = int(os.getenv('HISTORY_BUFFER_SIZE', '4'))
HISTORY_MAX_CHARS = int(os.getenv('HISTORY_MAX_CHARS', '4000'))
HISTORY_INCLUDE_CHUNKS = int(os.getenv('HISTORY_INCLUDE_CHUNKS', '6'))

# Vector search thresholds
AMY_DISTANCE_THRESHOLD = float(os.getenv('AMY_DISTANCE_THRESHOLD', '1.1'))
NA_DISTANCE_THRESHOLD = float(os.getenv('NA_DISTANCE_THRESHOLD', '1.4'))
HIP_DISTANCE_THRESHOLD = float(os.getenv('HIP_DISTANCE_THRESHOLD', '1.1'))

# Wake/sleep settings
WAKE_TIMEOUT = int(os.getenv('WAKE_TIMEOUT', '24'))
WAKE_SOUND_FILE = os.getenv('WAKE_SOUND_FILE', 'data/audio/wake.wav')
SLEEP_SOUND_FILE = os.getenv('SLEEP_SOUND_FILE', 'data/audio/sleep.wav')

# TTS settings
TTS_PYTHON_PATH = os.getenv('TTS_PYTHON_PATH', '/home/andy/venvs/tts-env/bin/python')
TTS_SCRIPT_PATH = os.getenv('TTS_SCRIPT_PATH', '/home/andy/scripts/tts/tts.py')

# Remote services
REMOTE_STORE_URL = os.getenv('REMOTE_STORE_URL', '')
REMOTE_INFERENCE_URL = os.getenv('REMOTE_INFERENCE_URL', '')
REMOTE_TRANSCRIBE_URL = os.getenv('REMOTE_TRANSCRIBE_URL', '')
SSH_HOST_TARGET = os.getenv('SSH_HOST_TARGET', None) # e.g., user@hostname

# Compute type - dependent on available hardware
DEVICE_TYPE = os.getenv('DEVICE_TYPE')
if not DEVICE_TYPE:
    try:
        import torch
        DEVICE_TYPE = "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        DEVICE_TYPE = "cpu"
        
COMPUTE_TYPE = os.getenv('COMPUTE_TYPE')
if not COMPUTE_TYPE:
    COMPUTE_TYPE = "float16" if DEVICE_TYPE == "cuda" else "float32"

# Reports and logs
QC_REPORT_DIR = os.getenv('QC_REPORT_DIR', 'reports')
GENERAL_REPORT_FILE = os.getenv('GENERAL_REPORT_FILE', 'general_report.txt')
LOG_FILE = os.getenv('LOG_FILE', 'logs/continuous.log')

def get_config_dict():
    """Return all config variables as a dictionary for context passing"""
    return {
        "SAMPLE_RATE": SAMPLE_RATE,
        "BUFFER_DURATION": BUFFER_DURATION,
        "SMALL_BUFFER_DURATION": SMALL_BUFFER_DURATION,
        "CHANNELS": CHANNELS,
        "CHUNK_SIZE": CHUNK_SIZE,
        "SILENCE_THRESHOLD": SILENCE_THRESHOLD,
        "AUDIO_SOURCE": AUDIO_SOURCE,
        "RTSP_URL": RTSP_URL,
        "RTSP_LATENCY_FLAGS": RTSP_LATENCY_FLAGS,
        "RTSP_AUDIO_CODEC": RTSP_AUDIO_CODEC,
        "RTSP_RECONNECT_INTERVAL": RTSP_RECONNECT_INTERVAL,
        "LANGUAGE": LANGUAGE,
        "SIMILARITY_THRESHOLD": SIMILARITY_THRESHOLD,
        "RISK_THRESHOLD": RISK_THRESHOLD,
        "COOLDOWN_PERIOD": COOLDOWN_PERIOD,
        "HISTORY_BUFFER_SIZE": HISTORY_BUFFER_SIZE,
        "HISTORY_MAX_CHARS": HISTORY_MAX_CHARS,
        "HISTORY_INCLUDE_CHUNKS": HISTORY_INCLUDE_CHUNKS,
        "AMY_DISTANCE_THRESHOLD": AMY_DISTANCE_THRESHOLD,
        "NA_DISTANCE_THRESHOLD": NA_DISTANCE_THRESHOLD,
        "HIP_DISTANCE_THRESHOLD": HIP_DISTANCE_THRESHOLD,
        "WAKE_TIMEOUT": WAKE_TIMEOUT,
        "WAKE_SOUND_FILE": WAKE_SOUND_FILE,
        "SLEEP_SOUND_FILE": SLEEP_SOUND_FILE,
        "TTS_PYTHON_PATH": TTS_PYTHON_PATH,
        "TTS_SCRIPT_PATH": TTS_SCRIPT_PATH,
        "REMOTE_STORE_URL": REMOTE_STORE_URL,
        "REMOTE_INFERENCE_URL": REMOTE_INFERENCE_URL,
        "REMOTE_TRANSCRIBE_URL": REMOTE_TRANSCRIBE_URL,
        "SSH_HOST_TARGET": SSH_HOST_TARGET,
        "DEVICE_TYPE": DEVICE_TYPE,
        "COMPUTE_TYPE": COMPUTE_TYPE,
        "QC_REPORT_DIR": QC_REPORT_DIR,
        "GENERAL_REPORT_FILE": GENERAL_REPORT_FILE,
    } 