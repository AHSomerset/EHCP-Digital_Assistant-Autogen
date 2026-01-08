"""
orchestrator.py

This module contains the core operational logic for the document generation
process. Its primary responsibility is to manage the processing of a single
document section from its initial creation through to its final validation.

The central function, `process_section`, implements the critical
"Write-Validate-Refine" loop. This iterative process ensures that each
document section is repeatedly improved until it meets all validation
criteria defined in the validation guidance. The module also manages the
concurrency semaphore to control resource utilisation.
"""



import logging
import asyncio
from typing import Dict
from autogen import ConversableAgent

from .. import config
from ..tasks import get_creation_task, get_correction_task, run_validation_async, extract_voice_snippets_with_llm, find_appendix_a_blob_name
from ..agents.writer import create_writer_team
from ..utils.utils import download_blob_as_text_async, list_blobs_async, parse_feedback_and_count_issues, download_all_sources_from_container_async

async def process_section(section_number: str, semaphore: asyncio.Semaphore, llm_config: Dict, llm_config_fast: Dict, prompt_writer: ConversableAgent):
    """Asynchronously processes a single section, including retries, under a semaphore."""
    # The semaphore ensures that we only process a fixed number of sections
    # concurrently (defined by CONCURRENT_SECTIONS in config), preventing
    # overwhelming the LLM service with too many simultaneous requests.
    async with semaphore:
        logging.info(f"Semaphore acquired for section {section_number}. Starting processing.")
       
        max_iterations = config.MAX_SECTION_ITERATIONS
        loop_logger = logging.getLogger('LoopTracer')
        
        try:
            
            # Get source content for this section, respecting any exclude list
            section_config = config.get_section_config(section_number)
            # Using .get() provides a default empty list if 'source_exclude_files'
            # is not defined for a section, preventing a KeyError.
            exclude_list = section_config.get("source_exclude_files", []) # Use .get for safety
            family_voice_examples = ""
            if section_number == "2":
                logging.info("--- Section 2 detected. Extracting family voice snippets from Appendix A. ---")
                try:
                    # 1. Get a list of all available processed documents
                    all_processed_blobs = await list_blobs_async(config.PROCESSED_BLOB_CONTAINER)
                
                    # 2. Use the finder function to intelligently locate Appendix A
                    appendix_a_blob = find_appendix_a_blob_name(all_processed_blobs)
                    
                    if appendix_a_blob:
                    # 3. If found, download its content and extract the voice
                        appendix_a_content = await download_blob_as_text_async(config.PROCESSED_BLOB_CONTAINER, appendix_a_blob)
                        family_voice_examples = await extract_voice_snippets_with_llm(
                            appendix_a_content, 
                            llm_config_fast=llm_config_fast
                        )
                    else:
                        family_voice_examples = "Could not locate Appendix A file."

                except Exception as e:
                    logging.warning(f"Could not extract family voice. Reason: {e}")
                    family_voice_examples = "An error occurred during voice extraction."

            
            logging.info(f"Fetching source documents for Section {section_number}...")
            source_content = await download_all_sources_from_container_async(
                config.PROCESSED_BLOB_CONTAINER, 
                exclude_files=exclude_list
            )

            # ==================================================================
            # === Initial Document Creation ================
            # ==================================================================
            logging.info(f"\n{'='*20} SECTION {section_number} - INITIAL CREATION {'='*20}")
            
            # The first output file is version 1
            current_output_name = f"output_s{section_number}_i1.md"

            writer_manager = create_writer_team(llm_config, llm_config_fast)
            writer_proxy_agent = writer_manager.groupchat.agent_by_name("Writer_User_Proxy")
            
            creation_task = await get_creation_task(section_number, current_output_name, source_content, family_voice_examples)
            await writer_proxy_agent.a_initiate_chat(
                recipient=writer_manager, message=creation_task, clear_history=True
            )
            loop_logger.info(f"Section {section_number}: Initial draft '{current_output_name}' created.")

            # ==================================================================
            # === Validation and Correction Loop =======================
            # ==================================================================
            # The loop starts at 1 to align with human-readable iteration numbers (e.g., "Iteration 1").
            for i in range(1, max_iterations + 1):
                logging.info(f"\n{'='*20} SECTION {section_number} - CORRECTION ITERATION {i} {'='*20}")

                # Define filename for the current iteration
                feedback_name = f"feedback_s{section_number}_i{i}.md"

                # --- VALIDATOR TEAM ---
                # Validates the output of the previous step and creates this iteration's feedback file.
                await run_validation_async(section_number, llm_config, llm_config_fast, current_output_name, feedback_name, source_content)
                loop_logger.info(f"Section {section_number}, Iteration {i}: Validator team completed.'{feedback_name}' created.")
            
                # --- ASSESSMENT ---
                feedback_content = await download_blob_as_text_async(config.OUTPUT_BLOB_CONTAINER, feedback_name)
                
                issue_counts = parse_feedback_and_count_issues(feedback_content)
                logging.info(f"Section {section_number} Issues Found: Critical={issue_counts.get('critical', 0)}, Standard={issue_counts.get('standard', 0)}")

                # --- SUCCESS CONDITION ---        
                # If a section passes on the first attempt, we force a second loop. This is a
                # deliberate robustness check to mitigate the risk of a "lucky pass" and to ensure that
                # we give an opportunity for any non-critical errors to be corrected.
                if issue_counts['critical'] == 0 and i >= 2:
                    logging.info(f"\n✅ Success! Section {section_number} passed validation on iteration {i}.")
                    loop_logger.info(f"===== Section {section_number} PASSED =====")
                    return True
                elif issue_counts['critical'] == 0 and i == 1:
                    logging.info(f"\n⚠️ Section {section_number} passed on first attempt. Forcing a second loop for robustness.")
                    loop_logger.info(f"Section {section_number}, Iteration 1: Passed, but continuing to mandatory second loop.")

                # --- PREPARE FOR NEXT ITERATION ---
                # If we've reached the max number of iterations, fail now.
                if i >= max_iterations:
                    break

                logging.info(f"--- Critical issues found. Preparing revision request for next iteration with Prompt_Writer. ---")
                
                previous_draft = await download_blob_as_text_async(config.OUTPUT_BLOB_CONTAINER, current_output_name)
                feedback_report = await download_blob_as_text_async(config.OUTPUT_BLOB_CONTAINER, feedback_name)
                
                prompt_writer_task = f"""
                Here is a document that failed validation and the feedback report. Create a clean [REVISION_REQUEST] for the Document_Writer.

                **Document to Revise:**
                {previous_draft}

                **Feedback Report:**
                {feedback_report}
                """
                # The 'Prompt_Writer' agent acts as a crucial buffer. It translates raw,
                # potentially negative feedback into a neutral, actionable set of revision
                # instructions, which makes the correction attempt by the Writer team more reliable.
                clean_request_message = await prompt_writer.a_generate_reply(messages=[{"role": "user", "content": prompt_writer_task}])
                
                revision_instructions = clean_request_message.get("content", "") if isinstance(clean_request_message, dict) else str(clean_request_message)
                
                # Define the name for the NEXT output file
                next_output_name = f"output_s{section_number}_i{i+1}.md"
                correction_task = await get_correction_task(section_number, previous_draft, revision_instructions, next_output_name, source_content, family_voice_examples)

                # --- CORRECTION WRITER TEAM ---
                await writer_proxy_agent.a_initiate_chat(
                    recipient=writer_manager, message=correction_task, clear_history=True
                )
                loop_logger.info(f"Section {section_number}, Iteration {i}: Writer team created revised draft '{next_output_name}'.")

                # The current output name is updated to point to the newly created file,
                # ensuring the next iteration of the loop validates the most recent version.
                current_output_name = next_output_name

            # If the loop completes without returning True, it means we've hit the
            # MAX_SECTION_ITERATIONS limit without passing validation.
            logging.error(f"\n🚫 FAILED: Section {section_number} could not pass after {max_iterations} iterations.")
            return False

        # This top-level exception handler catches any unexpected, critical errors
        # within a section's processing, ensuring that a single section's failure
        # doesn't crash the entire application. It logs the error and returns False.
        except Exception as e:
            logging.critical(f"FATAL ERROR in process_section '{section_number}': {e}", exc_info=True)
            loop_logger.critical(f"===== Section {section_number} FAILED with a critical exception: {e} =====")
            return False 


    