"""
utils.py

This module provides a collection of reusable helper functions that support
the main application logic. It abstracts away common, low-level operations
into well-defined, asynchronous functions.

The utilities are categorised into several key areas:
1.  **Azure Blob Storage Utilities:** A suite of async functions for all blob
    operations (list, upload, download, clear, copy), managed through a 
    singleton BlobServiceClient.
2.  **Data Pipeline Utilities:** High-level functions that orchestrate complex
    data workflows, such as the PDF pre-processing pipeline
    (`preprocess_all_pdfs_async`) and the final merging of sectional outputs
    (`merge_output_files_async`).
3.  **Parsing and Text Utilities:** Functions for cleaning text, sanitising
    strings for use as keys, and parsing structured data from markdown
    and feedback files.
4.  **Document Generation Utilities:** Functions for creating the final
    output document (e.g., generating a Word document from a template).
5.  **AutoGen Agent Helper Functions:** Functions required by the AutoGen
    framework, such as the custom termination message checker.
"""

import os
import re
import pypdf
import logging
from typing import List, Dict
import src.ehcp_autogen.config as config
import asyncio
import io
from azure.storage.blob.aio import BlobServiceClient
from docxtpl import DocxTemplate
from datetime import datetime, timedelta
from azure.storage.blob import generate_blob_sas, BlobSasPermissions
from azure.core.credentials import AzureKeyCredential
from azure.ai.documentintelligence.aio import DocumentIntelligenceClient

# ==============================================================================
# 1. AZURE BLOB STORAGE UTILITIES
# ==============================================================================
# Low-level functions for interacting with Azure Blob Storage.
# Includes a singleton client to manage the connection efficiently.

_blob_service_client = None

async def _get_blob_service_client():
    # This singleton pattern ensures that we create only one BlobServiceClient
    # instance for the entire application lifecycle. This is more efficient than
    # creating a new client for every blob operation, as it reuses the connection pool.
    """
    Gets the singleton async instance of the BlobServiceClient.
    If it doesn't exist, it creates one.
    """
    global _blob_service_client
    if _blob_service_client is None:
        logging.info("Initialising singleton async BlobServiceClient...")
        if not all([config.AZURE_STORAGE_ACCOUNT_URL, config.AZURE_STORAGE_ACCOUNT_KEY]):
            raise ValueError("Storage account URL or Key is not set in the environment.")
        
        # Create an async client.
        client = BlobServiceClient(
            account_url=config.AZURE_STORAGE_ACCOUNT_URL,
            credential=config.AZURE_STORAGE_ACCOUNT_KEY
        )
        _blob_service_client = client
        logging.info("Async BlobServiceClient initialised successfully.")
    return _blob_service_client

async def get_blob_container_client(container_name: str):
    """Helper to connect to a specific Azure Blob Storage container using the async singleton client."""
    blob_service_client = await _get_blob_service_client()
    return blob_service_client.get_container_client(container_name)

async def get_blob_sas_url_async(container_name: str, blob_name: str) -> str:
    """
    Generates a SAS URL to provide temporary, secure, read-only access to a blob.
    """
    # This is a synchronous operation, so we run it in an executor to be safe
    loop = asyncio.get_running_loop()
    def _generate_sas_sync():
        account_name = config.AZURE_STORAGE_ACCOUNT_NAME
        account_key = config.AZURE_STORAGE_ACCOUNT_KEY
        
        # The SAS token will be valid for 1 hour
        expiry_time = datetime.utcnow() + timedelta(hours=1)
        
        sas_token = generate_blob_sas(
            account_name=account_name,
            container_name=container_name,
            blob_name=blob_name,
            account_key=account_key,
            permission=BlobSasPermissions(read=True),
            expiry=expiry_time,
        )
        
        # Construct the full URL
        return f"https://{account_name}.blob.core.windows.net/{container_name}/{blob_name}?{sas_token}"
        
    return await loop.run_in_executor(None, _generate_sas_sync)

