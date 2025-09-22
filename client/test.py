#!/usr/bin/env python3
import subprocess
import sys
import time
from pathlib import Path

def main():
    path = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else "mic"
    publish_local = "--publish" in sys.argv
    
    # Get LAN IP
    try:
        lan_ip = subprocess.run(["hostname", "-I"], capture_output=True, text=True).stdout.split()[0]
    except:
        lan_ip = ""
    
    out_dir = Path.cwd() / "test_audio"
    out_dir.mkdir(parents=True, exist_ok=True)
    
    for ip in ["127.0.0.1"] + ([lan_ip] if lan_ip else []):
        url = f"rtsp://{ip}:8554/{path}"
        print(f"\n=== Testing {ip} ===")
        print(f"RTSP feed: {url}")
        pub_proc = None
        if publish_local and ip == "127.0.0.1":
            # Try to publish real mic audio briefly to create a deterministic feed
            try:
                src = subprocess.run(["pactl", "get-default-source"], capture_output=True, text=True).stdout.strip()
                if not src:
                    src = subprocess.run(["bash", "-lc", "pactl list short sources | awk 'NR==1{print $2}'"], capture_output=True, text=True).stdout.strip()
                if src:
                    print(f"Publishing from default source: {src} (12s)...")
                    pub_proc = subprocess.Popen([
                        "ffmpeg", "-hide_banner", "-loglevel", "error",
                        "-f", "pulse", "-i", src, "-t", "12",
                        "-c:a", "aac", "-b:a", "96k", "-ar", "16000", "-ac", "1",
                        "-f", "rtsp", "-rtsp_transport", "tcp", url
                    ])
                    time.sleep(2)
                else:
                    print("No PulseAudio source found; skipping local publish")
            except Exception as e:
                print(f"Local publish skipped: {e}")
        
        # Quick probe before play for clear PASS/FAIL
        probe = subprocess.run([
            "ffprobe", "-v", "error", "-rtsp_transport", "tcp",
            "-select_streams", "a:0", "-show_streams", "-of", "compact=p=0:nk=1", url
        ], capture_output=True, text=True)
        probe_ok = probe.returncode == 0
        print(f"PROBE: {'PASS' if probe_ok else 'FAIL'} (rc={probe.returncode})")
        if not probe_ok and probe.stderr:
            print(f"  ffprobe: {probe.stderr.strip()}")

        # Play live feed with ffplay and report result
        ffplay_cmd = [
            "ffplay", "-loglevel", "warning", "-rtsp_transport", "tcp", "-autoexit", url
        ]
        print("ffplay command:")
        print("  ", " ".join(ffplay_cmd))
        print("Opening ffplay now (Ctrl+C to stop)...")
        play = subprocess.run(ffplay_cmd)
        play_ok = play.returncode == 0
        print(f"PLAY: {'PASS' if play_ok else 'FAIL'} (rc={play.returncode})")

        # Cleanup local publisher if any
        if pub_proc is not None:
            try:
                pub_proc.terminate()
                pub_proc.wait(timeout=2)
            except Exception:
                try:
                    pub_proc.kill()
                except Exception:
                    pass

        overall = probe_ok and play_ok
        print(f"RESULT for {ip}: {'PASS' if overall else 'FAIL'}")
    
    print("\nDone.")

if __name__ == "__main__":
    main()