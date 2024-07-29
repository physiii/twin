import aiohttp
import json
import asyncio
import logging
import time
import os
from prompt import SYSTEM_PROMPT, PROMPT

logger = logging.getLogger("twin")

GPT4O_API_URL = "https://api.openai.com/v1/chat/completions"
GPT4O_API_KEY = os.environ.get("OPENAI_API_KEY")

OLLAMA_MODEL = "llama3"  # Set the model name here

def clean_gpt_response(raw_response):
    if raw_response.startswith('```json') and raw_response.endswith('```'):
        return raw_response.strip('```json').strip('```').strip()
    return raw_response

async def gpt4o_inference(source_text, accumbens_commands, previous_response=None):
    start_time = time.time()
    headers = {
        "Authorization": f"Bearer {GPT4O_API_KEY}",
        "Content-Type": "application/json"
    }
    
    formatted_prompt = PROMPT.format(
        source_text=source_text,
        accumbens_commands=accumbens_commands,
        previous_response=previous_response
    )
    
    data = {
        "model": "gpt-4o",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": formatted_prompt}
        ]
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(GPT4O_API_URL, headers=headers, json=data) as response:
                response.raise_for_status()
                raw_result = await response.json()
                cleaned_result = clean_gpt_response(raw_result['choices'][0]['message']['content'])
                result = json.loads(cleaned_result)
    except Exception as e:
        logger.error(f"Error in GPT-4o inference: {e}")
        result = None
    return result, time.time() - start_time

async def ollama_inference(source_text, accumbens_commands, previous_response=None):
    start_time = time.time()
    prompt = PROMPT.format(
        source_text=source_text,
        accumbens_commands=accumbens_commands,
        previous_response=previous_response
    )
    
    logger.info(f"prompt: {prompt}")
    
    try:
        proc = await asyncio.create_subprocess_exec(
            'ollama', 'run', OLLAMA_MODEL, prompt,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0:
            response = stdout.decode().strip()
            try:
                result = json.loads(response)
            except json.JSONDecodeError:
                result = {
                    "commands": ["echo " + response],
                    "response": response,
                    "risk": 0.5,
                    "confirmed": False
                }
        else:
            logger.error(f"Ollama inference failed: {stderr.decode()}")
            result = None
    except Exception as e:
        logger.error(f"Error in Ollama inference: {str(e)}")
        result = None
    return result, time.time() - start_time
