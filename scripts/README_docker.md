# Docker RTSP Client Deployment

This guide explains how to deploy RTSP microphone clients using Docker containers, making it easy to set up room-specific audio streaming across multiple Ubuntu machines.

## 🎯 Overview

The Docker setup provides:
- **Containerized Deployment**: Easy deployment without affecting host system
- **Room-Specific Configuration**: Each container streams to a specific room path
- **Automatic Restart**: Containers restart automatically if they crash
- **Audio Isolation**: Non-blocking audio capture using PulseAudio monitor sources
- **Easy Management**: Simple Docker Compose commands for all operations

## 🚀 Quick Start

### 1. Prerequisites

```bash
# Install Docker (if not already installed)
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Install Docker Compose v2 (plugin)
sudo mkdir -p /usr/local/lib/docker/cli-plugins
sudo curl -SL https://github.com/docker/compose/releases/download/v2.27.0/docker-compose-linux-x86_64 -o /usr/local/lib/docker/cli-plugins/docker-compose
sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

# Add user to docker group
sudo usermod -aG docker $USER
newgrp docker  # or log out and back in
```

### 2. Deploy for Any Room

```bash
# Make launcher script executable
chmod +x launch_rtsp_client.sh

# Launch RTSP server + client (no room arg; path is /mic)
./launch_rtsp_client.sh
```

### 3. Manual Deployment

```bash
# Set environment variables and deploy
# By default, the client publishes to this machine (local IP detected by the launcher)
# Or override explicitly to a central RTSP server host/IP
export RTSP_SERVER_IP=$(hostname -I | awk '{print $1}')
docker compose up -d
```

## 📁 Files Structure

```
scripts/
├── docker-compose.yml              # Main Docker Compose file
├── Dockerfile.rtsp-client          # Container image definition
├── rtsp_mic_client_docker.py      # Docker-optimized client
├── launch_rtsp_client.sh          # Simple room launcher script
├── env.office                      # Office configuration (optional)
├── env.kitchen                     # Kitchen configuration (optional)
├── env.living-room                 # Living room configuration (optional)
└── env.bedroom                     # Bedroom configuration (optional)
```

## 🔧 Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `RTSP_SERVER_IP` | RTSP server IP address | local machine IP |
| `RTSP_SERVER_PORT` | RTSP server port | 8554 |
| `STREAM_PATH` | Stream path (room name) | mic |
| `AUDIO_DEVICE` | Audio device name | default |
| `SAMPLE_RATE` | Audio sample rate (Hz) | 16000 |
| `CHANNELS` | Number of channels | 1 |

### Room-Specific Configs

Each room has its own environment file:

```bash
# Office
cat env.office
RTSP_SERVER_IP=192.168.1.40
STREAM_PATH=office
# ... other settings

# Kitchen
cat env.kitchen
RTSP_SERVER_IP=192.168.1.40
STREAM_PATH=kitchen
# ... other settings
```

## 🐳 Docker Commands

### Basic Operations

```bash
# Build images
docker compose build

# Start services
docker compose up -d

# Stop services
docker compose down

# View logs
docker compose logs -f

# Restart services
docker compose restart
```

### Operations

```bash
# Launch
./launch_rtsp_client.sh

# Manual deploy
docker compose up -d

# View container status
docker ps | grep rtsp-client
```

### Container Management

```bash
# View container logs
docker logs rtsp-client-mic

# Execute commands in container
docker exec -it rtsp-client-mic bash

# Check container health
docker inspect rtsp-client-mic | grep Health -A 10

# Restart specific container
docker restart rtsp-client-office
```

## 🎤 Audio Configuration

### PulseAudio Integration

The containers use host networking and mount the host's audio system:

```yaml
volumes:
  - /dev/snd:/dev/snd:rw                    # Audio devices
  - /run/user/1000/pulse:/run/user/1000/pulse:rw  # PulseAudio socket
  - /etc/pulse:/etc/pulse:ro                # PulseAudio config
  - /home/${USER}/.config/pulse:/home/${USER}/.config/pulse:ro
network_mode: host                           # Host networking for audio
```

### Non-Blocking Audio

