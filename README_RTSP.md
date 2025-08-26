# Ultra Low-Latency RTSP Microphone Stream

Simple, native solution for streaming microphone audio via RTSP with **sub-200ms latency**.

## Quick Start

```bash
# Start the RTSP microphone stream
./start_rtsp_mic.sh

# In another terminal, test the latency
./test_mic_latency.sh
```

## How It Works

1. **MediaMTX RTSP Server**: Handles the RTSP protocol
2. **Native Python Client**: Streams mic audio using FFmpeg with optimal settings
3. **G.711 μ-law Codec**: Minimal compression delay at 8kHz
4. **UDP Transport**: No TCP overhead or reliability delays

## Key Optimizations

- **Codec**: G.711 μ-law (no compression delay)
- **Sample Rate**: 8kHz (small packets, fast transmission)
- **Transport**: UDP only (no handshakes or retransmissions)
- **Buffering**: Minimal queues throughout the pipeline
- **Native Execution**: No Docker overhead

## Stream Details

- **URL**: `rtsp://127.0.0.1:8554/mic`
- **Codec**: G.711 μ-law
- **Format**: 8kHz, mono, 64 kbps
- **Latency**: Sub-200ms end-to-end

## Why No Docker?

Docker adds audio subsystem complexity and buffering layers. The native solution:
- Direct PulseAudio/PipeWire access
- No container audio routing overhead  
- Simpler debugging and maintenance
- Better real-time performance

Perfect for your twin project's real-time audio requirements! 🎤✨