async def list_blobs_async(container_name: str) -> List[str]:
    """Asynchronously lists the names of all blobs in a container."""
    logging.info(f"Listing blobs in container: {container_name}")
    try:
        container_client = await get_blob_container_client(container_name)
        return [blob.name async for blob in container_client.list_blobs()]
    except Exception as e:
        logging.error(f"Failed to list blobs in container '{container_name}'. Reason: {e}")
        return []

async def upload_blob_async(container_name: str, blob_name: str, data: str | bytes, overwrite: bool = True):
    """Asynchronously uploads string or byte data to a blob."""
    logging.info(f"Uploading to blob: {container_name}/{blob_name}")
    try:
        container_client = await get_blob_container_client(container_name)
        await container_client.upload_blob(name=blob_name, data=data, overwrite=overwrite)
    except Exception as e:
        logging.error(f"Failed to upload blob '{blob_name}'. Reason: {e}")
        raise

async def download_blob_as_text_async(container_name: str, blob_name: str) -> str:
    """Asynchronously downloads a blob and returns its content as a UTF-8 string."""
    logging.info(f"Downloading text blob: {container_name}/{blob_name}")
    try:
        container_client = await get_blob_container_client(container_name)
        blob_client = container_client.get_blob_client(blob_name)
        downloader = await blob_client.download_blob()
        return (await downloader.readall()).decode("utf-8")
    except Exception as e:
        logging.error(f"Failed to download blob '{blob_name}' as text. Reason: {e}")
        return ""

async def download_blob_as_bytes_async(container_name: str, blob_name: str) -> bytes:
    """Asynchronously downloads a blob and returns its content as raw bytes."""
    logging.info(f"Downloading bytes blob: {container_name}/{blob_name}")
    try:
        container_client = await get_blob_container_client(container_name)
        blob_client = container_client.get_blob_client(blob_name)
        downloader = await blob_client.download_blob()
        return await downloader.readall()
    except Exception as e:
        logging.error(f"Failed to download blob '{blob_name}' as bytes. Reason: {e}")
        return b""

async def download_all_sources_from_container_async(container_name: str, exclude_files: List[str] = None) -> str:
    """
    Asynchronously lists all blobs in a container, downloads
    their text content, and returns it as a single concatenated string.
    This is the primary tool for providing source context to agents. Optionally excludes specified files.
    """
    logging.info(f"--- Concurrently downloading all source documents from container: {container_name} ---")

    if exclude_files is None:
        exclude_files = []

    # A case-insensitive comparison is used for the exclusion list to make the
    # configuration more robust against user input variations (e.g., 'appendix a.pdf').
    exclude_files_lower = [f.lower().replace('.pdf', '') for f in exclude_files]

    logging.info(f"--- Downloading source documents from container: {container_name} ---")
    if exclude_files_lower:
        logging.info(f"--- Excluding files: {exclude_files} ---")
    
    # Get the list of all blob names to be downloaded.
    blob_names = await list_blobs_async(container_name)
    
    if not blob_names:
        logging.warning(f"No blobs found in container '{container_name}'.")
        return "ERROR: No source documents found in the specified container."
    
    full_content = ""
    # The source files are downloaded and concatenated serially (one after another)
    # rather than concurrently. This is a deliberate design choice to guarantee
    # that the order of documents in the final concatenated string is predictable.
    for blob_name in blob_names:
        filename = os.path.basename(blob_name)
        filename_lower = filename.lower()
        filename_base = filename_lower.removesuffix('.txt')
        # Check whether filename appears in exclude list.
        if any(exclusion in filename_base for exclusion in exclude_files_lower):
            logging.info(f"Skipping excluded source file: {filename}")
            continue

        logging.info(f"Reading source file: {blob_name}")
        full_content += f"--- START OF FILE {filename} ---\n\n"
        full_content += await download_blob_as_text_async(container_name, blob_name)
        full_content += f"\n\n--- END OF FILE {filename} ---\n\n"
        
    logging.info(f"--- Finished downloading {len(blob_names)} source documents. Formatting content. ---")

    return full_content

