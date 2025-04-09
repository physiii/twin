import numpy as np
import sounddevice as sd
import wavio
import os
import matplotlib.pyplot as plt

SAMPLE_RATE = 16000
DURATION = 5  # seconds
OUTPUT_DIR = "/home/twin"

# Create output directory if it doesn't exist
os.makedirs(OUTPUT_DIR, exist_ok=True)

def audio_callback(indata, frames, time, status):
    if status:
        print(f"Error: {status}")
    audio_data = indata[:, 0] if indata.shape[1] > 1 else indata.flatten()
    print(f"Audio data: {audio_data[:10]}")  # Log the first 10 samples for verification
    audio_buffer.extend(audio_data)

# Specify the correct input device if needed
input_device = None  # Replace with the correct device ID if necessary

audio_buffer = []

# Record audio
print("Recording...")
with sd.InputStream(callback=audio_callback, channels=1, samplerate=SAMPLE_RATE, device=input_device, dtype='float32'):
    sd.sleep(DURATION * 1000)
    print("Recording finished.")

# Convert to numpy array
audio_data = np.array(audio_buffer, dtype='float32')

# Normalize audio data
max_val = np.max(np.abs(audio_data))
if max_val > 0:
    audio_data /= max_val

# Save the normalized audio
output_path = os.path.join(OUTPUT_DIR, "test_recording_normalized.wav")
wavio.write(output_path, audio_data, SAMPLE_RATE, sampwidth=2)
print(f"Recording saved as {output_path}")

# Plot the audio data
plt.figure(figsize=(10, 4))
plt.plot(audio_data)
plt.title("Audio Waveform")
plt.xlabel("Samples")
plt.ylabel("Amplitude")
plt.grid()
plt.show()
