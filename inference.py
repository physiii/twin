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
OLLAMA_MODEL = "llama3.1"  # Ensure this matches your curl command

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

async def ollama_inference(source_text, accumbens_commands, previous_response=None, ollama_url=None):
    start_time = time.time()
    prompt = PROMPT.format(
        source_text=source_text,
        accumbens_commands=accumbens_commands,
        previous_response=previous_response
    )
    
    logger.info(f"Prompt: {prompt}")
    
    if ollama_url:
        return await remote_ollama_inference(prompt, ollama_url)
    else:
        return await local_ollama_inference(prompt)

async def local_ollama_inference(prompt):
    start_time = time.time()  # Add this line
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
            logger.error(f"Local Ollama inference failed: {stderr.decode()}")
            result = None
    except Exception as e:
        logger.error(f"Error in local Ollama inference: {str(e)}")
        result = None
    return result, time.time() - start_time

async def remote_ollama_inference(prompt, ollama_url):
    start_time = time.time()
    
    # Split the URL into host and port, defaulting to port 11434 if not specified
    if ':' in ollama_url:
        host, port = ollama_url.split(':')
    else:
        host = ollama_url
        port = 11434
    
    url = f"http://{host}:{port}/api/generate"
    logger.info(f"Requesting URL: {url}")
    
    data = {
        "model": OLLAMA_MODEL,
        "prompt": prompt
    }
    
    headers = {
        "Content-Type": "application/json"
    }
    logger.info(f"Headers: {headers}")
    logger.info(f"Data: {json.dumps(data)}")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=data, headers=headers) as response:
                response.raise_for_status()
                full_response = ""
                async for line in response.content:
                    if line:
                        # Extract the "response" value and concatenate
                        line_json = json.loads(line.decode('utf-8'))
                        full_response += line_json.get("response", "")
                
                logger.info(f"Full response: {full_response}")
                
                try:
                    parsed_content = json.loads(full_response)
                    return parsed_content, time.time() - start_time
                except json.JSONDecodeError:
                    # If the response is not valid JSON, create a default structure
                    logger.error("JSON decode error, returning raw response.")
                    return {
                        "commands": ["echo " + full_response],
                        "response": full_response,
                        "risk": 0.5,
                        "confirmed": False
                    }, time.time() - start_time
    except aiohttp.ClientConnectorError as e:
        logger.error(f"Connection error to Ollama server at {host}:{port}: {str(e)}")
        return None, time.time() - start_time
    except aiohttp.ClientResponseError as e:
        logger.error(f"Client response error: {str(e)}")
        return None, time.time() - start_time
    except Exception as e:
        logger.error(f"Error in remote Ollama inference: {str(e)}")
        return None, time.time() - start_time

async def run_inference(source_text, accumbens_commands, previous_response=None, use_local_inference=False, ollama_ip=None):
    if use_local_inference:
        if ollama_ip:
            return await ollama_inference(source_text, accumbens_commands, previous_response, ollama_ip)
        else:
            return await ollama_inference(source_text, accumbens_commands, previous_response)
    else:
        return await gpt4o_inference(source_text, accumbens_commands, previous_response)