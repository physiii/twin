import logging
import os
import datetime
import json

from model import model

logger = logging.getLogger("twin")

# Paths for storing reports and metrics
QC_REPORT_DIR = 'reports'
METRICS_FILE = os.path.join(QC_REPORT_DIR, 'cumulative_metrics.json')
GENERAL_REPORT_FILE = os.path.join(QC_REPORT_DIR, 'general_report.txt')

QUALITY_CONTROL_PROMPT_TEMPLATE = """
You are an expert quality control agent for a voice-controlled home assistant application.

Given the following session data and performance metrics:

**Session Details**:
- **Session ID**: {session_id}
- **Start Time**: {start_time}
- **End Time**: {end_time}
- **Duration**: {duration} seconds
- **Wake Phrase Used**: "{wake_phrase}"

**Conversation Transcript**:
{conversation_transcript}

**Inference Analysis**:
{inference_analysis}

**Command Execution Details**:
{command_execution_details}

**Vectorstore Search Results**:
{vectorstore_search_results}

**User Feedback**:
{user_feedback}

**Session Performance Metrics**:
- **Total Commands Executed**: {total_commands}
- **Successful Commands**: {successful_commands}
- **Failed Commands**: {failed_commands}
- **Success Rate**: {success_rate}%
- **Average Response Time**: {average_response_time} seconds
- **User Satisfaction Score**: {user_satisfaction_score}/10

Please analyze the session data and produce a detailed quality control report that includes:

1. **Session Analysis**:
   - **What Went Right**: Identify successful interactions with details and timestamps.
   - **What Went Wrong**: Identify mistakes or issues encountered, providing detailed analysis and timestamps.
   - **Root Cause Analysis**: For each issue, provide potential causes and suggestions for prevention.

2. **Patterns and Trends**:
   - Analyze any patterns or recurring issues within this session.
   - Highlight any user inputs that led to misinterpretations or errors.

3. **Recommendations and Action Items**:
   - Provide specific, actionable recommendations for system improvements based on this session.
   - List action items with clear steps.

Please present the report in clear, well-structured prose, using appropriate headings, subheadings, tables, and bullet points where necessary.

Do not include the raw session data in the report. Summarize and interpret the data to provide meaningful insights.

The final report should be in plain text, without any JSON or code blocks.
"""

GENERAL_REPORT_PROMPT_TEMPLATE = """
You are an expert quality control agent for a voice-controlled home assistant application.

Below is the cumulative performance data and recent findings:

**Cumulative Performance Metrics**:
- **Total Sessions**: {total_sessions}
- **Total Commands Executed**: {cumulative_total_commands}
- **Successful Commands**: {cumulative_successful_commands}
- **Failed Commands**: {cumulative_failed_commands}
- **Overall Success Rate**: {cumulative_success_rate}%
- **Average Response Time**: {cumulative_average_response_time} seconds
- **Average User Satisfaction Score**: {cumulative_user_satisfaction_score}/10

**Recent Session Findings**:
{recent_session_findings}

Please update the general report by incorporating insights from the recent sessions. The updated general report should:

- Summarize cumulative findings from all sessions with specific examples and timestamps.
- Highlight patterns, trends, and recurring issues, including specific language that leads to misinterpretations.
- Update sections on what's going right and what's going wrong with detailed examples.
- Present the updated cumulative performance scorecard with trends over time.

- Make detailed, actionable recommendations for system improvements.

Present the updated general report in clear, well-structured prose, using appropriate headings, subheadings, tables, and bullet points where necessary.

The final report should be in plain text, without any JSON or code blocks.
"""

