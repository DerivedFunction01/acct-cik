# Roadmap: Derivative Active User Classification

This document outlines the development roadmap for building a classified dataset of SEC filings to identify active derivative users.

## Phase 1: Data Extraction & Pre-training (Completed)

- [x] **1. Extract Raw Text from SEC Filings**

  - **Status:** Done.
  - **Implementation:** The `webpage.py` script successfully fetches SEC filings, parses them, and uses a `COMBINED_REGEX` to extract relevant paragraphs and tables containing derivative-related keywords.
  - **Output:** A raw text database (`web_data.db`) containing potential derivative mentions.

- [x] **2. Domain-Adaptive Pre-Training (DAPT)**
  - **Status:** Skipped - Regex-based approach sufficient.
  - **Rationale:** Advanced regex patterns with context-aware filtering provide adequate precision without requiring ML model training.

## Phase 2: Regex-Based Filtering & Classification

- [x] **3. Filter and Classify with Regex**

  - **Status:** Done.
  - **Task:** Create a Python script that uses advanced regex patterns to process `web_data.db` and classify derivative mentions.
  - **Training Data:** N/A - Rule-based approach.
  - **Output:** A filtered database with category labels (`ir`, `fx`, `cp`, `eq`, `gen`) per sentence.

- [x] **4. Implement Noise Filtering Script**

  - **Status:** Done.
  - **Task:** `filter_database.py` (now renamed to `prepare_database.py` or similar) processes `web_data.db` and applies comprehensive regex-based filtering.
  - **Workflow:** 
    1. Read paragraphs from the `webpage_result` table.
    2. Split into manageable 3-sentence chunks.
    3. Delete trading statements and non-position statements.
    4. Apply category disambiguation for multi-category sentences.
    5. Filter out false positives (equity compensation, legal/litigation, definitions, AOCI-only, PnL-only).
  - **Output:** Cleaned database (`prepared_data.db`) with parallel arrays: sentences and their categories.

- [x] **4.5 Pass-Through Merge (Simulated RoBERTa Step)**
  - **Status:** Done (modified).
  - **Task:** `roberta_merge.py` now performs a simple pass-through copy from `prepared_data.db` to `hedge_data.db` without any ML-based filtering.
  - **Rationale:** Regex filtering in Step 4 is comprehensive enough; no additional ML filtering needed.
  - **Workflow:**
    1. Copy all data from `prepared_data.db`.
    2. Maintain parallel array structure (sentences + categories).
    3. Save to `hedge_data.db` for next phase.

## Phase 3: Controlled Deletion & Final Dataset Assembly

- [ ] **5. Remove Historical References**

  - **Status:** To-Do.
  - **Task:** For each sentence, extract all mentioned years (`YYYY`). If `max(mentioned_years) < reporting_year` of the filing, discard the sentence. This ensures only current year or undated mentions remain.
  - **Output:** A filtered database containing only current or undated mentions of derivatives into `current_data.db`.

- [ ] **6. Category Validation & Refinement**

  - **Status:** To-Do (Optional).
  - **Task:** Review and validate the regex-based category assignments. May involve:
    - Statistical analysis of category distributions
    - Manual spot-checking of edge cases
    - Refinement of disambiguation rules if needed
  - **Goal:** Ensure high confidence in category labels before final analysis.

- [ ] **7. Final Controlled Deletion & Cleanup**

  - **Status:** To-Do.
  - **Task:** Perform final filtering steps on the classified data:
    1. **Remove Non-Essential Context:** Discard sentences kept only for context that do not contain primary derivative keywords.
    2. **Delete Denial Statements:** Remove sentences that explicitly state the company does not use derivatives (should be minimal after earlier filtering).
    3. **Delete Potential/Future Use:** Remove sentences indicating potential future use without confirmation of current use.
  - **Output:** The final, analysis-ready database (`active_data.db`) containing only current, relevant, and categorized derivative mentions.

- [ ] **8. Aggregation & Analysis**
  - **Status:** To-Do.
  - **Task:** Aggregate the cleaned and classified data to generate insights on active derivative users.
  - **Analysis Goals:**
    - Detect companies with active derivative use per category in the current year.
    - Generate summary statistics by category (IR, FX, CP, EQ).
    - Create exportable lists/reports of active derivative users.

## Updated Pipeline Architecture

| Stage                                            | Database File      | Produced By                        |
| ------------------------------------------------ | ------------------ | ---------------------------------- |
| Raw extraction                                   | `web_data.db`      | `webpage.py`                       |
| Prepared 3-sentence chunks + regex cleaning      | `prepared_data.db` | `filter_database.py` (regex-based) |
| Pass-through copy (maintains category alignment) | `hedge_data.db`    | `roberta_merge.py` (pass-through)  |
| After past-year deletion                         | `current_data.db`  | `year_deletion.py`                 |
| Final active-user dataset                        | `active_data.db`   | Final cleanup script (Step 7)      |

## Key Changes from Original Plan

1. **No ML Training Required:** Eliminated RoBERTa pre-training and fine-tuning steps.
2. **Regex-First Approach:** All classification and filtering done via pattern matching and context analysis.
3. **Simpler Pipeline:** Fewer dependencies, faster iteration, easier debugging.
4. **Maintained Structure:** Parallel array architecture (sentences + categories) preserved throughout.
5. **Cost Savings:** No GPU compute, no training data labeling, no model hosting.