import pandas as pd
import requests
import json
from pathlib import Path

# =============================================================================
# CONFIGURATION
# =============================================================================

# --- INPUT ---
# Create this Excel file and add your test sentences in a column named 'sentence'.
INPUT_EXCEL_PATH = "test_sentences.xlsx"

# --- OUTPUT ---
# The script will create this file with the model's predictions.
OUTPUT_EXCEL_PATH = "test_results.xlsx"

# --- SERVER ---
# Make sure your Flask server is running at this address.
SERVER_URL = "http://127.0.0.1:5000/predict"

# =============================================================================
# SERVER COMMUNICATION
# =============================================================================

def get_predictions_from_server(sentences: list, batch_size: int = 32) -> list:
    """
    Sends a list of sentences to the model server and returns predictions.

    Args:
        sentences (list): A list of strings to be classified.
        batch_size (int): How many sentences to send in each request.

    Returns:
        list: A list of prediction dictionaries from the server.
    """
    all_predictions = []
    headers = {"Content-Type": "application/json"}

    print(f"Sending {len(sentences)} sentences to the model server in batches of {batch_size}...")

    for i in range(0, len(sentences), batch_size):
        batch = sentences[i : i + batch_size]
        payload = {"texts": batch}

        try:
            response = requests.post(SERVER_URL, headers=headers, data=json.dumps(payload))
            response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)
            
            response_json = response.json()
            batch_predictions = response_json.get("predictions", [])

            if not isinstance(batch_predictions, list) or len(batch_predictions) != len(batch):
                print(f"  -> Warning: Server response mismatch for a batch. Expected {len(batch)} predictions, got {len(batch_predictions)}.")
                # Fill with error objects for the failed batch
                all_predictions.extend([{"error": "response_mismatch"}] * len(batch))
            else:
                all_predictions.extend(batch_predictions)

        except requests.exceptions.RequestException as e:
            print(f"  -> Error: Could not connect to the server at {SERVER_URL}.")
            print(f"     Reason: {e}")
            # Fill with error objects for the failed batch and stop trying
            all_predictions.extend([{"error": "network_error"}] * len(batch))
            break # Stop processing if the server is down

    return all_predictions

# =============================================================================
# MAIN EXECUTION
# =============================================================================

def main():
    """Main function to run the test script."""
    input_path = Path(INPUT_EXCEL_PATH)
    if not input_path.exists():
        print(f"Error: Input file not found at '{INPUT_EXCEL_PATH}'")
        print("\nPlease create this file with a column named 'sentence' containing your test texts.")
        # Create a sample file for the user
        sample_df = pd.DataFrame({'sentence': ['This is a sample sentence about an interest rate swap.', 'This is another sentence.']})
        sample_df.to_excel(input_path, index=False)
        print(f"A sample file has been created for you at '{input_path}'. Please edit it and run again.")
        return

    print(f"Reading sentences from '{INPUT_EXCEL_PATH}'...")
    df = pd.read_excel(input_path)

    if "sentence" not in df.columns:
        print("Error: The input Excel file must contain a column named 'sentence'.")
        return

    sentences_to_predict = df["sentence"].dropna().tolist()
    
    if not sentences_to_predict:
        print("No sentences found in the 'sentence' column.")
        return

    predictions = get_predictions_from_server(sentences_to_predict)

    # Combine original sentences with predictions and save
    df["model_prediction"] = [json.dumps(p) for p in predictions]
    df.to_excel(OUTPUT_EXCEL_PATH, index=False)
    print(f"\n✅ Success! Predictions saved to '{OUTPUT_EXCEL_PATH}'.")

if __name__ == "__main__":
    main()