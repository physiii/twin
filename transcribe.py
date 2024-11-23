import time
import numpy as np
import re
import requests
import logging
import io
import soundfile as sf
from fuzzywuzzy import fuzz

from logger import setup_logging
setup_logging()
logger = logging.getLogger('twin')

# Define common noise phrases
NOISE_PHRASES = [
    "thanks for watching",
    "thank you",
    "thank you very much",
    "okay"
]

# Transcription Model Initialization
def init_transcription_model(whisper_model, device_type, compute_type):
    from faster_whisper import WhisperModel  # Import only if needed
    model = WhisperModel(whisper_model, device=device_type, compute_type=compute_type)
    return model

def clean_transcription(text):
    text = re.sub(r'\[.*?\]', '', text)
    text = re.sub(r'\(.*?\)', '', text)
    return text.strip()

def is_similar(text, recent_transcriptions, similarity_threshold):
    return any(fuzz.ratio(text, recent) > similarity_threshold for recent in recent_transcriptions)

def is_noise(text):
    """Check if the text is a known noise phrase."""
    return any(noise.lower() in text.lower() for noise in NOISE_PHRASES)

def filter_segments(segments, confidence_threshold=0.7, min_duration=0.5, max_duration=10.0):
    """Filter segments based on confidence, duration, and noise phrases."""
    filtered = []
    for segment in segments:
        duration = segment.end - segment.start
        text = segment.text.strip().lower()
        confidence = 1 - segment.no_speech_prob  # Assuming no_speech_prob is the probability of no speech
        
        if (confidence >= confidence_threshold and
            min_duration <= duration <= max_duration and
            not is_noise(text)):
            filtered.append(segment)
    return filtered

async def transcribe_audio(model=None, audio_data=None, language="en", similarity_threshold=85, 
                           recent_transcriptions=None, history_buffer=None, history_max_chars=4000, 
                           use_remote=False, remote_url=None):
    if use_remote and remote_url:
        try:
            # Convert audio data to WAV format
            buffer = io.BytesIO()
            sf.write(buffer, audio_data, 16000, format='WAV')
            buffer.seek(0)

            # Send the audio data to the remote server
            files = {'file': ('audio.wav', buffer, 'audio/wav')}
            response = requests.post(remote_url, files=files)
            response.raise_for_status()

            response_data = response.json()
            text = response_data.get("transcription", "").strip()
            
            # Custom noise filtering for remote transcription
            if text and not is_noise(text) and not is_similar(text, recent_transcriptions or [], similarity_threshold):
                if recent_transcriptions is not None:
                    recent_transcriptions.append(text)
                if history_buffer is not None:
                    history_buffer.append(text)
                return [text], 0
            else:
                return [], 0
        except requests.RequestException as e:
            logger.error(f"Error in remote transcription: {str(e)}")
            return [], 0
    else:
        # Local transcription with enhanced filtering
        transcription_start = time.time()
        segments, _ = model.transcribe(
            audio_data, 
            language=language, 
            suppress_tokens=[2, 3], 
            suppress_blank=True, 
            condition_on_previous_text=True, 
            no_speech_threshold=0.5,
            vad_filter=True,  # Enable VAD
            vad_parameters=dict(min_silence_duration_ms=500)
        )
        transcription_time = time.time() - transcription_start
        
        # Apply filtering
        filtered_segments = filter_segments(segments, confidence_threshold=0.7, min_duration=0.5, max_duration=10.0)
        
        transcriptions = []
        for segment in filtered_segments:
            text = clean_transcription(segment.text.strip())
            if text and not is_similar(text, recent_transcriptions or [], similarity_threshold):
                transcriptions.append(text)
                if recent_transcriptions is not None:
                    recent_transcriptions.append(text)
                if history_buffer is not None:
                    history_buffer.append(text)

        return transcriptions, transcription_time

def get_history_text(history_buffer, history_max_chars):
    history_text = " ".join(history_buffer)
    if len(history_text) > history_max_chars:
        history_text = history_text[-history_max_chars:]
        history_text = history_text[history_text.index(' ') + 1:]
    return history_text
