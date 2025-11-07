# TODO: Upgrade from BERT Classifier to Generative Instruction-Tuned Model

This document outlines the plan to refactor the project from a multi-label classification system using a BERT-like model to a generative system using a GPT-style, instruction-tuned model (e.g., Phi-3, Llama-3).

## 1. Project Goal: Evolve from Classification to Generative Analysis

The primary objective is to move beyond simple multi-label classification (`"ir": 1, "curr": 1`) to a more powerful generative approach. The new model will not just classify text but will also generate a structured "thought process" and extract key details into a valid JSON object.

**Current State:** The `generator.py` script produces `(paragraph, labels_dict, label_int)` tuples to train a `AutoModelForSequenceClassification` model.

**Target State:** The new `generator.py` will produce prompt/response pairs to fine-tune an instruction-following model. The model's output will be a structured JSON object.

---

## 2. Phase 1: Redefine the Task and Refactor Data Generation (`generator.py`)

This is the most critical phase. Before any model training, the data generation process must be completely overhauled.

-   **[x] Define a Canonical Schema for the Model's Output:**
    -   **Done.** The model's sole task is to generate a valid JSON object that conforms to a strict, predefined schema. This schema becomes the new "ground truth" for every training sample.
    -   This approach completely replaces the old `labels` dictionary and `label_int`. The structured data **is** the label.
    -   **Action:** Create a formal Schema file. This allows for automated validation of the model's output during both training and inference, ensuring consistency and reliability.
    -   **Proposed Canonical Schema:**
        ```json
        {
          "chain_of_thought": "A step-by-step reasoning process. The model must explain *how* it reached its conclusions by citing specific parts of the text. E.g., 'The text mentions 'interest rate swaps' to manage 'variable-rate debt'. The notional amount is $100 million for year 2023. This indicates an active Interest Rate (IR) hedge.'",
          "analysis_summary": "A brief, one-sentence summary of the derivative activity in the provided text.",
          "exposure": {
            "IR": true,
            "FX": true,
            "CP": false,
            "EQ": false,
            "GEN": false
          },
          "mitigation": {
            "IR": "current",
            "FX": "current",
            "CP": "none",
            "EQ": "none",
            "GEN": "unknown"
          },
          "derivatives": [
            {
              "type": "Interest Rate Swap",
              "category": "IR",
              "level": "individual",
              "status": "current", 
              "amount": 100000000,
              "currency": "USD",
              "value_type": "notional"
            }
          ]
        }
        ```
    -   **Key Change:** The old `labels` array is **eliminated**. It is redundant. All necessary information is now captured with greater precision in the `derivatives` array and the `exposure`/`mitigation` maps.

-   **[x] Refactor `generator.py`:**
    -   **Done.** The new `generator2.py` completely overhauls the generation logic.
    -   Instead of just returning a paragraph and labels, these functions must now assemble and return the full JSON object described above.
    -   The `get_primary_label` and `label_paragraph` functions will be **deprecated and removed**. Their logic is superseded by the direct generation of structured data.

-   **[x] Improve Generation Quality:**
    -   **Action: Implement a "Narrative Generation" strategy.** **Done.** The `generator2.py` script now constructs a coherent, multi-paragraph narrative that mimics the structure of a real SEC filing's risk disclosure section (e.g., Item 7A). This creates more realistic and complex training data.
    -   **Complex Scenarios:** **Done.** The narratives now include more complex situations to train a robust model, such as:
        -   Multiple active instruments of the same type (e.g., two different interest rate swaps).
        -   Conflicting timelines within the same paragraph (e.g., terminating an old FX forward while entering a new FX collar).
        -   Mentions of accounting treatments (e.g., OCI, fair value).
        -   Inclusion of embedded derivatives alongside standard hedges.

-   **[x] Port Contextual "Noise" Generation:**
    -   **[x] Port Contextual "Noise" Generation:** The old `generator.py` had functions that created realistic, non-derivative sentences to provide context around the main topic. This "noise" is crucial for training the model to distinguish between a discussion *about* risk exposure and the use of a derivative to *hedge* that risk. Done.
    -   **[x] Port IR/Debt Context:** Done. `DebtContextSentence` has been created and integrated into the IR narrative generation in `generator2.py`.
    -   **[x] Port FX Context:**
        -   **[x] Action:** Create a new `FXContextSentence` class in `defs/fx_data.py`. Done.
    -   **[x] Port CP Context:**
        -   **[x] Action:** Create a new `CPContextSentence` class in `defs/cp_data.py`. Done.
    -   **[x] Port EQ Context:**
        -   **[x] Action:** Create a new `EQContextSentence` class in `defs/eq_data.py`. Done.
    -   **[x] Integrate New Context Classes:**
        -   **[x] Action:** Integrate the `build()` methods for `FXContextSentence` and `CPContextSentence` into `generator2.py`'s `_generate_category_narrative` function for their respective categories. This is done probabilistically to inject relevant, non-derivative context. Done.
        -   **[x] Action:** Integrate the `build()` method for `EQContextSentence` into `generator2.py`'s `_generate_category_narrative` function for the EQ category. Done.

