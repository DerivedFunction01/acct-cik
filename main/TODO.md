# Roadmap: Derivative Active User Classification

This document outlines the development roadmap for building a classified dataset of SEC filings to identify active derivative users.

## Phase 1: Data Extraction & Pre-training (Completed)

- [x] **1. Extract Raw Text from SEC Filings**  
  - **Status:** Done.  
  - **Implementation:** `webpage.py` → `web_data.db`

- [x] **2. Domain-Adaptive Pre-Training (DAPT)**  
  - **Status:** Skipped – regex-based approach sufficient.

## Phase 2: Regex-Based Filtering & Classification

- [x] **3. Filter and Classify with Regex** – Done  
- [x] **4. Implement Noise Filtering Script** – Done (`filter_database.py`)  
- [x] **4.5 Pass-Through Merge** – Done (`roberta_merge.py` → `hedge_data.db`)

## Phase 3: Controlled Deletion & Final Dataset Assembly

- [x] **5. Remove Historical References**  
  - **Status:** Completed (`year_deletion.py`)  
  - **Output:** `current_data.db` (only current-year or undated mentions)

- [x] **6. Remove Accounting Standards & Adoption Boilerplate**  
  - **Status:** Completed (high-precision `ACCOUNTING_STANDARDS_REGEX`)  
  - Integrated into the main filtering pass

- [x] **7. Final Controlled Deletion & Cleanup**  
  - **Status:** Completed (`active_use_filter.py`)  
  - Removes: non-essential context sentences, explicit denials, potential/future-use statements, pure PnL sentences  
  - **Output:** `active_data.db`

- [x] **8. Separate Active Year-End vs. Terminated Users**  
  - **Status:** Completed (`termination_filter.py` + `notional_filter.py`)  
  - **Workflow:**
    1. Start from `active_data.db`
    2. Remove all sentences containing termination language  
       (`expired`, `matured`, `terminated`, `settled`, `closed out`, etc.)
    3. Remove all sentences indicating zero/no outstanding notional  
       (`no outstanding`, `notional amount of zero`, `no longer outstanding`, etc.)
    4. Final classification:
       - **Any sentences remain** → company has **active derivatives at year-end**  
         → saved to **`active_year_end.db`**
       - **No sentences remain** → company used derivatives during the year but had **none outstanding at year-end**  
         → saved to **`active_data2.db`** (formerly called `terminated_during_year.db`)

- [ ] **9. Aggregation & Analysis**  
  - Generate final company lists by category from `active_year_end.db`  
  - Summary statistics, export CSVs, research datasets, etc.

## Current Pipeline Architecture (November 2025)

| Stage                                                  | Database File             | Produced By                          |
| ------------------------------------------------------ | ------------------------- | ------------------------------------ |
| Raw extraction                                         | `web_data.db`             | `webpage.py`                         |
| Prepared 3-sentence chunks + full regex cleaning       | `prepared_data.db`        | `filter_database.py`                 |
| Pass-through copy (maintains category alignment)       | `hedge_data.db`           | `roberta_merge.py`                   |
| After past-year deletion                               | `current_data.db`         | `year_deletion.py`                   |
| Accounting standards & boilerplate removed             | (handled in main filter)  | –                                    |
| Potential/future/denial statements removed             | `active_data.db`         | `active_use_filter.py`               |
| Termination + zero-notional sentences removed          | `active_data2.db`         | `termination_filter.py` + `notional_filter.py` |
| **Final active year-end users**                        | **`active_year_end.db`**  | `notional_filter.py` (when sentences remain) |

### Current Meaning of the Databases

| Database                     | Meaning                                                                                     |
|------------------------------|---------------------------------------------------------------------------------------------|
| `active_data.db`             | Contains **any** confirmed derivative usage **during** the fiscal year (including terminated positions) |
| `active_data2.db`            | Companies that had derivative activity **during the year** but **none outstanding at year-end** (i.e., “terminated during year”) |
| `active_year_end.db`         | Companies with **active, outstanding derivatives at fiscal year-end** – the true “Active Users” population |
