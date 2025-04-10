"""
Architectural Improvement Suggestions for Twin

This file provides concrete code examples showing how the current architecture
could be improved with better modularity and separation of concerns.
"""

# ----------------------------------------------------------------------
# 1. Event Bus - Decouple Components with Event-Based Communication
# ----------------------------------------------------------------------

class EventBus:
    """Simple event bus for decoupling components"""
    
    def __init__(self):
        self._subscribers = {}
        
    def subscribe(self, event_type, callback):
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(callback)
        
    def publish(self, event_type, data=None):
        if event_type in self._subscribers:
            for callback in self._subscribers[event_type]:
                callback(data)


# Example usage:
"""
# Initialize global event bus
event_bus = EventBus()

# Audio processor publishes events
def audio_processor_callback(indata, frames, time_info, status):
    # Process audio...
    if detected_speech:
        event_bus.publish('speech_detected', audio_data)

# Transcriber subscribes to speech events
def init_transcriber():
    event_bus.subscribe('speech_detected', process_speech)
    
def process_speech(audio_data):
    # Transcribe speech...
    event_bus.publish('transcription_ready', transcription)

# Command processor subscribes to transcriptions
event_bus.subscribe('transcription_ready', process_transcription)
"""

# ----------------------------------------------------------------------
# 2. Configuration Management - Extract Hardcoded Constants
# ----------------------------------------------------------------------

class Config:
    """Configuration manager with defaults and external loading"""
    
    def __init__(self):
        # Default configuration
        self._config = {
            'audio': {
                'sample_rate': 16000,
                'buffer_duration': 3,
                'small_buffer_duration': 0.2,
                'silence_threshold': 0.000005,
                'channels': 1,
                'chunk_size': 1024,
            },
            'transcription': {
                'device_type': 'cuda',
                'model': 'turbo',
                'language': 'en',
                'similarity_threshold': 85,
            },
            'wake': {
                'phrases': ["Hey computer.", "Hey twin"],
                'similarity_threshold': 60,
                'distance_threshold': 0.30,
                'timeout': 24,
            },
            'vector_search': {
                'amygdala_threshold': 1.1,
                'na_threshold': 1.2,
                'hip_threshold': 1.1,
            },
            'command': {
                'risk_threshold': 0.5,
                'cooldown_period': 0,
            },
            'paths': {
                'tts_python': '/home/andy/venvs/tts-env/bin/python',
                'tts_script': '/home/andy/scripts/tts/tts.py',
                'wake_sound': '/media/mass/scripts/twin/wake.wav',
                'sleep_sound': '/media/mass/scripts/twin/sleep.wav',
            }
        }
    
    def load_from_file(self, config_file):
        """Load configuration from file"""
        import json
        try:
            with open(config_file, 'r') as f:
                loaded_config = json.load(f)
                self._update_nested_dict(self._config, loaded_config)
        except Exception as e:
            print(f"Error loading config: {e}")
    
    def _update_nested_dict(self, d, u):
        """Update nested dictionary with another dictionary"""
        import collections.abc
        for k, v in u.items():
            if isinstance(v, collections.abc.Mapping):
                d[k] = self._update_nested_dict(d.get(k, {}), v)
            else:
                d[k] = v
        return d
    
    def get(self, section, key=None):
        """Get configuration value"""
        if key is None:
            return self._config.get(section, {})
        return self._config.get(section, {}).get(key)


# Example usage:
"""
config = Config()
config.load_from_file('config.json')

# Access configuration
sample_rate = config.get('audio', 'sample_rate')
wake_phrases = config.get('wake', 'phrases')
"""

# ----------------------------------------------------------------------
# 3. Audio Processing Module - Proper Class Design
# ----------------------------------------------------------------------