-   **[x] Improve Generation Quality (Continued):**
    -   **[x] Further Improvements to Generation Quality:**
        -   **[x] Probabilistic Component Generation:** In `generator2.py`, introduce probabilities for generating certain narrative sections to increase variety.
            -   **Drop Mitigation:** Added a random chance to skip generating the `MitigationSentence` for a category, even if instruments exist. This simulates filings that are less explicit about their strategy.
            -   **Drop Policy:** Added a random chance to skip generating the `AccountingPolicySentence` section.
            -   **Drop Details:** Added a random chance to skip generating detailed instrument disclosures (`TimelineSentence`, individual `NotionalSentence`), relying only on the aggregate summary. Done via `active_instrument_mention` probability.
        -   **[x] Implement "Noise-Only" Scenarios:** Create scenarios containing only contextual "noise" without any derivative instruments to improve negative sampling.
            -   **"Noise-Only" logic:** In `generator2.py`, a path was added that, for a given category (e.g., IR), generates only `DebtContextSentence` paragraphs without any `IRInstrument` or `NotionalSentence` for derivatives. This is crucial for training the model to distinguish between discussions *about* risk (e.g., having debt) and the use of derivatives to *hedge* that risk.
        -   **[x] Create Evidence for Contextual Noise:** Create a new evidence class for contextual noise sentences so the model can explain *why* a text is not a derivative disclosure.
            -   **Define `ContextEvidence` class:** In `defs/instrument_definitions.py`, the `ContextEvidence` class has been created.
                -   It should store the category of the context (e.g., "IR", "FX") and the text of the sentence.
                -   Its `to_string()` method should generate a `chain_of_thought` entry like: "The text discusses debt obligations but does not mention any derivative instruments used to hedge this interest rate exposure."
            -   **Integrate into Context Sentence classes:** Done. The various context sentence builders now return `ExposureEvidence` or `ContextEvidence`, which serves this purpose.
            -   **Update `generate_json_from_scenario`:** Done. The logic now handles `is_noise_only_scenario` correctly, producing an empty `derivatives` list and appropriate summary.
        -   **[x] Simulate "No Derivative" Chain of Thought:** For scenarios with only contextual noise, the `chain_of_thought` should simulate a human-like review process.
            -   **Enhance `generate_json_from_scenario`:** Done. The `is_noise_only_scenario` block in `generate_json_from_scenario` now generates a human-like review process in the `chain_of_thought`.
                -   "The text discusses [risk area, e.g., debt obligations], which could involve derivatives. I will scan for keywords like 'swap', 'hedge', or 'forward'."
                -   "After reviewing the text, no explicit mention of derivative instruments was found."
                -   "Let me review the text one more time to ensure no mentions were missed. The text confirms exposure to [risk area] but does not detail any hedging instruments."
        -   **[x] Refactor `Table` Class for Reusability:**
            -   **Create `defs/table_definitions.py`:** Done.
            -   **Generalize `Table` class:** Done. The `GenericTable` class now handles formatting.
                -   It should accept a list of headers, a list of data rows (as lists of strings), column widths, and alignments.
                -   The `build()` method should focus solely on formatting the text-based table with proper spacing and SEC tags (`<S>`, `<C>`).
            -   **Create Specific Table Builders:** New classes (e.g., `DerivativeNotionalTable`, `AOCITable`) that *use* the generic `Table` class have been created. These new classes contain the logic for preparing the specific data and headers for their respective table types.
            -   **Update `generator2.py`:** The `_generate_category_narrative` function has been modified to call the new specific table builder classes.
        -   **[x] Implement "Policy-Only" Scenarios:** Create scenarios that only contain policy discussions about derivatives (e.g., effectiveness testing, accounting treatment) without any corresponding instruments. This will train the model to recognize disclosures that talk *about* derivatives but don't confirm their *use*.
            -   **Create "Policy-Only" Archetype/Logic:** In `generator2.py`, a path or a new `ScenarioArchetype` has been added that generates a `GenerationScenario` with a `RiskManagementPolicy` containing `CategorySpecificPolicy` objects, but an empty `instruments` list.
            -   **Update Narrative Generation:** `generate_narrative_from_scenario` now correctly generates paragraphs from `_generate_narrative_accounting` and `_generate_narrative_policy` even when no instruments are present. The narrative contains text about hedge effectiveness, documentation, and accounting, but no sentences with notional amounts.
            -   **Verify JSON Output:** For these scenarios, the final JSON has an empty `derivatives` list. The `analysis_summary` reflects that no active derivatives were found, and the `chain_of_thought` explains that while policies were discussed, no evidence of active instruments was found.

