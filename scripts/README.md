# Twin Scripts Collection

This folder contains utility scripts for Twin voice assistant setup and operation.

## 🎤 RTSP Microphone Server

Stream your local microphone audio via RTSP for remote Twin deployment.

### Quick Start

```bash
# Basic usage - starts RTSP server on port 8554
python scripts/rtsp_mic_server.py

# List available audio devices
python scripts/rtsp_mic_server.py --list-devices

# Custom configuration
python scripts/rtsp_mic_server.py --port 8555 --device "USB Microphone"
```

### Connect to Twin

Once the RTSP server is running, connect Twin to it:

```bash
# On the Twin server
python main.py --source rtsp://client_ip:8554/audio
```

### Features

- ✅ **PipeWire/PulseAudio Support** - Works with modern Linux audio
- ✅ **Auto Device Detection** - Finds available microphones  
- ✅ **Configurable Quality** - Adjust sample rate and channels
- ✅ **Process Monitoring** - Automatic restart on failure
- ✅ **Clean Shutdown** - Handles SIGINT/SIGTERM gracefully
- ✅ **Dependency Checking** - Verifies FFmpeg availability

### Requirements

```bash
# Ubuntu/Debian
sudo apt install ffmpeg pulseaudio-utils

# Fedora/RHEL
sudo dnf install ffmpeg pulseaudio-utils

# Arch
sudo pacman -S ffmpeg pulseaudio
```

### Command Line Options

```
usage: rtsp_mic_server.py [-h] [--port PORT] [--device DEVICE] 
                         [--sample-rate SAMPLE_RATE] [--channels CHANNELS]
                         [--list-devices] [--verbose]

Options:
  --port, -p           RTSP server port (default: 8554)
  --device, -d         Audio input device (default: "default")
  --sample-rate, -r    Audio sample rate (default: 16000)
  --channels, -c       Number of audio channels (default: 1)
  --list-devices, -l   List available audio devices and exit
  --verbose, -v        Enable verbose logging
```

### Examples

```bash
# Start with custom port
python scripts/rtsp_mic_server.py --port 8555

# Use specific microphone
python scripts/rtsp_mic_server.py --device "USB Microphone"

# High quality audio
python scripts/rtsp_mic_server.py --sample-rate 44100 --channels 2

# List all available microphones
python scripts/rtsp_mic_server.py --list-devices
```

### Troubleshooting

#### No Audio Devices Found
```bash
# Check PulseAudio sources
pactl list short sources

# Check permissions
ls -la /dev/snd/
```

#### FFmpeg Not Found
```bash
# Install FFmpeg
sudo apt install ffmpeg  # Ubuntu/Debian
sudo dnf install ffmpeg  # Fedora
```

#### Connection Issues
```bash
# Test RTSP stream
ffplay rtsp://localhost:8554/audio

# Check firewall
sudo ufw allow 8554  # Ubuntu
sudo firewall-cmd --add-port=8554/tcp  # Fedora
```

#### PipeWire Issues
```bash
# Restart PipeWire
systemctl --user restart pipewire
systemctl --user restart pipewire-pulse
```

## 🔄 Running as a Service

To run the RTSP server automatically:

```bash
# Copy service file (create if needed)
sudo cp scripts/rtsp-mic.service /etc/systemd/system/

# Edit paths in service file
sudo nano /etc/systemd/system/rtsp-mic.service

# Enable and start
sudo systemctl enable rtsp-mic
sudo systemctl start rtsp-mic

# Check status
sudo systemctl status rtsp-mic
```

## 🌐 Network Setup

### Firewall Configuration

```bash
# Ubuntu/Debian
sudo ufw allow 8554

# Fedora/RHEL/CentOS
sudo firewall-cmd --permanent --add-port=8554/tcp
sudo firewall-cmd --reload

# Manual iptables
sudo iptables -A INPUT -p tcp --dport 8554 -j ACCEPT
```

### Multi-Room Deployment

For multiple rooms, run multiple instances:

```bash
# Office microphone (port 8554)
python scripts/rtsp_mic_server.py --port 8554

# Kitchen microphone (port 8555) 
python scripts/rtsp_mic_server.py --port 8555 --device "Kitchen USB Mic"

# Living room microphone (port 8556)
python scripts/rtsp_mic_server.py --port 8556 --device "Living Room Mic"
```

Update your Twin configuration:

```json
{
  "source_mappings": {
    "rtsp://office_pc:8554/audio": "office",
    "rtsp://kitchen_pc:8555/audio": "kitchen", 
    "rtsp://livingroom_pc:8556/audio": "living_room"
  }
}
```

## 🚀 Performance Tips

### Optimize for Low Latency

```bash
# Reduce buffer size and use faster codec
python scripts/rtsp_mic_server.py \
  --sample-rate 16000 \
  --channels 1
```

### Network Optimization

```bash
# Use wired connection when possible
# Ensure good WiFi signal strength
# Consider QoS settings for RTSP traffic
```

### Resource Usage

- **CPU**: ~2-5% on modern systems
- **RAM**: ~10-20MB
- **Network**: ~128kbps (16kHz mono) to 1.4Mbps (44kHz stereo)

## 🔧 Development

### Adding New Audio Sources

The script can be extended to support other audio sources:

```python
# Example: Add JACK support
def build_jack_command(self):
    cmd = [
        'ffmpeg',
        '-f', 'jack',
        '-i', 'system:capture_1',
        # ... rest of command
    ]
```

### Custom Audio Processing

Add audio filters before streaming:

```python
# Example: Add noise reduction
cmd.extend([
    '-af', 'highpass=f=200,lowpass=f=8000',  # Frequency filtering
    '-af', 'volume=2.0'  # Amplify quiet microphones
])
```

## 📝 Logs

Logs are written to stdout/stderr. To save logs:

```bash
# Save to file
python scripts/rtsp_mic_server.py > rtsp_server.log 2>&1

# Use with journald (if running as service)
journalctl -u rtsp-mic -f
``` 