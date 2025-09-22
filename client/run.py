#!/usr/bin/env python3
import os
import shlex
import signal
import subprocess
import sys
import time
from pathlib import Path


def ensure_sudo():
    # Not needed on port 8554; keep for backward compatibility (no-op)
    return


def main():
    ensure_sudo()

    client_dir = Path(__file__).resolve().parent
    bin_path = client_dir / "mediamtx"
    conf_path = client_dir / "mediamtx.yml"
    port = 8554

    if not bin_path.exists() or not os.access(bin_path, os.X_OK):
        print(f"Missing or non-executable {bin_path}")
        sys.exit(1)
    if not conf_path.is_file():
        print(f"Missing config {conf_path}")
        sys.exit(1)

    # If already listening, don't start a duplicate server; but still try to start publisher
    listening = subprocess.run(
        f"lsof -i :{port} -sTCP:LISTEN -Pn >/dev/null 2>&1",
        shell=True
    ).returncode == 0

    server_proc = None
    if listening:
        print(f"MediaMTX already running on port {port}")
    else:
        print(f"Starting MediaMTX on port {port} with {conf_path}")
        server_proc = subprocess.Popen([str(bin_path), str(conf_path)])

    def _handle(sig, frame):
        try:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        finally:
            sys.exit(0)

    signal.signal(signal.SIGINT, _handle)
    signal.signal(signal.SIGTERM, _handle)

    # Wait and print port status
    for _ in range(30):
        if subprocess.run(f"lsof -i :{port} -sTCP:LISTEN -Pn >/dev/null 2>&1", shell=True).returncode == 0:
            print(f"Listening on TCP {port}")
            break
        time.sleep(0.2)

    # Start mic publisher to RTSP so the feed is always ready
    # Detect default PulseAudio source; try to start PulseAudio if needed
    def detect_pulse_source() -> str:
        try:
            src = subprocess.run(["pactl", "get-default-source"], capture_output=True, text=True, check=False).stdout.strip()
            if not src:
                src = subprocess.run(["bash", "-lc", "pactl list short sources | awk 'NR==1{print $2}'"], capture_output=True, text=True, check=False).stdout.strip()
            return src
        except Exception:
            return ""

    src = detect_pulse_source()
    if not src:
        print("No PulseAudio source detected; trying to start PulseAudio daemon...")
        subprocess.run(["pulseaudio", "--start", "--log-level=1"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(0.8)
        src = detect_pulse_source()
    if not src:
        print("ERROR: Could not find a PulseAudio source. Ensure PulseAudio/PipeWire is running and a mic is available.")
        sys.exit(1)
    rtsp_url = "rtsp://127.0.0.1:8554/mic"
    pub_cmd = [
        "ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error",
        "-f", "pulse", "-i", src,
        "-c:a", "aac", "-b:a", "96k", "-ar", "16000", "-ac", "1",
        "-f", "rtsp", "-rtsp_transport", "tcp", rtsp_url
    ]
    print(f"Starting mic publisher from '{src}' -> {rtsp_url}")
    pub_proc = subprocess.Popen(pub_cmd)

    # Keep running until interrupted; clean up both processes
    try:
        if server_proc is not None:
            rc = server_proc.wait()
        else:
            # If server was already running, just idle until interrupted
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            if pub_proc.poll() is None:
                pub_proc.terminate()
                pub_proc.wait(timeout=3)
        except Exception:
            try:
                pub_proc.kill()
            except Exception:
                pass
        if server_proc is not None:
            try:
                server_proc.terminate()
                server_proc.wait(timeout=5)
            except Exception:
                try:
                    server_proc.kill()
                except Exception:
                    pass
    sys.exit(0)


if __name__ == "__main__":
    main()