-   **[x] Implement Non-Financial "Noise-Only" Scenarios:** Create scenarios containing completely non-financial text to train the model to identify and ignore irrelevant content. This is crucial for real-world application where extracted text chunks may not be related to SEC filings.
    -   **Action: Integrate a source for non-financial text.** Using a library like `wikipedia` is an excellent idea. A new function in `generator2.py` can fetch random Wikipedia articles.
    -   **Action: Create a "Non-Financial Noise" Archetype/Logic.** Add a path in `generator2.py` that generates a `GenerationScenario` containing only text from the non-financial source.
    -   **Action: Verify JSON Output for Non-Financial Noise.** For these scenarios, the `chain_of_thought` should explain that the text is not a financial disclosure, and the `derivatives` list should be empty. The `analysis_summary` should state that the text is unrelated to financial reporting.

---

## 3. Phase 2: Implement the Training Pipeline (`training.py`)

-   **[x] Adopt Instruction Fine-Tuning Format:**
    -   The training dataset will now consist of prompt-response pairs.
    -   **Input (Prompt):** A consistent instruction, e.g., `Analyze the following text... Text: <paragraph>`.
    -   **Output (Response):** The generated JSON string from `generator.py`.

-   **[x] Choose a Model and Training Framework:**
    -   **Model:** The `training2.py` script implements `unsloth/Qwen3-4B-Thinking-2507-unsloth-bnb-4bit`, a powerful 4B parameter model. This choice is excellent and aligns with the project's goals.
    -   **Framework:** `training2.py` correctly uses Hugging Face's `SFTTrainer` from the `trl` library.
    -   **Technique:** The training script successfully implements Q-LoRA via the Unsloth library for highly efficient fine-tuning.

---

## 4. Phase 3: Implement the Inference and Analysis Pipeline (In Progress)

-   **[ ] Re-evaluate Text Extraction (`webpage.py`):**
    -   The current method extracts small paragraphs (~1200 chars). With a larger context model (e.g., Phi-3 Mini with a 4k window), we can extract larger, more coherent chunks of text.
    -   **Action:** Modify `webpage.py`'s `filter_by_keywords` function to expand context more aggressively, creating larger text chunks. This reduces the number of separate inferences per filing and provides more context to the model for each analysis, improving its ability to connect related ideas.
    -   The goal is to find a balance between chunk size and the model's context length to maximize comprehension without truncation.

-   **[ ] Update `classify.py` to use the new Generative Model:**
    -   **In Progress.** This has been implemented in `test2.py`. It reads prompts, sends them to the `server2.py` endpoint, and collects the resulting JSON objects. The logic can be ported to a new `classify2.py` when ready.

-   **[ ] Update `analysis.py` for Aggregation:**
    -   The `PredictionsProcessor` needs to be rewritten.
    -   Its new job is to take the list of JSON outputs for a single filing and aggregate them into a master report.
    -   **New Aggregation Logic:**
        -   Combine `analysis_summary` and `chain_of_thought` fields to create a comprehensive audit trail.
        -   **De-duplicate and merge** the `derivatives` arrays to create a master list of all instruments mentioned in the filing.
        -   **Handle conflicting or evolving information.** The `chain_of_thought` must be detailed enough to capture status changes. For example, if one chunk indicates a `"status": "current"` swap and a later chunk mentions its termination, the aggregation logic must correctly resolve the final status to `"terminated"`. The old `term` label was a workaround for this; the new system handles it explicitly through status aggregation.
        -   **Derive Primary Labels (Post-Processing):** After aggregation, create a new function to derive simple, high-level flags (e.g., `is_ir_user: true`) from the final structured data for easy filtering or downstream use. This moves the "labeling" task from a model input to a flexible analysis output.

