#!/usr/bin/env python3
import os
import shlex
import signal
import subprocess
import sys
import time
from pathlib import Path


def ensure_sudo():
    if os.geteuid() != 0:
        print("Re-running with sudo for port 554...")
        os.execvp("sudo", ["sudo", sys.executable, *sys.argv])


def main():
    ensure_sudo()

    client_dir = Path(__file__).resolve().parent
    bin_path = client_dir / "mediamtx"
    conf_path = client_dir / "mediamtx.yml"
    port = 554

    if not bin_path.exists() or not os.access(bin_path, os.X_OK):
        print(f"Missing or non-executable {bin_path}")
        sys.exit(1)
    if not conf_path.is_file():
        print(f"Missing config {conf_path}")
        sys.exit(1)

    # If already listening, exit cleanly
    already = subprocess.run(
        f"lsof -i :{port} -sTCP:LISTEN -Pn >/dev/null 2>&1",
        shell=True
    ).returncode == 0
    if already:
        print(f"MediaMTX already running on port {port}")
        sys.exit(0)

    print(f"Starting MediaMTX on port {port} with {conf_path}")
    proc = subprocess.Popen([str(bin_path), str(conf_path)])

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
    for _ in range(10):
        if subprocess.run(f"lsof -i :{port} -sTCP:LISTEN -Pn >/dev/null 2>&1", shell=True).returncode == 0:
            print(f"Listening on TCP {port}")
            break
        time.sleep(0.3)

    # Tail child process until exit
    rc = proc.wait()
    sys.exit(rc)


if __name__ == "__main__":
    main()


