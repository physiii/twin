# Twin - Voice-Controlled Home Assistant

Twin is an advanced voice-controlled home assistant that combines real-time audio processing, AI-powered speech recognition, vector-based semantic search, and intelligent command execution to provide seamless home automation control.

## System Architecture

### Core Components

1. **Audio Processing Pipeline** (`audio.py`, `rtsp_audio.py`)
2. **Speech Recognition** (`transcribe.py`)
3. **Inference Engine** (`generator.py`)
4. **Vector Search System** (`search.py`)
5. **Command Execution** (`command.py`)
6. **Quality Control & Reporting** (`quality_control.py`)
7. **Web Interface** (`webserver.py`)

## Room/Location Awareness

**Yes! Twin has sophisticated room and location awareness similar to Home Assistant.** The system automatically detects which room commands should apply to and only controls devices in that specific room.

### How Room Detection Works:

1. **Self Context**: Each deployment has a location-specific "self" context file:
   - `stores/self/office.txt` - Office location context
   - `stores/self/media.txt` - Media room context  
   - `stores/self/kitchen.txt` - Kitchen context
   - `stores/self/bedroom.txt` - Bedroom context

2. **Room Configuration**: Devices are mapped to rooms in configuration files:
   ```json
   // tools/lights/rooms.json
   {
     "rooms": [
       {
         "name": "Media",
         "lights": [10, 11, 12, 13, 14]
       },
       {
         "name": "Kitchen", 
         "lights": [5, 6, 7, 8]
       },
       {
         "name": "Office",
         "lights": [1, 2, 3, 4, 5, 6, 7, 8, 9]
       }
     ]
   }
   ```

3. **Automatic Room Resolution**: When you say "turn on the lights", the system:
   - Identifies the room from the AI's self-context
   - Replaces `<room_name>` placeholders with the actual room
   - Only controls devices in that specific room

### Room-Aware Commands:

**Lighting Control:**
```bash
lights --power on --room office     # Turn on office lights only
lights --power off --room kitchen   # Turn off kitchen lights only
lights --brightness 75 --room media # Dim media room to 75%
lights --color blue --room bedroom  # Set bedroom lights to blue
```

**HVAC Control:**
```bash
thermostat --set-temp 72 --room office    # Set office temperature
thermostat --power on --room bedroom      # Turn on bedroom AC
thermostat --status --room kitchen        # Check kitchen thermostat
```

**Multi-Room Support:**
- Each room can have independent HVAC zones
- Lighting scenes can be room-specific
- Commands automatically scope to the correct room

### Example Room-Aware Interaction:

```
User: "Turn on the lights"
↓
System detects: Currently in "office" context
↓  
Generates: lights --power on --room office
↓
Result: Only office lights turn on (IDs 1-9)
```

**vs.**

```
User: "Turn on the lights" 
↓
System detects: Currently in "media" context
↓
Generates: lights --power on --room media  
↓
Result: Only media room lights turn on (IDs 10-14)
```

This ensures commands are contextually appropriate and prevents accidentally controlling the wrong room's devices.

### Explicit Room Commands:

You can also explicitly specify rooms in voice commands:

```
"Turn on the kitchen lights"        → lights --power on --room kitchen
"Set the bedroom temperature to 68" → thermostat --set-temp 68 --room bedroom  
"Turn off all the office lights"    → lights --power off --room office
"Dim the media room lights to 50%"  → lights --brightness 50 --room media
```

The system supports both implicit (context-based) and explicit (user-specified) room targeting for maximum flexibility.

## Source-to-Location Mapping for Docker Deployments

For multi-room Docker deployments, Twin provides dynamic location detection based on audio source:

### Quick Setup

1. **Run the setup wizard:**
   ```bash
   python setup_rooms.py
   ```

2. **Test the configuration:**
   ```bash
   python test_room_integration.py
   ```

### Configuration Structure

**File: `config/source_locations.json`**
```json
{
  "home_assistant": {
    "url": "http://homeassistant:8123",
    "token_env": "HA_TOKEN",
    "sync_rooms": true
  },
  "source_mappings": {
    "rtsp://192.168.1.100:554/audio": "office",
    "rtsp://192.168.1.101:554/audio": "kitchen",
    "device_13": "office",
    "pulse": "office"
  },
  "room_aliases": {
    "media": ["media_room", "entertainment", "tv_room"],
    "living_room": ["living", "lounge", "family_room"]
  },
  "non_ha_devices": {
    "office": {
      "philips_hue": {
        "bridge_ip": "192.168.1.129",
        "lights": [1, 2, 3, 4, 5, 6, 7, 8, 9]
      }
    }
  },
  "default_location": "office"
}
```

