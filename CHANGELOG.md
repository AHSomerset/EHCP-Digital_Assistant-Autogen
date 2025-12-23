# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 23-12-2025

### Changed
- Standardised the project's required Python version to `3.12.9` to ensure a consistent and reproducible development environment for all contributors. This is now enforced via a new `.python-version` file for use with `pyenv`.

---

## [1.0.0] - 24-10-2025

This is the first stable, production-ready release, marking a complete architectural overhaul from the initial proof-of-concept to a cloud-native, robust, and auditable system.

### Added
- **Run Auditing & Archiving:** Implemented a comprehensive archiving system. All source documents, final outputs, and logs for each run are now copied to a uniquely identified folder in a `run-archive` container for a complete audit trail.
- **Modular Project Structure:** Introduced a standard `src/ehcp_autogen` Python package structure, separating application code from project management files.
- **Dedicated Asset Folders:** Created `templates/` and `documentation/` folders to cleanly organise non-code assets.
- **Professional Documentation:** Added `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, and this `CHANGELOG.md`.

### Changed
- **Architecture: Moved to Azure Container App Jobs:** The deployment model was changed from a proof-of-concept to a script-based Azure Container App Job. This is cost-effective for this background processing workload.
- **Data Storage: Full Azure Blob Storage Integration:** All file I/O has been refactored. The application is now fully cloud-native, using Azure Blob Storage for all source, intermediate, and final documents.
- **Concurrency Model:** All synchronous, blocking I/O calls (file reads, blob operations) were refactored into non-blocking `async` functions using `asyncio.run_in_executor` or native `aio` clients to prevent deadlocks.

### Fixed
- **Application Hang on Startup:** Resolved a critical deadlock caused by synchronous, blocking I/O calls (both local file reads and Azure SDK calls) freezing the `asyncio` event loop.
- **`AttributeError: 'str' object has no attribute 'get'`:** Made the `orchestrator` more robust by checking the return type of agent replies before processing them.

### Removed

---

## [0.1.0] - Initial Proof-of-Concept

### Added
- Initial implementation of the multi-agent system using Microsoft AutoGen.
- `Writer` and `Validator` agent teams for processing document sections.
- Parallel processing of sections using `asyncio`.
- Iterative write-validate-refine loop for each section.
