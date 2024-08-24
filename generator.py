import asyncio
import logging
import os
import json
from prompt import SYSTEM_PROMPT, PROMPT
from model import Model

logger = logging.getLogger("twin")

# Initialize the model with relevant API URLs and keys
model = Model(
    gpt4o_url="https://api.openai.com/v1/chat/completions",
    gpt4o_key=os.environ.get("OPENAI_API_KEY"),
    ollama_model="llama3.1"
)

def clean_gpt_response(raw_response):
    if raw_response.startswith('```json') and raw_response.endswith('```'):
        return raw_response.strip('```json').strip('```').strip()
    return raw_response

def process_result(raw_result):
    # Check if raw_result is a string, indicating it needs to be parsed
    if isinstance(raw_result, str):
        try:
            raw_result = json.loads(raw_result)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse raw_result as JSON: {e}")
            return {
                "commands": ["echo " + str(raw_result)],
                "response": str(raw_result),
                "risk": 0.5,  # Fallback risk value if parsing fails
                "confirmed": False
            }

    if isinstance(raw_result, dict) and 'commands' in raw_result:
        try:
            # If the response field is itself a JSON string, parse it
            if isinstance(raw_result.get('response'), str):
                try:
                    nested_response = json.loads(raw_result['response'])
                    raw_result.update(nested_response)
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse nested response as JSON: {e}")
            
            return {
                "commands": raw_result.get("commands", ["echo " + str(raw_result)]),
                "response": raw_result.get("response", str(raw_result)),
                "risk": raw_result.get("risk", 0.5),
                "confirmed": raw_result.get("confirmed", False)
            }
        except (KeyError, TypeError) as e:
            logger.error(f"Error processing result: {e}")
            return {
                "commands": ["echo " + str(raw_result)],
                "response": str(raw_result),
                "risk": 0.5,
                "confirmed": False
            }
    else:
        logger.error(f"Unexpected raw result format: {type(raw_result)}, {raw_result}")
        return {
            "commands": ["echo " + str(raw_result)],
            "response": str(raw_result),
            "risk": 0.5,
            "confirmed": False
        }

async def run_inference(source_text, accumbens_commands, previous_response=None, use_local_inference=False, ollama_ip=None):
    prompt = PROMPT.format(
        source_text=source_text,
        accumbens_commands=accumbens_commands,
        previous_response=previous_response
    )

    if use_local_inference:
        if ollama_ip:
            raw_result, duration = await model.remote_ollama_inference(prompt, ollama_ip)
        else:
            raw_result, duration = await model.local_ollama_inference(prompt)
    else:
        raw_result, duration = await model.gpt4o_inference(prompt, SYSTEM_PROMPT)

    if raw_result:
        return process_result(raw_result), duration
    else:
        logger.error("No result returned from inference.")
        return None, duration
