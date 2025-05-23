# generator.py

import asyncio
import logging
import os
import json
from datetime import datetime

from model import Model
from prompt import PROMPT
from audio import play_tts_response
from search import run_search
from command import execute_commands, run_command_and_capture
from rapidfuzz import fuzz

logger = logging.getLogger("twin")

model = Model()

WAKE_PHRASES = ["Hey computer.", "Hey twin"]

def clean_gpt_response(raw_response):
    if raw_response.startswith('```json') and raw_response.endswith('```'):
        return raw_response.strip('```json').strip('```').strip()
    return raw_response

def process_result(raw_result):
    """
    Attempt to parse 'raw_result' into the single valid JSON structure expected by the app.
    Accepts either:
      1) The original format with a 'commands' list.
      2) The new format with a 'command' key that may be a string or a list of dicts.
    """
    if isinstance(raw_result, str):
        # If it's JSON in a string, try to parse it
        try:
            raw_result = json.loads(raw_result)
        except json.JSONDecodeError:
            # If not valid JSON, return a fallback
            return {
                "commands": ["echo " + str(raw_result)],
                "response": str(raw_result),
                "risk": 0.5,
                "confirmed": False,
                "requires_audio_feedback": False,
                "confidence": 0.5,
                "intent_reasoning": ""
            }

    # If we still don't have a dictionary, bail out
    if not isinstance(raw_result, dict):
        logger.error(f"Unexpected result type (expected dict or valid JSON str): {type(raw_result)}")
        return {
            "commands": [],
            "response": "",
            "risk": 0.5,
            "confirmed": False,
            "requires_audio_feedback": False,
            "confidence": 0.5,
            "intent_reasoning": ""
        }

    # Now handle the two known scenarios:
    # 1) We already have "commands" in raw_result (the old/original expected format).
    # 2) We have "command" but not "commands" (the new format).
    commands = []

    if "commands" in raw_result and isinstance(raw_result["commands"], list):
        # Original (expected) format
        commands = raw_result.get("commands", [])
    elif "command" in raw_result:
        # The new format. "command" might be a string or a list of dicts with "command".
        c = raw_result["command"]
        if isinstance(c, list):
            # e.g. "command": [ {"command": "lights --power off", ...}, {"command": "lights --room office", ...} ]
            # We only need the actual command strings for the final JSON output
            extracted = []
            for item in c:
                if isinstance(item, dict) and "command" in item:
                    extracted.append(item["command"])
                elif isinstance(item, str):
                    extracted.append(item)
            commands = extracted
        elif isinstance(c, str):
            # A single command string
            commands = [c]
        # else: if "command" is present but not parseable, commands remain empty

    # Construct the final JSON object in the shape your system expects.
    # The keys below are mandatory. We also keep the same default/fallback values as before.
    return {
        "commands": commands,
        "response": raw_result.get("response", ""),
        "risk": raw_result.get("risk", 0.5),
        "confirmed": raw_result.get("confirmed", False),
        "requires_audio_feedback": raw_result.get("requires_audio_feedback", False),
        "confidence": raw_result.get("confidence", 0.5),
        "intent_reasoning": raw_result.get("intent_reasoning", "")
    }

async def run_inference(source_text, accumbens_commands, tool_info, use_remote_inference=False, inference_url=None):
    """
    This function loads the text from stores/self/office.txt and injects it into the prompt
    as {self}, then performs the inference using the model.
    """
    # 1. Load the text from self files
    # Try multiple paths for self files in order of preference, with fallbacks
    self_text = ""  # Default empty string if no files are found
    
    # Possible locations for self text files
    self_locations = [
        os.path.join("/app/stores/self", "office.txt"),     # Docker container path
        os.path.join("/app/stores/self", "generic.txt"),    # Generic fallback
        os.path.join("stores/self", "office.txt"),          # Relative path
        os.path.join("stores/self", "generic.txt")          # Relative generic fallback
    ]
    
    # Try each location until we find one that works
    for location in self_locations:
        try:
            if os.path.exists(location):
                with open(location, "r", encoding="utf-8") as f:
                    self_text = f.read().strip()
                    logger.info(f"Loaded self text from {location}")
                    break  # Stop looking once we find a file
        except Exception as e:
            logger.warning(f"Failed to read self file at {location}: {e}")
    
    # If we didn't find any files, use a default
    if not self_text:
        logger.warning("No self text files found! Using minimal default.")
        self_text = "You are an assistant that helps with computer tasks. You are running on a system with Linux."
    
    # 2. Format the prompt, injecting self_text
    prompt = PROMPT.format(
        source_text=source_text,
        accumbens_commands="\n".join(accumbens_commands),
        tool_info=tool_info,
        self=self_text
    )

    logger.info(f"Running inference with prompt: {prompt}")
    
    try:
        raw_result, duration = await model.remote_inference(prompt, inference_url)
        
        if raw_result:
            logger.info(f"Received raw result from inference, length: {len(raw_result)}")
            parse_result = clean_gpt_response(raw_result)
            processed_result = process_result(parse_result)
            logger.info(f"Successfully processed inference result")
            # Return the self_text along with the result for use in command execution
            return processed_result, duration, self_text
        else:
            logger.error("No result returned from inference. The model.remote_inference call returned None or empty string.")
            return None, duration, self_text
    except Exception as e:
        logger.error(f"Exception during inference: {str(e)}", exc_info=True)
        return None, 0, self_text