async def generate_quality_control_report(session_data, context):
    """
    Generates a quality control report based on the session data.
    """
    try:
        # Ensure the reports directory exists
        os.makedirs(QC_REPORT_DIR, exist_ok=True)

        # Extract session details
        session_id = session_data.get('session_id', 'N/A')
        start_time = session_data.get('start_time', 'N/A')
        end_time = session_data.get('end_time', 'N/A')
        duration = session_data.get('duration', 'N/A')
        wake_phrase = session_data.get('wake_phrase', 'N/A')
        user_satisfaction_score = session_data.get('user_satisfaction_score', 'N/A')

        # Process commands and compute session metrics
        commands_executed = session_data.get('commands_executed', [])
        total_commands = len(commands_executed)
        successful_commands = sum(1 for cmd in commands_executed if cmd.get('success'))
        failed_commands = total_commands - successful_commands
        success_rate = (successful_commands / total_commands * 100) if total_commands > 0 else 0
        average_response_time = (
            sum(cmd.get('response_time', 0) for cmd in commands_executed) / total_commands
        ) if total_commands > 0 else 0

        # Update cumulative metrics
        cumulative_metrics = load_cumulative_metrics()
        cumulative_metrics = update_cumulative_metrics(
            cumulative_metrics,
            total_commands,
            successful_commands,
            failed_commands,
            average_response_time,
            user_satisfaction_score
        )
        save_cumulative_metrics(cumulative_metrics)

        # Prepare detailed sections for the prompt
        conversation_transcript = format_conversation_transcript(session_data.get('conversation', []))
        inference_analysis = format_inference_analysis(session_data.get('inferences', []))
        command_execution_details = format_command_execution_details(commands_executed)
        vectorstore_search_results = format_vectorstore_search_results(session_data.get('vectorstore_searches', []))
        user_feedback = format_user_feedback(session_data.get('user_feedback', []))

        # Prepare the prompt with extracted details
        prompt = QUALITY_CONTROL_PROMPT_TEMPLATE.format(
            session_id=session_id,
            start_time=start_time,
            end_time=end_time,
            duration=duration,
            wake_phrase=wake_phrase,
            conversation_transcript=conversation_transcript,
            inference_analysis=inference_analysis,
            command_execution_details=command_execution_details,
            vectorstore_search_results=vectorstore_search_results,
            user_feedback=user_feedback,
            total_commands=total_commands,
            successful_commands=successful_commands,
            failed_commands=failed_commands,
            success_rate=round(success_rate, 2),
            average_response_time=round(average_response_time, 2),
            user_satisfaction_score=user_satisfaction_score
        )

        # Use the remote_inference method
        remote_inference_url = context.get('REMOTE_INFERENCE_URL')
        if not remote_inference_url:
            logger.error("REMOTE_INFERENCE_URL is not set in the context.")
            return

        response_text, duration = await model.remote_inference(prompt, inference_url=remote_inference_url)

        if response_text:
            # Save the session report to a file
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            report_filename = f"qc_report_{timestamp}.txt"
            report_path = os.path.join(QC_REPORT_DIR, report_filename)
            with open(report_path, 'w') as report_file:
                report_file.write(response_text)
            logger.info(f"[QC Report] Generated quality control report: {report_path}")

            # Update the general report
            await update_general_report(response_text, cumulative_metrics, context)
        else:
            logger.error("[QC Report] Failed to generate quality control report.")
    except Exception as e:
        logger.exception(f"[QC Report] Exception occurred: {e}")

def load_cumulative_metrics():
    """
    Loads cumulative performance metrics from a JSON file.
    """
    if os.path.exists(METRICS_FILE):
        with open(METRICS_FILE, 'r') as file:
            return json.load(file)
    else:
        return {
            'total_sessions': 0,
            'cumulative_total_commands': 0,
            'cumulative_successful_commands': 0,
            'cumulative_failed_commands': 0,
            'cumulative_success_rate': 0.0,
            'cumulative_average_response_time': 0.0,
            'cumulative_user_satisfaction_score': 0.0
        }

def save_cumulative_metrics(metrics):
    """
    Saves cumulative performance metrics to a JSON file.
    """
    with open(METRICS_FILE, 'w') as file:
        json.dump(metrics, file, indent=2)

def update_cumulative_metrics(metrics, total_commands, successful_commands, failed_commands, average_response_time, user_satisfaction_score):
    """
    Updates the cumulative performance metrics with the latest session data.
    """
    metrics['total_sessions'] += 1
    metrics['cumulative_total_commands'] += total_commands
    metrics['cumulative_successful_commands'] += successful_commands
    metrics['cumulative_failed_commands'] += failed_commands

    # Update cumulative success rate
    if metrics['cumulative_total_commands'] > 0:
        metrics['cumulative_success_rate'] = (
            metrics['cumulative_successful_commands'] / metrics['cumulative_total_commands'] * 100
        )

    # Update cumulative average response time
    total_response_time = metrics.get('total_response_time', 0.0) + (average_response_time * total_commands)
    metrics['total_response_time'] = total_response_time
    metrics['cumulative_average_response_time'] = total_response_time / metrics['cumulative_total_commands'] if metrics['cumulative_total_commands'] > 0 else 0.0

    # Update cumulative user satisfaction score
    total_user_satisfaction = metrics.get('total_user_satisfaction', 0.0) + user_satisfaction_score
    metrics['total_user_satisfaction'] = total_user_satisfaction
    metrics['cumulative_user_satisfaction_score'] = total_user_satisfaction / metrics['total_sessions'] if metrics['total_sessions'] > 0 else 0.0

    return metrics

def format_conversation_transcript(conversation):
    """
    Formats the conversation transcript for the prompt.
    """
    transcript = ""
    for entry in conversation:
        timestamp = entry.get('timestamp', 'N/A')
        user_input = entry.get('user_input', 'N/A')
        system_transcription = entry.get('system_transcription', 'N/A')
        system_response = entry.get('system_response', 'N/A')
        transcript += f"- **Timestamp**: {timestamp}\n  - **User Input**: {user_input}\n  - **System Transcription**: {system_transcription}\n  - **System Response**: {system_response}\n\n"
    return transcript

