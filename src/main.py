"""
main.py

This module serves as the main entry point for the EHCP document
generation pipeline. It orchestrates the entire application lifecycle from
initial setup to final cleanup.

Key Responsibilities:
- Initialises a unique run ID for traceability.
- Executes the high-level, asynchronous workflow:
    1. Pre-processes source PDFs from Azure Blob Storage.
    2. Kicks off the concurrent processing of all document sections using the `process_section` orchestrator.
    3. Manages the final merge of validated sections.
    4. **Generates Dual Final Outputs:**
        - A "Fact Mapper" document (`fact_mapper.docx`) that preserves all
          inline source citations for auditing.
        - A "clean" version of the content, which is used to generate the
          final `.docx` document.
- Implements a guaranteed `finally` block to ensure that all run artifacts
  (logs, outputs, source files) are archived and that temporary containers
  are cleaned up, regardless of whether the run succeeded or failed.
"""

import os
import sys
import logging
import time
import asyncio
import litellm
import uuid
from datetime import datetime
from dotenv import load_dotenv

# The 'src' directory is the root for the execution.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from .ehcp_autogen import config 
from .ehcp_autogen.logging_config import setup_logging
from .ehcp_autogen.config import llm_config, llm_config_fast
from .ehcp_autogen.orchestration.orchestrator import process_section
from .ehcp_autogen.agents.specialist_agents import create_prompt_writer_agent
from .ehcp_autogen.utils.utils import (
    preprocess_all_pdfs_async,
    merge_output_files_async,
    clear_blob_container_async,
    parse_markdown_to_dict,
    generate_word_document,
    download_blob_as_text_async,
    upload_blob_async,
    archive_run_artifacts,
    create_fact_mapper_version,
    create_clean_version
)


# Load environment variables
load_dotenv()

