import textstat
import re

# ==============================================================================
# --- PASTE YOUR TEXTS HERE ---
# ==============================================================================

# Replace the content of these multi-line strings with your actual text.
# I have pre-filled them with examples that show a clear difference.

TEXT_A_NAME = "Human-Written Equivalent"
TEXT_A = """
Henry is in Year 8. He lives at home with his parents, Jemma and Rob, his twin, an
older brother with medical needs, and younger brother. He has an older half-sister
he sees occasionally who does not live at home. The family also have lots of pets
(cats, dogs, chickens, guinea pigs, horses). Henry has an NHS confirmed ADHD
diagnosis (09/01/25) following privately assessed indicators (May 2024) of dyslexia,
ADHD, Conduct Disorder and Oppositional Defiance Disorder. Traits of Autism
have also been indicated, and he has been on the neurodevelopmental pathway
for assessment for 18 months. At primary school a visual impairment was identified
in his left eye which did not respond to treatment. Henry was permanently
excluded from Huish Episcopi Academy on 05/12/24 for persistent disruptive
behaviour. While in the setting Henry had received daily sports development
group (20 minutes, 1:5), weekly Zones of Regulation intervention (30 minutes, 1:1),
literacy intervention 3 times per week (30 minutes), daily mentoring from a
pastoral support worker, time with the school counsellor (ended due to low
engagement),16 hours per week of additional adult support in core lessons, weekly
Forest School (small group, one hour), Somerset Activities Sports Partnership
intervention (one hour, 1:1), a part-time timetable (two hours per day) and SSPS
outreach for a Thrive assessment and plan.
"""

TEXT_B_NAME = "AI-Generated Document"
TEXT_B = """
Henry grew up in a close family with several siblings and many pets, and after moving homes a few times in his early years the family have lived in their current house for the past eight years.  
At his small primary school he received literacy intervention and support from the Family Intervention Service.  
On entering secondary school he accessed weekly Forest School sessions and other practical, movement-based interventions, but the much larger environment led to repeated suspensions and a permanent exclusion.  
Significant events such as the death of his grandad during the pandemic and several hospital visits for accidents have contributed to his strong sense of fairness and need for safety.  
He is now attending South Somerset Partnership School and is working with the Educational Psychologist and the Family Intervention Service to rebuild positive experiences of learning.

Henry engages best when adults take time to build trust, speak calmly, use clear visual prompts and offer regular check-ins so he can share how he feels before problems escalate.

"""

# ==============================================================================
# --- ANALYSIS FUNCTIONS (No need to edit below this line) ---
# ==============================================================================

def calculate_lexical_diversity(text: str) -> float:
    """Calculates the Type-Token Ratio (a measure of lexical diversity)."""
    # Find all words, convert to lowercase
    words = re.findall(r'\b\w+\b', text.lower())
    total_words = len(words)
    if total_words == 0:
        return 0.0
    
    unique_words = len(set(words))
    return unique_words / total_words

def analyze_text(text: str) -> dict:
    """Calculates all relevant readability scores for a text."""
    return {
        "flesch_reading_ease": textstat.flesch_reading_ease(text),
        "flesch_kincaid_grade": textstat.flesch_kincaid_grade(text),
        "lexical_diversity": calculate_lexical_diversity(text)
    }

def print_results(name: str, scores: dict):
    """Prints the formatted results for a single text."""
    print(f"--- Readability Scores for: {name} ---")
    print(f"Flesch Reading Ease:    {scores['flesch_reading_ease']:.2f} (Higher is better)")
    print(f"Flesch-Kincaid Grade:   {scores['flesch_kincaid_grade']:.2f} (Lower is better)")
    print(f"Lexical Diversity:      {scores['lexical_diversity']:.2f} (Lower is often more readable)")
    print("-" * 40)

def compare_results(scores_a: dict, scores_b: dict):
    """Prints a comparison of the two sets of scores."""
    grade_diff = scores_b['flesch_kincaid_grade'] - scores_a['flesch_kincaid_grade']
    lex_diff = scores_b['lexical_diversity'] - scores_a['lexical_diversity']

    print("\n--- Comparison Summary ---")
    print(f"The AI-Generated document is estimated to be written at a grade level that is {grade_diff:.2f} grades higher than the human version.")
    print(f"The AI-Generated document has a lexical diversity score that is {lex_diff:.2f} higher, indicating a wider (and potentially more complex) vocabulary.")
    print("-" * 40)

# ==============================================================================
# --- MAIN EXECUTION ---
# ==============================================================================

if __name__ == "__main__":
    # Analyze both texts
    scores_a = analyze_text(TEXT_A)
    scores_b = analyze_text(TEXT_B)

    # Print the individual results
    print_results(TEXT_A_NAME, scores_a)
    print_results(TEXT_B_NAME, scores_b)
    
    # Print the final comparison
    compare_results(scores_a, scores_b)