import asyncio
import subprocess
import os
import shlex
from datetime import datetime, timedelta
import logging

logger = logging.getLogger('twin')

last_executed_commands = {}

def is_in_cooldown(command, cooldown_period):
    now = datetime.now()
    if command in last_executed_commands:
        last_execution_time = last_executed_commands[command]
        if now - last_execution_time < timedelta(seconds=cooldown_period):
            return True
    last_executed_commands[command] = now
    return False

async def execute_commands(commands, cooldown_period, context):
    start_time = datetime.now()
    for command in commands:
        await execute_single_command(command, cooldown_period, context)
    return (datetime.now() - start_time).total_seconds()

async def execute_single_command(command, cooldown_period, context):
    if is_in_cooldown(command, cooldown_period):
        logger.info(f"[Cooldown] Command '{command}' skipped due to cooldown.")
        return (False, "", "Cooldown active")

    try:
        display = ":0"
        try:
            result = subprocess.run(['who'], capture_output=True, text=True)
            for line in result.stdout.split('\n'):
                if '(:' in line:
                    display = f":{line.split('(:')[-1].split(')')[0]}"
                    break
        except Exception as e:
            logger.error(f"Error detecting display: {str(e)}")

        env = os.environ.copy()
        env['DISPLAY'] = display

        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env
        )

        stdout, stderr = await proc.communicate()
        if proc.returncode == 0:
            logger.info(f"[Executed] Command: {command}")
            logger.info(f"[Output] {stdout.decode()}")
            success = True
            error = None
        else:
            logger.error(f"Command failed: {command}")
            logger.error(f"Error message: {stderr.decode()}")
            success = False
            error = stderr.decode()

        if 'session_data' in context and context['session_data'] is not None:
            context['session_data']['commands_executed'].append({
                "timestamp": datetime.now().isoformat(),
                "command": command,
                "output": stdout.decode(),
                "success": success,
                "error": error,
            })

        return (success, stdout.decode(), error)
    except Exception as e:
        logger.error(f"Error executing command '{command}': {str(e)}")
        if 'session_data' in context and context['session_data'] is not None:
            context['session_data']['commands_executed'].append({
                "timestamp": datetime.now().isoformat(),
                "command": command,
                "output": "",
                "success": False,
                "error": str(e),
            })
        return (False, "", str(e))

async def run_command_and_capture(command):
    # A helper function that runs a command and returns its output without logging to session_data.
    # This can be used for tool info retrieval.
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await proc.communicate()
        if proc.returncode == 0:
            return True, stdout.decode().strip(), None
        else:
            return False, "", stderr.decode().strip()
    except Exception as e:
        return False, "", str(e)