async def clear_blob_container_async(container_name: str):
    """
    Asynchronously and concurrently deletes all blobs within a specified container.
    """
    logging.info(f"--- Starting cleanup of blob container: {container_name} ---")
    try:
        container_client = await get_blob_container_client(container_name)
        blob_names = [blob.name async for blob in container_client.list_blobs()]

        if not blob_names:
            logging.info(f"Container '{container_name}' is already empty. No cleanup needed.")
            return

        logging.info(f"Found {len(blob_names)} blobs to delete in container '{container_name}'.")
        
        # Create a list of deletion tasks (coroutines)
        delete_tasks = [container_client.delete_blob(blob_name) for blob_name in blob_names]
        
        # Execute all deletion tasks concurrently
        await asyncio.gather(*delete_tasks)
            
        logging.info(f"--- Cleanup of container '{container_name}' complete. ---")
    except Exception as e:
        logging.error(f"Failed to clear container '{container_name}'. Reason: {e}", exc_info=True)

async def copy_blob_async(
    source_container_name: str,
    source_blob_name: str,
    dest_container_name: str,
    dest_blob_name: str
):
    """Asynchronously copies a blob from a source to a destination."""
    logging.info(f"Archiving blob from '{source_container_name}/{source_blob_name}' to '{dest_container_name}/{dest_blob_name}'")
    try:
        source_blob_url = f"{config.AZURE_STORAGE_ACCOUNT_URL}/{source_container_name}/{source_blob_name}"
        
        dest_container_client = await get_blob_container_client(dest_container_name)
        dest_blob_client = dest_container_client.get_blob_client(dest_blob_name)
        
        # Use the native async method
        await dest_blob_client.start_copy_from_url(source_blob_url)
    except Exception as e:
        logging.error(f"Failed to copy blob '{source_blob_name}'. Reason: {e}", exc_info=True)

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


# ==============================================================================
# 2. DATA PIPELINE UTILITIES
# ==============================================================================
# High-level functions that orchestrate the application's data workflow.

async def preprocess_all_pdfs_async() -> bool:
    """
    Processes all PDFs from the source container, intelligently routing each one
    to the correct custom Document Intelligence model based on its filename.
    """
    logging.info("--- Starting Intelligent PDF Pre-processing Router ---")
    try:
        source_container = config.SOURCE_BLOB_CONTAINER
        processed_container = config.PROCESSED_BLOB_CONTAINER
        pdf_blob_names = await list_blobs_async(source_container)
        pdf_blob_names = [name for name in pdf_blob_names if name.lower().endswith('.pdf')]

        if not pdf_blob_names:
            logging.warning(f"No PDF files found in container '{source_container}'.")
            return True

        for pdf_blob_name in pdf_blob_names:
            model_id_to_use = config.AZURE_DI_MODEL_IDS["default"] # Start with the fallback
            
            # --- ROUTING LOGIC ---
            filename_lower = pdf_blob_name.lower()
            sanitised_filename = re.sub(r'[^a-z0-9]', '', filename_lower)
            for keyword, model_id in config.AZURE_DI_MODEL_IDS.items():
                if keyword in sanitised_filename:
                    model_id_to_use = model_id
                    logging.info(f"Match found: Filename '{pdf_blob_name}' contains '{keyword}'. Routing to model '{model_id_to_use}'.")
                    break # Stop when we find the first match

            # --- ANALYSIS & UPLOAD ---
            # Call the function with the selected model ID
            processed_content = await analyse_document_with_di(pdf_blob_name, model_id_to_use)
            
            if processed_content:
                output_blob_name = pdf_blob_name + ".txt"
                await upload_blob_async(processed_container, output_blob_name, processed_content)
            else:
                logging.warning(f"No content was processed for '{pdf_blob_name}' (using model '{model_id_to_use}'). No output was saved.")

        logging.info("--- Intelligent PDF Pre-processing Finished ---")
        return True
    except Exception as e:
        logging.critical(f"A critical error occurred during PDF pre-processing: {e}", exc_info=True)
        return False


