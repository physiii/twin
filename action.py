import asyncio
import subprocess
import os
import shlex
from datetime import datetime, timedelta
import logging

logger = logging.getLogger("twin")

last_executed_commands = {}  # Dictionary to store the timestamp of last command executions

def get_timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def is_in_cooldown(command, cooldown_period):
    now = datetime.now()
    if command in last_executed_commands:
        last_execution_time = last_executed_commands[command]
        if now - last_execution_time < timedelta(seconds=cooldown_period):
            return True
    last_executed_commands[command] = now
    return False

async def execute_commands(commands, cooldown_period):
    start_time = datetime.now()
    for command in commands:
        if is_in_cooldown(command, cooldown_period):
            print(f"[Cooldown] {get_timestamp()} Command '{command}' skipped due to cooldown.")
            continue
        try:
            # Detect the current display
            display = ":0"  # Default to :0 if we can't detect it
            try:
                result = subprocess.run(['who'], capture_output=True, text=True)
                for line in result.stdout.split('\n'):
                    if '(:' in line:
                        display = f":{line.split('(:')[-1].split(')')[0]}"
                        break
            except Exception as e:
                logger.error(f"Error detecting display: {str(e)}")

            # Set the DISPLAY environment variable
            env = os.environ.copy()
            env['DISPLAY'] = display

            # Properly escape and prepare the command for execution
            args = shlex.split(command)
            
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env
            )

            stdout, stderr = await proc.communicate()
            if proc.returncode == 0:
                print(f"[Executed] {get_timestamp()} Command: {command}")
                print(f"[Output] {get_timestamp()} {stdout.decode()}")
            else:
                logger.error(f"Command failed: {command}")
                logger.error(f"Error message: {stderr.decode()}")
        except Exception as e:
            logger.error(f"Error executing command '{command}': {str(e)}")
    return (datetime.now() - start_time).total_seconds()
