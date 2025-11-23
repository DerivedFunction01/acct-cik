# Roadmap: Derivative Active User Classification

This document outlines the development roadmap for building a classified dataset of SEC filings to identify active derivative users.

## Phase 1: Data Extraction & Pre-training (Completed)

- [x] **1. Extract Raw Text from SEC Filings** - **Status:** Done.  
  - **Implementation:** `webpage.py` → `web_data.db`

- [x] **2. Domain-Adaptive Pre-Training (DAPT)** - **Status:** Skipped – regex-based approach sufficient.

## Phase 2: Regex-Based Filtering & Classification

- [x] **3. Filter and Classify with Regex** – Done  
- [x] **4. Implement Noise Filtering Script** – Done (`filter_database.py`)  
  - **Note:** Implements "Disambiguation" via category-specific terminology excision.
- [x] **4.5 Pass-Through Merge** – Done (`roberta_merge.py` → `hedge_data.db`)

## Phase 3: Controlled Deletion & Final Dataset Assembly

- [x] **5. Remove Historical References** - **Status:** Completed (`year_deletion.py`)  
  - **Output:** `current_data.db` (only current-year or undated mentions)

- [x] **6. Remove Accounting Standards & Adoption Boilerplate** - **Status:** Completed (high-precision `ACCOUNTING_STANDARDS_REGEX`)  
  - Integrated into the main filtering pass

- [x] **7. Linguistic Intent Filtering** - **Status:** Completed (`active_use_filter.py`)  
  - Removes: Potential/future-use statements, explicit denials, pure PnL sentences.  
  - **Output:** `active_data.db`

- [x] **8. Termination Logic (The "Salvation" Check)** - **Status:** Completed (`termination_filter.py`)  
  - **Logic:** 1. Scan 3-sentence window for termination keywords (`expired`, `matured`, `settled`).
    2. **Conditional Deletion:** If termination is found, check for "Salvation" terms (`outstanding`, `remaining`, `new`).
    3. If *no* salvation terms found → Discard the **entire** window (Fixes "We entered... it expired").
    4. If salvation terms found → Keep window, delete only the specific termination sentence.
  - **Output:** `active_data2.db`

- [x] **9. Quantitative Zero Filtering** - **Status:** Completed (`notional_filter.py`)  
  - **Logic:** Removes sentences where quantitative amounts specifically map to zero for the reporting year (e.g., "$0 million").  
  - **Output:** `active_nonzero_data.db`

- [x] **10. Final Verification (The Gatekeeper)** - **Status:** Completed (`final_verification.py`)  
  - **Logic:** Ensures every remaining sentence contains a **Strong Signal**:
    - An Action Verb ("use", "maintain", "hedge") OR
    - A Quantitative Indicator ("$100m", "notional", "fair value") OR
    - An Active State Descriptor ("outstanding", "open").
  - **Output:** `verified_active_data.db`

## Phase 4: Output & Analysis

- [x] **11. Final Export** - **Status:** Completed (`database_export.py`)  
  - **Input:** `verified_active_data.db`  
  - **Output:** `verified_active_data_active_users.csv`  
  - Generates binary classification flags (IR, FX, CP, EQ) for active year-end users.

## Current Pipeline Architecture (November 2025)

| Stage                                                  | Database File             | Produced By                          |
| ------------------------------------------------------ | ------------------------- | ------------------------------------ |
| Raw extraction                                         | `web_data.db`             | `webpage.py`                         |
| Prepared 3-sentence chunks + full regex cleaning       | `prepared_data.db`        | `filter_database.py`                 |
| Pass-through copy (maintains category alignment)       | `hedge_data.db`           | `roberta_merge.py`                   |
| After past-year deletion                               | `current_data.db`         | `year_deletion.py`                   |
| Potential/future/denial statements removed             | `active_data.db`          | `active_use_filter.py`               |
| Termination Clauses (Window-Level Logic)               | `active_data2.db`         | `termination_filter.py`              |
| Zero-Notional / Quant Zero removed                     | `active_nonzero_data.db`  | `notional_filter.py`                 |
| **Final Verified Active Users** | **`verified_active_data.db`** | `final_verification.py`          |

### Current Meaning of the Databases

| Database                     | Meaning                                                                                     |
|------------------------------|---------------------------------------------------------------------------------------------|
| `active_data.db`             | Contains **any** confirmed derivative usage **during** the fiscal year (may include terminated positions). |
| `active_data2.db`            | Refined list where "Pure Termination" windows have been removed. |
| `verified_active_data.db`    | The **Gold Standard**. Companies with active, outstanding derivatives at fiscal year-end, verified by strong linguistic signals (Verbs/Quants). |

---

## Known Issues, Weaknesses, & Limitations

### 1. The "Split Window" Problem (False Positives)
* **Description:** The pipeline processes text in isolated 3-sentence chunks.
* **Risk:** If a company writes: "We entered into an interest rate swap." (Window A) and "This swap matured on December 31." (Window B), the pipeline will correctly identify and delete Window B (Termination), but Window A remains.
* **Consequence:** The company may be classified as an Active User despite the instrument being terminated, because the termination clause fell outside the context window of the active statement.

### 2. Quantitative Mapping Ambiguity
* **Description:** `notional_filter.py` uses "Implicit Parallel Mapping" to match years to values (e.g., assuming `[Year1, Year2]` maps strictly to `[Value1, Value2]` based on sequence order).
* **Risk:** While standard for "respectively" constructions, inverted sentence structures (e.g., "Value X in Year Y, compared to Value A in Year B") may break this mapping if the regex extraction order does not align with semantic meaning.
* **Consequence:** A zero-exposure year might be misidentified as active, or vice versa.

### 3. Aggressive "Salvation" Logic
* **Description:** The new `termination_filter.py` deletes an *entire* paragraph if it contains termination language (`expired`) without active state language (`outstanding`).
* **Risk:** If a paragraph discusses two distinct instruments—one terminated and one active—but fails to use specific "active state" keywords for the second one (e.g., "We hold swaps."), the entire block is discarded.
* **Mitigation:** `filter_database.py` attempts to split categories into distinct rows, which minimizes this risk for *different* instrument types (e.g., IR vs FX), but it remains a risk for multiple instruments of the *same* category.

### 4. Table Data Omission
* **Description:** The pipeline logic (specifically `filter_matches_with_disambiguation`) often skips or passes through `<TABLE>` tags without the same rigorous sentence-level filtering applied to prose.
* **Consequence:** Companies that disclose active positions *only* in tables (without accompanying narrative text) might be filtered out or processed less accurately than those with narrative disclosures.

### 5. High-Precision / Low-Recall Bias
* **Description:** The final verification step (`final_verification.py`) mandates a "Strong Signal" (Action Verb, Quantitative, or Active State).
* **Risk:** Passive disclosures (e.g., "The policy for our derivatives is reviewed quarterly") are discarded. While this ensures high confidence in the *Active* label, it likely results in False Negatives (missing some quiet active users).