def _is_element_in_regions(element, all_table_regions) -> bool:
    """Generic helper to check if an element's bounding box is inside a table's."""
    if not element.bounding_regions:
        return False
    
    elem_region = element.bounding_regions[0]
    elem_coords = elem_region.polygon
    
    # Get the bounding box of the element
    elem_min_x = min(elem_coords[0::2])
    elem_max_x = max(elem_coords[0::2])
    elem_min_y = min(elem_coords[1::2])
    elem_max_y = max(elem_coords[1::2])

    for table_region in all_table_regions:
        if elem_region.page_number != table_region.page_number:
            continue

        table_coords = table_region.polygon
        table_min_x = min(table_coords[0::2])
        table_max_x = max(table_coords[0::2])
        table_min_y = min(table_coords[1::2])
        table_max_y = max(table_coords[1::2])

        # Check if the two bounding boxes overlap at all.
        # It is true if box A is not completely to the left/right/above/below box B.
        x_overlap = (elem_min_x < table_max_x) and (elem_max_x > table_min_x)
        y_overlap = (elem_min_y < table_max_y) and (elem_max_y > table_min_y)

        if x_overlap and y_overlap:
            return True # The boxes overlap, so the paragraph is part of the table.
    return False

def _format_table_as_markdown(table) -> str:
    """Converts a Document Intelligence table object into a Markdown string."""
    grid = [["" for _ in range(table.column_count)] for _ in range(table.row_count)]
    for cell in table.cells:
        if cell.row_index < len(grid) and cell.column_index < len(grid[0]):
            grid[cell.row_index][cell.column_index] = cell.content.replace('\n', ' ').strip()
    
    if not grid:
        return ""
        
    markdown = f"\n### Table (Page {table.bounding_regions[0].page_number})\n"
    header = " | ".join(grid[0])
    markdown += f"| {header} |\n"
    separator = " | ".join(["---"] * len(grid[0]))
    markdown += f"| {separator} |\n"
    for row in grid[1:]:
        data_row = " | ".join(row)
        markdown += f"| {data_row} |\n"
    
    return markdown + "\n"

