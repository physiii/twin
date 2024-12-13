# quality_control_prompt.py

QUALITY_CONTROL_PROMPT = """
You are an expert quality control agent for a voice-controlled home assistant application.

Given the following session data in JSON format:

{session_json}

Please analyze the session data and produce a detailed quality control report that includes:

1. **Session Overview**:
   - Session ID, start time, end time, and duration.
   - Wake phrase used and its detection context.

2. **Conversation Transcript**:
   - A chronological, step-by-step account of the interaction, including:
     - Voice source texts (user's spoken inputs).
     - System transcriptions.
     - System responses.

3. **Inference Analysis**:
   - For each inference made:
     - Source text provided to the LLM.
     - LLM's reasoning and response.
     - Commands generated.
     - Risk assessment and any confirmation steps.

4. **Command Execution Details**:
   - For each command executed:
     - Command text.
     - Execution timestamp.
     - Output or result of the command.
     - Success or failure status.
     - Any error messages encountered.

5. **Vectorstore Search Results**:
   - Summary of vectorstore queries and results during the session.
   - Explanation of how the results influenced the system's actions.

6. **User Feedback**:
   - Any feedback from the user, including confirmations or complaints.

7. **Session Analysis**:
   - Overall assessment of the system's performance during the session.
   - Identification of any issues, errors, or anomalies.
   - Recommendations for improvements or adjustments.

Please present the report in clear, well-structured prose, using appropriate headings and bullet points where necessary.

Do not include the raw session data in the report. Summarize and interpret the data to provide meaningful insights.

The final report should be in plain text, without any JSON or code blocks.
"""