class AudioProcessor:
    """Handles audio input, processing, and buffering"""
    
    def __init__(self, config, event_bus):
        self.config = config
        self.event_bus = event_bus
        self.audio_buffer = collections.deque(
            maxlen=self._calculate_buffer_size())
        self.small_audio_buffer = collections.deque(
            maxlen=self._calculate_small_buffer_size())
        
    def _calculate_buffer_size(self):
        sample_rate = self.config.get('audio', 'sample_rate')
        duration = self.config.get('audio', 'buffer_duration')
        return sample_rate * duration
    
    def _calculate_small_buffer_size(self):
        sample_rate = self.config.get('audio', 'sample_rate')
        duration = self.config.get('audio', 'small_buffer_duration')
        return int(sample_rate * duration)
    
    def audio_callback(self, indata, frames, time_info, status):
        """Handle audio data from sounddevice"""
        if status:
            self.event_bus.publish('audio_error', f"Audio callback error: {status}")
        
        # Process audio data
        audio_data = indata[:, 0] if indata.shape[1] > 1 else indata.flatten()
        self.audio_buffer.extend(audio_data)
        self.small_audio_buffer.extend(audio_data)
        
        # Calculate RMS for silence detection
        small_rms = self._calculate_rms(list(self.small_audio_buffer))
        silence_threshold = self.config.get('audio', 'silence_threshold')
        
        # Emit appropriate events
        if small_rms < silence_threshold:
            self.event_bus.publish('silence_detected', small_rms)
        else:
            self.event_bus.publish('audio_active', small_rms)
        
        # Periodically publish buffer for processing
        if len(self.audio_buffer) >= self.audio_buffer.maxlen * 0.95:
            buffer_data = np.array(list(self.audio_buffer), dtype=np.float32)
            self.event_bus.publish('buffer_ready', buffer_data)
    
    def _calculate_rms(self, audio_data):
        """Calculate Root Mean Square of audio data"""
        if len(audio_data) == 0:
            return 0
        return np.sqrt(np.mean(np.square(audio_data)))
    
    def start(self):
        """Start audio input stream"""
        import sounddevice as sd
        
        sample_rate = self.config.get('audio', 'sample_rate')
        channels = self.config.get('audio', 'channels')
        chunk_size = self.config.get('audio', 'chunk_size')
        
        try:
            # Find appropriate device
            self._find_and_log_devices()
            device = self._select_input_device()
            
            # Start the input stream
            self.stream = sd.InputStream(
                callback=self.audio_callback,
                channels=channels,
                samplerate=sample_rate,
                blocksize=chunk_size,
                device=device,
                dtype="float32",
            )
            self.stream.start()
            self.event_bus.publish('audio_started', device)
        except Exception as e:
            self.event_bus.publish('audio_error', f"Failed to start audio: {e}")
    
    def _find_and_log_devices(self):
        """Find and log available audio devices"""
        import sounddevice as sd
        devices = sd.query_devices()
        device_info = []
        for i, device in enumerate(devices):
            device_info.append({
                'id': i,
                'name': device['name'],
                'sample_rate': device['default_samplerate'],
                'input_channels': device['max_input_channels'],
            })
        self.event_bus.publish('audio_devices', device_info)
        return devices
    
    def _select_input_device(self):
        """Select appropriate input device"""
        # Implementation details omitted for brevity
        # Would use various fallback mechanisms as in current code
        return "default"  # For example


# ----------------------------------------------------------------------
# 4. Transcription Service - Better Separation of Concerns
# ----------------------------------------------------------------------

class TranscriptionService:
    """Handles audio transcription with model management"""
    
    def __init__(self, config, event_bus):
        self.config = config
        self.event_bus = event_bus
        self.recent_transcriptions = collections.deque(maxlen=10)
        self.history_buffer = collections.deque(
            maxlen=self.config.get('transcription', 'history_buffer_size', 4))
        
        # Initialize transcription model or remote client based on config
        self.use_remote = self.config.get('transcription', 'use_remote', False)
        if not self.use_remote:
            self._init_local_model()
        
        # Subscribe to events
        self.event_bus.subscribe('buffer_ready', self.process_audio)
    
    def _init_local_model(self):
        """Initialize local transcription model"""
        try:
            from faster_whisper import WhisperModel
            model_name = self.config.get('transcription', 'model')
            device = self.config.get('transcription', 'device_type')
            compute_type = "float16" if device == "cuda" else "float32"
            
            self.model = WhisperModel(model_name, device=device, compute_type=compute_type)
            self.event_bus.publish('model_loaded', {
                'type': 'transcription',
                'name': model_name,
                'device': device
            })
        except Exception as e:
            self.event_bus.publish('model_error', f"Failed to load transcription model: {e}")
            self.model = None
    
    async def process_audio(self, audio_data):
        """Process audio buffer and emit transcription events"""
        if audio_data is None or len(audio_data) == 0:
            return
        
        try:
            transcriptions, duration = await self._transcribe(audio_data)
            
            for text in transcriptions:
                self.recent_transcriptions.append(text)
                self.history_buffer.append(text)
                
                self.event_bus.publish('transcription', {
                    'text': text,
                    'duration': duration,
                    'history': list(self.history_buffer)
                })
        except Exception as e:
            self.event_bus.publish('transcription_error', str(e))
    
    async def _transcribe(self, audio_data):
        """Perform actual transcription, either locally or remotely"""
        if self.use_remote:
            return await self._remote_transcribe(audio_data)
        else:
            return await self._local_transcribe(audio_data)
    
    async def _local_transcribe(self, audio_data):
        """Transcribe using local model"""
        # Implementation similar to current code but adapted for class context
        pass
    
    async def _remote_transcribe(self, audio_data):
        """Transcribe using remote API"""
        # Implementation similar to current code but adapted for class context
        pass