async def analyse_document_with_di(blob_name: str, model_id: str) -> str:
    """
    Analyses a document from blob storage with a specified Document Intelligence
    model, intelligently separating paragraphs from tables and preserving order.
    """
    logging.info(f"Analysing document '{blob_name}' with model '{model_id}'...")
    try:
        endpoint = config.AZURE_DI_ENDPOINT
        key = config.AZURE_DI_KEY
        
        document_intelligence_client = DocumentIntelligenceClient(endpoint=endpoint, credential=AzureKeyCredential(key))
        blob_sas_url = await get_blob_sas_url_async(config.SOURCE_BLOB_CONTAINER, blob_name)

        poller = await document_intelligence_client.begin_analyze_document(
            model_id=model_id, body={"urlSource": blob_sas_url}
        )
        result = await poller.result()
        await document_intelligence_client.close()

        output_string = f"# Analysis of Document: {blob_name}\n\n"

        # Check if the result came from a custom model (which populates the 'documents' field).
        if result.documents:
            # --- PATH 1: Custom Model ---
            # This is the high-accuracy path.
            logging.info(f"Processing result from custom model '{model_id}'.")
            for doc in result.documents:
                output_string += f"## Form Data (Doc Type: {doc.doc_type})\n"
                for field_name, field in doc.fields.items():
                    # 'field.content' is the extracted value.
                    value_content = field.content.strip() if field.content else ""
                    output_string += f"**{field_name}:** {value_content}\n"
                output_string += "\n"
        else:
            # --- PATH 2: Pre-built/Layout Model (The Fallback) ---
            # This is the logic for handling documents which don't have a custom pre-trained model.
            logging.info(f"Processing result from pre-built model '{model_id}'.")
            
            all_elements = []
            table_regions = []

            if result.tables:
                for table in result.tables:
                    table_regions.extend(table.bounding_regions)
                    top_y = table.bounding_regions[0].polygon[1]
                    page_num = table.bounding_regions[0].page_number
                    all_elements.append({'type': 'table', 'content': table, 'page': page_num, 'y_pos': top_y})

            if result.paragraphs:
                for paragraph in result.paragraphs:
                    if not _is_element_in_regions(paragraph, table_regions):
                        top_y = paragraph.bounding_regions[0].polygon[1]
                        page_num = paragraph.bounding_regions[0].page_number
                        all_elements.append({'type': 'paragraph', 'content': paragraph.content, 'page': page_num, 'y_pos': top_y})

            all_elements.sort(key=lambda item: (item['page'], item['y_pos']))

            for element in all_elements:
                if element['type'] == 'paragraph':
                    output_string += f"{element['content']}\n\n"
                elif element['type'] == 'table':
                    output_string += _format_table_as_markdown(element['content'])
        
        return output_string

    except Exception as e:
        logging.error(f"Failed to analyse document '{blob_name}' with model '{model_id}'. Reason: {e}", exc_info=True)
        return ""

async def read_guidance_files_async(file_paths: list) -> str:
    """Asynchronously reads local guidance files without blocking."""
    loop = asyncio.get_running_loop()
    def _read_sync():
        full_content = ""
        for path in file_paths:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    full_content += f"--- START OF GUIDANCE FILE: {os.path.basename(path)} ---\n"
                    full_content += f.read()
                    full_content += f"\n--- END OF GUIDANCE FILE ---\n\n"
            except FileNotFoundError:
                logging.error(f"Guidance file not found: {path}")
        return full_content
    # Local file I/O in standard Python is blocking. To prevent this from stalling
    # the entire async event loop, we run the synchronous file-reading operations
    # in a separate thread pool using `run_in_executor`.
    return await loop.run_in_executor(None, _read_sync)

async def merge_output_files_async() -> bool:
    """Finds the latest iteration of each section's output file, then merges them into a single final document."""
    logging.info(f"--- Merging sectional outputs from blob storage ---")
    try:
        output_container = config.OUTPUT_BLOB_CONTAINER
        all_blobs = await list_blobs_async(output_container)

        # This dictionary will store the latest iteration found for each section.
        # Format: { section_number: (blob_name, iteration_number) }
        latest_iterations = {}
        
        # This regex is used to parse the section and iteration numbers from the
        # versioned filenames (e.g., 'output_s1_i2.md' -> section=1, iteration=2).
        pattern = re.compile(r'output_s(\d+)_i(\d+)\.md')

        for blob_name in all_blobs:
            match = pattern.match(blob_name)
            if match:
                section_number = int(match.group(1))
                iteration_number = int(match.group(2))

                # If we haven't seen this section yet, or if the current iteration is higher
                # than the one we've stored, update the dictionary.
                if section_number not in latest_iterations or iteration_number > latest_iterations[section_number][1]:
                    latest_iterations[section_number] = (blob_name, iteration_number)

        # Sanity check: Ensure we found a final version for every expected section.
        if len(latest_iterations) != config.TOTAL_SECTIONS:
            logging.error(f"Merge failed: Expected to find a final output for {config.TOTAL_SECTIONS} sections, but only found {len(latest_iterations)}.")
            return False

        # Sort the dictionary by section number to ensure the correct merge order.
        sorted_iterations = sorted(latest_iterations.items())
        
        # Extract just the blob names in the correct order.
        final_blob_names = [data[1][0] for data in sorted_iterations]
        
        logging.info(f"Found latest files to merge: {final_blob_names}")

        content_tasks = [download_blob_as_text_async(output_container, blob_name) for blob_name in final_blob_names]
        full_content = await asyncio.gather(*content_tasks)
        merged_content = "\n\n---\n\n".join(full_content)
        
        await upload_blob_async(output_container, config.FINAL_DOCUMENT_FILENAME, merged_content)
        logging.info(f"Successfully merged all sections into blob: {config.FINAL_DOCUMENT_FILENAME}")
        return True
    except Exception as e:
        logging.error(f"An I/O error occurred during blob merging: {e}", exc_info=True)
        return False