- Uses **monitor sources** (`device.monitor`)
- Audio is copied, not captured exclusively
- Other applications can still use the microphone
- No audio conflicts or blocking

## 🔍 Troubleshooting

### Common Issues

1. **"Permission denied" errors**
   ```bash
   # Check if user is in docker group
   groups $USER
   
   # Add user to docker group
   sudo usermod -aG docker $USER
   newgrp docker
   ```

2. **Audio not working**
   ```bash
   # Check if PulseAudio is running on host
   pactl info
   
   # Check audio devices
   pactl list short sources
   
   # Check container logs
   docker logs rtsp-client-office
   ```

3. **Container won't start**
   ```bash
   # Check container status
   docker ps -a | grep rtsp-client
   
   # View detailed logs
   docker compose logs rtsp-client-office
   
   # Check if ports are available
   netstat -tlnp | grep 8554
   ```

### Debug Mode

```bash
# Run container interactively
docker run -it --rm \
  --network host \
  --volume /dev/snd:/dev/snd:rw \
  --volume /run/user/1000/pulse:/run/user/1000/pulse:rw \
  rtsp-client-office bash

# Inside container, test audio
pactl list short sources
ffmpeg -f pulse -i default.monitor -f null -
```

## 📊 Monitoring

### Health Checks

Each container includes health checks:

```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python3 /app/rtsp_mic_client_docker.py --list-devices || exit 1
```

### Log Monitoring

```bash
# Follow all logs
docker compose logs -f

# Follow specific service
docker compose logs -f rtsp-client-mic

# View recent logs
docker compose logs --tail=100 rtsp-client-mic
```

### Resource Usage

```bash
# Check container resource usage
docker stats rtsp-client-office

# Check disk usage
docker system df

# Clean up unused resources
docker system prune -f
```

## 🔄 Integration with Twin

### 1. Update Source Mappings

Add the new RTSP streams to your `config/source_locations.json`:

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

### 2. Room Detection

Twin will automatically:
- Detect the RTSP source
- Map it to the correct room
- Load the appropriate self file
- Route commands to room-specific devices

### 3. Testing

```bash
# Test room detection
python3 test_room_integration.py

# Check if streams are accessible
ffprobe rtsp://192.168.1.100:8554/office
```

## 🚀 Production Deployment

### Systemd Service

Create a systemd service for automatic startup:

```bash
# Create service file
sudo tee /etc/systemd/system/rtsp-clients.service << EOF
[Unit]
Description=RTSP Clients
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/path/to/scripts
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
EOF

# Enable and start
sudo systemctl enable rtsp-clients.service
sudo systemctl start rtsp-clients.service
```

### Backup and Recovery

```bash
# Backup configurations
tar -czf rtsp-clients-backup-$(date +%Y%m%d).tar.gz \
  docker-compose*.yml env.* Dockerfile* *.py

# Restore configurations
tar -xzf rtsp-clients-backup-20241201.tar.gz
docker compose up -d
```

## 📝 Example Workflows

### Single Machine Setup

```bash
# 1. Clone repository
git clone <repo> && cd scripts

# 2. Configure room
cp env.office env.local
nano env.local  # Edit for your setup

# 3. Deploy
./setup_docker.sh

# 4. Verify
docker ps | grep rtsp-client
```

### Multi-Machine Deployment

```bash
# Machine 1 (Office)
scp -r scripts/ user@office-machine:/home/user/
ssh user@office-machine "cd scripts && ./setup_docker.sh"

# Machine 2 (Kitchen)
scp -r scripts/ user@kitchen-machine:/home/user/
ssh user@kitchen-machine "cd scripts && ./setup_docker.sh"

# Machine 3 (Living Room)
scp -r scripts/ user@livingroom-machine:/home/user/
ssh user@livingroom-machine "cd scripts && ./setup_docker.sh"
```

## 🤝 Support

For issues or questions:
- Check container logs: `docker logs <container-name>`
- Verify audio system: `pactl info`
- Test network connectivity: `nc -zv <server-ip> <port>`
- Check Docker status: `docker system info`
- Review this README and troubleshooting sections
