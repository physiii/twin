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

async def execute_commands(commands, context_or_cooldown=None, requires_confirmation=False, risk_level=0.0, self_text=""):
    """Execute a list of commands with enhanced validation and confirmation
    
    Compatible with both:
    - old signature: execute_commands(commands, cooldown_period, context)
    - new signature: execute_commands(commands, context, requires_confirmation, risk_level, self_text)
    """
    try:
        # Handle the old calling convention
        if isinstance(context_or_cooldown, int) or context_or_cooldown is None:
            # Old calling convention: third arg was context
            cooldown_period = context_or_cooldown if context_or_cooldown is not None else 0
            # Try to get context from the requires_confirmation parameter (which was actually context in old convention)
            context = requires_confirmation
            # Reset these parameters since they were misinterpreted
            requires_confirmation = False 
            risk_level = 0.0
            self_text = ""
        else:
            # New calling convention
            context = context_or_cooldown
            # For new convention, get cooldown from context
            cooldown_period = context.get('COOLDOWN_PERIOD', 0) if hasattr(context, 'get') else 0

        if not commands:
            logger.info("🔄 No commands to execute")
            return 0.0

        # Check risk level and confirmation status (only for new convention)
        if (hasattr(context, 'get') and 
            risk_level > context.get('RISK_THRESHOLD', 0.5) and 
            not requires_confirmation):
            logger.warning(f"⚠️ High risk command detected (Risk: {risk_level:.2f}) but not confirmed. Skipping execution.")
            return 0.0

        logger.info(f"🚀 Executing {len(commands)} command(s)")
        start_time = datetime.now()
                
        for idx, command in enumerate(commands, 1):
            logger.debug(f"🔧 Processing command {idx}/{len(commands)}")
            await execute_single_command(command, cooldown_period, context, self_text)
        
        duration = (datetime.now() - start_time).total_seconds()
        logger.info(f"✅ Completed {len(commands)} command(s) in {duration:.2f}s")
        return duration
    except Exception as e:
        logger.error(f"🔴 Critical error executing commands: {str(e)}", exc_info=True)
        return 0.0

