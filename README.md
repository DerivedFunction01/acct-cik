# Hedge and Derivative Analysis Result

## Overview

Automated pipeline analyzes SEC filings (10-Ks, 20-Fs) for derivatives/hedging via keyword search and fine-tuned ML model. Classifies interest rate (IR), FX, commodity (CP), equity (EQ), general (GEN) hedges; warrants; embedded derivatives; speculative/contextual mentions.

**Pipeline**: Modular `AnalysisPipeline` in `run_analysis.py` orchestrates data loading, processing, and optional steps (comparison, accuracy sampling, firm inspector, custom analyzers, sentence labeling).

## Key Outputs

- **Keyword-Model Comparison**: `keyword_model_comparison.xlsx` (summary, detailed, confusion matrices).
- **Labeled Sentences**: `./analysis_output/labeled_sentences/` (per-category Excel: e.g., `sentences_IR_Hedge.xlsx`).
- **Accuracy Sample**: `accuracy_check_sample.xlsx` (stratified by predicted label for manual review).
- **URL Inspector**: `url_sentence_analysis.xlsx` (detailed per-firm sentences from `firm_urls.csv`).
- **Synthetic Training Data**: `training_data.xlsx` / `.parquet` (generated via `generator.py`).

## Limitations

⚠️ **File Sizes**: Sentence files >100MB; use Parquet for efficiency.  
⚠️ **Coverage**: Filters derivative keywords; misses non-explicit mentions.  
⚠️ **Duplicates**: Includes repeated disclosures across years/sections.  
⚠️ **Foreign Filers**: 20-Fs may lack full content.  
⚠️ **Model Scope**: Research-grade; not for audits. ~5% data gaps from extraction failures.  
⚠️ **Synthetic Data**: Template-based; limited novelty but captures patterns.

## Pipeline Execution

Run via `python run_analysis.py` with `RunOptions`:
- `run_comparison=True`: Merges keyword/model flags; generates metrics.
- `run_accuracy_check=True`: Samples 50 sentences/label for review.
- `run_firm_inspector=True`: Analyzes URLs in `firm_urls.csv`.
- `run_custom_analyzers=True`: Executes registered `BaseAnalyzer` subclasses.
- `generate_sentence_files=True`: Creates category-specific labeled Excels.

**Config**: `Config` class auto-detects resources (CPU/RAM/Colab); sets thresholds (e.g., 0.25 confidence).

## Data Generation

**Synthetic Training Data** (`generator.py`):  
- Templates from `template/` modules (hedges, common, other, warrants/embedded).  
- Parallel generation (ThreadPoolExecutor); 1000 samples/label default.  
- Categories: Active/inactive hedges (IR/FX/CP/EQ/GEN), warrants/embedded (current/historic/speculative), noise.  
- **Labeling**: Each generated paragraph is assigned a multi-hot `labels` dictionary (e.g., `{"ir": 1, "curr": 1, "ir_use": 1, ...}`). A simplified `get_primary_label` function then determines a single integer `label` for stratified training data.
- **Cleanup**: Regex fixes (e.g., "We's" → "Our"); random nil/notional removal.

## Text Extraction Methodology

The `colab.py` script orchestrates the initial data gathering and text extraction from SEC filings. To avoid processing unrelated text, a strict keyword search filters content before model classification. The filtering uses specific regular expressions and then expands the context around each match to create a meaningful paragraph.

**Key Steps in `colab.py`**:
1.  **Fetch**: Downloads filing URLs from the SEC EDGAR API.
2.  **Parse**: Extracts clean text content from the raw HTML/text filings.
3.  **Filter & Expand**: Uses the regex patterns below to find relevant sentences and then expands the context around them to a length of ~1200 characters, ensuring the model has enough information.

### Interest Rate Derivatives (IR_REGEX)
Matches a **core term** + **base type** or a **specific phrase**.
- **Core Terms**: `interest-rate`, `SOFR`, `LIBOR`, `treasury-rate`, `fixed-rate`, `floating-rate`, etc.
- **Base Types**: `swap`, `forward`, `option`, `hedge`, `derivative`, `instrument`, etc.
- **Specific Phrases**: `zero-coupon swap`, `FRA`, `treasury lock`.
- *Example*: `interest-rate swap`, `treasury lock`.