# ==============================================================================
# 3. PARSING AND TEXT UTILITIES
# ==============================================================================
# Functions for cleaning, sanitising, and parsing text from documents.

def _clean_text(text: str) -> str:
    """
    Performs basic text cleaning. (Helper function, prefixed with _).
    """
    if not text:
        return ""
    cleaned_text = re.sub(r'\n{3,}', '\n\n', text)
    lines = [line.strip() for line in cleaned_text.split('\n')]
    return '\n'.join(lines)

def _sanitise_key(key: str) -> str:
    """
    A helper function to clean and sanitise a string to be used as a dictionary key.
    - Converts to lowercase
    - Replaces spaces and hyphens with underscores
    - Removes possessive apostrophes ('s or ’s)
    - Removes any other non-alphanumeric characters (except underscores)
    """
    sanitised = key.lower().replace(" ", "_").replace("-", "_")
    sanitised = sanitised.replace("'s", "").replace("’s", "")
    sanitised = re.sub(r'[^\w_]', '', sanitised)
    sanitised = re.sub(r'__+', '_', sanitised)
    return sanitised
        
def parse_feedback_and_count_issues(feedback_content: str) -> Dict[str, int]:
    """
    Parses a feedback document to find a [FEEDBACK_SUMMARY] block and extract issue counts.
    This is robust against formatting changes in the rest of the document.
    """

    if not feedback_content or feedback_content.strip().startswith("ERROR:"):
        # If the feedback file is missing or empty, it signifies a failure in the
        # validator team. We return a high number of critical issues to force the
        # orchestrator's correction loop to retry the validation step.
        logging.warning("Feedback file was not found or was empty. Forcing a validation retry by reporting 99 critical issues.")
        return {"critical": 99, "major": 99, "minor": 99}

    counts = {"critical": 0, "standard": 0}
    
    try:
        # Use regex to find the content within the [FEEDBACK_SUMMARY] block
        # re.DOTALL allows '.' to match newline characters
        summary_match = re.search(r"\[FEEDBACK_SUMMARY\](.*?)\[END_FEEDBACK_SUMMARY\]", feedback_content, re.DOTALL)
        
        if not summary_match:
            print("Warning: [FEEDBACK_SUMMARY] block not found in feedback.md. Assuming 0 issues.")
            return counts

        summary_block = summary_match.group(1)
        
        # Use regex to find all "Key: Value" pairs within the block
        # This is flexible to extra whitespace or different line endings
        found_issues = re.findall(r"(\w+):\s*(\d+)", summary_block)
        
        for key, value in found_issues:
            key_lower = key.strip().lower()
            if key_lower in counts:
                counts[key_lower] = int(value.strip())
                
    except Exception as e:
        print(f"Error parsing feedback summary block: {e}. Returning default counts.")
        # Return the default counts in case of any parsing error
        return {"critical": 0, "standard": 0}

    return counts