async def process_user_text(
    text, 
    context, 
    is_awake=False,
    force_awake=False
):
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
    WAKE_DISTANCE_THRESHOLD = 0.30
    FUZZY_SIMILARITY_THRESHOLD = 60

    response = {
        "woke_up": False,
        "inference_response": None,
        "sleep": False
    }

    logger.debug(f"[generator] Received text: '{text}', is_awake={is_awake}, force_awake={force_awake}")

    # If not awake and not forced awake, first check for wake phrase.
    if not is_awake and not force_awake:
        words = text.strip().split()
        window_size = min(len(words), 2)
        woke = False
        for i in range(len(words) - window_size + 1):
            window = " ".join(words[i : i + window_size])
            wake_results, _ = await run_search(window, "wake", remote_store_url=REMOTE_STORE_URL)
            relevant_wake = [r for r in wake_results if r[1] < WAKE_DISTANCE_THRESHOLD]

            fuzzy_matches = []
            for phrase in WAKE_PHRASES:
                similarity = fuzz.token_set_ratio(window, phrase)
                if similarity >= FUZZY_SIMILARITY_THRESHOLD:
                    fuzzy_matches.append((phrase, similarity))

            if relevant_wake and fuzzy_matches:
                response["woke_up"] = True
                woke = True
                break

        # If we did not wake up, return without inference
        if not woke:
            return response

    # If we're here and not forced awake but is_awake is still False,
    # it means we just woke up now. The calling function will set is_awake to True.
    # If is_awake or force_awake is now True, we can consider inference.

    # Double-check here: if the system is STILL not awake and not forced awake, do no inference.
    if not is_awake and not force_awake:
        return response

    # System is awake or forced awake from this point onward
    amygdala_results, _ = await run_search(text, 'amygdala', remote_store_url=REMOTE_STORE_URL)
    accumbens_results, _ = await run_search(text, 'na', remote_store_url=REMOTE_STORE_URL)
    hippocampus_results, _ = await run_search(text, 'hippocampus', remote_store_url=REMOTE_STORE_URL)
    tools_results, _ = await run_search(text, 'tools', remote_store_url=REMOTE_STORE_URL)

    if 'session_data' in context and context['session_data'] is not None:
        context['session_data']['vectorstore_results'].append({
            "timestamp": datetime.now().isoformat(),
            "transcription": text,
            "amygdala_results": amygdala_results,
            "accumbens_results": accumbens_results,
            "hippocampus_results": hippocampus_results,
            "tools_results": tools_results,
        })

    relevant_amygdala = [r for r in amygdala_results if r[1] < AMY_DISTANCE_THRESHOLD]
    relevant_accumbens = [r for r in accumbens_results if r[1] < NA_DISTANCE_THRESHOLD]
    relevant_tools = [r for r in tools_results if r[1] < NA_DISTANCE_THRESHOLD]

    # If no relevant matches, no inference needed
    if not (relevant_amygdala and relevant_accumbens):
        return response

    # Collect tool info
    tool_info = ""
    if relevant_tools:
        tool_info_lines = []
        for (tool_cmd, dist) in relevant_tools:
            success, out, err = await run_command_and_capture(tool_cmd)
            logger.info(f"Executed tool command: {tool_cmd}")
            if success:
                tool_info_lines.append(f"{tool_cmd}: {out}")
            else:
                tool_info_lines.append(f"{tool_cmd}: (error: {err})")
        tool_info = "\n".join(tool_info_lines)
    else:
        tool_info = "No relevant tool information."

    combined_commands = [snippet for snippet, _ in accumbens_results]

    logger.debug("Starting remote inference...")
    inference_result = await run_inference(
        source_text=text,
        accumbens_commands=combined_commands,
        tool_info=tool_info,
        use_remote_inference=bool(REMOTE_INFERENCE_URL),
        inference_url=REMOTE_INFERENCE_URL,
    )
    
    # Unpack the result - now includes self_text
    if len(inference_result) == 3:
        inference_response, raw_response, self_text = inference_result
        # Add self_text to context for command execution
        context['self_text'] = self_text
    else:
        inference_response, raw_response = inference_result[:2]
    
    logger.debug("Remote inference finished.")

    if inference_response:
        if 'session_data' in context and context['session_data'] is not None:
            context['session_data']['inferences'].append({
                "timestamp": datetime.now().isoformat(),
                "source_text": text,
                "inference_response": inference_response,
                "raw_response": raw_response,
            })

        logger.info(f"Inference response contains commands: {inference_response.get('commands', [])}")
        logger.info(f"Risk level: {inference_response.get('risk', 'unknown')}, Threshold: {RISK_THRESHOLD}")
        logger.info(f"Execute flag: {args.execute}")
        
        if args.execute:
            if inference_response.get('risk', 1.0) <= RISK_THRESHOLD or inference_response.get('confirmed', False):
                logger.info(f"Executing commands: {inference_response.get('commands', [])}")
                await execute_commands(inference_response.get('commands', []), COOLDOWN_PERIOD, context)
            else:
                logger.warning(
                    f"[Warning] Commands not executed. Risk: {inference_response.get('risk', 'unknown')}. Threshold: {RISK_THRESHOLD}. Confirmation required."
                )
        else:
            logger.warning("Command execution disabled (args.execute is False)")

        # If you wish to enable audio feedback, uncomment:
        # if not args.silent and inference_response.get('requires_audio_feedback', False):
        #     asyncio.create_task(
        #         play_tts_response(
        #             inference_response['response'],
        #             tts_python_path=TTS_PYTHON_PATH,
        #             tts_script_path=TTS_SCRIPT_PATH,
        #             silent=args.silent,
        #         )
        #     )

        response["inference_response"] = inference_response

    return response