### Foreign Exchange / Currency Derivatives (FX_REGEX)
Matches a **core term** + **base type** or a **specific phrase**.
- **Core Terms**: `foreign-exchange`, `foreign-currency`, `cross-currency`, `FX`.
- **Base Types**: `swap`, `forward`, `option`, `hedge`, `derivative`, `instrument`, etc.
- **Specific Phrases**: `NDF`, `non-deliverable forward`.
- *Example*: `foreign-exchange contract`, `currency option`.

### Commodity Price Derivatives (CP_REGEX)
Matches a **core term** + **base type** or a **specific phrase**.
- **Core Terms**: `commodity`, `crude oil`, `natural gas`, `aluminum`, `coal`, and many other specific commodities, with optional suffixes like `-price` or `-related`.
- **Base Types**: `swap`, `forward`, `option`, `hedge`, `derivative`, `instrument`, etc.
- **Specific Phrases**: `commodity index`.
- *Example*: `commodity swap`, `natural gas hedge`, `crude oil-price forward`.

### Equity Derivatives (EQ_REGEX)
Matches a **core term** + **base type** or a **specific phrase**.
- **Core Terms**: `equity`, `equity-related`.
- **Base Types**: `swap`, `forward`, `option`, `hedge`, `derivative`, `instrument`, etc.
- **Specific Phrases**: `call options`, `put options`, `equity collar`.
- *Example*: `equity swap`, `call options`.

### General Derivative & Hedge Terminology (GEN_REGEX)
Matches a **base type** + **suffix** or a **specific phrase**.
- **Base Types**: `swap`, `forward`, `option`, `hedge`, `derivative`, `instrument`, etc.
- **Suffixes**: `agreements`, `contracts`, `instruments`, `arrangements`, `assets`, `liabilities`.
- **Specific Phrases**: `embedded derivatives`, `notional amounts`, `over-the-counter derivatives`, `total-return swap`.
- *Example*: `swaps agreements`, `derivative instruments`, `hedge liabilities`, `notional values`.

**Future Consideration**: Time permitting, keyword terms could be relaxed to include more derivative liabilities/warrants and embedded derivatives, though this may impact model accuracy if keywords are incorrectly associated with labels.
Database: SQLite `web_data.db` (tables: `report_data`, `webpage_result`, `server_result`, `fail_results`).

## Label Mapping (`keywords_find.json`)

25 primary labels (0-24):  
- 0-2: GEN (Current/Historic/Spec).  
- 3-5: IR (Current/Historic/Spec).  
- 6-8: FX; 9-11: CP; 12-14: EQ.  
- 15-19: Contexts (GEN/IR/FX/CP/EQ).  
- 20-21: Warrant (Current/Historic).  
- 22-23: Embedded (Current/Historic).  
- 24: Irrelevant Non-Hedge.
 
**Multi-labels**: `ir`, `fx`, `cp`, `eq`, `gen` + `_use` + `curr`, `hist`, `spec` + `warr`, `emb`, `irr`.  
**`LabelMapper` Logic**: The `analysis.py` module contains the primary logic for converting the model's multi-label probability outputs into a final, prioritized list of labels. It uses a sophisticated priority system:
1.  **Current Hedge Usage** (e.g., `ir_use` + `curr` signals)
2.  **Historical Hedge Usage**
3.  **Speculative Hedge Usage**
4.  **Warrants & Embedded Derivatives**
5.  **Context-only Mentions** (e.g., `ir` signal without a `_use` or time signal)
6.  **Irrelevant**

## Model Processing

The model processing pipeline consists of two main stages:

1.  **Classification (`classify-new.py`)**: This script reads the extracted sentences from the database, sends them in batches to a running model server (e.g., Flask API), and stores the raw probability predictions back into the `server_result` table in the database.
2.  **Analysis (`analysis.py`)**:
    - **Load**: `DataLoader` queries the DB for the raw sentence predictions.
    - **Aggregate**: `PredictionsProcessor` counts labels that are above the confidence threshold for each firm-year to create summary flags (e.g., `model_ir_user`).

## Comparison Analysis (`comparison.py`)

