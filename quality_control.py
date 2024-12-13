import os
import json
import logging
from datetime import datetime
from model import model

logger = logging.getLogger("twin")

QC_REPORT_DIR = 'reports'
REPORT_FILE = os.path.join(QC_REPORT_DIR, 'report.json')

# Updated prompt: now instructing the LLM to produce strictly JSON
QUALITY_CONTROL_PROMPT_TEMPLATE = """
You are an expert quality control agent for a voice-controlled home assistant application.

You are given session data and performance metrics. Analyze and summarize the session comprehensively, focusing on what went right, what went wrong, root causes, patterns, and actionable recommendations. Also provide a final numeric score between 0.0 and 1.0 for the overall session quality.

Your output must be strictly in JSON format as follows:

{
  "description": "<A concise, information-rich description>",
  "score": <A numeric score between 0.0 and 1.0>
}

Do not include any additional text outside of the JSON.
"""

def load_report():
    if os.path.exists(REPORT_FILE):
        with open(REPORT_FILE, 'r') as f:
            data = json.load(f)
    else:
        data = {
            "sessions": [],
            "summary": "No sessions yet.",
            "average_score": 0.0
        }
    return data

def save_report(data):
    with open(REPORT_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def update_summary_and_average(data):
    sessions = data.get("sessions", [])
    if not sessions:
        data["summary"] = "No sessions recorded yet."
        data["average_score"] = 0.0
        return
    scores = [s.get("score", 0) for s in sessions]
    avg = sum(scores) / len(scores)
    data["average_score"] = round(avg, 3)
    data["summary"] = f"{len(sessions)} sessions recorded. Average score: {data['average_score']}."

def extract_description_and_score(response_text):
    # Parse JSON directly
    try:
        response_json = json.loads(response_text.strip())
        description = response_json.get("description", "No description provided.")
        score = response_json.get("score", 0.0)
        if not isinstance(score, (float, int)):
            score = 0.0
        return description, score
    except json.JSONDecodeError:
        return "No description provided.", 0.0

def format_conversation_transcript(conversation):
    transcript = ""
    for entry in conversation or []:
        timestamp = entry.get('timestamp', 'N/A')
        user_input = entry.get('user_input', 'N/A')
        system_transcription = entry.get('system_transcription', 'N/A')
        system_response = entry.get('system_response', 'N/A')
        transcript += f"- Timestamp: {timestamp}\n  User Input: {user_input}\n  System Transcription: {system_transcription}\n  System Response: {system_response}\n\n"
    return transcript

def format_inference_analysis(inferences):
    analysis = ""
    for inference in inferences or []:
        timestamp = inference.get('timestamp', 'N/A')
        source_text = inference.get('source_text', 'N/A')
        reasoning = inference.get('reasoning', 'N/A')
        commands_generated = inference.get('commands_generated', 'N/A')
        risk_assessment = inference.get('risk_assessment', 'N/A')
        confirmation_steps = inference.get('confirmation_steps', 'N/A')
        analysis += f"- Timestamp: {timestamp}\n  Source Text: {source_text}\n  Reasoning: {reasoning}\n  Commands Generated: {commands_generated}\n  Risk Assessment: {risk_assessment}\n  Confirmation Steps: {confirmation_steps}\n\n"
    return analysis

def format_command_execution_details(commands):
    details = ""
    for cmd in commands or []:
        timestamp = cmd.get('timestamp', 'N/A')
        command_text = cmd.get('command_text', 'N/A')
        execution_output = cmd.get('execution_output', 'N/A')
        success = cmd.get('success', False)
        status = 'Success' if success else 'Failure'
        error_message = cmd.get('error_message', 'N/A')
        details += f"- Timestamp: {timestamp}\n  Command: {command_text}\n  Output: {execution_output}\n  Status: {status}\n  Errors: {error_message}\n\n"
    return details

def format_vectorstore_search_results(searches):
    results = ""
    for search in searches or []:
        timestamp = search.get('timestamp', 'N/A')
        query = search.get('query', 'N/A')
        results_list = search.get('results', [])
        results += f"- Timestamp: {timestamp}\n  Query: {query}\n  Results: {results_list}\n\n"
    return results

def format_user_feedback(feedback_list):
    feedback = ""
    for feedback_entry in feedback_list or []:
        timestamp = feedback_entry.get('timestamp', 'N/A')
        feedback_text = feedback_entry.get('feedback', 'N/A')
        feedback += f"- Timestamp: {timestamp}\n  Feedback: {feedback_text}\n\n"
    return feedback

async def generate_quality_control_report(session_data, context):
    try:
        os.makedirs(QC_REPORT_DIR, exist_ok=True)

        session_id = session_data.get('session_id', 'N/A')
        start_time = session_data.get('start_time', 'N/A')
        end_time = session_data.get('end_time', 'N/A')
        duration = session_data.get('duration', 'N/A')
        wake_phrase = session_data.get('wake_phrase', 'N/A')

        user_satisfaction_score = session_data.get('user_satisfaction_score', 0.0)
        if not isinstance(user_satisfaction_score, (int, float)):
            user_satisfaction_score = 0.0

        commands_executed = session_data.get('commands_executed', [])
        total_commands = len(commands_executed)
        successful_commands = sum(1 for cmd in commands_executed if cmd.get('success'))
        failed_commands = total_commands - successful_commands
        success_rate = (successful_commands / total_commands * 100) if total_commands > 0 else 0.0
        average_response_time = (
            sum(cmd.get('response_time', 0.0) for cmd in commands_executed) / total_commands
        ) if total_commands > 0 else 0.0

        conversation_transcript = format_conversation_transcript(session_data.get('conversation', []))
        inference_analysis = format_inference_analysis(session_data.get('inferences', []))
        command_execution_details = format_command_execution_details(commands_executed)
        vectorstore_search_results = format_vectorstore_search_results(session_data.get('vectorstore_results', []))
        user_feedback = format_user_feedback(session_data.get('user_feedback', []))

        prompt = QUALITY_CONTROL_PROMPT_TEMPLATE

        # Construct a final prompt that includes the session details for the LLM to analyze.
        session_details = f"""
Session Details:
- Session ID: {session_id}
- Start Time: {start_time}
- End Time: {end_time}
- Duration: {duration} seconds
- Wake Phrase Used: "{wake_phrase}"

Conversation Transcript:
{conversation_transcript}

Inference Analysis:
{inference_analysis}

Command Execution Details:
{command_execution_details}

Vectorstore Search Results:
{vectorstore_search_results}

User Feedback:
{user_feedback}

Session Performance Metrics:
- Total Commands Executed: {total_commands}
- Successful Commands: {successful_commands}
- Failed Commands: {failed_commands}
- Success Rate: {round(success_rate, 2)}%
- Average Response Time: {round(average_response_time, 2)} seconds
- User Satisfaction Score: {round(user_satisfaction_score, 2)}/10
"""

        full_prompt = prompt + "\n" + session_details.strip()

        remote_inference_url = context.get('REMOTE_INFERENCE_URL')
        if not remote_inference_url:
            logger.error("REMOTE_INFERENCE_URL not set. Cannot generate QC report.")
            return

        response_text, inference_duration = await model.remote_inference(full_prompt, inference_url=remote_inference_url)

        if not response_text:
            logger.error("[QC Report] No response from LLM, cannot update report.json")
            return

        description, score = extract_description_and_score(response_text)

        data = load_report()
        timestamp = datetime.now().isoformat()
        data["sessions"].append({
            "timestamp": timestamp,
            "description": description,
            "score": score
        })
        update_summary_and_average(data)
        save_report(data)

        logger.info(f"[QC Report] Session recorded in {REPORT_FILE}, Score: {score}, Sessions: {len(data['sessions'])}, Avg: {data['average_score']}")
    except Exception as e:
        logger.exception(f"[QC Report] Exception occurred: {e}")

def get_recent_session_findings():
    return "No separate per-session text reports. All in report.json now."
