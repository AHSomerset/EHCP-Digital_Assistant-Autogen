import config
import logging
import asyncio
from typing import Dict
from autogen import ConversableAgent
from tasks import get_creation_task, get_correction_task, run_validation_async
from writer import create_writer_team
from utils import download_blob_as_text_async, parse_feedback_and_count_issues, download_all_sources_from_container_async

async def process_section(section_number: str, semaphore: asyncio.Semaphore, llm_config: Dict, llm_config_fast: Dict, prompt_writer: ConversableAgent):
    """Asynchronously processes a single section, including retries, under a semaphore."""
    async with semaphore:
        logging.info(f"Semaphore acquired for section {section_number}. Starting processing.")
       
        max_iterations = config.MAX_SECTION_ITERATIONS
        loop_logger = logging.getLogger('LoopTracer')
        
        try:
            
            # Get source content for this section, respecting any exclude list
            section_config = config.get_section_config(section_number)
            exclude_list = section_config.get("source_exclude_files", []) # Use .get for safety
            
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
            
            creation_task = await get_creation_task(section_number, current_output_name, source_content)
            await writer_proxy_agent.a_initiate_chat(
                recipient=writer_manager, message=creation_task, clear_history=True
            )
            loop_logger.info(f"Section {section_number}: Initial draft '{current_output_name}' created.")

            # ==================================================================
            # === Validation and Correction Loop =======================
            # ==================================================================
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

                clean_request_message = await prompt_writer.a_generate_reply(messages=[{"role": "user", "content": prompt_writer_task}])
                
                revision_instructions = clean_request_message.get("content", "") if isinstance(clean_request_message, dict) else str(clean_request_message)
                
                # Define the name for the NEXT output file
                next_output_name = f"output_s{section_number}_i{i+1}.md"
                correction_task = await get_correction_task(section_number, previous_draft, revision_instructions, next_output_name, source_content)

                # --- CORRECTION WRITER TEAM ---
                await writer_proxy_agent.a_initiate_chat(
                    recipient=writer_manager, message=correction_task, clear_history=True
                )
                loop_logger.info(f"Section {section_number}, Iteration {i}: Writer team created revised draft '{next_output_name}'.")

                # Update the current_output_name for the next loop
                current_output_name = next_output_name

            # If the loop finishes, it means we hit max_iterations without passing.
            logging.error(f"\n🚫 FAILED: Section {section_number} could not pass after {max_iterations} iterations.")
            return False

        except Exception as e:
            logging.critical(f"FATAL ERROR in process_section '{section_number}': {e}", exc_info=True)
            loop_logger.critical(f"===== Section {section_number} FAILED with a critical exception: {e} =====")
            return False 


    