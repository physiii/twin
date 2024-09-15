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

async def run_search(text, collection_name, args, milvus_host=None):
    start_time = time.time()

    base_url = 'http://192.168.1.40:5000/vectorstore'
    headers = {'Content-Type': 'application/json'}

    # Prepare the search payload with the query text
    search_payload = {
        "type": "search",
        "query": text,
        "collection": collection_name
    }

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(base_url, headers=headers, json=search_payload) as response:
                if response.status == 200:
                    data = await response.json()
                    results = data.get('results', [])
                    result = [(r['text'], round(r['distance'], 2)) for r in results]
                else:
                    logger.error(f"Error in search API call. Status code: {response.status}")
                    result = []
        except Exception as e:
            logger.error(f"Exception during API call: {str(e)}")
            result = []

    return result, time.time() - start_time