async def main_async():
    """Main async function that contains the entire application lifecycle."""
    start_time = time.monotonic()
    run_timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    short_uuid = str(uuid.uuid4())[:4]
    # A unique run_id is generated for each execution to ensure all artifacts
    # (logs, outputs, archives) from a single run can be traced and audited.
    run_id = f"{run_timestamp}_{short_uuid}"

    setup_logging(run_timestamp)

    # Caching is disabled to ensure that each run is deterministic and uses the
    # latest instructions, which is critical during development and for auditability.
    litellm.caching = False

    litellm.max_retries = 5
    loop_logger = logging.getLogger('LoopTracer')
    # This flag tracks the overall success of the run, determining whether to
    # upload a 'fail.txt' marker and influencing final log messages.
    process_completed_successfully = False

    try:
        loop_logger.info("Main process started.")
        
        # --- PRE-PROCESSING ---
        is_preprocessing_successful = await preprocess_all_pdfs_async()
        if not is_preprocessing_successful:
            logging.critical("Pre-processing failed. Aborting main process.")
            return # This will still trigger the finally block for cleanup

        loop_logger.info("Pre-processing complete. Starting agent workflow.")
        
        # --- CONCURRENT SECTIONAL PROCESSING ---
        prompt_writer = create_prompt_writer_agent(llm_config_fast)
        semaphore = asyncio.Semaphore(config.CONCURRENT_SECTIONS)
        
        logging.info(f"Starting concurrent processing for {config.TOTAL_SECTIONS} sections...")
        
        sections_to_process = [str(i) for i in range(1, config.TOTAL_SECTIONS + 1)]
        processing_tasks = [
            process_section(sec_id, semaphore, llm_config, llm_config_fast, prompt_writer)
            for sec_id in sections_to_process
        ]
        
        section_results = await asyncio.gather(*processing_tasks)
        process_completed_successfully = all(section_results)

        if not process_completed_successfully:
            logging.error("Process stopped before final merge due to failures in sectional generation.")
        else:
            # --- FINAL MERGE AND WORD DOCUMENT GENERATION ---
            logging.info(f"\n{'#'*25} CREATING FINAL DOCUMENT {'#'*25}")
            merge_success = await merge_output_files_async()

            if not merge_success:
                logging.error("Failed to merge sectional documents.")
                process_completed_successfully = False
            else:
                # This sub-try block handles errors in Word generation without losing the successful merge status
                try:
                    logging.info("Downloading final markdown from blob...")
                    cited_markdown_content = await download_blob_as_text_async(config.OUTPUT_BLOB_CONTAINER, config.FINAL_DOCUMENT_FILENAME)

                    if not cited_markdown_content:
                        raise ValueError("Downloaded final markdown content is empty.")

                    # Create and upload Fact Mapper document
                    logging.info("Cleaning citation tags for the final Fact Mapper...")
                    # This function finds '.pdf.txt' that is immediately followed by a ']' and removes it.
                    fact_mapper_content = create_fact_mapper_version(cited_markdown_content)

                    logging.info("Parsing fact_mapper to generate Word document.")
                    fact_mapper_context = parse_markdown_to_dict(fact_mapper_content)
                    
                    template_path = os.path.join(config.TEMPLATES_DIR, "template.docx")
                    temp_fact_mapper_doc_path = os.path.join(config.OUTPUTS_DIR, "fact_mapper.docx")
                    generate_word_document(fact_mapper_context, template_path, temp_fact_mapper_doc_path)

                    fact_mapper_blob_name = "fact_mapper.docx"
                    logging.info(f"Uploading fact mapper document to blob: {fact_mapper_blob_name}")
                    with open(temp_fact_mapper_doc_path, "rb") as docx_file:
                        await upload_blob_async(config.FINAL_DOCUMENT_CONTAINER, fact_mapper_blob_name, docx_file.read())

                    # Create the clean version for the final Word document
                    logging.info("Creating clean version of markdown by removing citation tags...")
                    # Use regex function to remove all [SOURCE: ...] tags
                    final_markdown_content = create_clean_version(cited_markdown_content)
                    
                    logging.info("Parsing final markdown to generate Word document.")
                    final_data_context = parse_markdown_to_dict(final_markdown_content)
                    
                    template_path = os.path.join(config.TEMPLATES_DIR, "template.docx")
                    temp_output_doc_path = os.path.join(config.OUTPUTS_DIR, "draft_EHCP.docx")
                    generate_word_document(final_data_context, template_path, temp_output_doc_path)

                    output_blob_name = "draft_EHCP.docx"
                    logging.info(f"Uploading final Word document to blob: {output_blob_name}")
                    with open(temp_output_doc_path, "rb") as docx_file:
                        await upload_blob_async(config.FINAL_DOCUMENT_CONTAINER, output_blob_name, docx_file.read())
                    
                    logging.info(f"✅ Final documents (Fact Mapper and Word Doc) successfully generated and uploaded.")
                
                except Exception as e:
                    logging.error(f"Failed during Word document generation phase. Reason: {e}", exc_info=True)
                    process_completed_successfully = False
        
        # --- FINAL SUMMARY LOGGING ---
        logging.info(f"\n{'#'*25} PROCESS COMPLETE {'#'*25}")
        end_time = time.monotonic()
        total_duration_minutes = (end_time - start_time) / 60
        
        loop_logger.info("=" * 40)
        loop_logger.info("            RUN SUMMARY")
        loop_logger.info("=" * 40)
        if process_completed_successfully:
            loop_logger.info("Overall Status: SUCCESS")
        else:
            loop_logger.info("Overall Status: FAILED / STOPPED EARLY")
        loop_logger.info(f"Total Execution Time: {total_duration_minutes:.2f} minutes")
        loop_logger.info("=" * 40)

    # The 'finally' block is critical. It guarantees that cleanup and archiving
    # operations run every time, even if a critical, unhandled exception occurs 
    # during the main process. This prevents leaving the system in a dirty state
    #  for the next run.
    finally:
        if not process_completed_successfully:
            try:
                logging.warning("--- Process failed. Uploading 'fail.txt' to the output container. ---")
                # The 'fail.txt' file acts as a simple, explicit marker in blob storage,
                # allowing external systems (Flow) to easily determine if the process 
                # completed successfully without parsing logs.
                await upload_blob_async(
                    container_name=config.FINAL_DOCUMENT_CONTAINER,
                    blob_name="fail.txt",
                    data=b""  # Upload empty bytes to create an empty file
                )
                logging.info("Successfully uploaded 'fail.txt'.")
            except Exception as e:
                # Log an error if the fail marker itself fails, but don't crash.
                logging.error(f"Failed to upload 'fail.txt' failure marker. Reason: {e}", exc_info=True)
                
        print("\n--- Archiving run artifacts. ---")
        await archive_run_artifacts(run_id, run_timestamp)

        print("\n--- Running final cleanup process. ---")
        await clear_blob_container_async(config.PROCESSED_BLOB_CONTAINER)
        await clear_blob_container_async(config.OUTPUT_BLOB_CONTAINER)
        
        print("\n--- Clearing source documents for next run. ---")
        #await clear_blob_container_async(config.SOURCE_BLOB_CONTAINER)

if __name__ == "__main__":
    try:
        # 'exist_ok=True' prevents an error from being thrown if the directories
        # already exist, making the script safe to run multiple times.
        os.makedirs(config.LOGS_DIR, exist_ok=True)
        os.makedirs(config.OUTPUTS_DIR, exist_ok=True)
        
        asyncio.run(main_async())

    except KeyboardInterrupt:
        print("\nProcess interrupted by user. Shutting down.")
    except Exception as e:
        logging.critical(f"A fatal, unhandled error occurred in the main entry point: {e}", exc_info=True)