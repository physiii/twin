import aiohttp
import asyncio
import logging
import os
import time
import json  # Ensure the json module is imported

logger = logging.getLogger("model")

class Model:
    def __init__(self, gpt4o_url, gpt4o_key, ollama_model):
        self.gpt4o_url = gpt4o_url
        self.gpt4o_key = gpt4o_key
        self.ollama_model = ollama_model

    async def gpt4o_inference(self, prompt, system_prompt):
        start_time = time.time()
        headers = {
            "Authorization": f"Bearer {self.gpt4o_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "gpt-4o",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ]
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.gpt4o_url, headers=headers, json=data) as response:
                    response.raise_for_status()
                    raw_result = await response.json()
                    return raw_result, time.time() - start_time
        except Exception as e:
            logger.error(f"Error in GPT-4o inference: {e}")
            return None, time.time() - start_time

    async def local_ollama_inference(self, prompt):
        start_time = time.time()
        try:
            proc = await asyncio.create_subprocess_exec(
                'ollama', 'run', self.ollama_model, prompt,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode == 0:
                return stdout.decode().strip(), time.time() - start_time
            else:
                logger.error(f"Local Ollama inference failed: {stderr.decode()}")
                return None, time.time() - start_time
        except Exception as e:
            logger.error(f"Error in local Ollama inference: {str(e)}")
            return None, time.time() - start_time

    async def remote_ollama_inference(self, prompt, ollama_url):
        start_time = time.time()
        host, port = (ollama_url.split(':') + [11434])[:2]
        url = f"http://{host}:{port}/api/generate"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json={"model": self.ollama_model, "prompt": prompt}) as response:
                    response.raise_for_status()
                    full_response = ""
                    async for line in response.content:
                        full_response += json.loads(line.decode('utf-8')).get("response", "")
                    return full_response, time.time() - start_time
        except Exception as e:
            logger.error(f"Error in remote Ollama inference: {str(e)}")
            return None, time.time() - start_time

# Initialize the model instance here
model = Model(
    gpt4o_url="https://api.openai.com/v1/chat/completions",
    gpt4o_key=os.environ.get("OPENAI_API_KEY"),
    ollama_model="llama3.1"
)