-   **[x] Improve Chain of Thought (COT) Generation:**
    -   **Done.** The COT is now more explicit about its reasoning process, especially when handling multiple mentions of the same instrument.
    -   **"Instrument-by-Instrument" COT:**
        -   Instead of summarizing mentions (e.g., "IR swap, 2 mentions"), the COT should process each `NotionalEvidence` object individually.
        -   It should explicitly state the properties of each mention (type, amount, year, category).
        -   It must then perform a "self-correction" or "realization" step when it encounters a duplicate or an alias for an instrument it has already processed.
        -   **Example Logic:**
            1.  "Found mention of an 'interest-rate swap' with notional XX > 0 for year 2023 > 2025. This is an active IR instrument."
            2.  "Found mention of a 'hedging contract' with notional XX > 0 for year 2023 > 2025. This appears to be a separate GEN instrument."
            3.  "Found another mention of a 'swap contract' with notional YY > 0 for year 2023 > 2025. Wait, this seems to be an alias for the 'interest-rate swap' from step 1. I will treat it as a duplicate mention."
            4.  "Found another mention of an 'interest-rate swap' with the same notional and year. This is a duplicate of the instrument from step 1."

    -   **[x] Improve Chain of Thought (COT) for Tables:**
        -   **[x] Improve Chain of Thought (COT):**
            -   The COT is now more explicit about its reasoning process, especially when handling multiple mentions of the same instrument.
        -   **[x] Explain how it will create the JSON object:** The COT now generates an explicit "JSON Construction Plan" before the final JSON output.
            -   **Action:** In `generator2.py`, update `generate_json_from_scenario` to append a detailed, structured plan to the `chain_of_thought`.
            -   This plan should explicitly state the values for the `exposure` and `mitigation` maps.
            -   It should then iterate through the final list of identified instruments and detail the JSON object to be created for each one, specifying its `type`, `category`, `amount`, etc.
            -   This makes the final JSON generation step a simple "fill-in-the-blanks" exercise for the model, dramatically improving output reliability.
        -   **[x] Update `DerivativeTable` and COT Generation:**
            -   Modify the table builder classes (e.g., `DerivativeTable`) to also return metadata about which columns and rows correspond to specific instrument properties (e.g., notional amounts, maturity dates).
            -   Update the COT generation logic to use this metadata to create more explicit reasoning, such as: "From the 'Notional Amounts' table, I see the row for 'Interest Rate Swaps' shows a value of $100 million for 2023, indicating an active instrument."
        - **[] Implement having smaller text, similar to the previous text classification:** Right now, it is trained on large amounts of text at once, similar to an SEC filing, that it doesn't consider a simple one-liner such as "The company uses IR swaps ..." because it is too short.
            -   **Action: Add a new function in `generator2.py` that generates simple `NotionalSentence` Objects, similar to the old `generator.py` for text classification** This function should generate sentences that are short enough to be considered for training but still contain relevant information.

-   **[ ] Implement a Bootstrapped Training Strategy:** To bridge the gap between general financial knowledge and the final, complex JSON generation task, implement a multi-stage data generation loop.
    -   **Goal:** Use the model's own reasoning to create a high-quality, perfectly formatted dataset for the final fine-tuning stage.
    -   **Stage A: Generate Simple Prompts.** Use a function like `generate_simple_notional_sentence_scenario` to create a dataset of short, single-idea paragraphs.
    -   **Stage B: Initial Extraction.** Feed these simple prompts to the Stage 1 fine-tuned model (the one trained on the general finance dataset). The instruction will be to extract key facts in natural language (e.g., "Extract the instrument, notional amount, and status.").
    -   **Stage C: Programmatic Formatting.** Create a script that takes the model's correct natural language output from Stage B (the "thought bubble"). This script will then programmatically wrap this reasoning into a perfect `<|think|>` block and construct the corresponding, valid JSON object.
    -   **Stage D: Final Fine-Tuning.** Use the high-quality dataset created in Stage C for the final fine-tuning process. This teaches the model the exact output format while building on its existing reasoning capabilities.

---

## 5. Deprecation Plan

-   The concept of a single "primary label" (0-29) will be deprecated.
-   The `labels` dictionary (e.g., `{"ir": 1, "curr": 1}`) is fully deprecated and will be removed from the data generation and analysis process.
-   The `LabelMapper` logic in `analysis.py` will be replaced by functions that operate directly on the aggregated JSON, deriving any necessary flags or classifications as a final step.
