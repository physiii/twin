# command.py

import asyncio
import subprocess
import os
import logging
import json
from datetime import datetime, timedelta
import re

logger = logging.getLogger('twin')
last_executed_commands = {}

def log_command_structure(command):
    """Log detailed information about command structure"""
    try:
        logger.debug("🎛️ Command structure analysis:")
        logger.debug(f"📦 Type: {type(command)}")
        
        if isinstance(command, dict):
            logger.debug("📖 Dictionary contents:")
            for k, v in command.items():
                logger.debug(f"   🔑 Key: {k:15} 🏷️ Type: {type(v).__name__:8} 📝 Value: {str(v)[:60]}")
        elif isinstance(command, (list, tuple)):
            logger.debug(f"🧮 Sequence length: {len(command)}")
            for i, item in enumerate(command[:3]):
                logger.debug(f"   #{i+1}: 🏷️ Type: {type(item).__name__:8} 📝 Value: {str(item)[:60]}")
        else:
            logger.debug(f"📝 Value: {str(command)[:100]}")
            
        logger.debug("🔍 Structure analysis complete")
    except Exception as e:
        logger.error(f"🔴 Failed to analyze command structure: {str(e)}", exc_info=True)

def is_in_cooldown(command_str, cooldown_period):
    """Check if a command is in cooldown period with enhanced logging"""
    now = datetime.now()
    if command_str in last_executed_commands:
        last_time = last_executed_commands[command_str]
        elapsed = (now - last_time).total_seconds()
        logger.debug(f"⏳ Cooldown check: '{command_str[:30]}...' - {elapsed:.1f}s/{cooldown_period}s")
        return elapsed < cooldown_period
    return False

async def execute_commands(commands, cooldown_period, context):
    """Execute a list of commands with enhanced validation"""
    try:
        if not commands:
            logger.info("🔄 No commands to execute")
            return 0.0

        logger.info(f"🚀 Executing {len(commands)} command(s)")
        start_time = datetime.now()
        
        for idx, command in enumerate(commands, 1):
            logger.debug(f"🔧 Processing command {idx}/{len(commands)}")
            await execute_single_command(command, cooldown_period, context)
        
        duration = (datetime.now() - start_time).total_seconds()
        logger.info(f"✅ Completed {len(commands)} command(s) in {duration:.2f}s")
        return duration
    except Exception as e:
        logger.error(f"🔴 Critical error executing commands: {str(e)}", exc_info=True)
        return 0.0

async def execute_single_command(command, cooldown_period, context):
    """Execute a single command with comprehensive validation"""
    try:
        # Log raw command structure
        log_command_structure(command)
        
        # Extract the command string from dict or fallback to a bare string
        if isinstance(command, dict):
            command_str = command.get('cli') or command.get('command', '')
            if not command_str:
                logger.error("🔴 Invalid command format: Dictionary missing 'cli' or 'command' key")
                logger.error(f"💔 Invalid command: {json.dumps(command, indent=2)[:200]}...")
                return (False, "", "Missing 'cli' or 'command' key in command dictionary")
        else:
            command_str = str(command).strip()
            if not command_str:
                logger.warning("⚠️  Empty command string received")
                return (False, "", "Empty command")

        # --- NEW: Process light commands to replace placeholders ---
        if "lights" in command_str and "<room_name>" in command_str:
            # Extract 'self' location from context
            self_location = "office"  # Default fallback
            if "self_text" in context:
                # Try to find location in self text
                if "office" in context["self_text"].lower():
                    self_location = "office"
                elif "kitchen" in context["self_text"].lower():
                    self_location = "kitchen"
                elif "bedroom" in context["self_text"].lower():
                    self_location = "bedroom"
                elif "media" in context["self_text"].lower():
                    self_location = "media"
            
            # Replace <room_name> with the actual location
            command_str = command_str.replace("<room_name>", self_location)
            logger.info(f"🏠 Replaced room placeholder: '{command_str}'")
        # ---------------------------------------------------------

        # --- NEW: sanitize angle-bracket placeholders (avoid shell redirect) ---
        if "<" in command_str or ">" in command_str:
            new_command_str = re.sub(r"<[^>]*>", "office", command_str)
            logger.warning(f"⚠️ Command contained angle-bracket placeholders. "
                           f"Replacing them: '{command_str}' -> '{new_command_str}'")
            command_str = new_command_str
        # ----------------------------------------------------------------------

        logger.info(f"🛠️  Processing command: {command_str[:80]}...")

        # Cooldown check
        if is_in_cooldown(command_str, cooldown_period):
            logger.warning(f"⏳ Command in cooldown: {command_str[:50]}...")
            return (False, "", "Command in cooldown")

        # Detect display for GUI commands
        display = ":0"
        try:
            who_result = subprocess.run(['who'], capture_output=True, text=True)
            for line in who_result.stdout.splitlines():
                if '(:' in line:
                    display = f":{line.split('(:')[-1].split(')')[0]}"
                    logger.debug(f"🖥️  Detected display: {display}")
                    break
        except Exception as e:
            logger.error(f"🔴 Display detection failed: {str(e)}")

        # Prepare execution environment
        env = os.environ.copy()
        env['DISPLAY'] = display
        logger.debug(f"🧩 Execution environment: DISPLAY={display}")

        # Execute command
        proc = await asyncio.create_subprocess_shell(
            command_str,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env
        )

        stdout, stderr = await proc.communicate()
        exit_code = await proc.wait()

        success = (exit_code == 0)
        output = stdout.decode().strip()
        error = stderr.decode().strip()

        if success:
            logger.info(f"✅ Success: {command_str[:60]}...")
            logger.debug(f"📤 Output: {output[:200]}...")
        else:
            logger.error(f"🔴 Failed: {command_str[:60]}... (Code: {exit_code})")
            logger.error(f"📤 Output: {output[:200]}...")
            logger.error(f"📥 Error: {error[:200]}...")

        # Update session data if in context
        if context.get('session_data'):
            context['session_data']['commands_executed'].append({
                "timestamp": datetime.now().isoformat(),
                "command": command_str,
                "output": output,
                "success": success,
                "error": error,
                "exit_code": exit_code
            })

        return (success, output, error)

    except Exception as e:
        logger.error(f"🔴 Critical command error: {str(e)}", exc_info=True)
        if context.get('session_data'):
            context['session_data']['commands_executed'].append({
                "timestamp": datetime.now().isoformat(),
                "command": str(command) if 'command_str' not in locals() else command_str,
                "output": "",
                "success": False,
                "error": str(e),
                "exit_code": -1
            })
        return (False, "", str(e))

async def run_command_and_capture(command):
    """Helper function for non-context command execution"""
    try:
        if isinstance(command, dict):
            command_str = command.get('cli') or command.get('command', '')
            if not command_str:
                logger.error("🔴 Invalid command dict in helper")
                return (False, "", "Missing 'cli' or 'command' key")
        else:
            command_str = str(command).strip()

        logger.debug(f"🛠️  Helper executing: {command_str[:80]}...")

        proc = await asyncio.create_subprocess_shell(
            command_str,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await proc.communicate()
        exit_code = await proc.wait()

        output = stdout.decode().strip()
        error = stderr.decode().strip()

        if exit_code == 0:
            logger.debug(f"✅ Helper success: {command_str[:60]}...")
            return (True, output, None)
        
        logger.warning(f"⚠️  Helper command failed: {command_str[:60]}...")
        return (False, output, error)

    except Exception as e:
        logger.error(f"🔴 Helper command error: {str(e)}", exc_info=True)
        return (False, "", str(e))
