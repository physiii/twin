import json
from datetime import datetime
import logging
from model import model  # Import the initialized model instance
from prompt_reflection import SYSTEM_PROMPT_REFLECTION, PROMPT_REFLECTION  # Import the system prompt and user prompt

logger = logging.getLogger("twin")

async def reflect(running_log, previous_response=""):
    logger.info("Reflecting on the running log...")

    # Convert the running log into a single string for analysis
    running_log_text = "\n".join(running_log)
    
    # Inject the running log and previous response into the reflection prompt
    prompt = PROMPT_REFLECTION.format(
        running_log=running_log_text,
        previous_response=previous_response
    )
    
    # Call the model to analyze the log using the injected system prompt
    analysis_result, inference_time = await model.gpt4o_inference(prompt, SYSTEM_PROMPT_REFLECTION)

    if analysis_result:
        try:
            # Process the result assuming it might be JSON format
            cleaned_result = json.loads(analysis_result['choices'][0]['message']['content'])
            reflection_report = {
                "timestamp": datetime.now().isoformat(),
                "analysis": cleaned_result.get("analysis", []),
                "feedback": cleaned_result.get("feedback", {}),
                "inference_time": inference_time
            }
        except json.JSONDecodeError:
            logger.error("Error decoding JSON response from inference.")
            reflection_report = {
                "timestamp": datetime.now().isoformat(),
                "error": "Failed to decode reflection response",
                "inference_time": inference_time
            }
    else:
        reflection_report = {
            "timestamp": datetime.now().isoformat(),
            "error": "Failed to generate reflection",
            "inference_time": inference_time
        }
    
    return reflection_report