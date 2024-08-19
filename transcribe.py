import time
import numpy as np
import re
import requests  # For making HTTP requests to the remote transcription server
import logging

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

async def transcribe_audio(model=None, audio_data=None, language="en", similarity_threshold=85, recent_transcriptions=None, history_buffer=None, history_max_chars=4000, use_remote=False, remote_url=None):
    if use_remote and remote_url:
        # Transcribe using the remote server
        audio_file_path = "temp_audio.wav"
        np_data = np.array(audio_data, dtype=np.float32)
        np_data.tofile(audio_file_path)  # Save audio data to a temporary file
        
        with open(audio_file_path, 'rb') as audio_file:
            response = requests.post(remote_url, files={"file": audio_file})
        
        response_data = response.json()
        text = response_data.get("transcription", "").strip()
        return [text], 0  # Returning as a list to keep consistency with faster_whisper
    else:
        # Transcribe using faster_whisper
        transcription_start = time.time()
        segments, _ = model.transcribe(audio_data, language=language, suppress_tokens=[2, 3], suppress_blank=True, condition_on_previous_text=True, no_speech_threshold=0.5)
        transcription_time = time.time() - transcription_start
        
        transcriptions = []
        for segment in segments:
            text = clean_transcription(segment.text.strip())
            if not text or any(is_similar(text, recent_transcriptions, similarity_threshold)):
                continue
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
        # Trim to the nearest word
        history_text = history_text[history_text.index(' ') + 1:]
    return history_text

def is_similar(text, recent_transcriptions, similarity_threshold):
    # Dummy implementation for similarity check
    return False
