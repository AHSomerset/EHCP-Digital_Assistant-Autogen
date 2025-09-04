import os
import sys
import logging
import time
import asyncio
import litellm
import uuid
from datetime import datetime
from dotenv import load_dotenv

import config
from config import llm_config, llm_config_fast
from orchestrator import process_section
from specialist_agents import create_prompt_writer_agent
from utils import (
    preprocess_all_pdfs_async,
    merge_output_files_async,
    clear_blob_container_async,
    parse_markdown_to_dict,
    generate_word_document,
    download_blob_as_text_async,
    upload_blob_async,
    copy_blob_async,
    list_blobs_async
)

# Load environment variables
load_dotenv()

def setup_logging(run_timestamp: str) -> tuple[str, str]:
    """Configures logging to capture all output to both the console and a file."""
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    # File Handler for the full run log
    full_log_filename = f"full_run_{run_timestamp}.log"
    full_log_path = os.path.join(config.LOGS_DIR, full_log_filename)
    file_handler = logging.FileHandler(full_log_path, mode='w', encoding='utf-8')
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # Stream Handler for console output
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    root_logger.addHandler(stream_handler)
    
    # Separate logger for the high-level trace
    loop_log_filename = f"loop_trace_{run_timestamp}.log"
    loop_log_path = os.path.join(config.LOGS_DIR, loop_log_filename)
    loop_logger = logging.getLogger('LoopTracer')
    loop_logger.setLevel(logging.INFO)
    loop_logger.handlers.clear()
    
    loop_file_handler = logging.FileHandler(loop_log_path, mode='w', encoding='utf-8')
    loop_file_handler.setFormatter(formatter)
    loop_logger.addHandler(loop_file_handler)
    loop_logger.propagate = False
    
    logging.info(f"Logging initialized. Full log: {full_log_filename}, Loop trace: {loop_log_filename}")

    return full_log_path, loop_log_path

async def _upload_log_files_async(container_name: str, full_log_path: str, loop_log_path: str):
    """Reads the final log files and uploads them to blob storage."""
    logging.info(f"--- Uploading log files to container: {container_name} ---")
    try:
        # Read the full log file and upload it
        with open(full_log_path, "rb") as data:
            full_log_blob_name = os.path.basename(full_log_path)
            await upload_blob_async(container_name, full_log_blob_name, data)
            logging.info(f"Successfully uploaded full log: {full_log_blob_name}")

        # Read the loop trace log file and upload it
        with open(loop_log_path, "rb") as data:
            loop_log_blob_name = os.path.basename(loop_log_path)
            await upload_blob_async(container_name, loop_log_blob_name, data)
            logging.info(f"Successfully uploaded loop trace: {loop_log_blob_name}")
            
    except FileNotFoundError:
        logging.error("Log files not found, could not upload to blob storage.")
    except Exception as e:
        logging.error(f"Failed to upload log files to blob storage. Reason: {e}", exc_info=True)

async def archive_run_artifacts(run_id: str, run_timestamp: str):
    """
    Copies all important files from a run into a dedicated folder
    in the run-archive container for auditing purposes.
    """
    logging.info(f"--- Archiving artifacts for Run ID: {run_id} ---")
    archive_container = config.ARCHIVE_BLOB_CONTAINER
    
    try:
        # 1. Archive Source Documents
        source_container = config.SOURCE_BLOB_CONTAINER
        source_blobs = await list_blobs_async(source_container)
        for blob_name in source_blobs:
            dest_blob_name = f"{run_id}/source_docs/{blob_name}"
            await copy_blob_async(source_container, blob_name, archive_container, dest_blob_name)

        # 2. Archive Final Outputs
        final_docs_container = config.FINAL_DOCUMENT_CONTAINER
        final_blobs = await list_blobs_async(final_docs_container)
        for blob_name in final_blobs:
            dest_blob_name = f"{run_id}/outputs/{blob_name}"
            await copy_blob_async(final_docs_container, blob_name, archive_container, dest_blob_name)

        # 2. Archive All Outputs
        output_container = config.OUTPUT_BLOB_CONTAINER
        output_blobs = await list_blobs_async(output_container)
        for blob_name in output_blobs:
            dest_blob_name = f"{run_id}/outputs/{blob_name}"
            await copy_blob_async(output_container, blob_name, archive_container, dest_blob_name)

        # 3. Archive Log Files
        log_files = [f for f in os.listdir(config.LOGS_DIR) if run_timestamp in f]
        for log_file in log_files:
            log_file_path = os.path.join(config.LOGS_DIR, log_file)
            dest_blob_name = f"{run_id}/logs/{log_file}"
            with open(log_file_path, "rb") as log_data:
                await upload_blob_async(archive_container, dest_blob_name, log_data.read())
        
        logging.info(f"--- Archiving for Run ID {run_id} complete. ---")

    except Exception as e:
        logging.error(f"A critical error occurred during artifact archiving for Run ID {run_id}. Reason: {e}", exc_info=True)

async def main_async():
    """Main async function that contains the entire application lifecycle."""
    start_time = time.monotonic()
    run_timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    short_uuid = str(uuid.uuid4())[:4]
    run_id = f"{run_timestamp}_{short_uuid}"

    setup_logging(run_timestamp)

    litellm.caching = False

    litellm.max_retries = 5
    loop_logger = logging.getLogger('LoopTracer')
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
                    final_markdown_content = await download_blob_as_text_async(config.OUTPUT_BLOB_CONTAINER, config.FINAL_DOCUMENT_FILENAME)
                    
                    logging.info("Parsing final markdown to generate Word document.")
                    final_data_context = parse_markdown_to_dict(final_markdown_content)
                    
                    template_path = os.path.join(config.BASE_DIR, "template.docx")
                    temp_output_doc_path = os.path.join(config.OUTPUTS_DIR, "draft_EHCP.docx")
                    generate_word_document(final_data_context, template_path, temp_output_doc_path)

                    output_blob_name = "draft_EHCP.docx"
                    logging.info(f"Uploading final Word document to blob: {output_blob_name}")
                    with open(temp_output_doc_path, "rb") as docx_file:
                        await upload_blob_async(config.FINAL_DOCUMENT_CONTAINER, output_blob_name, docx_file.read())
                    
                    logging.info(f"✅ Final Word document successfully generated and uploaded.")
                
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

    finally:
        print("\n--- Archiving run artifacts. ---")
        await archive_run_artifacts(run_id, run_timestamp)

        print("\n--- Running final cleanup process. ---")
        await clear_blob_container_async(config.PROCESSED_BLOB_CONTAINER)
        await clear_blob_container_async(config.OUTPUT_BLOB_CONTAINER)
        
        print("\n--- Clearing source documents for next run. ---")
        #await clear_blob_container_async(config.SOURCE_BLOB_CONTAINER)

if __name__ == "__main__":
    try:
        # Create local directories needed for logs and temp files
        os.makedirs(config.LOGS_DIR, exist_ok=True)
        os.makedirs(config.OUTPUTS_DIR, exist_ok=True)
        
        asyncio.run(main_async())

    except KeyboardInterrupt:
        print("\nProcess interrupted by user. Shutting down.")
    except Exception as e:
        logging.critical(f"A fatal, unhandled error occurred in the main entry point: {e}", exc_info=True)