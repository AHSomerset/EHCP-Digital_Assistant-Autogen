"""
config.py

This module acts as the central configuration hub for the entire application.
It is responsible for loading all settings, credentials, paths, and constants
required for the pipeline to run.

Key Responsibilities:
- Loads sensitive credentials (API keys, storage keys) from the .env file.
- Defines static paths for local directories (logs, outputs, instructions).
- Specifies Azure Blob Storage container names and connection details.
- Sets application-level operational parameters, such as the number of
  concurrent sections to process and the maximum number of correction loops.
- Constructs the LLM configuration dictionaries (`llm_config`, `llm_config_fast`)
  for use with the AutoGen framework.
- Dynamically provides the correct paths to instruction and guidance files
  for each document section via the `get_section_config` function.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ==============================================================================
# 1. DIRECTORY & PATH DEFINITIONS (For Local Files Only)
# ==============================================================================
# These paths point to files bundled with the application (e.g., instructions)
# or temporary local files (e.g., logs, temp outputs).
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(os.path.join(__file__, '..'))))
OUTPUTS_DIR = os.path.join(BASE_DIR, "outputs")  
INSTRUCTIONS_DIR = os.path.join(BASE_DIR, "instructions")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
LOGS_DIR = os.path.join(BASE_DIR, "logs")

# ==============================================================================
# 2. AZURE & APPLICATION SETTINGS
# ==============================================================================
# --- Azure Storage Credentials ---
AZURE_STORAGE_ACCOUNT_NAME = os.getenv("AZURE_STORAGE_ACCOUNT_NAME")
AZURE_STORAGE_ACCOUNT_KEY = os.getenv("AZURE_STORAGE_ACCOUNT_KEY")
AZURE_STORAGE_ACCOUNT_URL = f"https://{AZURE_STORAGE_ACCOUNT_NAME}.blob.core.windows.net"

# --- Blob Storage Container Names ---
SOURCE_BLOB_CONTAINER = "source-docs"
PROCESSED_BLOB_CONTAINER = "processed-docs"
OUTPUT_BLOB_CONTAINER = "outputs"
FINAL_DOCUMENT_CONTAINER = "final-document"
ARCHIVE_BLOB_CONTAINER = "run-archive"

# --- Azure AI Document Intelligence Settings ---
AZURE_DI_ENDPOINT = os.getenv("AZURE_DI_ENDPOINT")
AZURE_DI_KEY = os.getenv("AZURE_DI_KEY")

AZURE_DI_MODEL_IDS = {
    #"appendixa": "App.A",  
    #"appendixb": "AppB",  
    "default": "prebuilt-layout" # The fallback for everything else
}

# --- Application-Level Settings ---
TOTAL_SECTIONS = 3
CONCURRENT_SECTIONS = 3
MAX_SECTION_ITERATIONS = 10

# --- Final Document Blob Name ---
FINAL_DOCUMENT_FILENAME = "final_document.md"

# ==============================================================================
# 3. LLM AND API CONFIGURATIONS
# ==============================================================================
# --- Load Azure OpenAI Credentials ---
azure_api_key = os.getenv("AZURE_OPENAI_API_KEY")
azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
azure_model_name = os.getenv("AZURE_OPENAI_MODEL_NAME")
azure_model_name2 = os.getenv("AZURE_OPENAI_MODEL_NAME2")
azure_api_version = os.getenv("AZURE_OPENAI_API_VERSION")

# --- Build LLM Config Dictionaries ---
config_list = [{"model": azure_model_name, "api_key": azure_api_key, "base_url": azure_endpoint, "api_type": "azure", "api_version": azure_api_version}]
llm_config = {"config_list": config_list, "timeout": 300, "cache_seed": None}

config_list_fast = [{"model": azure_model_name2, "api_key": azure_api_key, "base_url": azure_endpoint, "api_type": "azure", "api_version": azure_api_version}]
llm_config_fast = {"config_list": config_list_fast, "timeout": 300, "cache_seed": None}

if not all([azure_api_key, azure_endpoint, azure_model_name, azure_model_name2, azure_api_version]):
    raise ValueError("One or more critical Azure OpenAI environment variables are not set in .env")

# ==============================================================================
# 4. DYNAMIC SECTION CONFIGURATION
# ==============================================================================
# Define paths to reusable instruction partials
_PARTIALS_DIR = os.path.join(INSTRUCTIONS_DIR, "partials")
WRITER_COMMON_RULES = os.path.join(_PARTIALS_DIR, "_writer_common_rules.md")
NEED_CATEGORISATION_GUIDE = os.path.join(_PARTIALS_DIR, "_need_categorisation_guide.md")
VALIDATOR_COMMON_RULES = os.path.join(_PARTIALS_DIR, "_validator_common_rules.md")
VALIDATOR_COMMON_FEEDBACK_FORMAT = os.path.join(_PARTIALS_DIR, "_validator_common_feedback_format.md")
STRUCTURE_S1 = os.path.join(_PARTIALS_DIR, "_structure_s1.md")
STRUCTURE_S2 = os.path.join(_PARTIALS_DIR, "_structure_s2.md")
STRUCTURE_S3 = os.path.join(_PARTIALS_DIR, "_structure_s3.md")

def get_section_config(section_number: str) -> dict:
    """
    Returns a dictionary of all necessary configuration (blob names and local
    guidance file paths) for a specific section number.
    """
    section_str = str(section_number)
    
    writer_guidance_s = os.path.join(INSTRUCTIONS_DIR, f"writer_guidance_s{section_str}.md")
    validation_guidance_s = os.path.join(INSTRUCTIONS_DIR, f"validation_guidance_s{section_str}.md")

    path_map = {
        "1": {
            "writer_guidance": [writer_guidance_s, WRITER_COMMON_RULES, STRUCTURE_S1],
            "validation_guidance": [validation_guidance_s, VALIDATOR_COMMON_RULES, VALIDATOR_COMMON_FEEDBACK_FORMAT, STRUCTURE_S1],
            "source_exclude_files": []
        },
        "2": {
            "writer_guidance": [writer_guidance_s, WRITER_COMMON_RULES, STRUCTURE_S2],
            "validation_guidance": [validation_guidance_s, VALIDATOR_COMMON_RULES, VALIDATOR_COMMON_FEEDBACK_FORMAT, STRUCTURE_S2],
            "source_exclude_files": []
        },
        "3": {
            "writer_guidance": [writer_guidance_s, WRITER_COMMON_RULES, NEED_CATEGORISATION_GUIDE, STRUCTURE_S3],
            "validation_guidance": [validation_guidance_s, VALIDATOR_COMMON_RULES, VALIDATOR_COMMON_FEEDBACK_FORMAT, NEED_CATEGORISATION_GUIDE, STRUCTURE_S3],
            "source_exclude_files": ['Appendix A.pdf']
        },
    }

    config_data = {}
    config_data.update(path_map.get(section_str, {}))
    return config_data