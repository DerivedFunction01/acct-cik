import sqlite3
import json
import re
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

# Import definitions
from defs.regex_lib import SENTENCE_SPLIT_PATTERN
from defs.union_regex import UNION_REGEX

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(message)s')

DB_PATH = "filtered_union_data.db"

class UnionExtractor:
    """
    Extracts unionization details from text based on the specifications in union.md.
    Currently focused on Part 1, Example 1: Simple Domestic Unionization with Percentage.
    """
    def __init__(self):
        # Regex for explicit percentages (e.g., "12%", "12.5%")
        # Captures the number in group 1
        self.percent_pattern = re.compile(r"(\d+(?:\.\d+)?)\s*%", re.IGNORECASE)
        
        # Regex for USA context (Simple version for Example 1)
        # Matches: U.S., USA, United States, Domestic
        self.usa_pattern = re.compile(
            r"\b(?:U\.?S\.?A?|United\s+States|Domestic)\b", 
            re.IGNORECASE
        )
        
        # Union keywords from definitions
        self.union_regex = UNION_REGEX

    def analyze_sentence(self, sentence: str) -> Optional[Dict[str, Any]]:
        """
        Analyzes a single sentence to extract union coverage details.
        """
        # 1. Check for Union Keywords
        # Rule: "Union mention required"
        keyword_match = self.union_regex.search(sentence)
        if not keyword_match:
            return None
            
        matched_keyword = keyword_match.group(0)

        # 2. Extract Coverage Data (Percentage)
        # Rule: "Explicit percentage first"
        coverage_data = None
        pct_match = self.percent_pattern.search(sentence)
        
        if pct_match:
            try:
                pct_val = float(pct_match.group(1))
                coverage_data = {
                    "percentage": pct_val,
                    "type": "EXPLICIT_PERCENT",
                    "percentage_qualifier": None, 
                    "negated": False, # Assumption for Example 1
                    "temporal_scope": "CURRENT" # Assumption for Example 1 ("Assume current unless stated otherwise")
                }
            except ValueError:
                pass
        
        # 3. Geographic Context
        # Rule: Explicit Country/Region Mention
        geo_context = {
            "region": "UNKNOWN",
            "countries": [],
            "specificity": "implicit"
        }
        
        if self.usa_pattern.search(sentence):
            geo_context = {
                "region": "USA",
                "countries": ["USA"],
                "specificity": "explicit"
            }
            
        # Construct the final JSON object for this sentence
        result = {
            "sentence": sentence,
            "keyword_matched": matched_keyword,
            "geographic_context": geo_context,
            "coverage_data": coverage_data
        }
        
        return result

    def process_text_block(self, text: str) -> List[Dict[str, Any]]:
        """
        Splits a text block into sentences and processes each one.
        """
        results = []
        # Split sentences using the robust pattern from regex_lib
        sentences = SENTENCE_SPLIT_PATTERN.split(text)
        
        for sent in sentences:
            sent = sent.strip()
            if not sent:
                continue
            
            analysis = self.analyze_sentence(sent)
            
            # For "solving Example 1", we strictly look for: USA + Percentage + Union Keyword
            if analysis and analysis['coverage_data'] and analysis['geographic_context']['region'] == 'USA':
                results.append(analysis)
                
        return results

def run_analysis():
    if not Path(DB_PATH).exists():
        print(f"Database {DB_PATH} not found. Please run filter_paragraphs.py first.")
        return

    print(f"Reading from {DB_PATH}...")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT accession, item1, item1a FROM webpage_result")
    
    extractor = UnionExtractor()
    match_count = 0
    
    print("\n--- Searching for Example 1 Matches (Domestic + Percentage) ---\n")
    
    for row in c:
        accession, item1_json, item1a_json = row
        
        content = []
        if item1_json: 
            try: content.extend(json.loads(item1_json))
            except: pass
        
        for block in content:
            extracted_items = extractor.process_text_block(block)
            
            for item in extracted_items:
                match_count += 1
                print(f"Accession: {accession}")
                print(json.dumps(item, indent=2))
                print("-" * 40)
                
                if match_count >= 5: # Limit output for demonstration
                    print("... (Stopping after 5 matches for review) ...")
                    conn.close()
                    return

    if match_count == 0:
        print("No matches found for the specific Example 1 criteria in the database.")

    conn.close()

if __name__ == "__main__":
    run_analysis()