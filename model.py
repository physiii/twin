# model.py

import aiohttp
import asyncio
import logging
import os
import time
import json

logger = logging.getLogger("twin")

class Model:
    def __init__(self):
        self.gpt4o_url = os.environ.get("GPT4O_URL")
        self.gpt4o_key = os.environ.get("GPT4O_KEY")

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

    async def remote_inference(self, prompt, inference_url):
        """
        Sends a POST request to the remote inference server with the required payload.
        
        Args:
            prompt (str): The inference prompt.
            inference_url (str): The full URL of the remote inference server.
        
        Returns:
            tuple: (response_text, duration)
        """
        start_time = time.time()
        # command-r7b mistralsmall:22b, llama3.2:3b, llama3.1:8b deepseek-r1:7b deepseek-r1:8b
        payload = {
            "model": "llama3.1:8b",
            "prompt": prompt,
            "stream": False
        }
        headers = {
            "Content-Type": "application/json"
        }

        try:
            logger.info(f"Sending request to inference URL: {inference_url}")
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    inference_url, 
                    headers=headers, 
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=60)  # 60 second timeout
                ) as response:
                    if response.status == 200:
                        logger.info(f"Received 200 OK response from inference server")
                        try:
                            response_data = await response.json()
                            response_text = response_data.get("response", "").strip()
                            logger.info(f"Successfully parsed JSON response, length: {len(response_text)}")
                            logger.debug(f"Prompt: {prompt}")
                            logger.debug(f"Response: {response_text}")
                            return response_text, time.time() - start_time
                        except Exception as json_error:
                            logger.error(f"Failed to parse JSON response: {str(json_error)}")
                            raw_text = await response.text()
                            logger.error(f"Raw response: {raw_text[:200]}...")
                            return None, time.time() - start_time
                    else:
                        error_message = await response.text()
                        logger.error(f"Error in remote inference: {response.status}, message='{error_message}', url={inference_url}")
                        return None, time.time() - start_time
        except asyncio.TimeoutError:
            logger.error(f"Timeout error in remote inference after {time.time() - start_time:.2f}s")
            return None, time.time() - start_time
        except Exception as e:
            logger.error(f"Error in remote inference: {str(e)}")
            return None, time.time() - start_time

# Initialize the model instance here
model = Model()
