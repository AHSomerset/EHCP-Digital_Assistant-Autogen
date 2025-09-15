# AutoGen EHCP Document Automation Pipeline

This project is a sophisticated multi-agent system designed to automate the generation of complex, multi-section Education, Health, and Care Plan (EHCP) documents. It leverages the Microsoft AutoGen framework to orchestrate teams of AI agents that perform specialised roles. The entire data pipeline is built on Azure Blob Storage, moving from raw source documents in the cloud to a fully validated and merged final output in a robust, parallel, and fault-tolerant manner.

## Key Features

-   **Multi-Agent System:** Utilises distinct agent teams for writing and validation, each with specialised roles (`Planner`, `Document_Writer`, `Quality_Assessor`, `Fact_Checker`).
-   **Azure Blob Storage Integration:** All document I/O (source, processed, and final outputs) is handled through Azure Blob Storage, making the system scalable, cloud-native, and independent of local file systems.
-   **Parallel Processing:** Employs Python's `asyncio` and a semaphore to concurrently generate and validate multiple document sections, significantly reducing total runtime.
-   **Robust Correction Loop:** Each document section is created once, then put through a rigorous validate-correct-revalidate loop. This ensures that the expensive creation step is not repeated and that corrections are iteratively applied until the document meets quality standards.
**Traceable, Versioned Outputs:** Every draft and feedback report for each iteration is saved as a separate, versioned file (e.g., `output_s1_i2.md`, `feedback_s1_i2.md`), providing a complete and auditable trail of the entire generation process.
-   **Word Document Export:** Automatically parses the final structured Markdown output and populates a custom `.docx` template, producing a professionally formatted, ready-to-use final document.
-   **Configuration-Driven:** A central `config.py` file manages all application settings, file paths, and LLM configurations, making the system easy to manage and reconfigure.
-   **Modular and DRY Guidance:** Agent instructions are externalised into a version-controllable `instructions/` directory. Reusable partials, including shared "structure" files, ensure consistency and adhere to the DRY (Don't Repeat Yourself) principle across both Writer and Validator teams.
-   **Cloud-Ready Logging:** The system generates detailed run logs and a high-level process trace, saving them both locally and uploading them to a dedicated Azure Blob Storage container for persistent, reliable access.
-   **Automated File Management:** Includes a pre-processing step to convert source PDFs to clean text and a guaranteed cleanup process to ensure a clean state for every run.
-   **Tiered LLM Strategy:** Uses two different LLM tiers—a powerful model for content generation and a faster model for orchestration and planning.

## Architectural Overview

The application follows a robust, multi-stage pipeline designed to maximise quality and efficiency.

**Stage 1: Pre-processing**
-   The script begins by scanning the `source-docs` Azure Blob Storage container for all PDF source documents.
-   Each PDF is read, its text is extracted, cleaned, and then saved as a `.txt` file in the `/processed_docs` directory. This ensures that the AI agents work with a clean, consistent data source.

**Stage 2: Concurrent Sectional Generation**
-   The system initiates a writer and validator team for each of the document sections.
-   Using `asyncio`, these teams work in parallel, up to the concurrency limit set in `config.py`.
-   For each section, it first fetches the correct source documents, applying any section-specific exclusions as defined in config.py. This requires a strict naming convention for appendix documents.

**Stage 3: The Write-Validate-Refine Loop**
-   For each section, the process is as follows:
    1.  **Initial Creation:** The `Writer Team` is called once to create the first version of the section's content (e.g., output_s1_i1.md).
    2.  **Validation Loop Starts:** The system enters an iterative loop.
    3.  **Validator Team:** The Validator Team reviews the latest draft against a strict set of rules (including a shared structure file), producing a versioned feedback report (e.g., feedback_s1_i1.md).
    4.  **Assessment:** The orchestrator parses the feedback.
    -   If the feedback file is missing or the Validator team failed, the error is caught, and the validation step is automatically retried in the next loop.
    -   If no critical issues are found, the section is considered "passed," and the loop for that section ends.
    -   If critical issues are found, a specialist `Prompt_Writer` agent reframes the feedback into a concise set of correction instructions. 
    5.  **Correction:** The `Writer Team` is called again, but this time in "correction mode," using the concise instructions to improve the previous draft and save a new, versioned output (e.g., output_s1_i2.md). The loop then returns to step 3.
-   This loop continues until the section passes validation or `MAX_SECTION_ITERATIONS` is reached.

**Stage 4: Final Merge**
-   Once all sections have successfully passed validation, the `merge_output_files_async` utility is called.
-   It intelligently finds the **latest valid iteration** for each section (e.g., output_s1_i3.md, output_s2_i2.md, etc.) and concatenates them into a single, complete document: final_document.md.   

**Stage 5: Word Document Generation**
-   A robust Python parser reads the structured `final_document.md`.
-   The parsed data is converted into a flat key-value dictionary.
-   The `docxtpl` library is used to render this dictionary into a pre-defined Microsoft Word template (`template.docx`).
-   The final, professionally formatted output is saved to the `outputs` container as `draft_EHCP.docx`..

**Stage 6: Cleanup**
-   The `finally` block in `main.py` guarantees that final tasks are always run.
-   Log Upload: The complete log files for the run are uploaded to the logs blob container for permanent storage.
-   Container Cleanup: The processed-docs container is cleared to ensure the next run starts from a clean state.


## Agent Team Structure

#### 1. The Writer Team (`create_writer_team`)
-   **Purpose:** To draft and revise a specific document section from source files.
-   **Context:** Receives its guidance and pre-filtered source documents directly in the initial prompt from the orchestrator.
-   **Agents:**
    -   `Planner`: Orchestrates the team's workflow. Follows a strict plan to delegate drafting and order the saving of the file. It is the only agent in this team authorised to issue the `TERMINATE` signal.
    -   `Document_Writer`: The content specialist. Its sole job is to synthesise information and write the document text. It does not engage in conversation.
    -   `Writer_User_Proxy`:  Executes tool calls, primarily for saving the final output file.

#### 2. The Validator Team (`create_validator_team`)
-   **Purpose:** To validate a single section draft for factual accuracy, structural integrity, and rule compliance.
-   **Context:** Receives its validation rules and the same pre-filtered source documents as the writer directly in its prompt.
-   **Agents:**
    -   `Quality_Assessor`: The lead validator. It performs structural checks and consolidates all findings into the final feedback report. It is the only agent in this team authorised to issue the `TERMINATE` signal.
    -   `Fact_Checker`: The accuracy specialist. Its sole job is to compare the draft against the source documents and report any factual discrepancies or hallucinations.
    -   `Validator_User_Proxy`: The tool user. Its main jobs are to download the draft being reviewed and upload the final feedback report.

## Project Structure

```text
.
├── 📂 instructions/          # Guidance prompts for all agents.
│   ├── 📂 partials/          # Reusable markdown components for guidance files.
│   ├── writer_guidance_s1.md
│   └── ...
├── 📂 logs/                  # All output logs are saved here.
├── 📂 outputs/               # Local copy of the final .docx is saved here for inspection.
├── 📄 config.py              # Central configuration for all paths, settings, and LLMs.
├── 📄 main.py                # Main application entry point and high-level orchestration.
├── 📄 orchestrator.py        # Contains the core logic for processing and correcting sections.
├── 📄 tasks.py               # Generates the initial prompts for all agent teams.
├── 📄 utils.py               # Helper functions, parsers, and tool functions.
├── 📄 writer.py              # Defines the agent teams responsible for writing.
├── 📄 validator.py           # Defines the agent teams responsible for validation.
├── 📄 specialist_agents.py   # Defines standalone specialist agents like the Prompt_Writer.
├── 📄 .env                   # Environment variables for API keys and endpoints.
├── 📄 requirements.txt       # Python package dependencies.
├── 📄 template.docx          # The Word template for the final output document.

```

## Setup and Installation

1.  **Prerequisites:**
    -   You must have an Azure account and an Azure Storage Account.
    -   Create five blob containers within your storage account: source-docs, processed-docs, outputs, final-document, and run-archive

2.  **Clone the repository:**
    ```bash
    git clone <your-repo-url>
    cd <your-repo-directory>
    ```

3.  **Create and activate a virtual environment:**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
    ```

4.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

5. **Deploy AI models in Azure AI Foundry**
    This project requires two separate large language model deployments — a reasoning model for complex tasks and a faster model for orchestration tasks.

6.  **Configure environment variables:**
    -   Create a file named `.env` in the root of the project.
    -   Add your Azure Sotrage and Azure OpenAI credentials to this file. Use the template below:

    ```env
    AZURE_OPENAI_API_KEY="your_api_key"
    AZURE_OPENAI_ENDPOINT="https://your_endpoint.openai.azure.com/"
    AZURE_OPENAI_API_VERSION="2024-02-15-preview"

    # Deployment name for your powerful reasoning model 
    AZURE_OPENAI_MODEL_NAME=""

    # Deployment name for your fast orchestration model 
    AZURE_OPENAI_MODEL_NAME2=""

    # Azure Storage Account Credentials
    AZURE_STORAGE_ACCOUNT_NAME="your_storage_account_name"
    AZURE_STORAGE_ACCOUNT_KEY="your_storage_account_key"
    ```

7.  **Create the Word Template:**
    -   Create a Microsoft Word document named `template.docx` in the project's root directory.
    -   Design this document with your desired final formatting.
    -   Fill it with Jinja2-style placeholders (e.g., `{{ name }}`, `{{ history_summary }}`) where data should be inserted.

## How to Run

1.  Upload Source Documents: Using the Azure Portal, Azure Storage Explorer, or the Azure CLI, upload all your source PDF documents into the source-docs blob container.
2.  Ensure your guidance files in `/instructions` and your `template.docx` are configured as needed.
3.  Run the main script from the root directory:
    ```bash
    python main.py
    ```

## Outputs and Logging

After a successful run:
-   **Final Document:** The final draft_EHCP.docx and the merged final_document.md will be located in your `outputs` Azure Blob Storage container.
-   **Intermediate Files:** Sectional drafts (output_sX_iY.md) and their feedback reports (feedback_sX_iY.md) will also be in the outputs  container, providing a full audit trail.
-   **Local Logs:** Detailed logs are saved in the run-archive storage container and in the local 'logs' directory.
    -   /logs/full_run_YYYY-MM-DD_HH-MM-SS.log contains the full, verbose console output.
    -   /logs/loop_trace_YYYY-MM-DD_HH-MM-SS.log contains a high-level summary of the process flow.
