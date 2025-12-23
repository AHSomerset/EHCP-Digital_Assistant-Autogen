# AutoGen EHCP Document Automation Pipeline

This project is a sophisticated multi-agent system designed to automate the generation of complex, multi-section Education, Health, and Care Plan (EHCP) documents. It leverages the Microsoft AutoGen framework to orchestrate teams of AI agents that perform specialised roles. The entire data pipeline is built on Azure Blob Storage, moving from raw source documents in the cloud to a fully validated and merged final output in a robust, parallel, and fault-tolerant manner.

## Key Features

-   **Multi-Agent System:** Utilises distinct agent teams for writing and validation, each with specialised roles (`Planner`, `Document_Writer`, `Quality_Assessor`, `Fact_Checker`).
-   **Cloud-Native Architecture:** All document I/O (source, processed, and final outputs) is handled through **Azure Blob Storage**, making the system scalable and independent of local file systems.
-   **Parallel Processing:** Employs Python's `asyncio` and a semaphore to concurrently generate and validate multiple document sections, significantly reducing total runtime.
-   **Robust Correction Loop:** Each document section is created once, then put through a rigorous validate-correct-revalidate loop. This ensures that the expensive creation step is not repeated and that corrections are iteratively applied until the document meets quality standards.
**Traceable, Versioned Outputs:** Every draft and feedback report for each iteration is saved as a separate, versioned file (e.g., `output_s1_i2.md`, `feedback_s1_i2.md`), providing a complete and auditable trail of the entire generation process.
-   **Word Document Export:** Automatically parses the final structured Markdown output and populates a custom `.docx` template, producing a professionally formatted, ready-to-use final document.
-   **Configuration-Driven:** A central `src/ehcp_autogen/config.py` file manages all application settings, file paths, and LLM configurations.
-   **Modular agent Guidance:** Agent instructions are externalised into a version-controllable `instructions/` directory. Reusable partials, including shared "structure" files, ensure consistency and adhere to the DRY (Don't Repeat Yourself) principle across both Writer and Validator teams.
-   **Cloud-Ready Logging:** The system generates detailed run logs and a high-level process trace, saving them both locally and uploading them to a dedicated Azure Blob Storage container for persistent, reliable access.
-   **Automated File Management:** Includes a pre-processing step to convert source PDFs to clean text and a guaranteed cleanup process to ensure a clean state for every run.
-   **Tiered LLM Strategy:** Uses two different LLM tiers—a powerful model for content generation and a faster model for orchestration and planning.

---

## Prerequisites

Before you begin, ensure you have the following installed and configured:

-   **Python 3.12.9**
-   **Python Version Manager:** It is recommend to install and use `pyenv` to manage your Python versions.  This project includes a `.python-version` file in the root directory, which will automatically configure `pyenv` to use the correct Python version when you are in the project folder.
*   **Operating System:** The project was developed on a Linux environment, using **WSL 2 (Ubuntu)** on Windows.
-   **An Azure Subscription** with permissions to create resources.
-   **Azure CLI**
-   **Docker Desktop** (for containerised deployment)

---

## Architectural Overview

The application follows a robust, multi-stage pipeline designed to maximise quality and efficiency.

**Stage 1: Pre-processing**
-   The script begins by scanning the `source-docs` Azure Blob Storage container for all PDF source documents.
-   Each PDF is read, its text is extracted, cleaned, and then saved as a `.txt` file in the `processed-docs` container. This ensures that the AI agents work with a clean, consistent data source.

**Stage 2: Concurrent Sectional Generation**
-   The system initiates a writer and validator team for each of the document sections.
-   Using `asyncio`, these teams work in parallel, up to the concurrency limit set in `config.py`.
-   For each section, it first fetches the correct source documents, applying any section-specific exclusions as defined in config.py. This requires a strict naming convention for appendix documents.

**Stage 3: The Write-Validate-Refine Loop**
-   For each section, the process is as follows:
    1.  **Initial Creation:** The `Writer Team` is called once to create the first version of the section's content (e.g., output_s1_i1.md).
    2.  **Validation Loop Starts:** The system enters an iterative loop.
    3.  **Validator Team:** The Validator Team reviews the latest draft against a strict set of rules (including a shared structure file), producing a versioned feedback report (e.g. feedback_s1_i1.md).
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
-   The final, professionally formatted output is saved to the `final-document` container as `draft_EHCP.docx`..

**Stage 6: Archiving & Cleanup**
-   The `finally` block in `main.py` guarantees that final tasks are always run.
-   All artifacts for the run (source documents, final outputs, logs) are copied to a timestamped folder in the `run-archive` container for a complete audit trail.
-   The temporary containers (`processed-docs`, `outputs`) are then cleared to prepare for the next run.

---

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

---

## LLM Model Choices

This project uses a tiered LLM strategy to balance performance and cost. You will need to create two separate model deployments in your Azure OpenAI service.

1. **Heavy Reasoning Model** (AZURE_OPENAI_MODEL_NAME)
-   **Purpose:** Used for tasks requiring deep understanding, synthesis, and content generation. This is assigned to the Document_Writer, Quality_Assessor, and Fact_Checker agents.
-   **Recommended Model:** o3 or equivalent high-capability model.
2.  **Fast Orchestration Model** (AZURE_OPENAI_MODEL_NAME2)
-   **Purpose:** Used for faster, less complex tasks like planning, managing conversations, and reformatting prompts. This is assigned to the Planner, GroupChatManager, and Prompt_Writer agents.
-   **Recommended Model:** gpt-4o, or equivalent fast model.

---

## Project Structure

```text
.
├── 📂 documentation/          # Supplementary documents for users.
├── 📂 instructions/           # Guidance prompts for all agents.
│   ├── 📂 partials/           # Reusable markdown components for guidance files.
│   ├── writer_guidance_s1.md
│   └── ...
├── 📂 logs/                   # Local copies of run logs (also archived to blobs).
├── 📂 outputs/                # Temporary local storage for the generated .docx before upload.
├── 📂 src/                    # The main Python source code package.
│   └── 📂 ehcp_autogen/
│       ├── 📄 __init__.py
│       ├── 📂 agents/         # Agent and team definitions.
│       ├── 📂 cloud/          # Azure Blob Storage utilities.
│       ├── 📂 orchestration/  # Core workflow and pipeline logic.
│       ├── 📂 utils/          # Helper functions, parsers, and tool functions.
│       ├── 📄 config.py       # Central configuration for all paths, settings, and LLMs.
│       └── 📄 tasks.py        # Generates the initial prompts for all agent teams.
│       └── 📄 logging_config.py  # Configures the application logging system
│   └── 📄 main.py             # Main application entry point and high-level orchestration.
├── 📂 templates/              # Contains the template.docx file.
├── 📄 .env.example            # Template for environment variables.
├── 📄 Dockerfile              # Instructions to build the application container.
└── 📄 requirements.txt        # Python package dependencies.

```

## Setup and Installation

1.  **Prerequisites:**
    -   You must have Python 3.11+ installed on your local machine.
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
    -   Copy the `.env.example` file to a new file named `.env`.
    -   Fill in the values for your Azure OpenAI and Azure Storage credentials.

7.  **Create the Word Template:**
    -   Place a Microsoft Word document named `template.docx` in the `/templates` directory.
    -   Fill it with Jinja2-style placeholders (e.g., `{{ name }}`, `{{ history_summary }}`) where data should be inserted.

---

## How to Run

1.  Upload Source Documents: Using the Azure Portal, Azure Storage Explorer, or the Azure CLI, upload all your source PDF documents into the source-docs blob container.
2.  Ensure your guidance files in `/instructions` and your `template.docx` are configured as needed.
3.  Run the main script from the root directory:
    ```bash
    python -m src.main
    ```
4.  Run via Docker (for cloud deployment):
    -   Follow the instructions in the deployment guides to build and push the Docker image to your Azure Container Registry and run it as an Azure Container App Job.

---

## Outputs and Logging

After a successful run:
-   **Final Document:** The final draft_EHCP.docx will be located in your `outputs` Azure Blob Storage container.
-   **Intermediate Files:** All intermediate files, including sectional drafts (output_sX_iY.md) and their feedback reports (feedback_sX_iY.md) will stored in the run-archive container.
-   **Local Logs:** Detailed logs are saved in the run-archive storage container and in the local 'logs' directory.
    -   /logs/full_run_YYYY-MM-DD_HH-MM-SS.log contains the full, verbose console output.
    -   /logs/loop_trace_YYYY-MM-DD_HH-MM-SS.log contains a high-level summary of the process flow.
-   **Cleanup:** All temporary storage containers are cleared to leave a clean slate.

---

## Troubleshooting

**1. `python: can't open file '.../main.py': [Errno 2] No such file or directory`**
   -   **Cause:** You are trying to run a script from the project root directory directly.
   -   **Solution:** Always run the application using the command `python -m src.main`.

**2. Docker Build Fails:**
   -   **Cause:** Your `requirements.txt` file may be out of date.
   -   **Solution:** Run `pip freeze > requirements.txt` locally to update the file before building the Docker image.

**3. Azure Authentication Errors:**
   -   **Cause:** Your Azure CLI is not logged in or is set to the wrong subscription.
   -   **Solution:** Run `az login` and then `az account set --subscription "Your_Subscription_Name"` to switch to the correct subscription.