# ----------------------------------------------------------------------
# 5. State Manager - Better State Management
# ----------------------------------------------------------------------

class StateManager:
    """Manages application state and transitions"""
    
    def __init__(self, config, event_bus):
        self.config = config
        self.event_bus = event_bus
        self.state = 'sleeping'  # Initial state
        self.wake_start_time = None
        self.session_data = None
        
        # Subscribe to relevant events
        self.event_bus.subscribe('wake_detected', self.handle_wake)
        self.event_bus.subscribe('command_executed', self.update_activity)
        self.event_bus.subscribe('transcription', self.handle_transcription)
    
    def handle_wake(self, wake_data):
        """Handle wake word detection"""
        if self.state == 'sleeping':
            self.state = 'awake'
            self.wake_start_time = time.time()
            
            # Create new session
            self.session_data = {
                "session_id": str(uuid.uuid4()),
                "start_time": datetime.now().isoformat(),
                "wake_phrase": wake_data.get('text', ''),
                "before_transcriptions": wake_data.get('recent_transcriptions', []),
                "after_transcriptions": [],
                "inferences": [],
                "commands_executed": [],
                "vectorstore_results": [],
                "user_feedback": [],
                "complete_transcription": "",
                "source_commands": [],
            }
            
            # Notify system is awake
            self.event_bus.publish('state_changed', {
                'old_state': 'sleeping',
                'new_state': 'awake',
                'session_id': self.session_data["session_id"]
            })
            
            # Play wake sound
            self.event_bus.publish('play_sound', {
                'type': 'wake',
                'path': self.config.get('paths', 'wake_sound')
            })
    
    def handle_transcription(self, transcription_data):
        """Handle new transcription"""
        if self.state == 'awake' and self.session_data:
            # Add to session data
            self.session_data['after_transcriptions'].append(transcription_data['text'])
            
            # Reset timeout if appropriate
            self.update_activity()
    
    def update_activity(self, data=None):
        """Update last activity timestamp to prevent timeout"""
        if self.state == 'awake':
            self.wake_start_time = time.time()
    
    def check_timeout(self):
        """Check if system should go to sleep due to inactivity"""
        if self.state == 'awake' and self.wake_start_time:
            timeout = self.config.get('wake', 'timeout')
            if (time.time() - self.wake_start_time) > timeout:
                self.go_to_sleep()
    
    def go_to_sleep(self):
        """Transition to sleep state"""
        if self.state != 'sleeping':
            old_state = self.state
            self.state = 'sleeping'
            
            # Finalize session data
            if self.session_data:
                self.session_data['end_time'] = datetime.now().isoformat()
                self.session_data['duration'] = time.time() - self.wake_start_time
                complete_transcription = " ".join(self.session_data['after_transcriptions'])
                self.session_data['complete_transcription'] = complete_transcription
                
                # Generate quality control report
                self.event_bus.publish('generate_report', self.session_data)
                self.session_data = None
            
            # Notify system is asleep
            self.event_bus.publish('state_changed', {
                'old_state': old_state,
                'new_state': 'sleeping'
            })
            
            # Play sleep sound
            self.event_bus.publish('play_sound', {
                'type': 'sleep',
                'path': self.config.get('paths', 'sleep_sound')
            })


# ----------------------------------------------------------------------
# 6. Main Application - Orchestrating Components with DI
# ----------------------------------------------------------------------