### Room Detection Priority

Twin uses a smart priority system for room detection:

1. **Explicit Room in Voice Command**: "Turn on kitchen lights" → `kitchen`
2. **Source-Based Location**: RTSP source mapped to specific room  
3. **Self-Context Analysis**: Legacy room detection from context files
4. **Default Fallback**: Configured default location

### Integration Benefits

- **Home Assistant Sync**: Automatically discovers HA rooms and entities
- **Command Validation**: Prevents executing commands on non-existent devices
- **Multi-Device Support**: Handles both HA entities and direct device APIs
- **Flexible Sources**: Supports RTSP, USB mics, PulseAudio, etc.
- **Room Aliases**: Natural language variants ("living room" = "lounge")

### Environment Variables

```bash
# Home Assistant Integration
HA_TOKEN=your_long_lived_access_token_here
HA_URL=http://homeassistant:8123

# Device Credentials (as needed)
MIDEA_TOKEN=your_midea_token
MIDEA_KEY=your_midea_key
```

### Voice Command Examples

```
# Uses source location (e.g., office RTSP camera)
"Turn on the lights" → office lights activated

# Explicit room override
"Turn on the kitchen lights" → kitchen lights activated

# Room validation prevents errors
"Turn on the bathroom lights" → Error: No lights in bathroom

# Multiple room types supported
"Set bedroom temperature to 70" → bedroom thermostat
```

## 📡 RTSP Microphone Streaming

For remote microphone setups, use the included RTSP server scripts:

### Quick Setup

```bash
# Install dependencies and setup
./scripts/setup_rtsp_mic.sh

# Start RTSP server (interactive menu)
./scripts/start_rtsp_mic.sh

# Or start directly
python3 scripts/rtsp_mic_server.py --port 8554
```

### Multi-Room RTSP Deployment

```bash
# Office computer
python3 scripts/rtsp_mic_server.py --port 8554 --device "Office USB Mic"

# Kitchen computer  
python3 scripts/rtsp_mic_server.py --port 8555 --device "Kitchen Mic"

# Living room computer
python3 scripts/rtsp_mic_server.py --port 8556 --device "Living Room Mic"
```

Then connect Twin to these streams:

```json
{
  "source_mappings": {
    "rtsp://office_pc:8554/audio": "office",
    "rtsp://kitchen_pc:8555/audio": "kitchen",
    "rtsp://livingroom_pc:8556/audio": "living_room"
  }
}
```

### Features

- 🎤 **PipeWire/PulseAudio Support** - Modern Linux audio compatibility
- 🔧 **Auto-Setup Scripts** - Dependency installation and configuration
- 🚀 **Interactive Launcher** - Easy device selection and testing
- 🔄 **Systemd Service** - Run as background service
- 🛡️ **Firewall Setup** - Automatic network configuration
- 📊 **Quality Control** - Configurable sample rates and formats

See [`scripts/README.md`](scripts/README.md) for detailed documentation.

## Signal Path & Data Flow

### 1. Audio Capture
```
Audio Input → Buffer Management → Silence Detection → Transcription
```

**Audio Sources:**
- **Microphone Input**: Direct audio capture via sounddevice
- **RTSP Stream**: Network audio capture from IP cameras or streaming devices

**Buffer Management:**
- **Main Buffer**: 3-second rolling buffer for transcription (`BUFFER_DURATION = 3`)
- **Small Buffer**: 0.2-second buffer for silence detection (`SMALL_BUFFER_DURATION = 0.2`)
- **Sample Rate**: 16kHz (`SAMPLE_RATE = 16000`)
- **Silence Threshold**: Configurable RMS threshold to filter ambient noise (`SILENCE_THRESHOLD = 0.01`)

### 2. Speech Recognition & Transcription
```
Audio Buffer → Whisper Model → Text Transcription → Similarity Filtering
```

**Whisper Integration:**
- **Model**: Configurable Whisper model (default: `turbo`)
- **Language**: English (`LANGUAGE = 'en'`)
- **Similarity Filtering**: 85% similarity threshold to prevent duplicate transcriptions
- **Remote Option**: Can use remote transcription services via `REMOTE_TRANSCRIBE_URL`

**Transcription Process:**
1. RMS calculation determines if audio contains speech
2. Audio data sent to Whisper model
3. Transcribed text filtered for duplicates
4. Results stored in rolling buffers for context

### 3. Wake Detection & State Management
```
Transcription → Wake Phrase Detection → System State Change → Audio Feedback
```

