# Project Roadmap: Union & Labor Disclosure Analysis

## ✅ Phase 1: Data Acquisition (Extract)
- [x] **SEC Scraping Engine** (`webpage.py`)
    - [x] Download 10-K filings from EDGAR.
    - [x] Parse HTML/Text content.
    - [x] Extract "Item 1" (Business) and "Item 1A" (Risk Factors).
    - [x] Store raw data in `web_data.db`.

## ✅ Phase 2: Definitions & Cleaning (Define)
- [x] **Regex Library** (`defs/`)
    - [x] Define generic labor terms (`union_regex.py`).
    - [x] Define global regions, nations, and specific unions (`region_regex.py`).
    - [x] Add translated keywords (French, Spanish, German, etc.) for international detection.
- [x] **Text Normalization** (`defs/text_cleaner.py`)
    - [x] Normalize company names (e.g., "Apple Inc." -> "the Company").
    - [x] Convert word-numbers to digits ("five thousand" -> "5000").
    - [x] Handle fractions and percentages.
    - [x] **Currency Removal**: Strip dollar figures to isolate employee counts.

## ✅ Phase 3: Filtering (Transform)
- [x] **Paragraph Filtering** (`filter_paragraphs.py`)
    - [x] Load raw data from `web_data.db`.
    - [x] Apply `MinimalTextCleaner` and `CurrencyRemover`.
    - [x] Filter paragraphs matching generic labor terms OR specific union names.
    - [x] Save relevant, cleaned paragraphs to `filtered_union_data.db`.
    - [x] Copy metadata (`report_data`, `names`) to the filtered database.

## 🚧 Phase 4: Analysis & Extraction (Analyze)
- [ ] **Extraction Logic Implementation** (`union_extractor.py`)
    - [ ] **Sentence Segmentation**: Split paragraphs into sentences while preserving context for inheritance.
    - [ ] **Temporal Scope Engine**: Implement rules to classify statements as PAST, CURRENT, or FUTURE (handling "decertified", "will be", etc.).
    - [ ] **Geographic State Machine**: Implement context inheritance (carrying region forward) and inference (Union Name -> Region).
    - [ ] **Negation & Calculation**:
        - [ ] Detect "NOT covered" and flip percentages (e.g., 60% not covered -> 40% covered).
        - [ ] Calculate percentages from raw employee counts (Covered / Total).
    - [ ] **Risk Classification (Item 1A)**: Differentiate between generic `LABOR_RISK` and specific `UNION_RISK`.
- [ ] **JSON Construction**
    - [ ] Build `item1_details_json` array with full metadata (specificity, ambiguity flags).
    - [ ] Build `item1a_details_json` array for risk factors.

## ⏳ Phase 5: Reporting & Validation (Load)
- [ ] **Data Aggregation**
    - [ ] Process all rows in `filtered_union_data.db` and store results (JSON columns or JSONL).
- [ ] **Validation**
    - [ ] Verify JSON schema compliance against `union.md`.
    - [ ] Manual audit of "Ambiguous" or "Inferred" flags.
