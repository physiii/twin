import re
import time
import json
import asyncio
import logging
from fuzzywuzzy import fuzz
from pymilvus import Collection

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

async def run_search(text, collection_name, args, local_embedding_model=None, milvus_host=None):
    start_time = time.time()
    if args.local_embed:
        query_embedding = local_embedding_model.encode([text], prompt_name="query")[0].tolist()
        collection = Collection(collection_name)
        search_params = {
            "metric_type": "L2",
            "params": {"nprobe": 10},
        }
        try:
            results = collection.search(
                data=[query_embedding],
                anns_field="vector",
                param=search_params,
                limit=5,
                output_fields=["snippet"]
            )
            result = [(hit.entity.get('snippet'), hit.distance) for hit in results[0]]
        except Exception as e:
            logger.error(f"Error in Milvus search: {str(e)}")
            result = []
    else:
        search_command = f'python /media/mass/scripts/vectorstore/search.py "{text}" --collection {collection_name} --ip-address {milvus_host}'
        try:
            proc = await asyncio.create_subprocess_shell(
                search_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode == 0:
                search_results = json.loads(stdout)
                result = [(r['snippet'], round(r['distance'], 2)) for r in search_results]
            else:
                logger.error(f"Error running search: {stderr.decode()}")
                result = []
        except Exception as e:
            logger.error(f"Error in search process: {str(e)}")
            result = []
    return result, time.time() - start_time