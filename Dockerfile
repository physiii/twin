# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Install system dependencies that might be needed for audio libraries
# libportaudio2 is often needed by sounddevice/pyaudio
# libasound2-dev is for ALSA development headers
# ffmpeg is needed for RTSP audio stream capture
# pulseaudio-utils provides paplay
# playerctl is for media control
# openssh-client is for SSH connections
RUN apt-get update && apt-get install -y --no-install-recommends \
    libportaudio2 \
    libasound2-dev \
    ffmpeg \
    pulseaudio-utils \
    playerctl \
    openssh-client \
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements file into the container
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
# Using --no-cache-dir to reduce image size
RUN pip install --no-cache-dir -r requirements.txt

# Copy SSH key for remote host commands
RUN mkdir -p /root/.ssh && chmod 700 /root/.ssh
# Make sure the source path ./container_ssh_keys/id_ed25519_twin is correct
COPY ./container_ssh_keys/id_ed25519_twin /root/.ssh/id_ed25519
RUN chmod 600 /root/.ssh/id_ed25519

# Copy the rest of the application code into the container
COPY . .

# Define the command to run the application
CMD ["python", "main.py"] 