async def execute_single_command(command, cooldown_period, context, self_text=""):
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

        # --- Enhanced room detection with multiple sources ---
        if ("lights" in command_str or "thermostat" in command_str) and "<room_name>" in command_str:
            room_location = None
            
            # Get room manager from context
            room_manager = context.get("ROOM_MANAGER") if hasattr(context, 'get') else None
            
            # Priority 1: Explicit room in transcript (if we have session data)
            if hasattr(context, 'get') and context.get('session_data'):
                latest_transcripts = context['session_data'].get('after_transcriptions', [])
                if latest_transcripts and room_manager:
                    room_from_transcript = room_manager.resolve_room_from_transcript(latest_transcripts[-1])
                    if room_from_transcript:
                        room_location = room_from_transcript
                        logger.info(f"🎯 Room from transcript: '{room_from_transcript}'")
            
            # Priority 2: Source-based location from context
            if not room_location and hasattr(context, 'get'):
                room_location = context.get("DETECTED_LOCATION")
                if room_location:
                    logger.info(f"🎯 Room from source: '{room_location}'")
            
            # Priority 3: Self-text analysis (legacy fallback)
            if not room_location and self_text:
                if "office" in self_text.lower():
                    room_location = "office"
                elif "kitchen" in self_text.lower():
                    room_location = "kitchen"
                elif "bedroom" in self_text.lower():
                    room_location = "bedroom"
                elif "media" in self_text.lower():
                    room_location = "media"
                if room_location:
                    logger.info(f"🎯 Room from self-text: '{room_location}'")
            
            # Priority 4: Default fallback
            if not room_location:
                room_location = "office"
                logger.info(f"🎯 Using default room: '{room_location}'")
            
            # Validate command can be executed in this room
            if room_manager:
                valid, message = room_manager.validate_room_command(command_str, room_location)
                if not valid:
                    logger.warning(f"⚠️ Command validation failed: {message}")
                    return (False, "", message)
            
            # Replace placeholder
            command_str = command_str.replace("<room_name>", room_location)
            logger.info(f"🏠 Executing in room '{room_location}': {command_str}")
        # ---------------------------------------------------------

        # --- NEW: sanitize angle-bracket placeholders (avoid shell redirect) ---
        if "<" in command_str or ">" in command_str:
            new_command_str = re.sub(r"<[^>]*>", "office", command_str)
            logger.warning(f"⚠️ Command contained angle-bracket placeholders. "
                           f"Replacing them: '{command_str}' -> '{new_command_str}'")
            command_str = new_command_str
        # ----------------------------------------------------------------------

        logger.info(f"🛠️  Processing command: {command_str[:80]}...")
        logger.info(f"🔍 FULL COMMAND: {command_str}")

        # Check if we need to execute via SSH (moved up to fix scoping)
        from twin.core import config  # Import config to check for SSH_HOST_TARGET
        ssh_target = getattr(config, 'SSH_HOST_TARGET', None)
        logger.info(f"🔌 SSH_TARGET: {ssh_target}")

        # If command includes background separators, split and run sequentially for reliability
        if " & " in command_str and not command_str.strip().startswith("bash -c"):
            parts = [p.strip() for p in command_str.split("&") if p.strip()]
            logger.info(f"🔧 Splitting composite command into {len(parts)} parts: {parts}")
            all_ok = True
            last_out, last_err = "", ""
            for i, part in enumerate(parts, start=1):
                logger.info(f"🔩 Executing part {i}/{len(parts)}: {part}")
                ok, out, err = await execute_single_command(part, cooldown_period, context, self_text)
                logger.info(f"🔩 Part {i} result: ok={ok}, out='{out[:100]}', err='{err[:100]}'")
                all_ok = all_ok and ok
                last_out = out or last_out
                last_err = err or last_err
            return (all_ok, last_out, last_err)

        # Cooldown check
        if is_in_cooldown(command_str, cooldown_period):
            logger.warning(f"⏳ Command in cooldown: {command_str[:50]}...")
            return (False, "", "Command in cooldown")
        
        # Detect display for GUI commands
        display = ":0"
        try:
            if not ssh_target:  # Only try to detect local display if not using SSH
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
        if ssh_target:
            # Use the same minimal SSH pattern that worked for pause/media control, plus DBus session from user bus
            # Build remote command using the EXACT working format (single quotes, no bash -c)
            remote_cmd = f"uid=$(id -u); export XDG_RUNTIME_DIR=/run/user/$uid; export DISPLAY={display}; export DBUS_SESSION_BUS_ADDRESS=unix:path=$XDG_RUNTIME_DIR/bus; export PATH=$PATH:/usr/local/bin:/usr/bin:/bin; echo '[diag] UID='$uid' XDG='$XDG_RUNTIME_DIR' DBUS='$DBUS_SESSION_BUS_ADDRESS 1>&2; playerctl --version 1>&2 || true; {command_str}"
            # Use the exact working SSH format
            ssh_args = [
                "ssh", "-o", "StrictHostKeyChecking=no", "-i", "/root/.ssh/id_ed25519", ssh_target,
                remote_cmd
            ]
            logger.info(f"🔄 SSH ARGS: {ssh_args}")
            logger.info(f"🔄 REMOTE_CMD: {remote_cmd}")
            # Log the exact copyable command for debugging
            copyable_cmd = f"ssh -o StrictHostKeyChecking=no -i /root/.ssh/id_ed25519 {ssh_target} '{remote_cmd}'"
            logger.info(f"📋 COPYABLE COMMAND: {copyable_cmd}")
            logger.info(f"🔄 Executing via SSH: ssh {ssh_target} '{remote_cmd[:150]}...'")
            proc = await asyncio.create_subprocess_exec(
                *ssh_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
        else:
            # Normal local execution
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
            logger.debug(f"📤 Output: {output[:500]}...")
        else:
            logger.error(f"🔴 Failed: {command_str[:60]}... (Code: {exit_code})")
            logger.error(f"📤 Output: {output[:500]}...")
            logger.error(f"📥 Error: {error[:500]}...")

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
