#!/usr/bin/env python3
import os
import shlex
import socket
import subprocess
import sys
import time
from pathlib import Path


def run(cmd: str, check: bool = False, timeout: int | None = None) -> int:
    return subprocess.run(cmd, shell=True, check=check, timeout=timeout).returncode


def capture(cmd: list[str]) -> str:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return out.stdout.strip()
    except Exception:
        return ""


def detect_default_pulse_source() -> str:
    source = capture(["pactl", "get-default-source"]) or ""
    if not source:
        # fallback: first input source
        out = capture(["pactl", "list", "short", "sources"]) or ""
        for line in out.splitlines():
            parts = line.split('\t')
            if len(parts) >= 2:
                return parts[1]
    return source


def port_listening(port: int) -> bool:
    rc = run(f"lsof -i :{port} -sTCP:LISTEN -Pn >/dev/null 2>&1")
    return rc == 0


def main():
    server_ip = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
    path_name = sys.argv[2] if len(sys.argv) > 2 else "mic"
    duration = int(sys.argv[3]) if len(sys.argv) > 3 else 5

    client_dir = Path(__file__).resolve().parent
    server_cfg = client_dir / "mediamtx.yml"
    server_bin = client_dir / "mediamtx"

    if not server_cfg.is_file() or not server_bin.exists():
        print("Missing mediamtx assets in client/")
        sys.exit(1)

    # Verify server is running
    if not port_listening(554):
        print("RTSP server not listening on 554. Start it with client/run.py (sudo required) or enable the service with install.sh")
        sys.exit(1)

    # Detect LAN IP for second playback
    lan_ip = capture(["bash", "-lc", "hostname -I | awk '{print $1}'"]) or ""

    # Detect PulseAudio default source
    source = detect_default_pulse_source()
    if not source:
        print("No PulseAudio source found; install pulseaudio-utils and ensure audio is available")
        sys.exit(1)
    print(f"Using PulseAudio source: {source}")

    # Function to publish and play against a target address
    def publish_and_play(target: str) -> None:
        print(f"\nTesting target: rtsp://{target}:554/{path_name} for {duration}s")
        # Start ffplay first so it will latch when publish begins
        ffplay_cmd = f"timeout {duration + 6} ffplay -loglevel warning -autoexit -nodisp rtsp://{target}:554/{path_name}"
        ffplay_proc = subprocess.Popen(ffplay_cmd, shell=True)
        time.sleep(0.6)

        # Publish for duration seconds
        publish_cmd = (
            "ffmpeg -hide_banner -loglevel error "
            f"-f pulse -i {shlex.quote(source)} -t {duration} "
            "-c:a aac -b:a 128k -ar 16000 -ac 1 "
            f"-f rtsp -rtsp_transport tcp rtsp://{target}:554/{path_name}"
        )
        rc = run(publish_cmd)
        print("Publish:", "OK" if rc == 0 else f"FAIL (rc={rc})")

        # Wait for ffplay to exit
        try:
            ffplay_proc.wait(timeout=duration + 8)
        except subprocess.TimeoutExpired:
            ffplay_proc.kill()

    # 1) Localhost
    publish_and_play("127.0.0.1")

    # 2) LAN IP (if available)
    if lan_ip:
        publish_and_play(lan_ip)

    print("\nDone. If you didn't hear audio, verify the selected PulseAudio source.")


if __name__ == "__main__":
    main()


