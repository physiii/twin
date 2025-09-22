# RTSP Microphone Client

This client allows Ubuntu machines with microphones to stream audio to an RTSP server, enabling room-specific voice control for your Twin home automation system.

## 🎯 Key Features

- **Non-blocking Audio**: Uses PulseAudio monitor sources so other apps can still use the microphone
- **Room Mapping**: Streams to specific paths that map to room locations
- **Automatic Restart**: Built-in monitoring and restart capabilities
- **Flexible Configuration**: Support for different audio devices and settings
- **Systemd Service**: Can run as a background service

## 🚀 Quick Start

### 1. Setup (First time only)

```bash
# Make scripts executable
chmod +x setup_rtsp_client.sh

# Run setup script
./setup_rtsp_client.sh
```

### 2. List Available Audio Devices

```bash
python3 rtsp_mic_client.py --list-devices
```

### 3. Start Streaming

```bash
# Basic streaming to default path
python3 rtsp_mic_client.py --server 192.168.1.40

# Stream to specific room
python3 rtsp_mic_client.py --server 192.168.1.40 --path office

# Use specific microphone device
python3 rtsp_mic_client.py --server 192.168.1.40 --device "USB Microphone" --path kitchen
```

## 📁 Files

- **`rtsp_mic_client.py`** - Main client script
- **`setup_rtsp_client.sh`** - Setup and dependency installation
- **`rtsp_client_config.json`** - Configuration template
- **`rtsp-mic-client.service`** - Systemd service file

## ⚙️ Configuration

### Command Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--server, -s` | RTSP server IP address | Required |
| `--port, -p` | RTSP server port | 8554 |
| `--path, -P` | Stream path (room name) | mic |
| `--device, -d` | Audio device name | default |
| `--sample-rate, -r` | Audio sample rate (Hz) | 16000 |
| `--channels, -c` | Number of channels | 1 |
| `--list-devices, -l` | List available devices | False |

### Room Configuration

Update your `config/source_locations.json` to include the new RTSP streams:

```json
{
  "source_mappings": {
    "rtsp://192.168.1.100:8554/office": "office",
    "rtsp://192.168.1.101:8554/kitchen": "kitchen",
    "rtsp://192.168.1.102:8554/living_room": "living_room",
    "rtsp://192.168.1.103:8554/bedroom": "bedroom"
  }
}
```

## 🔧 Running as a Service

### 1. Install Service

```bash
# Copy service file to systemd directory
sudo cp rtsp-mic-client.service /etc/systemd/system/

# Edit the service file to match your setup
sudo nano /etc/systemd/system/rtsp-mic-client.service

# Update the ExecStart line with your server IP and room path
# Example: --server 192.168.1.40 --path office
```

### 2. Enable and Start

```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable service (starts on boot)
sudo systemctl enable rtsp-mic-client@$USER

# Start service
sudo systemctl start rtsp-mic-client@$USER

# Check status
sudo systemctl status rtsp-mic-client@$USER
```

### 3. Service Management

```bash
# Stop service
sudo systemctl stop rtsp-mic-client@$USER

# Restart service
sudo systemctl restart rtsp-mic-client@$USER

# View logs
sudo journalctl -u rtsp-mic-client@$USER -f
```

## 🎤 Audio Device Selection

### Finding Your Device

```bash
# List all audio sources
pactl list short sources

# Example output:
# 0	alsa_input.pci-0000_00_1f.3.analog-stereo	module-alsa-card.c	s16le 2ch 48000Hz	RUNNING
# 1	alsa_input.usb-0c76_USB_PnP_Audio_Device-00.analog-mono	module-alsa-card.c	s16le 1ch 16000Hz	RUNNING
```

### Using Specific Devices

```bash
# Use USB microphone
python3 rtsp_mic_client.py --server 192.168.1.40 --device "USB PnP Audio Device" --path office

# Use built-in microphone
python3 rtsp_mic_client.py --server 192.168.1.40 --device "analog-stereo" --path kitchen
```

## 🔒 Non-Blocking Audio

The client uses **monitor sources** which means:

- ✅ Other applications can still use the microphone
- ✅ No audio conflicts or blocking
- ✅ Audio is copied, not captured exclusively
- ✅ Perfect for simultaneous use cases

## 📊 Performance Tuning

### Sample Rate Recommendations

- **16000 Hz**: Best for voice recognition, low bandwidth
- **22050 Hz**: Good balance of quality and bandwidth
- **44100 Hz**: High quality, higher bandwidth usage

### Network Considerations

- Use TCP transport for reliability
- Monitor network bandwidth usage
- Consider QoS settings for audio streams

## 🐛 Troubleshooting

### Common Issues

1. **"Audio device not found"**
   - Run `--list-devices` to see available devices
   - Check device name spelling
   - Ensure PulseAudio is running

2. **"FFmpeg process failed"**
   - Check if FFmpeg is installed: `ffmpeg -version`
   - Verify RTSP server is accessible
   - Check firewall settings

3. **"Permission denied"**
   - Ensure user has access to audio devices
   - Check PulseAudio user permissions
   - Run as regular user, not root

### Debug Mode

```bash
# Enable verbose logging
export PYTHONUNBUFFERED=1
python3 rtsp_mic_client.py --server 192.168.1.40 --path office 2>&1 | tee client.log
```

### Network Testing

```bash
# Test RTSP server connectivity
nc -zv 192.168.1.40 8554

# Test with curl (if server supports HTTP)
curl -I http://192.168.1.40:8554
```

## 🔄 Integration with Twin

Once your RTSP streams are running, Twin will automatically:

1. **Detect Room Location**: Based on RTSP source mapping
2. **Load Room Context**: Use appropriate self file (e.g., `office.txt`)
3. **Route Commands**: Execute Home Assistant commands for that specific room
4. **Validate Devices**: Ensure commands only affect devices in the detected room

## 📝 Example Workflow

1. **Setup Client**: Run setup script on Ubuntu machine
2. **Configure Room**: Set stream path to room name (e.g., `--path office`)
3. **Start Streaming**: Client connects to RTSP server
4. **Update Twin Config**: Add RTSP URL to `source_mappings`
5. **Test Voice Control**: Speak into microphone, Twin detects room and executes commands

## 🤝 Support

For issues or questions:
- Check the troubleshooting section above
- Review system logs: `journalctl -u rtsp-mic-client@$USER`
- Verify network connectivity and firewall settings
- Ensure all dependencies are properly installed

