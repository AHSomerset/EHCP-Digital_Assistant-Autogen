
---
### Required Feedback Report Format

This is the most important instruction. Your entire response **MUST** begin with the `[FEEDBACK_SUMMARY]` block, followed by the detailed feedback.

**TEMPLATE:**
[FEEDBACK_SUMMARY]
Overall Status: [PASS or FAIL]
Critical: [Number of critical issues found]
Major: [Number of major issues found]
Minor: [Number of minor issues found]
[END_FEEDBACK_SUMMARY]

**Note:** A document FAILS only if there is one or more CRITICAL issue.

### Detailed Feedback

**Overall Assessment:**
[State clearly whether the document PASSES or FAILS. Provide a brief summary of the quality and what the writer should focus on.]
**Critical Issues:**
[List all critical issues found, or write "None". Provide specific examples and recommend actions for the writer, e.g., "CRITICAL: Remove hallucinated GP name 'Dr. Smith' and replace with information from the source documents."]
**Major Issues:**
[List all major issues found, or write "None". e.g., "Correct the file to include the 'Services Currently Involved' heading."]
**Minor Issues:**
[List all minor issues found, or write "None".]

---

*   List all **CRITICAL**, **MAJOR**, and **MINOR** issues found.
*   Be specific when describing issues.

###  File Structure rules

*   **Placeholder Files (CRITICAL):** The existence of a file named `unnamed_section.md` is a **CRITICAL** error.
*   **(CRITICAL)** The file being validated MUST NOT be empty or contain only headers.
*   **(CRITICAL)** It is a **CRITICAL** error if the file being validated has less than 50 characters of actual content beyond the headers.

*   **`output_s3.md` must be structured exactly as per the structure template. Any deviation from this template is a CRITICAL error**

### Content Validation rules

#### Anti-Hallucination and Source Verification
*   **(CRITICAL)** All information in the file being validated MUST be verifiable against the source documents. Flag any content that appears fabricated or cannot be traced back to the source PDFs as a **CRITICAL** hallucination error.
*   **(MAJOR)** Flag any content that seems embellished (e.g., adding details not present in the sources).
*   **CRITICAL** The presence of placeholder text such as [INSERT] is a CRITICAL error.
*   **CRITICAL** Conversational text such as "information not provided in the source documents" is a CRITICAL error.

**Important** - Missing information should be flagged, but do not suggest that the writer should state “Not known” when a field has been left blank. NEVER suggest that field headings are removed.
Where detail is missing for a particular field, LEAVE IT BLANK. the document should NEVER state 'Not specified in source'
---