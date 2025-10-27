"""
tasks.py

This module is responsible for the dynamic generation of the main prompts
(tasks) that are assigned to the AutoGen agent teams.

It acts as a prompt factory, abstracting the complexity of assembling the
correct guidance files, source content, and runtime instructions into a
single, coherent prompt. By centralising prompt construction here, the main
orchestration logic in `orchestrator.py` remains clean and focused on workflow
management rather than prompt engineering.

The module provides functions to create tasks for:
- Initial document creation (`get_creation_task`).
- Document correction/revision (`get_correction_task`).
- Kicking off the validation process (`run_validation_async`).
"""

import logging
from .agents.validator import create_validator_team
from . import config
from .utils.utils import read_guidance_files_async


async def get_creation_task(section_number: str, output_blob_name: str, source_content: str) -> str:
    """Asynchronously generates the initial creation task prompt."""
    paths = config.get_section_config(section_number) 
    guidance_content = await read_guidance_files_async(paths["writer_guidance"])
    
    return f"""
    Your task is to generate the summary document for section '{section_number}'.
    Your full instructions and rules are provided below:
    {guidance_content}
    Here is the full content of all relevant source documents needed for this task:
    {source_content}
    Once completed, you must save your completed document by calling `upload_blob_async` with container '{config.OUTPUT_BLOB_CONTAINER}' and blob name '{output_blob_name}'.
    The Planner must now create a plan.
    """

async def get_correction_task(section_number: str, previous_draft: str, revision_request: str, output_blob_name: str, source_content: str) -> str:
    """Asynchronously generates the correction task prompt."""
    paths = config.get_section_config(section_number) 
    guidance_content = await read_guidance_files_async(paths["writer_guidance"])

    return f"""
    The document for section '{section_number}' requires revision. Your general guidance is below:
    {guidance_content}

    Here is the full content of all relevant source documents needed for this task:
    {source_content}

    **To the Document_Writer:** You are not starting from scratch. Apply the instructions in the [REVISION_REQUEST] block to the [PREVIOUS_DRAFT] provided below. Preserve all correct information and only change what is requested.

    {revision_request}

    [PREVIOUS_DRAFT]
    {previous_draft}    
    
    **To the Planner:** Ensure the revised text is saved to blob '{output_blob_name}' in container '{config.OUTPUT_BLOB_CONTAINER}' and then terminate.
    
    """

async def run_validation_async(section_number: str, llm_config: dict, llm_config_fast: dict, output_blob_name: str, feedback_blob_name: str, source_content: str):
    """
    Asynchronously runs the validator team for a section.
    """

    logging.info(f"\n--- Kicking off Validator Team for Section {section_number} ---")
    paths = config.get_section_config(section_number)
    guidance_content = await read_guidance_files_async(paths["validation_guidance"])

    validator_manager = create_validator_team(llm_config, llm_config_fast)
    validator_proxy_agent = validator_manager.groupchat.agent_by_name("Validator_User_Proxy")

    validator_task = f"""
    You task is to validate the document '{output_blob_name}'. 
    Your full instructions and rules are below:
    {guidance_content}
    
    Here is the full content of all relevant source documents you must use for validation:
    {source_content}

    **Workflow:**
    1. Call `download_blob_as_text_async` on container '{config.OUTPUT_BLOB_CONTAINER}' to read '{output_blob_name}'.
    2. The `Fact_Checker` will now perform its review using the source content provided above.
    3. The `Quality_Assessor` will create the final report.
    4. Call `upload_blob_async` on container '{config.OUTPUT_BLOB_CONTAINER}' to save the report as '{feedback_blob_name}'.
    5. `Quality_Assessor` terminates.
    Begin.
    """
    await validator_proxy_agent.a_initiate_chat(
        recipient=validator_manager, 
        message=validator_task, 
        clear_history=True
    )
    