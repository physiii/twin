# search.py

import re
import time
import json
import asyncio
import logging
import aiohttp
from fuzzywuzzy import fuzz

logger = logging.getLogger("twin")

def clean_text(text):
    text = re.sub(r'\[.*?\]|\(.*?\)|\*.*?\*|\{.*?\}', '', text)
    return text.strip()

def is_similar(text, buffer, similarity_threshold):
    clean_text_val = clean_text(text)
    for recent_text in buffer:
        clean_recent_text = clean_text(recent_text)
        similarity = fuzz.ratio(clean_text_val, clean_recent_text)
        if similarity > similarity_threshold:
            return True
    return False

async def run_search(text, collection_name, remote_store_url):
    start_time = time.time()

    # Ensure base_url is a string
    base_url = str(remote_store_url) if remote_store_url is not None else ""
    if not base_url:
        logger.error("Empty or None remote_store_url provided")
        return [], time.time() - start_time
        
    headers = {'Content-Type': 'application/json'}

    # Prepare the search payload with the query text
    search_payload = {
        "type": "search",
        "query": text,
        "collection": collection_name
    }

    # Log the request details
    logger.debug(f"Making search request to URL: {base_url}")
    logger.debug(f"With payload: {json.dumps(search_payload)}")

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(base_url, headers=headers, json=search_payload) as response:
                if response.status == 200:
                    data = await response.json()
                    results = data.get('results', [])
                    result = [(r['text'], round(r['distance'], 2)) for r in results]
                else:
                    logger.error(f"Error in search API call. Status code: {response.status}")
                    response_text = await response.text()
                    logger.error(f"Response text: {response_text}")
                    result = []
        except Exception as e:
            import traceback
            logger.error(f"Exception during API call: {str(e)}")
            logger.error(f"Exception type: {type(e)}")
            logger.error(f"Exception args: {e.args}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            logger.error(f"Search payload: {search_payload}")
            result = []

    return result, time.time() - start_time
