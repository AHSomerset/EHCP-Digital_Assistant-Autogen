import textstat
import re

# ==============================================================================
# --- PASTE YOUR TEXTS HERE ---
# ==============================================================================

# Replace the content of these multi-line strings with your actual text.
# I have pre-filled them with examples that show a clear difference.

TEXT_A_NAME = "Human-Written Equivalent"
TEXT_A = """
Jack lives at home with his parents, Kirsty and Mark, and two brothers, Jamie and
Jasper. Jack currently attends Stoke St Michael Primary School, and he is due to
transition to secondary school in September 2025. His attendance has been
impacted by anxiety-related difficulties, particularly around school transitions, this
has been ongoing since Year 3.
Jack has been diagnosed with ADHD and he is currently on the
neurodevelopmental pathway for an autism assessment.
"""

TEXT_B_NAME = "AI-Generated Document"
TEXT_B = """
Jack was born and raised in Somerset, growing up in a close-knit family with his mum, dad and two younger brothers. His early milestones such as sitting, walking and talking came along without difficulty, and he enjoyed a happy start to life filled with art projects, playful adventures with his siblings and lots of time building imaginative Lego creations. During nursery, his parents began to notice that Jack sometimes approached activities a little differently from his peers, especially when routines changed or tasks had many steps. As he moved on through primary education, he continued to shine in creative subjects and loved making others laugh, yet found the bustle of the school morning overwhelming. On difficult days he struggled to leave the house, becoming tearful and reluctant to get dressed, but once settled in class he could relax and show his curiosity, especially in history, science and art. Supportive teachers introduced visual timetables, smaller group work and clear, step-by-step instructions, which helped him feel calmer and more able to contribute. At home, Jack’s family provide constant encouragement; they celebrate his caring nature, his sense of humour and the way he looks out for his brothers. While he still faces challenges with worries about schoolwork, homework and unexpected changes, he is surrounded by adults who work together to help him build confidence, develop steady routines and enjoy the activities he loves most.

Jack responds best when adults speak calmly, give him time to think and break information into small, clear chunks, using visual prompts such as now-and-next boards; involving him in choices and checking his understanding helps him feel in control and ready to share his ideas.



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