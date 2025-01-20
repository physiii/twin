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
    if isinstance(raw_result, str):
        try:
            raw_result = json.loads(raw_result)
        except json.JSONDecodeError:
            return {
                "commands": ["echo " + str(raw_result)],
                "response": str(raw_result),
                "risk": 0.5,
                "confirmed": False,
                "requires_audio_feedback": False,
                "confidence": 0.5,
                "intent_reasoning": ""
            }

    if isinstance(raw_result, dict) and 'commands' in raw_result:
        return {
            "commands": raw_result.get("commands", []),
            "response": raw_result.get("response", ""),
            "risk": raw_result.get("risk", 0.5),
            "confirmed": raw_result.get("confirmed", False),
            "requires_audio_feedback": raw_result.get("requires_audio_feedback", False),
            "confidence": raw_result.get("confidence", 0.5),
            "intent_reasoning": raw_result.get("intent_reasoning", "")
        }
    else:
        logger.error(f"Unexpected raw result format: {type(raw_result)}, {raw_result}")
        return {
            "commands": [],
            "response": "",
            "risk": 0.5,
            "confirmed": False,
            "requires_audio_feedback": False,
            "confidence": 0.5,
            "intent_reasoning": ""
        }

async def run_inference(source_text, accumbens_commands, tool_info, use_remote_inference=False, inference_url=None):
    """
    This function loads the text from stores/self/office.txt and injects it into the prompt
    as {self}, then performs the inference using the model.
    """
    # 1. Load the text from office.txt
    # Adjust the file path if your structure is different.
    home_directory = os.path.expanduser("~")
    self_file_path = os.path.join(home_directory, "self.txt")
    with open(self_file_path, "r", encoding="utf-8") as f:
        self_text = f.read().strip()

    # 2. Format the prompt, injecting self_text
    prompt = PROMPT.format(
        source_text=source_text,
        accumbens_commands="\n".join(accumbens_commands),
        tool_info=tool_info,
        self=self_text
    )

    logger.info(f"Running inference with prompt: {prompt}")
    raw_result, duration = await model.remote_inference(prompt, inference_url)

    parse_result = clean_gpt_response(raw_result)

    if raw_result:
        return process_result(parse_result), duration
    else:
        logger.error("No result returned from inference.")
        return None, duration

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

    inference_response, raw_response = await run_inference(
        source_text=text,
        accumbens_commands=combined_commands,
        tool_info=tool_info,
        use_remote_inference=bool(REMOTE_INFERENCE_URL),
        inference_url=REMOTE_INFERENCE_URL,
    )

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
                    f"[Warning] Commands not executed. Risk: {inference_response['risk']}. Confirmation required."
                )

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
