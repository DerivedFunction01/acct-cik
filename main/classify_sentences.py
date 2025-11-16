#%%
# =============================================================================
# SENTENCE CLASSIFICATION SCRIPT
# =============================================================================
# This script reads the extracted derivative sentences and classifies them
# into categories like 'current', 'historical', 'terminated', or 'speculative'
# using a zero-shot classification model.
#
# To run this, you'll need to install the transformers library:
# pip install transformers torch
# =============================================================================

import sqlite3
import json
from tqdm import tqdm
from transformers import pipeline
import torch

# =============================================================================
# CONFIGURATION
# =============================================================================

DB_PATH = "clean_web_data.db"

# The labels you want to classify sentences into.
SIMPLE_LABELS = ["current", "historical", "terminated", "speculative"]

# Multi-shot examples to guide the classifier.
# These provide context for what each label means.
LABEL_EXAMPLES = {
    "current": "The company holds interest rate swaps with a notional value of $100 million.",
    "historical": "In 2022, the company settled all of its outstanding forward contracts.",
    "terminated": "The commodity hedge was terminated in the third quarter, resulting in a loss.",
    "speculative": "We may in the future enter into derivative contracts to manage risk."
}

# The template for creating the classification hypotheses.
HYPOTHESIS_TEMPLATE = "Given the report is for the year {report_year}, this sentence is about {label} derivatives. For example: '{example}'"


# You can choose a different model. distilbert is a good balance of speed and accuracy.
MODEL_NAME = "facebook/bart-large-mnli"

# Determine if a GPU is available for faster processing
DEVICE = 0 if torch.cuda.is_available() else -1

# =============================================================================
# DATABASE FUNCTIONS
# =============================================================================

def create_classification_table():
    """Creates the table to store sentence classification results."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("""
            CREATE TABLE IF NOT EXISTS sentence_classifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT,
                sentence TEXT,
                label TEXT,
                score REAL,
                derivative_type TEXT
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_sentence_url ON sentence_classifications (url)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_sentence_label ON sentence_classifications (label)")
        conn.commit()
        print("✅ `sentence_classifications` table created or already exists.")
    except Exception as e:
        print(f"❌ Error creating table: {e}")
    finally:
        conn.close()

def get_url_to_year_map():
    """Fetches data from the source DB to map URLs to their report year."""
    # This function connects to the *source* DB to get metadata
    conn = sqlite3.connect(SOURCE_DB_PATH)
    c = conn.cursor()
    url_map = {}
    try:
        c.execute("SELECT url, year FROM report_data WHERE url IS NOT NULL")
        for url, year in c.fetchall():
            url_map[url] = year
    finally:
        conn.close()
    return url_map

def get_sentences_to_classify():
    """Fetches all unique sentences from the derivative_type_matches table."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    sentences = {} # Use a dict to store sentences and their types, ensuring uniqueness
    
    try:
        c.execute("SELECT url, ir_matches, fx_matches, cp_matches, eq_matches FROM derivative_type_matches")
        rows = c.fetchall()
        
        for row in rows:
            url, ir_json, fx_json, cp_json, eq_json = row
            type_map = {
                "ir": json.loads(ir_json),
                "fx": json.loads(fx_json),
                "cp": json.loads(cp_json),
                "eq": json.loads(eq_json),
            }
            
            for dtype, sentence_list in type_map.items():
                for sentence in sentence_list:
                    # Store by sentence to keep it unique, value is a tuple of (url, type)
                    if sentence not in sentences:
                        sentences[sentence] = (url, dtype)

        print(f"📚 Found {len(sentences)} unique sentences to classify.")
        return list(sentences.items())
    except Exception as e:
        print(f"❌ Error fetching sentences: {e}")
        return []
    finally:
        conn.close()

def save_classifications(results):
    """Saves a batch of classification results to the database."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.executemany(
            "INSERT INTO sentence_classifications (url, sentence, label, score, derivative_type) VALUES (?, ?, ?, ?, ?)",
            results
        )
        conn.commit()
    except Exception as e:
        print(f"❌ Error saving batch to database: {e}")
    finally:
        conn.close()

# =============================================================================
# MAIN EXECUTION
# =============================================================================

if __name__ == "__main__":
    print("="*80)
    print("🚀 Starting Sentence Classification")
    print("="*80)

    create_classification_table()
    
    sentences_with_meta = get_sentences_to_classify()
    if not sentences_with_meta:
        print("❌ No sentences to classify. Exiting.")
    else:
        # Load the zero-shot classification pipeline
        print(f"Loading zero-shot model '{MODEL_NAME}'...")
        classifier = pipeline("zero-shot-classification", model=MODEL_NAME, device=DEVICE)
        
        print("🧠 Mapping URLs to report years...")
        url_to_year = get_url_to_year_map()

        # Group sentences by report year to create year-specific hypotheses
        sentences_by_year = {}
        for sentence, (url, dtype) in sentences_with_meta:
            report_year = url_to_year.get(url)
            if not report_year:
                continue # Skip if we can't find a year for the report
            
            if report_year not in sentences_by_year:
                sentences_by_year[report_year] = []
            sentences_by_year[report_year].append({'sentence': sentence, 'url': url, 'dtype': dtype})

        print(f"🤖 Found sentences from {len(sentences_by_year)} different report years. Classifying year by year...")
        db_records = []

        for report_year, items in tqdm(sentences_by_year.items(), desc="Processing by year"):
            # 1. Create year-specific hypotheses
            candidate_labels_with_examples = [
                HYPOTHESIS_TEMPLATE.format(report_year=report_year, label=label, example=LABEL_EXAMPLES[label])
                for label in SIMPLE_LABELS
            ]
            hypothesis_to_label_map = {desc: label for desc, label in zip(candidate_labels_with_examples, SIMPLE_LABELS)}
            
            # 2. Get sentences for this year
            sentence_texts = [item['sentence'] for item in items]

            # 3. Classify this batch
            outputs = classifier(sentence_texts, candidate_labels_with_examples, multi_label=False, batch_size=16)

            # 4. Process and store results
            for i, output in enumerate(outputs):
                original_item = items[i]
                sentence = output['sequence']
                best_hypothesis = output['labels'][0]
                label = hypothesis_to_label_map[best_hypothesis]
                score = output['scores'][0]
                db_records.append((original_item['url'], sentence, label, score, original_item['dtype']))

        print("💾 Saving results to the database...")
        save_classifications(db_records)
        print("\n✨ Classification complete! Results are saved in the `sentence_classifications` table.")
        print("="*80)