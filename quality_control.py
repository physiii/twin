import logging
import os
import datetime
import json

from model import model

logger = logging.getLogger("twin")

QUALITY_CONTROL_PROMPT_TEMPLATE = """
You are an expert quality control agent for a voice-controlled home assistant application.

Given the following session data in JSON format:

{session_json}

Please analyze the session data and produce a detailed quality control report that includes:

1. **Session Overview**:
   - **Session ID**: {session_id}
   - **Start Time**: {start_time}
   - **End Time**: {end_time}
   - **Duration**: {duration} seconds
   - **Wake Phrase Used**: "{wake_phrase}"
   - **Detection Context**: Include the context in which the wake phrase was detected.

2. **Conversation Transcript**:
   - Provide a chronological, timestamped log of the interaction, including:
     - **Timestamp**
     - **User Input**: Actual voice source texts.
     - **System Transcription**: How the system transcribed the input.
     - **System Response**: Responses given to the user.

3. **Inference Analysis**:
   - For each inference made, include:
     - **Timestamp**
     - **Source Text**: The text provided to the LLM.
     - **LLM Reasoning and Response**: Detailed reasoning and output.
     - **Commands Generated**
     - **Risk Assessment**
     - **Confirmation Steps**: Any steps taken to confirm actions with the user.

4. **Command Execution Details**:
   - For each command executed, provide:
     - **Timestamp**
     - **Command Text**
     - **Execution Output/Result**
     - **Success or Failure Status**
     - **Error Messages**: Any errors encountered.

5. **Vectorstore Search Results**:
   - Summarize vectorstore queries and results with timestamps.
   - Explain how these results influenced system actions.

6. **User Feedback**:
   - Include any feedback from the user, with timestamps.
   - Note expressions of satisfaction, frustration, or corrections.

7. **Session Analysis**:
   - Provide an overall assessment, identifying:
     - **What Went Right**: Successful interactions with details and timestamps.
     - **What Went Wrong**: Issues encountered with analysis and timestamps.
   - Use expert quality control protocols to support your analysis.

8. **Patterns and Trends**:
   - Analyze any patterns or recurring issues.
   - Include source commands and feedback mechanisms.
   - Compare with previous sessions to identify improvements or regressions.

9. **Performance Scorecard**:
   - Present a scorecard summarizing key performance metrics:
     - **Total Commands Executed**: {total_commands}
     - **Successful Commands**: {successful_commands}
     - **Failed Commands**: {failed_commands}
     - **Success Rate**: {success_rate}%
     - **Average Response Time**: {average_response_time} seconds
     - **User Satisfaction Score**: {user_satisfaction_score}/10

10. **Recommendations and Action Items**:
    - Provide specific, actionable recommendations for system improvements.
    - List action items with clear steps and responsible parties if applicable.

Please present the report in clear, well-structured prose, using appropriate headings, subheadings, tables, and bullet points where necessary.

Do not include the raw session data in the report. Summarize and interpret the data to provide meaningful insights.

The final report should be in plain text, without any JSON or code blocks.
"""

GENERAL_REPORT_PROMPT_TEMPLATE = """
You are an expert quality control agent for a voice-controlled home assistant application.

Below is the previous general report:

[Previous General Report]
{previous_general_report}

And here is the new session report:

[New Session Report]
{new_session_report}

Please update the general report by incorporating insights from the new session report. The updated general report should:

- Summarize cumulative findings from all sessions with timestamps and actual user inputs.
- Highlight patterns, trends, and recurring issues, including specific language that leads to misinterpretations.
- Update sections on what is going right and what is going wrong with detailed examples.
- Include a cumulative performance scorecard that tracks metrics over time.
- Make detailed, actionable recommendations for system improvements.

Present the updated general report in clear, well-structured prose, using appropriate headings, subheadings, tables, and bullet points where necessary.

The final report should be in plain text, without any JSON or code blocks.
"""

async def generate_quality_control_report(session_data, context):
    """
    Generates a quality control report based on the session data.
    """
    try:
        # Extract session details for the prompt
        session_json = json.dumps(session_data, indent=2)
        session_id = session_data.get('session_id', 'N/A')
        start_time = session_data.get('start_time', 'N/A')
        end_time = session_data.get('end_time', 'N/A')
        duration = session_data.get('duration', 'N/A')
        wake_phrase = session_data.get('wake_phrase', 'N/A')
        total_commands = len(session_data.get('commands_executed', []))
        successful_commands = sum(1 for cmd in session_data.get('commands_executed', []) if cmd.get('success'))
        failed_commands = total_commands - successful_commands
        success_rate = (successful_commands / total_commands * 100) if total_commands > 0 else 0
        average_response_time = sum(cmd.get('response_time', 0) for cmd in session_data.get('commands_executed', [])) / total_commands if total_commands > 0 else 0
        user_satisfaction_score = session_data.get('user_satisfaction_score', 'N/A')

        # Prepare the prompt with extracted details
        prompt = QUALITY_CONTROL_PROMPT_TEMPLATE.format(
            session_json=session_json,
            session_id=session_id,
            start_time=start_time,
            end_time=end_time,
            duration=duration,
            wake_phrase=wake_phrase,
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
            report_path = os.path.join(context.get('QC_REPORT_DIR', 'reports'), report_filename)
            with open(report_path, 'w') as report_file:
                report_file.write(response_text)
            logger.info(f"[QC Report] Generated quality control report: {report_path}")

            # Update the general report
            await update_general_report(response_text, context)
        else:
            logger.error("[QC Report] Failed to generate quality control report.")
    except Exception as e:
        logger.exception(f"[QC Report] Exception occurred: {e}")

async def update_general_report(new_session_report, context):
    """
    Updates the general report by incorporating the new session report.
    """
    try:
        # Ensure the reports directory exists
        qc_report_dir = context.get('QC_REPORT_DIR', 'reports')
        os.makedirs(qc_report_dir, exist_ok=True)

        # Define the general report file path
        general_report_file = os.path.join(qc_report_dir, context.get('GENERAL_REPORT_FILE', 'general_report.txt'))

        # Read the previous general report if it exists
        if os.path.exists(general_report_file):
            with open(general_report_file, 'r') as file:
                previous_general_report = file.read()
        else:
            previous_general_report = "No previous general report available."

        # Prepare the prompt for updating the general report
        prompt = GENERAL_REPORT_PROMPT_TEMPLATE.format(
            previous_general_report=previous_general_report,
            new_session_report=new_session_report
        )

        remote_inference_url = context.get('REMOTE_INFERENCE_URL')
        if not remote_inference_url:
            logger.error("REMOTE_INFERENCE_URL is not set in the context.")
            return

        updated_general_report, duration = await model.remote_inference(prompt, inference_url=remote_inference_url)

        if updated_general_report:
            # Save the updated general report
            with open(general_report_file, 'w') as file:
                file.write(updated_general_report)
            logger.info(f"[QC Report] General report updated: {general_report_file}")
        else:
            logger.error("[QC Report] Failed to update general report.")
    except Exception as e:
        logger.exception(f"[QC Report] Exception occurred while updating general report: {e}")
