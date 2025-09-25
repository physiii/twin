import time
import numpy as np
import re
import requests
import logging
import io
import soundfile as sf
from fuzzywuzzy import fuzz

logger = logging.getLogger('twin')

# Define common noise phrases
NOISE_PHRASES = [
    "thanks for watching",
    "thank you",
    "thank you very much",
    "okay"
    "I'm sorry",
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

def filter_segments(segments, confidence_threshold=0.6, min_duration=0.5, max_duration=10.0):
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

async def transcribe_audio(model=None, audio_data=None, audio_buffer=None, language="en", similarity_threshold=85, 
                           recent_transcriptions=None, history_buffer=None, history_max_chars=4000, 
                           use_remote=False, remote_url=None, sample_rate=16000):
    """Transcribes audio data, handling both numpy array and BytesIO buffer inputs."""
    if use_remote and remote_url:
        try:
            send_buffer = None
            if audio_buffer:
                # Use the provided buffer directly
                audio_buffer.seek(0) # Ensure buffer is at the start
                send_buffer = audio_buffer
                buffer_size = send_buffer.getbuffer().nbytes
                logger.debug(f"Using provided audio buffer (Size: {buffer_size} bytes)")
            elif audio_data is not None:
                # Convert numpy array to WAV buffer
                audio_max = np.max(np.abs(audio_data))
                audio_mean = np.mean(np.abs(audio_data))
                audio_shape = audio_data.shape
                logger.debug(f"Converting numpy audio data: shape={audio_shape}, max={audio_max:.6f}, mean={audio_mean:.6f}, dtype={audio_data.dtype}")
                
                buffer = io.BytesIO()
                # Explicitly write as FLOAT (32-bit float) to match input numpy array
                sf.write(buffer, audio_data, sample_rate, format='WAV', subtype='FLOAT')
                buffer.seek(0)
                send_buffer = buffer
                buffer_size = send_buffer.getbuffer().nbytes
                logger.debug(f"Converted numpy audio to buffer (Size: {buffer_size} bytes, Format: WAV/FLOAT)")
            else:
                logger.error("Remote transcription called with no audio data or buffer.")
                return [], 0

            # Send the buffer to the remote server
            files = {'file': ('audio.wav', send_buffer, 'audio/wav')}
            response = requests.post(remote_url, files=files)
            response.raise_for_status()

            response_data = response.json()
            text = response_data.get("transcription", "").strip()
            logger.debug(f"Remote transcription response: {response_data}")
            
            # Custom noise filtering for remote transcription
            if text and not is_noise(text) and not is_similar(text, recent_transcriptions or [], similarity_threshold):
                if recent_transcriptions is not None:
                    recent_transcriptions.append(text)
                if history_buffer is not None:
                    history_buffer.append(text)
                return [text], 0
            else:
                if text:
                    logger.debug(f"Filtered out text: '{text}', is_noise={is_noise(text)}, is_similar={is_similar(text, recent_transcriptions or [], similarity_threshold)}")
                return [], 0
        except requests.RequestException as e:
            logger.error(f"Error in remote transcription: {str(e)}")
            return [], 0
        except Exception as e:
             logger.error(f"Unexpected error during remote transcription prep/send: {e}", exc_info=True)
             return [], 0
    elif audio_data is not None:
        # Local transcription requires numpy array
        transcription_start = time.time()
        segments, _ = model.transcribe(
            audio_data, 
            language=language, 
            suppress_tokens=[2, 3], 
            suppress_blank=True, 
            condition_on_previous_text=True, 
            no_speech_threshold=0.1,
            vad_filter=True,  # Enable VAD
            vad_parameters=dict(min_silence_duration_ms=100)
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
    else:
        logger.error("Local transcription called without audio data.")
        return [], 0

def get_history_text(history_buffer, history_max_chars):
    history_text = " ".join(history_buffer)
    if len(history_text) > history_max_chars:
        history_text = history_text[-history_max_chars:]
        history_text = history_text[history_text.index(' ') + 1:]
    return history_text
