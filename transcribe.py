# transcribe.py

import time
import numpy as np
import re
import requests
import logging
import io
import soundfile as sf
from fuzzywuzzy import fuzz

logger = logging.getLogger("twin")

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
            
            # Process the transcription similar to local transcription
            if text and not is_similar(text, recent_transcriptions or [], similarity_threshold):
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
        # Local transcription
        transcription_start = time.time()
        segments, _ = model.transcribe(audio_data, language=language, suppress_tokens=[2, 3], 
                                       suppress_blank=True, condition_on_previous_text=True, 
                                       no_speech_threshold=0.5)
        transcription_time = time.time() - transcription_start
        
        transcriptions = []
        for segment in segments:
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
