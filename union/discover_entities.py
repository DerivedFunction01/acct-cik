import sqlite3
import json
import re
from collections import Counter
from pathlib import Path

# Import definitions
from defs.region_regex import (
    NORTH_AMERICA,
    EUROPE,
    ASIA_PACIFIC,
    LATIN_AMERICA,
    MIDDLE_EAST_AFRICA,
    INTERNATIONAL,
)

DB_PATH = "filtered_union_data.db"

def get_known_terms():
    """Builds a set of known terms (lowercase) from region definitions and common noise."""
    known = set()
    regions = [
        NORTH_AMERICA,
        EUROPE,
        ASIA_PACIFIC,
        LATIN_AMERICA,
        MIDDLE_EAST_AFRICA,
        INTERNATIONAL,
    ]
    
    for region in regions:
        for nation in region:
            known.add(nation.name.lower())
            for p in nation.phrases:
                known.add(p.lower())
            for u in nation.unions:
                known.add(u.lower())
            for k in nation.keywords:
                known.add(k.lower())
            for loc in nation.locations:
                known.add(loc.name.lower())
                for p in loc.phrases:
                    known.add(p.lower())
                for city in loc.cities:
                    known.add(city.name.lower())
                    for cp in city.phrases:
                        known.add(cp.lower())
                        
    # Add common noise and generic terms
    known.update([
        "company", "the company", "inc", "corp", "ltd", "llc", "plc",
        "group", "holdings", "trust", "association", "union", "labor",
        "agreement", "agreements", "collective", "bargaining",
        "employees", "workers", "workforce", "staff", "personnel",
        "january", "february", "march", "april", "may", "june",
        "july", "august", "september", "october", "november", "december",
        "fiscal", "year", "ended", "december", "quarter",
        "u.s.", "us", "usa", "united states",
        "board", "directors", "committee", "securities", "exchange", "commission", "sec",
        "act", "code", "law", "regulations", "gaap", "fasb", "irs",
        "item", "part", "form", "table", "note", "data",
    ])
    
    return known

def analyze_entities():
    if not Path(DB_PATH).exists():
        print(f"Database {DB_PATH} not found. Run filter_paragraphs.py first.")
        return

    print("Loading known terms...")
    known_terms = get_known_terms()
    
    print(f"Reading from {DB_PATH}...")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Fetch all item1 and item1a content
    c.execute("SELECT item1, item1a FROM webpage_result")
    
    single_word_counter = Counter()
    multi_word_counter = Counter()
    
    row_count = 0
    
    for row in c:
        row_count += 1
        content_list = []
        if row[0]:
            try:
                content_list.extend(json.loads(row[0]))
            except: pass
        if row[1]:
            try:
                content_list.extend(json.loads(row[1]))
            except: pass
            
        for text in content_list:
            if not text:
                continue
                
            # Split into sentences to handle "First word" logic
            sentences = re.split(r'[.!?]+', text)
            
            for sent in sentences:
                sent = sent.strip()
                if not sent:
                    continue
                
                words = sent.split()
                if not words:
                    continue
                
                # Skip the first word (often capitalized just because it's start of sentence)
                tokens_to_check = words[1:]
                
                current_phrase = []
                
                for word in tokens_to_check:
                    # Check for trailing punctuation that breaks sequence (commas, colons)
                    has_separator = word.endswith(',') or word.endswith(';') or word.endswith(':')
                    
                    # Clean punctuation for analysis
                    clean_word = re.sub(r'^[^a-zA-Z0-9]+|[^a-zA-Z0-9]+$', '', word)
                    
                    if not clean_word:
                        if current_phrase:
                            # Commit phrase if we hit a symbol/empty token
                            phrase = " ".join(current_phrase)
                            (multi_word_counter if len(current_phrase) > 1 else single_word_counter)[phrase] += 1
                            current_phrase = []
                        continue
                    
                    # Check capitalization (Title Case or Acronyms)
                    if clean_word[0].isupper():
                        current_phrase.append(clean_word)
                        if has_separator:
                             # End sequence here due to comma/separator
                             phrase = " ".join(current_phrase)
                             (multi_word_counter if len(current_phrase) > 1 else single_word_counter)[phrase] += 1
                             current_phrase = []
                    else:
                        # Lowercase word breaks the sequence
                        if current_phrase:
                            phrase = " ".join(current_phrase)
                            (multi_word_counter if len(current_phrase) > 1 else single_word_counter)[phrase] += 1
                            current_phrase = []
                
                # End of sentence check
                if current_phrase:
                    phrase = " ".join(current_phrase)
                    (multi_word_counter if len(current_phrase) > 1 else single_word_counter)[phrase] += 1

    conn.close()
    print(f"Processed {row_count} rows.")
    
    print("\n--- Top Unknown Multi-Word Entities (Potential Unions/Regions) ---")
    count = 0
    for phrase, freq in multi_word_counter.most_common(200):
        if phrase.lower() not in known_terms:
            print(f"{freq:5d} : {phrase}")
            count += 1
            if count >= 50: break
            
    print("\n--- Top Unknown Single-Word Entities (Check for Countries) ---")
    count = 0
    for word, freq in single_word_counter.most_common(200):
        if word.lower() not in known_terms and len(word) > 2:
            print(f"{freq:5d} : {word}")
            count += 1
            if count >= 50: break

if __name__ == "__main__":
    analyze_entities()