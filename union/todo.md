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

## ✅ Phase 3.5: Entity Discovery (Explore)
- [ ] **Entity Discovery Script** (`discover_entities.py`)
    - [ ] Scan filtered text for consecutive capitalized words.
    - [ ] Filter out known unions/regions/noise.
    - [ ] Report potential new unions or countries for manual review.

## 🚧 Phase 4: Analysis & Extraction (Analyze)
- [ ] **Region Assignment**
    - [ ] Create a script to scan filtered paragraphs against `region_regex.py`.
    - [ ] Assign specific `Nation` and `Region` tags based on matches (e.g., "IG Metall" -> Germany).
    - [ ] Handle disambiguation (e.g., generic "International" vs. specific country).
- [ ] **Employee Count Extraction**
    - [ ] Develop regex logic to extract employee numbers (e.g., "approximately 5,000 employees").
    - [ ] Distinguish between "total employees" and "unionized employees".
    - [ ] Calculate unionization rates where available.

## ⏳ Phase 5: Reporting (Load)
- [ ] **Data Aggregation**
    - [ ] Join extracted tags and counts with company metadata (CIK, Year, Name).
    - [ ] Generate a final structured dataset (CSV/SQL).
- [ ] **Validation**
    - [ ] Manual review of a sample set to verify region assignment accuracy.
    - [ ] Verify employee count extraction against known ground truths.
