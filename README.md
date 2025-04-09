# Twin

Twin is a voice-controlled assistant that transcribes audio, processes commands, and interacts with a user's environment.

## Project Structure

```
twin/
├── twin/               # Main package
│   ├── __init__.py
│   ├── audio/          # Audio processing
│   │   ├── __init__.py
│   │   ├── devices.py  # Audio device handling
│   │   └── playback.py # Sound playback functions
│   ├── commands/       # Command processing
│   │   ├── __init__.py
│   │   └── processor.py # Command execution logic
│   ├── core/           # Core functionality
│   │   ├── __init__.py
│   │   └── prompt.py   # Prompt templates
│   ├── logging/        # Logging setup
│   │   ├── __init__.py
│   │   └── setup.py    # Logging configuration
│   ├── nlp/            # Natural language processing
│   │   ├── __init__.py
│   │   ├── generation.py     # Text generation
│   │   ├── model.py          # LLM interface
│   │   ├── search.py         # Vector search
│   │   └── transcription.py  # Speech to text
│   ├── services/       # External services
│   │   ├── __init__.py
│   │   └── webserver.py      # API server
│   ├── utils/          # Utilities
│   │   ├── __init__.py
│   │   └── quality.py        # Quality control
│   └── main.py         # Main entry point
├── data/               # Data files
│   ├── audio/          # Audio assets
│   │   ├── wake.wav    # Wake sound
│   │   └── sleep.wav   # Sleep sound
│   └── prompts/        # Prompt templates
├── logs/               # Log directory
├── reports/            # Quality control reports
├── service/            # Service configuration
│   ├── twin.service    # Systemd service file
│   └── twin.env        # Environment variables
├── stores/             # Vector stores for semantic search
│   ├── amygdala.txt
│   ├── load.py
│   ├── na.txt
│   └── wake.txt
├── requirements.txt    # Python dependencies
└── run.py             # Application runner script
```

## Installation

1. Install the required dependencies:

```bash
pip install -r requirements.txt
```

2. Set up the systemd service:

```bash
cp service/twin.service ~/.config/systemd/user/
cp service/twin.env ~/.config/systemd/user/
systemctl --user daemon-reload
```

## Running

You can run Twin directly:

```bash
./run.py
```

Or as a service:

```bash
systemctl --user start twin
```

## Configuration

Twin can be configured with command-line arguments:

- `-e, --execute`: Execute commands returned by the inference model
- `--remote-inference`: URL for remote inference server
- `--remote-store`: URL for vector store server
- `-s, --silent`: Disable TTS playback
- `--source`: Manually set audio source (index or name)
- `--whisper-model`: Specify Whisper model size (default: turbo)
- `--remote-transcribe`: URL for remote transcription server 