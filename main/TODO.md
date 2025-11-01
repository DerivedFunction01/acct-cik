# TODO: Upgrade from BERT Classifier to Generative Instruction-Tuned Model

This document outlines the plan to refactor the project from a multi-label classification system using a BERT-like model to a generative system using a GPT-style, instruction-tuned model (e.g., Phi-3, Llama-3).

## 1. Project Goal: Evolve from Classification to Generative Analysis

The primary objective is to move beyond simple multi-label classification (`"ir": 1, "curr": 1`) to a more powerful generative approach. The new model will not just classify text but will also generate a structured "thought process" and extract key details into a JSON object.

**Current State:** The `generator.py` script produces `(paragraph, labels_dict, label_int)` tuples to train a `AutoModelForSequenceClassification` model.

**Target State:** The new `generator.py` will produce prompt/response pairs to fine-tune an instruction-following model. The model's output will be a structured JSON object.

---

## 2. Phase 1: Redefine the Task and Refactor Data Generation (`generator.py`)

This is the most critical phase. Before any model training, the data generation process must be completely overhauled.

-   **[ ] Define a Canonical JSON Schema for the Model's Output:**
    -   **Done.** The model's sole task is to generate a valid JSON object that conforms to a strict, predefined schema. This schema becomes the new "ground truth" for every training sample.
    -   This approach completely replaces the old `labels` dictionary and `label_int`. The structured data **is** the label.
    -   **Action:** Create a formal JSON Schema file (e.g., `output_schema.json`). This allows for automated validation of the model's output during both training and inference, ensuring consistency and reliability.
    -   **Proposed Canonical Schema:**
        ```json
        {
          "chain_of_thought": "A step-by-step reasoning process. The model must explain *how* it reached its conclusions by citing specific parts of the text. E.g., 'The text mentions 'interest rate swaps' to manage 'variable-rate debt'. The notional amount is $100 million for year 2023. This indicates an active Interest Rate (IR) hedge.'",
          "analysis_summary": "A brief, one-sentence summary of the derivative activity in the provided text.",
          "exposure": {
            "IR": true,
            "FX": true,
            "CP": false,
            "EQ": false
          },
          "mitigation": {
            "IR": true,
            "FX": false,
            "CP": false,
            "EQ": false
          },
          "derivatives": [
            {
              "type": "Interest Rate Swap",
              "category": "IR",
              "status": "current",
              "notional_amount": 100000000,
              "currency": "USD"
            }
          ]
        }
        ```
    -   **Key Change:** The `labels` array is **eliminated**. It is redundant. All necessary information is captured with greater precision in the `derivatives` array. For example, `{"category": "IR", "status": "current"}` is far more explicit than `["ir", "ir_use", "curr"]`.

-   **[x] Refactor `generator.py`:**
    -   **Done.** The new `generator2.py` completely overhauls the generation logic.
    -   Instead of just returning a paragraph and labels, these functions must now assemble and return the full JSON object described above.
    -   The `get_primary_label` and `label_paragraph` functions will be **deprecated and removed**. Their logic is superseded by the direct generation of structured data.

-   **[x] Improve Generation Quality:**
    -   The user expressed a desire for "higher quality compared to using templates randomly selected."
    -   **Action: Implement a "Narrative Generation" strategy.** **Done.** The `generator2.py` script now constructs a coherent, multi-paragraph narrative that mimics the structure of a real SEC filing's risk disclosure section (e.g., Item 7A). This creates more realistic and complex training data.
    -   **Complex Scenarios:** **Done.** The narratives now include more complex situations to train a robust model, such as:
        -   Multiple active instruments of the same type (e.g., two different interest rate swaps).
        -   Conflicting timelines within the same paragraph (e.g., terminating an old FX forward while entering a new FX collar).
        -   Mentions of accounting treatments (e.g., OCI, fair value).
        -   Inclusion of embedded derivatives alongside standard hedges.
    -   **Example of a Complex Narrative and Target JSON:**
        -   **Narrative:** `"<reportingYear>2023</reportingYear> ... To manage interest rate risk, we held an interest rate swap with a notional amount of $150.0 million, which was entered into in 2021 and matures in 2026. In the third quarter of 2023, we entered into an additional pay-fixed interest rate swap with a notional value of $100.0 million... During the first quarter of 2023, our portfolio of foreign currency forward contracts with a notional value of €25.0 million matured and were settled. Subsequently, to hedge against volatility in the British Pound, we entered into a series of foreign currency collar contracts with a total notional value of £40.0 million, which were outstanding at year-end... Additionally, in 2022, the Company issued convertible senior notes... accounted for as an embedded derivative liability..."`
        -   **Target JSON:**
            ```json
            {
              "chain_of_thought": "The text details two separate interest rate swaps: one existing from 2021 ($150M) and a new one from Q3 2023 ($100M), confirming 'current' IR use. For FX, it explicitly states that €25.0M in forwards 'matured and were settled', indicating termination. However, it then describes new, 'outstanding' foreign currency collars in GBP, confirming 'current' FX use. Finally, it identifies a convertible note from 2022 with an 'embedded derivative liability', confirming a 'current' embedded derivative.",
              "analysis_summary": "The company holds multiple active interest rate swaps, has recently entered into new foreign currency collars after settling previous forwards, and carries an embedded derivative liability from convertible notes.",
              "exposure": {
                "IR": true,
                "FX": true,
                "CP": false,
                "EQ": false,
                "EMB": true,
                "GEN": false
              },
              "mitigation": {
                "IR": true,
                "FX": true,
                "CP": false,
                "EQ": false,
                "EMB": true,
                "GEN": false
              },
              "derivatives": [{"type":"Interest Rate Swap","category":"IR","status":"current","notional_amount":150000000,"currency":"USD"},{"type":"Interest Rate Swap","category":"IR","status":"current","notional_amount":100000000,"currency":"USD"},{"type":"Foreign Currency Forward","category":"FX","status":"terminated","notional_amount":25000000,"currency":"EUR"},{"type":"Foreign Currency Collar","category":"FX","status":"current","notional_amount":40000000,"currency":"GBP"},{"type":"Embedded Derivative","category":"EMB","status":"current","notional_amount":12500000,"currency":"USD"}]
            }
            ```
    -   **Proposed Narrative Flow:**
        1.  **Introduction (Market Risk Disclosure):** Start with a broad statement about market risk exposure, similar to the beginning of an "Item 7A. Quantitative and Qualitative Disclosures About Market Risk" section.
            -   *Templates to use:* `hedge_begin_context_templates`.
        2.  **Policy and Strategy:** Describe the company's high-level hedging policy and state that derivatives are not used for trading.
            -   *Templates to use:* `hedge_policy_templates`, `hedge_no_trading_templates`.
        3.  **Specific Instrument Disclosure (The Core):** Introduce the specific derivative instruments being used. This is where the key details (notional amounts, years, types, currency) will be generated, forming the basis for the JSON output.
            -   *Templates to use:* `hedge_position_templates`.
        4.  **Effectiveness and Accounting:** Provide details on hedge effectiveness, documentation, and accounting treatment. This adds crucial context.
            -   *Templates to use:* `hedge_effectiveness_actual_templates`, `hedge_documentation_templates`.
        5.  **Termination/Maturity (Conditional):** For scenarios involving historical or terminated derivatives, conclude the narrative with sentences about swaps expiring or being settled.
            -   *Templates to use:* `hedge_termination_templates`, `hedge_zero_templates`.

