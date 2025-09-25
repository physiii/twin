# hass_run_command.py
import subprocess

def hass_run_command(args):
    """
    Custom MCP tool that runs a shell command.
    
    Expected args:
      - value: the command string (e.g., "ls /tmp")
      - timeout (optional): how many seconds to wait for command execution (default 10)
    
    Returns a dict with stdout and stderr.
    """
    command = args.get("value", "")
    timeout = args.get("timeout", 10)
    if not command:
        return {"error": "No command provided"}
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=timeout)
        return {"stdout": result.stdout, "stderr": result.stderr}
    except Exception as e:
        return {"error": str(e)} 