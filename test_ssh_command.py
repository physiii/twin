#!/usr/bin/env python3
"""
Test script to verify SSH command execution matches working manual commands
"""
import asyncio
import sys
import os

# Add src to path
sys.path.insert(0, 'src')

async def test_ssh_command():
    """Test the exact SSH command that should work"""
    ssh_target = "andy@192.168.1.43"
    display = ":0"
    command_str = "playerctl play"
    
    # This is the EXACT pattern that worked manually
    remote_cmd = (
        "uid=$(id -u); "
        "export XDG_RUNTIME_DIR=/run/user/$uid; "
        f"export DISPLAY={display}; "
        "export DBUS_SESSION_BUS_ADDRESS=unix:path=$XDG_RUNTIME_DIR/bus; "
        "export PATH=$PATH:/usr/local/bin:/usr/bin:/bin; "
        "echo '[TEST] DBUS='$DBUS_SESSION_BUS_ADDRESS' DISPLAY='$DISPLAY' PATH='$PATH; "
        "playerctl --version || echo 'playerctl version failed'; "
        f"{command_str}"
    )
    
    ssh_args = [
        "ssh", "-o", "StrictHostKeyChecking=no", "-i", "/tmp/id_ed25519_twin", ssh_target,
        "bash", "-c", remote_cmd
    ]
    
    print(f"🔄 SSH ARGS: {ssh_args}")
    print(f"🔄 REMOTE_CMD: {remote_cmd}")
    
    try:
        proc = await asyncio.create_subprocess_exec(
            *ssh_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await proc.communicate()
        exit_code = await proc.wait()
        
        output = stdout.decode().strip()
        error = stderr.decode().strip()
        
        print(f"🔄 EXIT CODE: {exit_code}")
        print(f"🔄 STDOUT: {output}")
        print(f"🔄 STDERR: {error}")
        
        if exit_code == 0:
            print("✅ SUCCESS!")
        else:
            print("❌ FAILED!")
            
    except Exception as e:
        print(f"🔴 EXCEPTION: {e}")

if __name__ == "__main__":
    asyncio.run(test_ssh_command())
