"""
tasks.py

This module is responsible for the dynamic generation of the main prompts
(tasks) that are assigned to the AutoGen agent teams.

It acts as a prompt factory, abstracting the complexity of assembling the
correct guidance files, source content, and runtime instructions into a
single, coherent prompt. By centralising prompt construction here, the main
orchestration logic in `orchestrator.py` remains clean and focused on workflow
management rather than prompt engineering.

The module also contains the pre-processing logic needed to extract
representative "voice of the family" snippets from Appendix A using a
focused LLM call. These snippets are then incorporated into the creation
and correction tasks to help the writer capture the unique voice of the
child and family.

The module provides functions to create tasks for:
- Initial document creation (`get_creation_task`).
- Document correction/revision (`get_correction_task`).
- Kicking off the validation process (`run_validation_async`).
"""

import logging
import json
import litellm
from typing import List, Optional
from .agents.validator import create_validator_team
from . import config
from .utils.utils import read_guidance_files_async, _get_sanitised_base_name

# ==============================================================================
# LLM-Driven Text Analysis for Family Voice Extraction
# ==============================================================================

def find_appendix_a_blob_name(blob_names: List[str]) -> Optional[str]:
    """
    Finds the blob name for Appendix A from a list of blob names by sanitising each name and matching its logical core.
    """
    logging.info("Attempting to intelligently locate Appendix A file...")
    
    # The logical name we are looking for, after sanitisation.
    target_logical_name = "appendix a"

    for blob_name in blob_names:
        # Sanitise the current blob name to get its core logical name
        sanitised_name = _get_sanitised_base_name(blob_name)

        # Check if the sanitised name matches the target logical name
        if sanitised_name == target_logical_name:
            logging.info(f"Found Appendix A file: '{blob_name}'")
            return blob_name

    logging.warning(f"Could not find a file ending with '{target_logical_name}'.")
    return None

async def extract_voice_snippets_with_llm(appendix_a_text: str, llm_config_fast: dict, num_snippets: int = 10) -> str:
    """
    Uses a focused LLM call to analyse Appendix A and extract the most
    representative snippets that capture the voice of the child and family.
    """
    if not appendix_a_text or len(appendix_a_text.strip()) < 50:
        return "No meaningful Appendix A text provided to analyze."

    logging.info("--- Using LLM to extract representative family voice snippets... ---")

    # System prompt for our "Voice Analyst"
    system_prompt = """You are an expert literary analyst. Your task is to read the following text, which contains the views of a child/young person and their parent or carer, and extract a few extracts that best represent their unique "voice".

    Focus on extracts that convey emotion or use personal descriptive language:
    - The families love and affection for the child.
    - Their primary hopes for themselves/their child.
    - Their biggest fears or worries.
    - The specific, personal language they use to describe the child's strengths or challenges.

    Do not summarise or rephrase. 
    
    Your entire output MUST be a single, valid JSON object. The object should have one key, "snippets", which is a JSON list of strings. Each string in the list should be a single, directly quoted extract from the source text.
    """
    
    user_prompt = f"Here is the text which captures the views of the child and family. Please extract the {num_snippets} best examples to capture their voice and return them as a JSON object:\n\n---\n{appendix_a_text}"

    try:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        # Get the deployment name from your config
        deployment_name = llm_config_fast["config_list"][0]["model"]
        
        # Prepend "azure/" to the model name for LiteLLM
        litellm_model_name = f"azure/{deployment_name}"
        
        response = await litellm.acompletion(
            model=litellm_model_name,
            messages=messages,
            response_format={"type": "json_object"},
            api_key=llm_config_fast["config_list"][0]["api_key"],
            base_url=llm_config_fast["config_list"][0]["base_url"],
            api_version=llm_config_fast["config_list"][0]["api_version"]
        )
        
        extracted_json_str = response.choices[0].message.content.strip()
        
        # Safely parse the JSON string
        data = json.loads(extracted_json_str)
        snippets = data.get("snippets", [])
        
        if not snippets:
            return "LLM analysis did not find any representative snippets."

        # Format the final output string from the clean, parsed data
        formatted_snippets = ""
        for i, snippet in enumerate(snippets):
            if snippet:
                formatted_snippets += f"--- EXAMPLE OF CHILD'S/FAMILY'S VOICE {i+1} ---\n\"{snippet}\"\n"
        
        return formatted_snippets.strip()

    except json.JSONDecodeError:
        logging.error("Failed to parse JSON response from the voice analyst LLM.")
        return "Error: LLM returned invalid JSON for voice analysis."
    except Exception as e:
        logging.error(f"Failed to extract voice snippets with LLM. Reason: {e}", exc_info=True)
        return "Error: Could not analyse family's voice."


# ==============================================================================
# Task Prompt Generation Functions
# ==============================================================================

async def get_creation_task(section_number: str, output_blob_name: str, source_content: str, family_voice_examples: str) -> str:
    """Asynchronously generates the initial creation task prompt, including all guidance,
    source content, and "voice of the family" examples."""
    paths = config.get_section_config(section_number) 
    guidance_content = await read_guidance_files_async(paths["writer_guidance"])

    # Conditionally build the voice prompt section only if examples were provided.
    voice_prompt_section = ""
    if family_voice_examples:
        voice_prompt_section = f"""
**FAMILY VOICE EXAMPLES FOR THIS CASE:**
The following snippets are provided as a reference for the "CAPTURING THE FAMILY VOICE" rule in your style guide.

{family_voice_examples}
---
"""

    return f"""
    Your task is to generate the summary document for section '{section_number}'.

    {voice_prompt_section}

    Your full instructions and rules are provided below:
    {guidance_content}

    Here is the full content of all relevant source documents needed for this task:
    {source_content}

    Once completed, you must save your completed document by calling `upload_blob_async` with container '{config.OUTPUT_BLOB_CONTAINER}' and blob name '{output_blob_name}'.
    The Planner must now create a plan.
    """

async def get_correction_task(section_number: str, previous_draft: str, revision_request: str, output_blob_name: str, source_content: str, family_voice_examples: str) -> str:
    """Asynchronously generates the correction task prompt."""
    paths = config.get_section_config(section_number) 
    guidance_content = await read_guidance_files_async(paths["writer_guidance"])

    # Conditionally build the voice prompt section only if examples were provided.
    voice_prompt_section = ""
    if family_voice_examples:
        voice_prompt_section = f"""
**FAMILY VOICE EXAMPLES FOR THIS CASE:**
The following snippets are provided as a reference for the "CAPTURING THE FAMILY VOICE" rule in your style guide.

{family_voice_examples}
---
"""

    return f"""
    The document for section '{section_number}' requires revision. 
    
    {voice_prompt_section}
    
    Your general guidance is below:
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
    