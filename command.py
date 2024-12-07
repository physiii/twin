import time
import json
from datetime import datetime, timedelta
import asyncio
import subprocess
import os
import shlex

from generator import run_inference
from search import run_search
from audio import play_tts_response


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
        if is_in_cooldown(command, cooldown_period):
            logger.info(f"[Cooldown] Command '{command}' skipped due to cooldown.")
            continue
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

            # Updated condition to include '&'
            if any(op in command for op in ['&&', '||', '|', ';', '>', '>>', '<', '&']):
                proc = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env,
                    shell=True
                )
            else:
                args = shlex.split(command)
                proc = await asyncio.create_subprocess_exec(
                    *args,
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
    return (datetime.now() - start_time).total_seconds()

async def process_command_text(text, context):
    REMOTE_STORE_URL = context['REMOTE_STORE_URL']
    REMOTE_INFERENCE_URL = context['REMOTE_INFERENCE_URL']
    args = context['args']
    RISK_THRESHOLD = context['RISK_THRESHOLD']
    COOLDOWN_PERIOD = context['COOLDOWN_PERIOD']
    TTS_PYTHON_PATH = context['TTS_PYTHON_PATH']
    TTS_SCRIPT_PATH = context['TTS_SCRIPT_PATH']
    AMY_DISTANCE_THRESHOLD = context['AMY_DISTANCE_THRESHOLD']
    NA_DISTANCE_THRESHOLD = context['NA_DISTANCE_THRESHOLD']
    HIP_DISTANCE_THRESHOLD = context['HIP_DISTANCE_THRESHOLD']

    process_start = time.time()
    logger.info(f"[Process Command] Processing text: '{text}'")

    amygdala_results, _ = await run_search(text, 'amygdala', remote_store_url=REMOTE_STORE_URL)
    logger.info(f"[Search] Amygdala results: {amygdala_results}")

    accumbens_results, _ = await run_search(text, 'na', remote_store_url=REMOTE_STORE_URL)
    logger.info(f"[Search] Accumbens results: {accumbens_results}")

    hippocampus_results, _ = await run_search(text, 'hippocampus', remote_store_url=REMOTE_STORE_URL)
    logger.info(f"[Search] Hippocampus results: {hippocampus_results}")

    relevant_amygdala = [r for r in amygdala_results if r[1] < AMY_DISTANCE_THRESHOLD]
    relevant_accumbens = [r for r in accumbens_results if r[1] < NA_DISTANCE_THRESHOLD]

    if relevant_amygdala or relevant_accumbens:
        logger.info("[Inference] Relevant vector matches found; proceeding with inference.")

        combined_commands = [snippet for snippet, _ in relevant_accumbens]

        inference_start = time.time()
        inference_response, raw_response = await run_inference(
            source_text=text,
            accumbens_commands=combined_commands,
            use_remote_inference=bool(REMOTE_INFERENCE_URL),
            inference_url=REMOTE_INFERENCE_URL,
        )
        inference_end = time.time()

        if inference_response:
            if 'session_data' in context and context['session_data'] is not None:
                context['session_data']['inferences'].append({
                    "timestamp": datetime.now().isoformat(),
                    "source_text": text,
                    "inference_response": inference_response,
                    "raw_response": raw_response,
                })

            if args.execute:
                if inference_response['risk'] <= RISK_THRESHOLD or inference_response.get('confirmed', False):
                    await execute_commands(inference_response['commands'], COOLDOWN_PERIOD, context)
                else:
                    logger.warning(
                        f"[Warning] Commands not executed. Risk: {inference_response['risk']}. "
                        f"Confirmation required."
                    )

            if not args.silent and inference_response.get('requires_audio_feedback', False):
                asyncio.create_task(play_tts_response(
                    inference_response['response'],
                    tts_python_path=TTS_PYTHON_PATH,
                    tts_script_path=TTS_SCRIPT_PATH,
                    silent=args.silent,
                ))

            logger.info(
                f"[Timing] Total: {time.time() - process_start:.4f}s, "
                f"Inference: {inference_end - inference_start:.4f}s"
            )
            return inference_response
        else:
            logger.info("[Inference] No inference response received.")
            return None
    else:
        logger.info("[Inference] No relevant vector matches found; skipping inference.")
        return None