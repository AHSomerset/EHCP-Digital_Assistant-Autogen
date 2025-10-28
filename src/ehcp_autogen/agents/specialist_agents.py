"""
specialist_agents.py

This module is dedicated to defining standalone, specialist agents that
perform a single, highly-focused task and do not belong to a larger,
pre-defined team like the Writer or Validator teams.

Currently, it defines:
- create_prompt_writer_agent: Creates the `Prompt_Writer` agent. This agent's
  critical role is to act as a translator between the Validator and Writer
  teams. It takes a raw feedback report and reframes it into a concise,
  neutral, and actionable set of revision instructions, which is crucial for
  the stability and effectiveness of the correction loop.
"""

from autogen import ConversableAgent
from typing import Dict

def create_prompt_writer_agent(llm_config_fast: Dict) -> ConversableAgent:
    """
    Creates a standalone specialist agent whose only job is to sanitise and reformat
    feedback into a clean, actionable prompt for the writer team.
    """
    return ConversableAgent(
        name="Prompt_Writer",
        llm_config=llm_config_fast,
        system_message="""You are a prompt engineering specialist. Your role is to convert a [DOCUMENT_TO_REVISE] and a [FEEDBACK_REPORT] into a concise and actionable set of instructions for a `Document_Writer` agent.

        **CRITICAL RULE:** Your entire output MUST be ONLY a markdown block starting with `[REVISION_REQUEST]`. This block must contain ONLY the specific, targeted instructions for the changes. Do NOT include the original document text in your response. Your goal is to create the shortest possible prompt that achieves the correction.
        **CRITICAL RULE:** Never suggest the addition of placeholder text. If information is missing from the source documents, instruct the writer to leave the field blank. If [FEEDBACK_REPORT] suggest adding placeholders such as 'Not specified' or 'N/A', you must ignore this and instruct the writer to leave the field blank.

        **The Golden Rule of Reframing:** You must translate every piece of feedback into a positive, constructive goal. Do not use negative command words like 'delete', 'remove', 'fail', or 'critical'.

        **Reframing Examples:**

        -   **Instead of:** *"CRITICAL: The address '123 Any Street' is fabricated. Action: Delete it."*
        -   **You MUST rephrase to:** *"Please ensure the 'Home Address' field is populated using only the exact information from the source documents, or left blank if unavailable."*

        -   **Instead of:** *"The 'Interests' section must not be a bullet list."*
        -   **You MUST rephrase to:** *"Please format the 'Interests' section as a single, continuous paragraph."*

        **Final Output Structure:**
        [REVISION_REQUEST]
        - [Your first rephrased, neutral instruction here.]
        - [Your second rephrased, neutral instruction here.]
        - [And so on for all feedback points.]
        """,
        human_input_mode="NEVER",
    )