def format_inference_analysis(inferences):
    """
    Formats the inference analysis for the prompt.
    """
    analysis = ""
    for inference in inferences:
        timestamp = inference.get('timestamp', 'N/A')
        source_text = inference.get('source_text', 'N/A')
        reasoning = inference.get('reasoning', 'N/A')
        commands_generated = inference.get('commands_generated', 'N/A')
        risk_assessment = inference.get('risk_assessment', 'N/A')
        confirmation_steps = inference.get('confirmation_steps', 'N/A')
        analysis += f"- **Timestamp**: {timestamp}\n  - **Source Text**: {source_text}\n  - **LLM Reasoning and Response**: {reasoning}\n  - **Commands Generated**: {commands_generated}\n  - **Risk Assessment**: {risk_assessment}\n  - **Confirmation Steps**: {confirmation_steps}\n\n"
    return analysis

def format_command_execution_details(commands):
    """
    Formats the command execution details for the prompt.
    """
    details = ""
    for cmd in commands:
        timestamp = cmd.get('timestamp', 'N/A')
        command_text = cmd.get('command_text', 'N/A')
        execution_output = cmd.get('execution_output', 'N/A')
        success = cmd.get('success', False)
        status = 'Success' if success else 'Failure'
        error_message = cmd.get('error_message', 'N/A')
        details += f"- **Timestamp**: {timestamp}\n  - **Command Text**: {command_text}\n  - **Execution Output/Result**: {execution_output}\n  - **Status**: {status}\n  - **Error Messages**: {error_message}\n\n"
    return details

def format_vectorstore_search_results(searches):
    """
    Formats the vectorstore search results for the prompt.
    """
    results = ""
    for search in searches:
        timestamp = search.get('timestamp', 'N/A')
        query = search.get('query', 'N/A')
        results_list = search.get('results', [])
        results += f"- **Timestamp**: {timestamp}\n  - **Query**: {query}\n  - **Results**: {results_list}\n\n"
    return results

def format_user_feedback(feedback_list):
    """
    Formats the user feedback for the prompt.
    """
    feedback = ""
    for feedback_entry in feedback_list:
        timestamp = feedback_entry.get('timestamp', 'N/A')
        feedback_text = feedback_entry.get('feedback', 'N/A')
        feedback += f"- **Timestamp**: {timestamp}\n  - **Feedback**: {feedback_text}\n\n"
    return feedback

async def update_general_report(new_session_report, cumulative_metrics, context):
    """
    Updates the general report by incorporating the new session report.
    """
    try:
        # Read recent session findings (last few session reports)
        recent_session_findings = get_recent_session_findings()

        # Prepare the prompt for updating the general report
        prompt = GENERAL_REPORT_PROMPT_TEMPLATE.format(
            total_sessions=cumulative_metrics['total_sessions'],
            cumulative_total_commands=cumulative_metrics['cumulative_total_commands'],
            cumulative_successful_commands=cumulative_metrics['cumulative_successful_commands'],
            cumulative_failed_commands=cumulative_metrics['cumulative_failed_commands'],
            cumulative_success_rate=round(cumulative_metrics['cumulative_success_rate'], 2),
            cumulative_average_response_time=round(cumulative_metrics['cumulative_average_response_time'], 2),
            cumulative_user_satisfaction_score=round(cumulative_metrics['cumulative_user_satisfaction_score'], 2),
            recent_session_findings=recent_session_findings
        )

        remote_inference_url = context.get('REMOTE_INFERENCE_URL')
        if not remote_inference_url:
            logger.error("REMOTE_INFERENCE_URL is not set in the context.")
            return

        updated_general_report, duration = await model.remote_inference(prompt, inference_url=remote_inference_url)

        if updated_general_report:
            # Save the updated general report
            with open(GENERAL_REPORT_FILE, 'w') as file:
                file.write(updated_general_report)
            logger.info(f"[QC Report] General report updated: {GENERAL_REPORT_FILE}")
        else:
            logger.error("[QC Report] Failed to update general report.")
    except Exception as e:
        logger.exception(f"[QC Report] Exception occurred while updating general report: {e}")

def get_recent_session_findings():
    """
    Retrieves findings from recent session reports.
    """
    recent_reports = []
    report_files = sorted(
        [f for f in os.listdir(QC_REPORT_DIR) if f.startswith('qc_report_') and f.endswith('.txt')],
        reverse=True
    )
    # Get the latest 5 session reports
    for report_file in report_files[:5]:
        with open(os.path.join(QC_REPORT_DIR, report_file), 'r') as file:
            recent_reports.append(file.read())
    return "\n\n".join(recent_reports)