class TwinApplication:
    """Main application class that orchestrates all components"""
    
    def __init__(self, config_file=None):
        # Initialize core systems
        self.event_bus = EventBus()
        self.config = Config()
        if config_file:
            self.config.load_from_file(config_file)
        
        # Initialize logging
        self._setup_logging()
        
        # Initialize components with dependency injection
        self.audio = AudioProcessor(self.config, self.event_bus)
        self.transcriber = TranscriptionService(self.config, self.event_bus)
        self.state_manager = StateManager(self.config, self.event_bus)
        self.vector_search = VectorSearchService(self.config, self.event_bus)
        self.inference = InferenceService(self.config, self.event_bus)
        self.command_executor = CommandExecutor(self.config, self.event_bus)
        
        # Setup periodic tasks
        self.tasks = []
    
    def _setup_logging(self):
        """Set up logging system"""
        import logging
        import os
        
        log_dir = self.config.get('logging', 'directory', 'logs')
        log_file = self.config.get('logging', 'file', 'continuous.log')
        os.makedirs(log_dir, exist_ok=True)
        
        handlers = [
            logging.FileHandler(os.path.join(log_dir, log_file), mode='a'),
            logging.StreamHandler()
        ]
        
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(name)s] [%(levelname)s] [%(filename)s] %(message)s",
            handlers=handlers
        )
        
        # Configure specific loggers
        logging.getLogger("faster_whisper").setLevel(logging.ERROR)
        
        self.logger = logging.getLogger("twin")
        self.logger.info("Logging initialized")
    
    async def start(self):
        """Start all components and main processing loop"""
        # Start audio processing
        self.audio.start()
        
        # Setup periodic tasks
        self.tasks.append(asyncio.create_task(self._periodic_state_check()))
        
        # Start webserver if enabled
        if self.config.get('webserver', 'enabled', True):
            from webserver import start_webserver
            self.web_runner = await start_webserver(self.event_bus, self.config)
        
        self.logger.info("Twin application started")
        
        # Keep application running
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            self.logger.info("Shutdown requested")
        except Exception as e:
            self.logger.error(f"Unexpected error: {str(e)}")
            self.logger.exception("Error details:")
        finally:
            await self.stop()
    
    async def _periodic_state_check(self):
        """Periodic task to check system state"""
        while True:
            # Check for sleep timeout
            self.state_manager.check_timeout()
            await asyncio.sleep(1)
    
    async def stop(self):
        """Stop all components and cleanup"""
        # Cancel all tasks
        for task in self.tasks:
            task.cancel()
        
        # Stop audio
        if hasattr(self.audio, 'stream') and self.audio.stream:
            self.audio.stream.stop()
        
        # Stop webserver
        if hasattr(self, 'web_runner'):
            await self.web_runner.cleanup()
        
        self.logger.info("Twin application stopped")


# ----------------------------------------------------------------------
# 7. Entry Point - Clean Startup with Better Argument Handling
# ----------------------------------------------------------------------

def parse_arguments():
    """Parse command line arguments"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Twin voice assistant with flexible inference options."
    )
    parser.add_argument(
        "-c", "--config", 
        help="Path to configuration file"
    )
    parser.add_argument(
        "-e", "--execute", 
        action="store_true", 
        help="Execute the commands returned by the inference model"
    )
    parser.add_argument(
        "--remote-inference", 
        help="Use remote inference. Specify the full URL for the inference server."
    )
    parser.add_argument(
        "--remote-store", 
        help="Specify the URL for the vector store server."
    )
    parser.add_argument(
        "-s", "--silent", 
        action="store_true", 
        help="Disable TTS playback"
    )
    parser.add_argument(
        "--source", 
        default=None, 
        help="Manually set the audio source (index or name)"
    )
    parser.add_argument(
        "--whisper-model", 
        default="turbo", 
        help="Specify the Whisper model size"
    )
    parser.add_argument(
        "--remote-transcribe", 
        help="Use remote transcription. Specify the URL for the transcription server."
    )
    
    return parser.parse_args()


async def main():
    """Application entry point"""
    args = parse_arguments()
    
    # Initialize and start the application
    app = TwinApplication(config_file=args.config)
    
    # Apply command line overrides to config
    if args.execute:
        app.config._config['command']['execute'] = True
    if args.remote_inference:
        app.config._config['inference']['remote_url'] = args.remote_inference
        app.config._config['inference']['use_remote'] = True
    if args.remote_store:
        app.config._config['vector_search']['remote_url'] = args.remote_store
    if args.silent:
        app.config._config['audio']['silent'] = True
    if args.source:
        app.config._config['audio']['source'] = args.source
    if args.whisper_model:
        app.config._config['transcription']['model'] = args.whisper_model
    if args.remote_transcribe:
        app.config._config['transcription']['remote_url'] = args.remote_transcribe
        app.config._config['transcription']['use_remote'] = True
    
    # Start the application
    await app.start()


if __name__ == "__main__":
    asyncio.run(main())