---

## 3. Phase 2: Implement the Training Pipeline (`training.py`)

-   **[ ] Adopt Instruction Fine-Tuning Format:**
    -   The training dataset will now consist of prompt-response pairs.
    -   **Input (Prompt):** A consistent instruction, e.g., `Analyze the following text... Text: <paragraph>`.
    -   **Output (Response):** The generated JSON string from `generator.py`.

-   **[ ] Choose a Model and Training Framework:**
    -   **Model:** Based on available hardware (T4, laptop 5070 GPU), `microsoft/phi-3-mini-4k-instruct` (3.8B parameters) is the recommended starting point. It offers an excellent balance of performance and resource efficiency.
    -   **Framework:** Replace the current `Trainer` with Hugging Face's `SFTTrainer` (from the `trl` library), which is specifically designed for supervised fine-tuning of instruction models.
    -   **Technique:** Use Q-LoRA for memory-efficient fine-tuning on consumer-grade GPUs.

---

## 4. Phase 3: Implement the Inference and Analysis Pipeline

-   **[ ] Re-evaluate Text Extraction (`webpage.py`):**
    -   The current method extracts small paragraphs (~1200 chars). With a larger context model (e.g., Phi-3 Mini with a 4k window), we can extract larger, more coherent chunks of text.
    -   **Action:** Modify `webpage.py`'s `filter_by_keywords` function to expand context more aggressively, creating larger text chunks. This reduces the number of separate inferences per filing and provides more context to the model for each analysis, improving its ability to connect related ideas.
    -   The goal is to find a balance between chunk size and the model's context length to maximize comprehension without truncation.

-   **[ ] Update `classify.py` to use the new Generative Model:**
    -   The current workflow of extracting relevant paragraphs from filings (`webpage.py`) remains valid.
    -   Modify `classify.py` to loop through these paragraphs. For each one, it will format the instruction prompt and send it to the fine-tuned generative model.
    -   The script will collect a list of JSON objects (one for each paragraph).

-   **[ ] Update `analysis.py` for Aggregation:**
    -   The `PredictionsProcessor` needs to be rewritten.
    -   Its new job is to take the list of JSON outputs for a single filing and aggregate them into a master report.
    -   **New Aggregation Logic:**
        -   Combine `analysis_summary` and `chain_of_thought` fields to create a comprehensive audit trail.
        -   **De-duplicate and merge** the `derivatives` arrays to create a master list of all instruments mentioned in the filing.
        -   **Handle conflicting or evolving information.** The `chain_of_thought` must be detailed enough to capture status changes. For example, if one chunk indicates a `"status": "current"` swap and a later chunk mentions its termination, the aggregation logic must correctly resolve the final status to `"terminated"`. The old `term` label was a workaround for this; the new system handles it explicitly through status aggregation.
        -   **Derive Primary Labels (Post-Processing):** After aggregation, create a new function to derive simple, high-level flags (e.g., `is_ir_user: true`) from the final structured data for easy filtering or downstream use. This moves the "labeling" task from a model input to a flexible analysis output.

---

## 5. Deprecation Plan

-   The concept of a single "primary label" (0-29) will be deprecated.
-   The `labels` dictionary (e.g., `{"ir": 1, "curr": 1}`) is fully deprecated and will be removed from the data generation and analysis process.
-   The `LabelMapper` logic in `analysis.py` will be replaced by functions that operate directly on the aggregated JSON, deriving any necessary flags or classifications as a final step.
