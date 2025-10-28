"""
validator.py

This module defines the multi-agent "Validator Team" responsible for quality
assurance. It constructs and configures the agents and the group chat manager
that form this team.

The Validator Team's purpose is to meticulously review a generated document
draft against a set of predefined rules and the original source materials.
It is designed to identify factual inaccuracies, structural errors,
hallucinations, and rule violations. 

The Validator team also reveiws inline source citations to ensure that all
facts are correctly attributed to the appropriate source document.

The final output of this team is a
structured markdown feedback report that includes a summary of critical and
standard issues found.

The team consists of:
- Quality_Assessor: The lead agent that consolidates feedback and creates the final report.
- Fact_Checker: A specialist agent focused solely on verifying content against source documents, 
including verifying citations.
- Validator_User_Proxy: The tool-executing agent for downloading drafts and uploading feedback.
"""


import autogen
from autogen import ConversableAgent, UserProxyAgent, GroupChat, GroupChatManager
from typing import Dict

from ..utils.utils import (
    is_terminate_message,
    download_blob_as_text_async,
    upload_blob_async,
)

# This team is responsible for validating the document against criteria and generating a feedback report.
def create_validator_team(llm_config: Dict, llm_config_fast: Dict) -> GroupChatManager:
    """
    Creates and configures the validator multi-agent team.
    """
    validator_user_proxy = UserProxyAgent(
        name="Validator_User_Proxy",
        is_termination_msg=is_terminate_message,
        human_input_mode="NEVER",
        max_consecutive_auto_reply=20,
        code_execution_config={"use_docker": False},
        llm_config=llm_config_fast,
        system_message="""You are the user proxy and tool executor for the validation team.
        Your job is to execute tool calls as directed by other agents.
        You will read files when asked and, crucially, you will save the final consolidated feedback report using the `upload_blob` tool when the `Quality_Assessor` provides it.
        You will listen for the `Quality_Assessor` to say 'TERMINATE', at which point the task will end."""
    )

    quality_assessor = ConversableAgent(
        name="Quality_Assessor",
        llm_config=llm_config,
        system_message="""You are a Quality Assurance expert. Your role is to lead the validation process and produce the final report. You have a very strict, multi-step role. Follow it precisely.

         **Issue Severities:**
        You will classify issues into one of two categories:
        1.  **Critical:** An issue that makes the document unusable. This includes factual errors, hallucinations, or a direct violation of a core rule (e.g., "The child's history contains hallucinations").
        2.  **Standard:** All other issues, including stylistic problems, minor formatting errors, or suggestions for improvement that are not critical failures.

        **Your Workflow:**

        1.  **First Turn (Generate Report):** You will be called upon AFTER the `Fact_Checker` has provided its findings. In this turn, your **ENTIRE response MUST be the complete and final feedback report** in the specified markdown format. The report must consolidate your own assessment with the findings from the `Fact_Checker` and include the `[FEEDBACK_SUMMARY]` block with the correct counts.

        2.  **Second Turn (Terminate):** After the user proxy has saved your report, you will be called upon one final time. In this turn, your **ENTIRE response MUST be the single word `TERMINATE`**.
        
        You MUST treat the `Fact_Checker`'s report as the absolute truth for all content issues. You are a report compiler, not a second-level fact-checker. You do not need to consult the source documents.
        """

    )

    fact_checker = ConversableAgent(
        name="Fact_Checker",
        llm_config=llm_config,
        system_message="""You are a meticulous Fact Checker and Source Verifier. Your role is to validate every statement in a document against the original source materials.

        The document you are reviewing contains citation tags like `[SOURCE: filename]` after each statement.

        Your SOLE FOCUS is content verification. Your specific rules for what constitutes a CRITICAL or STANDARD factual error are detailed in the validation guidance provided in the main user prompt. 
        **You are responsible for enforcing ALL content-related rules, including:**
        -   Basic fact-checking (names, dates, etc.).
        -   Anti-hallucination rules.
        -   The "Golden Thread" rules.
        -   The "Provision Specificity" rules.
        -   The "SMART Outcomes" rules.
        -   The "Needs Categorisation" rules.

        **Workflow:**
        1.  Wait until the source document content is available in the chat history.
        2.  Analyse the draft document against the source text, strictly applying all content-related rules from the validation guidance.
        3.  Verify all citations. Check if the fact actually exists in the specific `filename` mentioned in its citation tag.
        3.  Report your findings as a detailed, clear list of all discrepancies. If all facts and their citations are correct, your entire response must be the single phrase "ALL FACTS AND CITATIONS VERIFIED". 
        Do not comment on formatting or structure..

        You must not comment on the final report's formatting. You do not call any tools."""
    )


    agent_tools = [
        download_blob_as_text_async,
        upload_blob_async
    ]

    for func in agent_tools:
        description = f"{func.__doc__} The `container_name` argument is required."
        
        autogen.agentchat.register_function(
            func,
            caller=validator_user_proxy,
            executor=validator_user_proxy,
            name=func.__name__,
            description=description
        )

    groupchat = GroupChat(
        agents=[validator_user_proxy, quality_assessor, fact_checker],
        messages=[],
        max_round=40
    )
    
    manager = GroupChatManager(
        groupchat=groupchat,
        llm_config=llm_config_fast,
        system_message="""You are the manager of the validation team. Your role is to coordinate the agents to produce a single, consolidated feedback report.
        Follow the workflow:
        1. `Fact_Checker` (factual review).
        2. `Quality_Assessor` (consolidate and create the single, final report).
        3. `Validator_User_Proxy` (save report).
        4. `Quality_Assessor` (final termination signal).
        Ensure the conversation flows in this exact order."""
    )
    
    return manager
