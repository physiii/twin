from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer
import uvicorn
import numpy as np
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI()

# Load the model
model = SentenceTransformer("Alibaba-NLP/gte-Qwen2-1.5B-instruct", trust_remote_code=True)

class EmbedRequest(BaseModel):
    text: str

class EmbedResponse(BaseModel):
    embedding: list[float]

@app.post("/embed", response_model=EmbedResponse)
async def create_embedding(request: EmbedRequest):
    try:
        # Log the incoming request text
        logger.info(f"Received embedding request for text: {request.text[:100]}...")  # Log first 100 characters

        # Generate the embedding
        embedding = model.encode([request.text], prompt_name="query")[0]
        
        # Convert numpy array to list for JSON serialization
        embedding_list = embedding.tolist()
        
        logger.info(f"Successfully generated embedding of length {len(embedding_list)}")
        
        return {"embedding": embedding_list}
    except Exception as e:
        logger.error(f"Error generating embedding: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.on_event("startup")
async def startup_event():
    logger.info("Embedding server is starting up...")
    try:
        model_info = f"Model loaded: {model.__class__.__name__}"
        if hasattr(model, '_model_card_vars'):
            if 'name' in model._model_card_vars:
                model_info += f" - {model._model_card_vars['name']}"
            elif 'modelId' in model._model_card_vars:
                model_info += f" - {model._model_card_vars['modelId']}"
        logger.info(model_info)
    except Exception as e:
        logger.error(f"Error retrieving model information: {str(e)}")
        logger.info("Model loaded, but unable to retrieve detailed information.")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)