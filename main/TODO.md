# Roadmap: Derivative Active User Classification

This document outlines the development roadmap for building a classified dataset of SEC filings to identify active derivative users.

## Phase 1: Data Extraction & Pre-training (Completed)

- [x] **1. Extract Raw Text from SEC Filings**
  - **Status:** Done.
  - **Implementation:** The `webpage.py` script successfully fetches SEC filings, parses them, and uses a `COMBINED_REGEX` to extract relevant paragraphs and tables containing derivative-related keywords.
  - **Output:** A raw text database (`web_data.db`) containing potential derivative mentions.

- [x] **2. Domain-Adaptive Pre-Training (DAPT)**
  - **Status:** Done.
  - **Implementation:** A RoBERTa model was pre-trained on general SEC filing snippets to adapt it to financial and legal language. The `create_hf_dataset.py` script is used to generate the training corpus from the extracted text.
  - **Goal:** Improve model performance on downstream tasks by familiarizing it with the specific domain.

## Phase 2: Fine-Tuning for Classification & Filtering

- [X] **3. Fine-Tune RoBERTa for Noise Classification**
  - **Status:** Done.
  - **Task:** Fine-tune the domain-adapted RoBERTa model for a binary text classification task: Filtering out false positives, such as accounting standard s updates, legal/litigation, equity compensation, and definitions.
  - **Training Data:** Requires a labeled dataset of sentences, distinguishing between true derivative discussions and noise (e.g., employee stock options, legal boilerplate, forward-looking statements). Done via simple regex filtering in the database for candidate sentences, with automated labeling based on keyword presence.
    - **Output:** A fine-tuned RoBERTa model capable of classifying sentences as `std` (accounting standards noise) vs. `hedge` (true derivative discussion).

- [x] **4. Implement Noise Filtering Script**
  - **Status:** Done.
  - **Task:** Create a new Python script that uses the fine-tuned noise classification model (from Step 3) to process `web_data.db`. Using `classify.py` for classification and `filter_database.py` to split up text chunks into manageable 3-sentence paragraphs.
  - **Workflow:**
    0. Prepare the database by splitting long paragraphs into smaller chunks (3 sentences each) using `filter_database.py`. Delete all trading statements that are not relevant.
    1. Read paragraphs from the `webpage_result` table.
    2. For each paragraph send it to the model.
    3. Classify each sentence within the paragraph as `hedge` or other false positive categories (`std`, `law`, `cmp`,  etc.).
    4. Store the model results back into the database `server_result`, marking sentences for retention or deletion.

- [] **4. Start using the Noise Filtering Script**
  - **Status:** To-Do.
  - **Task:** Run the script, this will take time, so I am going to skip this step and assume it works for now.
  - **Workflow:**
    1. Run the noise filtering script on the existing `web_data.db`.
    2. Merge the results into the database for further processing.

- [ ] **4.5 Implement Discarding Script**
  - **Status:** To-Do.
  - **Task:** Create a new Python script that takes the results from step 4 to process `web_data.db`. 
  - **Workflow:**
    1. Read paragraphs from the `webpage_result` table.
    2. Retrieve the classification results from the `server_result` table.
    3. Combine the results to identify and retain only the sentences classified as relevant (`hedge`). Use a special regex to identify sentences that contain derivative keywords to ensure no relevant information is lost in case of false negatives.
    4. Discard false positives.
    5. Store the cleaned, relevant-only paragraphs in a new database (e.g., `clean_web_data.db`).

## Phase 3: Controlled Deletion & Final Dataset Assembly

- [ ] **5. Remove Historical References**
  - **Status:** To-Do.
  - **Task:** For each sentence, extract all mentioned years (`YYYY`). If `max(mentioned_years) < reporting_year` of the filing, discard the sentence. This ensures only current year or undated mentions remain, which is essential for the "active any use in current year" use case.
  - **Output:** A filtered database containing only current or undated mentions of derivatives. Since we already determined the category, we can keep that metadata to determine active users. Note: peform a loose regex filter again to ensure no sentences without derivative keywords remain, or else we might have sentences that are only context.

- [ ] **6. Fine-Tune RoBERTa for High-Level Classification**
  - **Status:** To-Do.
  - **Task:** Fine-tune a separate RoBERTa model (or the same one, depending on strategy) to perform multi-label or multi-class classification on the *relevant* sentences. Reason: the current regex will not be able to capture all forms of derivative instruments and usage contexts.
  - **Classification Schema:**
    - **Category:** `interest_rate`, `foreign_exchange`, `commodity`, `equity`, `generic_other`.
    - **Usage Indicator (Optional but Recommended):** `active_use` vs. `passive_mention` vs `denial`. This is the core of the "active user" goal. We should have deleted all trading statements, so `denial` should be straightforward. Also, since we are supposed to be left with only current year mentions, `active_use` should be easier to identify.
        - `active_use`: Sentences indicating current or recent usage of derivatives for hedging or trading purposes.
        - `passive_mention`: Passive statements such as PnL impact, accounting treatment.
        - `denial`: Explicit statements denying the use of derivatives or none at all. 
  - **Training Data:** Requires a labeled dataset of relevant sentences categorized by derivative type and usage
  - **Goal:** Retain high-level metadata about each sentence before the final deletion stage. The output should be structured data, not just text.

- [ ] **7. Final Controlled Deletion & Cleanup**
  - **Status:** To-Do.
  - **Task:** Perform final filtering steps on the classified data:
    1. **Remove Non-Essential Context:** Discard sentences kept only for context that do not contain primary derivative keywords, which may include PnL impact statements or accounting treatment without active usage context.
    2. **Delete AOCI-Only Mentions:** Remove sentences that only mention AOCI, as these are not indicative of active use.
    3. **Delete Denial Statements:** Remove sentences that explicitly state the company does not use derivatives.
    4. **Delete Potential use but not confirmed:** Remove sentences that indicate potential future use without confirmation of current use.
  - **Output:** The final, analysis-ready database (`final_web_data.db`) containing only current, relevant, and categorized derivative mentions.


- [ ] **8. Aggregation & Analysis**
  - **Status:** To-Do.
  - **Task:** Aggregate the cleaned and classified data to generate insights on active derivative users.
  - **Analysis Goals:**
    - With controlled deletion, detect if there is still any mentions of active use classified from Step 5. If none exist, then it meant that controlled deletion deleted all previous years mentions, leaving only current year/non year mentions.