Merges keyword CSV (`derivatives_data.csv`) vs. model flags.  
Metrics: Accuracy/Precision/Recall/F1 per category (IR/FX/CP/Hedges/All).  
Confusion matrices in Excel.

| Category | Accuracy | Precision | Recall | F1 |
|----------|----------|-----------|--------|----|
| IR      | XX%     | XX%      | XX%   | XX% |
| FX      | XX%     | XX%      | XX%   | XX% |
| ...     | ...     | ...      | ...   | ... |

## **Metrics Explained**

### How Scores Are Calculated

### Accuracy
Percentage of correct predictions (agreements):
```
Accuracy = (True Positives + True Negatives) / Total Observations × 100
```

**Example**: If we analyzed 1,000 company-years:
- 850 agreements (700 TN + 150 TP)
- 150 disagreements (100 FP + 50 FN)
- Accuracy = (150 + 700) / 1,000 × 100 = **85%**

### Precision
When model predicts "derivative user," how often is it correct (agrees with keywords)?
```
Precision = True Positives / (True Positives + False Positives) × 100
```

### Recall (Sensitivity)
Of all keyword-identified derivative users, what percentage did the model find?
```
Recall = True Positives / (True Positives + False Negatives) × 100
```

### F1 Score
Balanced measure combining precision and recall:
```
F1 = 2 × (Precision × Recall) / (Precision + Recall)
```

**Why it matters**: High F1 means the model is both precise (few false alarms) and comprehensive (catches most cases).

## Ground Truth and Validation

### Important Caveat

This does NOT mean keywords are perfect. It means we use them as our validation baseline since they represent the original, established methodology. 

**The model may actually identify cases that keywords miss** (shown as "False Positives"), which could represent genuine improvements rather than errors. Manual review of disagreements is recommended to distinguish between:
- Model improvements (catching cases keywords missed)
- Model errors (incorrect classifications)

### Interpreting Results

### High Agreement (Accuracy > 90%)
The model and keywords largely agree. The model is a reliable alternative to keyword searching.

### High Precision, Lower Recall
Model is conservative. It rarely makes mistakes but might miss some cases. **Action**: Review False Negatives to understand what was missed.

### Lower Precision, High Recall
Model is aggressive. It catches more cases but may have more false alarms. **Action**: Review False Positives to determine if they're genuine improvements or errors.

### Improvement from Current to Current+Historic
Positive improvements show that including historical mentions enhances detection. This is especially valuable for companies that discuss past derivative use.

### Keyword vs. Model Classification Scope

### Directly Comparable Categories:
- Interest Rate (IR) hedging
- Foreign Exchange (FX) hedging
- Commodity Price (CP) hedging

### Excluded from Comparison:
- Unknown / general hedge mentions
- Derivative liabilities or warrants
- Embedded derivatives

This keeps evaluation focused on true hedging categories where both methods can be directly compared.

## Accuracy Sampling (`accuracy.py`)

Stratified: 50 sentences/primary label.  
Columns: sentence, predicted_primary_label, multilabels (top-5), reviewer fields, firm flags.  
Merge: Optional firm-year model flags.

## Firm Inspector (`firm_inspector.py`)

Processes `firm_urls.csv`: Fetches DB sentences; labels; summarizes per-CIK/year (counts, user flags).  
Sheets: Summary + per-firm details.

## Sentence Labeling (`reporting.py`)

Explodes multi-labels; assigns mutually exclusive categories (priority:  Hedges > Warrant/Embedded > Spec > Context > Irrelevant).  
Parallel writes: One Excel workbook per category group (e.g., `sentences_IR_Hedge.xlsx`).

## Usage Tips

- **Review**: Start with accuracy sample; validate FP/FN.  
- **Trends**: Pivot on CIK/year for hedge evolution.  
- **Custom**: Extend `BaseAnalyzer` for new analyses.  
- **Resources**: Colab-friendly; auto-adjusts workers/chunks.

## Technical Notes

- **DB Schema**: webpage_result (url, matches), report_data (cik/year/url), server_result (url, server_response).  
- **Parallelism**: ProcessPoolExecutor for CPU tasks.  
- **Version**: Modular v2 (Oct 2025); backward-compatible with v1 keywords.  

For issues: Check logs; ensure DB populated.