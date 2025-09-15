import os
import re
import pypdf
import logging
from typing import List, Dict
import config
import asyncio
import io
#from azure.storage.blob import BlobServiceClient
from azure.storage.blob.aio import BlobServiceClient
from azure.core.exceptions import ResourceNotFoundError
from docxtpl import DocxTemplate

# ==============================================================================
# 1. AZURE BLOB STORAGE UTILITIES
# ==============================================================================
# Low-level functions for interacting with Azure Blob Storage.
# Includes a singleton client to manage the connection efficiently.

_blob_service_client = None

async def _get_blob_service_client():
    """
    Gets the singleton async instance of the BlobServiceClient.
    If it doesn't exist, it creates one.
    """
    global _blob_service_client
    if _blob_service_client is None:
        logging.info("Initializing singleton async BlobServiceClient...")
        if not all([config.AZURE_STORAGE_ACCOUNT_URL, config.AZURE_STORAGE_ACCOUNT_KEY]):
            raise ValueError("Storage account URL or Key is not set in the environment.")
        
        # Create an async client.
        client = BlobServiceClient(
            account_url=config.AZURE_STORAGE_ACCOUNT_URL,
            credential=config.AZURE_STORAGE_ACCOUNT_KEY
        )
        _blob_service_client = client
        logging.info("Async BlobServiceClient initialized successfully.")
    return _blob_service_client

async def get_blob_container_client(container_name: str):
    """Helper to connect to a specific Azure Blob Storage container using the async singleton client."""
    blob_service_client = await _get_blob_service_client()
    return blob_service_client.get_container_client(container_name)

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

    # Convert exclusion list to lowercase for case-insensitive comparison
    exclude_files_lower = [f.lower() for f in exclude_files]

    logging.info(f"--- Downloading source documents from container: {container_name} ---")
    if exclude_files_lower:
        logging.info(f"--- Excluding files: {exclude_files} ---")
    
    # Get the list of all blob names to be downloaded.
    blob_names = await list_blobs_async(container_name)
    
    if not blob_names:
        logging.warning(f"No blobs found in container '{container_name}'.")
        return "ERROR: No source documents found in the specified container."
    
    full_content = ""
    for blob_name in blob_names:
        filename = os.path.basename(blob_name)
        # Check against the original name (e.g., appendix_a.pdf.txt) and the name without .txt
        if filename.lower() in exclude_files_lower or filename.lower().replace(".txt", "") in exclude_files_lower:
            logging.info(f"Skipping excluded source file: {filename}")
            continue

        logging.info(f"Reading source file: {blob_name}")
        full_content += f"--- START OF FILE {filename} ---\n\n"
        full_content += await download_blob_as_text_async(container_name, blob_name)
        full_content += f"\n\n--- END OF FILE {filename} ---\n\n"
    # # Step 2: Create a list of download tasks without awaiting them yet.
    # download_tasks = [download_blob_as_text_async(container_name, blob_name) for blob_name in blob_names]

    # # Step 3: Execute all the download tasks concurrently using asyncio.gather.
    # contents = await asyncio.gather(*download_tasks)
    
    logging.info(f"--- Finished downloading {len(blob_names)} source documents. Formatting content. ---")

    # Step 4: Now that all content is downloaded, format it into a single string.
    # full_content_parts = []
    # for i, content in enumerate(contents):
    #     blob_name = blob_names[i]
    #     filename = os.path.basename(blob_name)
    #     full_content_parts.append(f"--- START OF FILE {filename} ---\n\n{content}\n\n--- END OF FILE {filename} ---\n\n")
    
    # return "".join(full_content_parts)
    return full_content

async def _read_local_guidance_files_async(file_paths: list) -> str:
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
    return await loop.run_in_executor(None, _read_sync)

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


# ==============================================================================
# 2. DATA PIPELINE UTILITIES
# ==============================================================================
# High-level functions that orchestrate the application's data workflow.

async def preprocess_all_pdfs_async() -> bool:
    """Asynchronously downloads, processes, and re-uploads all PDFs."""
    logging.info("--- Starting PDF Pre-processing from Blob Storage ---")
    try:
        source_container = config.SOURCE_BLOB_CONTAINER
        processed_container = config.PROCESSED_BLOB_CONTAINER
        pdf_blob_names = await list_blobs_async(source_container)
        pdf_blob_names = [name for name in pdf_blob_names if name.lower().endswith('.pdf')]

        if not pdf_blob_names:
            logging.warning(f"No PDF files found in container '{source_container}'.")
            return True

        for pdf_blob_name in pdf_blob_names:
            logging.info(f"Processing blob: {pdf_blob_name}")
            pdf_bytes = await download_blob_as_bytes_async(source_container, pdf_blob_name)
            if not pdf_bytes:
                logging.warning(f"Skipping empty blob: {pdf_blob_name}")
                continue

            reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
            extracted_text = "".join(page.extract_text() or "" for page in reader.pages)
            cleaned_content = _clean_text(extracted_text)
            
            output_blob_name = pdf_blob_name + ".txt"
            await upload_blob_async(processed_container, output_blob_name, cleaned_content)

        logging.info("--- PDF Pre-processing Finished ---")
        return True
    except Exception as e:
        logging.critical(f"A critical error occurred during PDF pre-processing: {e}", exc_info=True)
        return False

async def merge_output_files_async() -> bool:
    """Finds the latest iteration of each section's output file, then merges them into a single final document."""
    logging.info(f"--- Merging sectional outputs from blob storage ---")
    try:
        output_container = config.OUTPUT_BLOB_CONTAINER
        all_blobs = await list_blobs_async(output_container)

        # This dictionary will store the latest iteration found for each section.
        # Format: { section_number: (blob_name, iteration_number) }
        latest_iterations = {}
        
        # Define the regex pattern to match and extract numbers from versioned filenames.
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
    
    # This regex finds a **Key:** at the start of a line, then captures all content
    # (including newlines and bullets) until it hits the next **Key:** or Heading (##) or ---
    pattern = re.compile(r'^\*\*(.*?):\*\*(.*?)(?=^\*\*|^##\s|---\n|\Z)', re.DOTALL | re.MULTILINE)
    
    for match in pattern.finditer(markdown_content):
        # The raw key is something like "Comms & Interaction Need 1"
        key_raw = match.group(1).strip()
        value = match.group(2).strip()
        
        # The sanitiser turns it into "comms_interaction_need_1"
        final_key = _sanitise_key(key_raw)
        
        flat_context[final_key] = value
            
    return flat_context


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





