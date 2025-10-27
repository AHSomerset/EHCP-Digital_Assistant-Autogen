### Universal Validation Rules

#### Anti-Hallucination and Source Verification
*   **(CRITICAL)** All information in the file being validated MUST be verifiable against the source documents. Flag any content that appears fabricated or cannot be traced back to the source PDFs as a **CRITICAL** hallucination error.
*   **(CRITICAL)** The presence of placeholder text such as `[INSERT]` is a CRITICAL error.
*   **(CRITICAL)** The presence of conversational text such as "information not provided in the source documents" is a CRITICAL error.

### Citation Rules
The file being validated contains citation tags like `[SOURCE: filename.txt]` after each statement.
*   **(STANDARD)** A statement that is factually correct (it exists in one of the source documents) but its `[SOURCE: ...]` tag points to the **wrong document** is a **STANDARD** error. You must * state which document the fact was actually found in.

#### File Structure Rules
*   **(CRITICAL)** The file being validated MUST NOT be empty or contain only headers. It is a **CRITICAL** error if the file has less than 50 characters of actual content beyond the headers.