**Wake Mechanism:**
- Continuous monitoring for wake phrases (e.g., "Hey computer")
- **Awake State**: 24-second timeout (`WAKE_TIMEOUT = 24`)
- **Audio Feedback**: Wake/sleep sounds for user confirmation
- **Media Pause**: Automatically pauses media players via `playerctl`

**State Transitions:**
```
Sleeping → Wake Phrase Detected → Awake → Command Processing → Timeout → Sleeping
```

### 4. Vector Search & Semantic Classification
```
Transcription → Embedding Generation → Vector Search → Centroid Classification
```

**Vector Store System:**
- **Centroids**: Pre-computed semantic clusters for different contexts
  - `complete_centroid.json`: Complete command patterns
  - `incomplete_centroid.json`: Partial/incomplete patterns
- **Distance Thresholds**:
  - AMY (Amygdala): `1.1` - Emotional/urgent responses
  - NA (Not Applicable): `1.4` - Non-actionable content
  - HIP (Hippocampus): `1.1` - Memory/context retrieval

**Search Process:**
1. Text converted to embeddings
2. Vector similarity search against knowledge base
3. Centroid classification determines response type
4. Results influence command generation

### 5. Inference & Command Generation
```
Context + Transcription → AI Inference → Command Generation → Risk Assessment
```

**Inference Pipeline:**
- **Context Building**: History buffer + current transcription
- **AI Processing**: Local or remote inference engine
- **Command Extraction**: Structured commands from natural language
- **Risk Assessment**: Commands evaluated for safety (`RISK_THRESHOLD = 0.5`)

**Command Structure:**
```json
{
  "commands": ["command1", "command2"],
  "risk": 0.3,
  "confirmed": false,
  "reasoning": "User wants to control lights"
}
```

### 6. Command Execution & Home Automation
```
Generated Commands → Validation → Execution → Feedback
```

**Execution Framework:**
- **SSH Integration**: Remote command execution via `SSH_HOST_TARGET`
- **Home Assistant**: Integration with Home Assistant API
- **Tool Integration**: Direct system tool execution
- **Confirmation**: High-risk commands require user confirmation

**Supported Command Types:**
- Lighting control (Philips Hue, smart switches)
- HVAC/Thermostat control
- Media control (play/pause/volume)
- Security systems (locks, cameras)
- Screenshots and system operations

### 7. Quality Control & Session Tracking
```
Session Data → Quality Analysis → Report Generation → Performance Metrics
```

**Session Management:**
- **Session ID**: Unique identifier for each interaction
- **Transcription Log**: Complete conversation history
- **Command Tracking**: All executed commands with timestamps
- **Performance Metrics**: Success rate, response time, user satisfaction

**Quality Metrics:**
- Command success rate
- Wake phrase accuracy
- Response latency
- User satisfaction scoring
- Error pattern analysis

## Configuration & Deployment

### Environment Configuration
Key configuration options in `config.py`:

```python
# Audio Settings
SAMPLE_RATE = 16000
BUFFER_DURATION = 3.0
SILENCE_THRESHOLD = 0.01

# AI Models
WHISPER_MODEL = 'turbo'
DEVICE_TYPE = 'cuda'  # or 'cpu'
COMPUTE_TYPE = 'float16'

# Thresholds
SIMILARITY_THRESHOLD = 85
RISK_THRESHOLD = 0.5
WAKE_TIMEOUT = 24

# Remote Services
REMOTE_STORE_URL = 'http://vector-store:8000'
REMOTE_INFERENCE_URL = 'http://inference:8000'
REMOTE_TRANSCRIBE_URL = 'http://transcribe:8000'
```

### Room Configuration

**Device Mapping**: Configure which devices belong to each room:

```json
// tools/lights/rooms.json
{
  "rooms": [
    {
      "name": "Office",
      "lights": [1, 2, 3, 4, 5, 6, 7, 8, 9]
    },
    {
      "name": "Kitchen",
      "lights": [5, 6, 7, 8]
    },
    {
      "name": "Media",
      "lights": [10, 11, 12, 13, 14]
    }
  ]
}
```

**Location Context**: Create self-context files for each room:

```bash
# stores/self/office.txt
You are an intelligence woven into the fabric of this office, 
sensing light, temperature, and environment. Always reference 
the "office" location for device commands.

# stores/self/media.txt  
You are an intelligence woven into the fabric of this environment.
The name of this location is "media".

# stores/self/kitchen.txt
You are an intelligence for the kitchen environment.
The name of this location is "kitchen".
```

**Multi-Room Deployment**: Deploy separate instances for each room:
```bash
# Office instance
python main.py -e --source pulse --room office

# Media room instance  
python main.py -e --source rtsp --room media

# Kitchen instance
python main.py -e --source device_5 --room kitchen
```

