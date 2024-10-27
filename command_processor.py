import time
import json
import logging
from datetime import datetime
import asyncio

from action import execute_commands
from generator import run_inference
from search import run_search
from audio import play_tts_response

logger = logging.getLogger(__name__)

def get_timestamp():
    USE_TIMESTAMP = False
    if USE_TIMESTAMP:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    else:
        return ""

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
    is_processing = True

    # Search
    search_start = time.time()
    amygdala_results, _ = await run_search(text, 'amygdala', remote_store_url=REMOTE_STORE_URL)
    accumbens_results, _ = await run_search(text, 'na', remote_store_url=REMOTE_STORE_URL)
    hippocampus_results, _ = await run_search(text, 'hippocampus', remote_store_url=REMOTE_STORE_URL)
    search_end = time.time()
    search_time = search_end - search_start

    relevant_amygdala = [r for r in amygdala_results if r[1] < AMY_DISTANCE_THRESHOLD]
    relevant_accumbens = [r for r in accumbens_results if r[1] < NA_DISTANCE_THRESHOLD]
    relevant_hippocampus = [r for r in hippocampus_results if r[1] < HIP_DISTANCE_THRESHOLD]

    if relevant_amygdala and relevant_accumbens:
        for snippet, distance in relevant_amygdala:
            logger.info(f"[Amygdala] {get_timestamp()} {snippet} | {distance}")

        accumbens_commands = [snippet for snippet, _ in relevant_accumbens]

        for snippet, distance in relevant_accumbens:
            logger.info(f"[Accumbens] {get_timestamp()} {snippet} | {distance}")

        if relevant_hippocampus:
            hippocampus_commands = [snippet for snippet, _ in relevant_hippocampus]
            for snippet, distance in relevant_hippocampus:
                logger.info(f"[Hippocampus] {get_timestamp()} {snippet} | {distance}")
        else:
            hippocampus_commands = []

        combined_commands = accumbens_commands + hippocampus_commands

        # Inference
        inference_start = time.time()
        if REMOTE_INFERENCE_URL:
            inference_response, raw_response = await run_inference(
                text,
                combined_commands,
                use_remote_inference=True,
                inference_url=REMOTE_INFERENCE_URL,
            )
        inference_end = time.time()
        inference_time = inference_end - inference_start

        if inference_response:
            # Execution
            execution_time = 0

            if 'commands' in inference_response:
                # Handle JSON string commands
                if isinstance(inference_response['commands'], list) and len(inference_response['commands']) > 0:
                    if isinstance(inference_response['commands'][0], str) and 'json' in inference_response['commands'][0]:
                        try:
                            # Extract the JSON string
                            command_string = inference_response['commands'][0].replace("echo ```json", "").replace("```", "").strip()
                            commands_json = json.loads(command_string)
                            
                            # Update the entire inference response with the parsed JSON
                            if isinstance(commands_json, dict):
                                # Extract just the commands array from the parsed JSON
                                if 'commands' in commands_json:
                                    inference_response['commands'] = commands_json['commands']
                                # Update other fields from the parsed JSON
                                for key in ['response', 'risk', 'confirmed', 'confidence', 'intent_reasoning', 'requires_audio_feedback']:
                                    if key in commands_json:
                                        inference_response[key] = commands_json[key]
                        except json.JSONDecodeError as e:
                            logger.error(f"Failed to parse command JSON: {e}")
                            return None
                        except Exception as e:
                            logger.error(f"Error processing JSON command: {e}")
                            return None

            if args.execute:
                execution_start = time.time()
                if inference_response['risk'] <= RISK_THRESHOLD or (
                    inference_response['risk'] > RISK_THRESHOLD and inference_response.get('confirmed', False)
                ):
                    await execute_commands(inference_response['commands'], COOLDOWN_PERIOD)
                else:
                    logger.warning(
                        f"[Warning] {get_timestamp()} Commands not executed. Risk: {inference_response['risk']}. "
                        f"Confirmation required."
                    )
                execution_end = time.time()
                execution_time = execution_end - execution_start

            # TTS
            # if not args.silent and inference_response.get('requires_audio_feedback', False):
            #     asyncio.create_task(play_tts_response(
            #         inference_response['response'],
            #         tts_python_path=TTS_PYTHON_PATH,
            #         tts_script_path=TTS_SCRIPT_PATH,
            #         silent=args.silent,
            #     ))

            total_time = time.time() - process_start
            logger.info(
                f"[Timing] {get_timestamp()} Total: {total_time:.4f}s, Search: {search_time:.4f}s, "
                f"Inference: {inference_time:.4f}s, Execution: {execution_time:.4f}s"
            )

            return inference_response

        else:
            return None
    else:
        logger.debug(
            f"Thresholds not met. Amygdala: {bool(relevant_amygdala)}, Accumbens: {bool(relevant_accumbens)}"
        )
        return None