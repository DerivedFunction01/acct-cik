import re
import pandas as pd
from pathlib import Path

# =============================================================================
# CONFIGURATION
# =============================================================================

# Define the paths for the input and output files.
BASE_PATH = Path(__file__).parent
INPUT_XML_PATH = BASE_PATH / "q_a.md"
OUTPUT_PARQUET_PATH = BASE_PATH / "q_a.parquet"
OUTPUT_CSV_PATH = BASE_PATH / "q_a_.csv"

# =============================================================================
# SCRIPT LOGIC
# =============================================================================

def parse_xml_with_regex(file_path: Path):
    """
    Parses an XML-like file using regular expressions to avoid issues with
    invalid characters. Extracts main questions, assistant answers, and
    follow-up questions.

    Args:
        file_path (Path): The path to the input XML-like file.

    Returns:
        tuple[pd.DataFrame, pd.DataFrame]: A tuple containing two DataFrames:
        one for the main Q&A and one for the follow-up questions.
    """
    print(f"Reading data from '{file_path}'...")
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        print(f"❌ Error: Input file not found at '{file_path}'.")
        return None, None

    # Regex to find all <response> blocks
    response_blocks = re.findall(r"<response>(.*?)</response>", content, re.DOTALL)
    print(f"Found {len(response_blocks)} response blocks to process.")

    qa_data = []
    followup_data = []

    for block in response_blocks:
        # Extract the main question and the explanation (assistant answer)
        question_match = re.search(r"<question>(.*?)</question>", block, re.DOTALL)
        explanation_match = re.search(r"<explanation>(.*?)</explanation>", block, re.DOTALL)

        if question_match and explanation_match:
            main_question = question_match.group(1).strip()
            assistant_answer = explanation_match.group(1).strip()
            qa_data.append({"question": main_question, "assistant_answer": assistant_answer})

            # Extract the follow-up questions within the same block
            followup_block_match = re.search(r"<follow-up>(.*?)</follow-up>", block, re.DOTALL)
            if followup_block_match:
                followup_content = followup_block_match.group(1)
                # Find all <qX> tags
                followup_questions = re.findall(r"<q\d+>(.*?)</q\d+>", followup_content, re.DOTALL)
                for fq in followup_questions:
                    followup_data.append({"followup_question": fq.strip()})

    # Convert the lists of dictionaries to pandas DataFrames
    qa_df = pd.DataFrame(qa_data)
    followup_df = pd.DataFrame(followup_data)

    return qa_df, followup_df

if __name__ == "__main__":
    qa_df, followup_df = parse_xml_with_regex(INPUT_XML_PATH)

    if qa_df is not None and followup_df is not None:
        print(f"Extracted {len(qa_df)} main Q&A pairs and {len(followup_df)} follow-up questions.")
        # Save the main Q&A to a Parquet file
        qa_df.to_parquet(OUTPUT_PARQUET_PATH, index=False)
        print(f"✅ Main Q&A data saved to '{OUTPUT_PARQUET_PATH}'")

        # Save the follow-up questions to a CSV file
        followup_df.to_csv(OUTPUT_CSV_PATH, index=False)
        print(f"✅ Follow-up questions saved to '{OUTPUT_CSV_PATH}'")