### Docker Deployment

**Container Architecture:**
```
twin-app → Main application container
├── Audio processing
├── Speech recognition
├── Inference engine
└── Command execution

External Services (optional):
├── Vector Store Service
├── Inference Service
└── Transcription Service
```

**Running the System:**

1. **Development Mode:**
```bash
python main.py -e --source pulse
```

2. **Docker Compose:**
```bash
docker-compose up -d
```

3. **With Remote Services:**
```bash
python main.py -e \
  --remote-inference http://inference:8000 \
  --remote-store http://vector-store:8000 \
  --remote-transcribe http://transcribe:8000
```

### Command Line Options

- `-e, --execute`: Enable command execution
- `--source`: Audio source (device index or name)
- `--whisper-model`: Whisper model size
- `--remote-inference`: Remote inference service URL
- `--remote-store`: Remote vector store URL
- `--remote-transcribe`: Remote transcription URL
- `-s, --silent`: Disable TTS playback

## Monitoring & Logs

### Docker Logs
```bash
# View main application logs
docker logs twin-app

# Follow logs in real-time
docker logs -f twin-app

# View specific service logs
docker-compose logs inference
docker-compose logs vector-store
```

### Log Files
- **Application Logs**: `logs/continuous.log`
- **Quality Reports**: `reports/`
- **Session Reports**: `reports/report.json`

### Quality Control Reports

The system generates comprehensive quality control reports stored in `reports/report.json`:

```json
{
  "sessions": [
    {
      "timestamp": "2025-01-01T12:00:00",
      "session_id": "uuid",
      "duration": 24.5,
      "commands_executed": 3,
      "success_rate": 100.0,
      "score": 0.8,
      "description": "Session analysis and recommendations"
    }
  ],
  "summary": "530 sessions recorded. Average score: 0.492.",
  "average_score": 0.492
}
```

### Web Interface

Access the web interface at `http://localhost:8080` for:
- Real-time system status
- Session monitoring
- Configuration management
- Log viewing
- Quality metrics dashboard

## Performance Optimization

### Audio Processing
- **Silence Detection**: Reduces unnecessary transcription overhead
- **Buffer Management**: Optimized buffer sizes for responsiveness
- **RMS Calculation**: Efficient audio level monitoring

### AI Processing
- **CUDA Support**: GPU acceleration for Whisper and embeddings
- **Remote Services**: Distribute processing across multiple containers
- **Model Caching**: Persistent model loading

### Network & Storage
- **RTSP Streaming**: Low-latency audio capture
- **Vector Caching**: Pre-computed embeddings
- **Session Persistence**: Efficient data storage

## Troubleshooting

### Common Issues

1. **Audio Device Not Found**
   - Check available devices: `python -c "import sounddevice; print(sounddevice.query_devices())"`
   - Specify device explicitly: `--source 13`

2. **RTSP Connection Issues**
   - Verify RTSP URL accessibility
   - Check network connectivity
   - Validate audio codec support

3. **Wake Detection Problems**
   - Adjust `SILENCE_THRESHOLD`
   - Check microphone levels
   - Review wake phrase training

4. **Command Execution Failures**
   - Verify SSH connectivity
   - Check Home Assistant API access
   - Review command permissions

5. **Room Detection Issues**
   - Verify `stores/self/<room>.txt` exists and contains location name
   - Check `tools/lights/rooms.json` device mappings
   - Ensure device IDs match your actual hardware
   - Test with explicit room: `lights --power on --room office`

### Performance Tuning

1. **Latency Optimization**
   - Reduce buffer sizes for faster response
   - Use remote services for distributed processing
   - Optimize wake timeout settings

2. **Accuracy Improvement**
   - Tune similarity thresholds
   - Update vector store with more examples
   - Adjust risk assessment parameters

## Development & Extension

### Adding New Commands
1. Update vector store with new command patterns
2. Extend command execution handlers
3. Add safety validation rules
4. Update quality control metrics

### Custom Integrations
- Implement new command executors in `command.py`
- Add vector embeddings for new domains
- Extend quality control reporting

### API Extensions
- RESTful endpoints for external control
- WebSocket integration for real-time updates
- Plugin architecture for modular extensions

## Security Considerations

- **Command Validation**: All commands validated before execution
- **Risk Assessment**: High-risk operations require confirmation
- **SSH Security**: Key-based authentication for remote execution
- **Network Security**: Secure communication with remote services
- **Audio Privacy**: Local processing option available

This comprehensive system provides a robust foundation for voice-controlled home automation with enterprise-grade monitoring, quality control, and extensibility. 