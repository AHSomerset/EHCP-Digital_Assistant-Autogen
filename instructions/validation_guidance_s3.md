# Validation Guidance: Section 3 - Needs, Provisions, Outcomes

Your task is to validate `output_s3_i#.md` and produce a feedback report.

## Section-Specific Validation Rules

### Structure
*   **(CRITICAL)** The file structure **MUST** perfectly match the template defined in the `_structure_s3.md` guidance file. All six main headings must be present.

### The Golden Thread
The "Golden Thread" is the logical link between Needs, Provisions, and Outcomes. A broken thread is a **STANDARD** error.
1.  **Every Need must have a Provision:** Is there a specific provision listed for every single need identified?
2.  **Outcomes must be supported by Provisions:** Are the outcomes achievable based on the provisions listed?

### Provision and Outcome Specificity
*   **(CRITICAL) Hallucination of Specifics:** For any Provision or Outcome, if the writer has added a quantifiable detail (e.g., a ratio like "1:1", a frequency like "weekly", a duration like "30 minutes", or a timeframe like "by the end of term") that was **NOT** explicitly stated in the source documents, this is a **CRITICAL** hallucination error.
*   **(CRITICAL) Omission of Important detail:** If the source documents **DID** provide a specific detail for a provision or outcome, but the writer failed to include it, this is a **CRITICAL** error. The document must contain all relevant information for each provision and outcome.
*   **(NOT an Error) Correctly Recording a Vague Provision or Outcome:** If a provision or outcome in the draft is vague (e.g., "regular support from a TA") because the source text itself was vague, the writer has acted correctly. This is **NOT an error** and should not be flagged.

### SMART Outcome Rules
*   **Definition:** An outcome is SMART if it is Specific, Measurable, Achievable, Relevant, and Time-bound. "To improve social skills" is not SMART. "By the end of the term, Gemma will initiate a conversation with a peer on at least 3 occasions per week" is SMART.
*   **(STANDARD) Failure to Synthesise a SMART Outcome:** If the source documents contained all the necessary elements for a SMART outcome but the writer produced a vague, non-SMART outcome, this is a **STANDARD** error.

### Field Formatting Rules
*   **(NOT an Error) Use of Bullet Points:** It is acceptable for the `Provision` and `Outcome` fields to contain a bulleted list (using hyphens) if a single need is associated with multiple provisions or outcomes. This is **NOT** a formatting error and should be considered correct.

### Content Categorisation & Rules
*   **(STANDARD) Need Duplication:** A single, distinct need appearing under more than one category is a **STANDARD** error. Any deviation from the classification in the _need_categorisation_guidance.md should be flagged as a **STANDARD** error.
*   **(STANDARD) Social Care H1/H2:** Check for plausible classification of social care provision. Misclassification is a **STANDARD** error.
*   **(CRITICAL) Relevance to SEN:** Health and Social Care needs described MUST relate to the child's special educational needs.
*   **(CRITICAL) Prohibited Content:** The file MUST NOT mention the names of specific prescribed drugs or medications.
*   **(STANDARD) No Needs Statement:** If no needs are present under a specific category, the file MUST use the exact phrase "[Child's name] has no identified special educational needs in this area" in the 'Need 1' field for that category.




