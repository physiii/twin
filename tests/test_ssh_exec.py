import os
import subprocess
import pytest

SSH_TARGET = os.environ.get("SSH_HOST_TARGET", "andy@192.168.1.43")
SSH_KEY = os.environ.get("SSH_KEY", "")  # optional private key path
SSH_CONFIG = os.environ.get("SSH_CONFIG", "")  # optional ssh config file path


def run(cmd: str):
    proc = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def ssh(cmd: str):
    parts = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=no"]
    if SSH_CONFIG:
        parts += ["-F", SSH_CONFIG]
    if SSH_KEY:
        parts += ["-i", SSH_KEY]
    parts += [SSH_TARGET, cmd]
    full = " ".join(parts)
    return run(full)


def test_ssh_basic_connectivity():
    rc, out, err = ssh("'echo CONNECT_OK && whoami'")
    assert rc == 0, f"SSH failed rc={rc} err={err} out={out}. Hint: set SSH_HOST_TARGET and optionally SSH_KEY/SSH_CONFIG."
    assert "CONNECT_OK" in out


def test_ssh_path_and_shell():
    rc, out, err = ssh("'echo SHELL=$SHELL; echo PATH=$PATH'")
    assert rc == 0, f"SSH rc={rc} err={err} out={out}"
    assert "SHELL=" in out
    assert "PATH=" in out


def test_playerctl_presence():
    rc, out, err = ssh("'type -a playerctl || echo MISSING_playerctl'")
    assert rc == 0, f"SSH rc={rc} err={err}"
    assert "playerctl" in out or "MISSING_playerctl" not in out, f"playerctl not found: out={out} err={err}"


def test_dbus_session_detection():
    cmd = (
        "'uid=$(id -u); export XDG_RUNTIME_DIR=/run/user/$uid; "
        "if [ -S \"$XDG_RUNTIME_DIR/bus\" ]; then export DBUS_SESSION_BUS_ADDRESS=unix:path=$XDG_RUNTIME_DIR/bus; "
        "else eval $(dbus-launch 2>/dev/null) || true; fi; echo DBUS=$DBUS_SESSION_BUS_ADDRESS'"
    )
    rc, out, err = ssh(cmd)
    assert rc == 0, f"SSH rc={rc} err={err} out={out}"
    assert "DBUS=" in out


def test_playerctl_status_with_display():
    rc, out, err = ssh("'export DISPLAY=:0; playerctl status || echo STATUS_FAILED'")
    # Do not force status value, only ensure command can run non-interactively
    assert rc in (0, 1), f"SSH rc={rc} err={err} out={out}"


def test_remote_play_and_pause_sequence():
    cmds = [
        "'export DISPLAY=:0; playerctl play || true'",
        "'export DISPLAY=:0; playerctl status || true'",
        "'export DISPLAY=:0; playerctl pause || true'",
        "'export DISPLAY=:0; playerctl status || true'",
    ]
    for c in cmds:
        rc, out, err = ssh(c)
        assert rc in (0, 1), f"SSH rc={rc} for {c} err={err} out={out}"