def parse_markdown_to_dict(markdown_content: str) -> dict[str,any]:
    """
    Parses a markdown document assuming every **Key:** is globally unique.
    It ignores all headers and simply extracts all key-value pairs.
    """

    flat_context = {}
    
    # This regex is designed to find key-value pairs. It looks for a **Key:** at the
    # start of a line (`^`), captures the key (`.*?`), and then captures all content
    # (`.*?`) until it hits the next key, a markdown header, a horizontal rule,
    # or the end of the file (`\Z`). This makes it robust to multi-line values.
    pattern = re.compile(r'^\*\*(.*?):\*\*(.*?)(?=^\*\*|^##\s|---\n|\Z)', re.DOTALL | re.MULTILINE)
    
    for match in pattern.finditer(markdown_content):
        # The raw key is something like "Comms & Interaction Need 1"
        key_raw = match.group(1).strip()
        value = match.group(2).strip()
        
        # The sanitiser turns it into "comms_interaction_need_1"
        final_key = _sanitise_key(key_raw)
        
        flat_context[final_key] = value
            
    return flat_context

def create_fact_mapper_version(cited_markdown_content: str) -> str:
    """
    Parses a markdown string containing [SOURCE: ...] tags, cleans the filenames
    within them by removing numeric prefixes and file extensions, and returns
    the processed string for the Fact Mapper.
    """
    logging.info("Cleaning citation tags for the final Fact Mapper version...")

    # This inner function will be applied to every citation tag found
    def replacer(match):
        # The content is group 1 (e.g., "19_Appendix D.pdf.txt, 20_Appendix E.pdf.txt")
        citation_content = match.group(1)
        
        # Split by comma to handle multiple sources
        filenames = [name.strip() for name in citation_content.split(',')]
        
        cleaned_filenames = []
        for filename in filenames:
            # This regex removes a numeric prefix (e.g., "19_") AND the common file extensions
            cleaned_name = re.sub(r'^\d+_|\.pdf\.txt$|\.docx\.txt$', '', filename)
            cleaned_filenames.append(cleaned_name)
        
        # Join the cleaned filenames back together and format the final tag
        return f"[SOURCE: {', '.join(cleaned_filenames)}]"

    # This pattern finds [SOURCE: followed by anything until the closing ]
    # and calls the 'replacer' function on each match.
    fact_mapper_content = re.sub(r'\[SOURCE:\s*(.*?)\]', replacer, cited_markdown_content)
    
    return fact_mapper_content

def create_clean_version(cited_markdown_content: str) -> str:
    """
    Removes all [SOURCE: ...] citation tags from a markdown string to create
    a clean, final version for the end-user document.
    """
    logging.info("Creating clean version of markdown by removing all citation tags...")
    
    # This regex finds any whitespace followed by [SOURCE: ... ] and removes it.
    # The '.*?' part is a non-greedy match for any character.
    clean_content = re.sub(r'\s*\[SOURCE:.*?\]', '', cited_markdown_content)
    
    return clean_content

# ==============================================================================
# 4. DOCUMENT GENERATION UTILITIES
# ==============================================================================
# Functions for creating final output documents (e.g., .docx).

def generate_word_document(context: dict, template_path: str, output_path: str) -> None:
    """
    Generates a Word document by rendering a context dictionary into a docx template.
    """
    try:
        doc = DocxTemplate(template_path)
        doc.render(context)
        doc.save(output_path)
        logging.info(f"Successfully generated Word document at: {output_path}")
    except Exception as e:
        logging.error(f"Failed to generate Word document. Reason: {e}", exc_info=True)


# ==============================================================================
# 5. AUTOGEN AGENT HELPER FUNCTIONS
# ==============================================================================
# Functions required specifically by the AutoGen agent framework.

def is_terminate_message(message):
    """
    Custom function to check for termination message in groupchat.
    Safely handles messages that are not simple strings.
    """
    # Check if the message is a dictionary and has a "content" key
    if isinstance(message, dict) and "content" in message:
        content = message["content"]
        # Check if the content is not None before calling string methods
        if content is not None:
            return content.strip() == "TERMINATE"
    return False





