# Twin - Voice-Controlled Home Assistant

A sophisticated voice-controlled home assistant that combines real-time audio processing, AI-powered speech recognition, vector-based semantic search, and intelligent command execution to provide seamless home automation control.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run the application
python main.py -e --source pulse

# Or install as package
pip install -e .
twin -e --source pulse
```

## Features

- 🎤 **Multi-source Audio**: Support for microphones, RTSP streams, and network audio
- 🧠 **AI-Powered**: Advanced speech recognition with Whisper and intelligent command processing
- 🏠 **Room-Aware**: Automatic room detection and context-aware device control
- 🔍 **Vector Search**: Semantic understanding using vector embeddings
- 🛡️ **Quality Control**: Comprehensive session tracking and performance monitoring
- 🌐 **Web Interface**: Real-time monitoring and control dashboard
- 🐳 **Docker Ready**: Containerized deployment with Docker Compose

## Architecture

```
twin/
├── src/twin/           # Main application package
│   ├── core/          # Core functionality (config, room management)
│   ├── audio/         # Audio processing and RTSP handling
│   ├── ai/            # AI models, transcription, and inference
│   ├── commands/      # Command execution and home automation
│   ├── quality/       # Quality control and reporting
│   ├── web/           # Web server and API
│   └── utils/         # Utility functions and helpers
├── config/            # Configuration files
├── data/              # Data files (audio, stores, centroids)
├── scripts/           # RTSP server and utility scripts
├── tools/             # Home automation tools and integrations
├── tests/             # Test files
├── deployment/        # Docker and service files
└── docs/              # Documentation
```

## Documentation

- [Full Documentation](docs/README.md) - Complete system documentation
- [RTSP Setup Guide](scripts/README.md) - Multi-room audio streaming
- [Docker Deployment](deployment/) - Container deployment guide

## Quick Commands

```bash
# Development mode
python main.py -e --source pulse

# With remote services
python main.py -e \
  --remote-inference http://inference:8000 \
  --remote-store http://vector-store:8000 \
  --remote-transcribe http://transcribe:8000

# Docker deployment (from root directory)
docker compose up -d

# Docker build and run
docker compose up --build
```

## License

This project is licensed under the MIT License - see the LICENSE file for details.
