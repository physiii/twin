# RTSP Microphone Service Setup

Ultra low-latency RTSP microphone streaming as a systemd service.

## Quick Install

```bash
# Install the service
./install_service.sh

# Start immediately  
sudo systemctl start rtsp-mic

# Enable auto-start on boot
sudo systemctl enable rtsp-mic

# Check it's working
sudo systemctl status rtsp-mic
```

## Usage

### Service Commands
```bash
sudo systemctl start rtsp-mic      # Start service
sudo systemctl stop rtsp-mic       # Stop service  
sudo systemctl restart rtsp-mic    # Restart service
sudo systemctl status rtsp-mic     # Check status
sudo systemctl enable rtsp-mic     # Auto-start on boot
sudo systemctl disable rtsp-mic    # Disable auto-start
```

### Monitoring
```bash
journalctl -u rtsp-mic -f          # Live logs
journalctl -u rtsp-mic --since today  # Today's logs
```

### Testing
```bash
./test_mic_latency.sh              # Test latency manually
ffplay rtsp://127.0.0.1:8554/mic   # Basic playback test
```

## Stream Details

- **URL**: `rtsp://[YOUR_IP]:8554/mic`
- **Codec**: G.711 μ-law (ultra low latency)
- **Format**: 8kHz, mono, 64 kbps
- **Transport**: UDP (no handshakes)
- **Latency**: ~50-100ms end-to-end

## Troubleshooting

### Check Service Status
```bash
sudo systemctl status rtsp-mic
journalctl -u rtsp-mic --no-pager
```

### Test Audio Device
```bash
python3 scripts/rtsp_mic_client.py --list-devices
```

### Manual Start (for debugging)
```bash
./start_rtsp_mic.sh
```

### Port Conflicts
If you get "address already in use" errors:
```bash
sudo netstat -tulpn | grep :8554
sudo systemctl stop rtsp-mic
```

## Uninstall

```bash
./uninstall_service.sh
```

## Auto-Start Configuration

The service is configured to:
- ✅ Start after network and audio systems
- ✅ Restart automatically if it crashes  
- ✅ Run as your user account (proper audio access)
- ✅ Log to systemd journal

Perfect for production use! 🎤✨
