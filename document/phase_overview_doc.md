# PHASE OVERVIEW: The 7-Phase Active User Classification System

## System Architecture

Your derivative classification system processes SEC filings through **7 sequential phases**, each designed to remove specific categories of false positives while preserving evidence of actual derivative positions.

```
Raw Filing Text
      ↓
┌─────────────────────────────────────────────────────────────┐
│ PHASE 1: EXTRACTION & NOISE REMOVAL                         │
│ - Isolate paragraphs containing derivative keywords          │
│ - Remove entity names (CFTC, ISDA, etc.)                    │
│ - Convert tables to text                                    │
└─────────────────────────────────────────────────────────────┘
      ↓
┌─────────────────────────────────────────────────────────────┐
│ PHASE 2: CATEGORY DETECTION & DISAMBIGUATION                │
│ - Classify by category (IR, FX, CP, EQ, CR)                 │
│ - Split multi-category sentences                            │
│ - Excise cross-category terminology                         │
└─────────────────────────────────────────────────────────────┘
      ↓
┌─────────────────────────────────────────────────────────────┐
│ PHASE 3: TEMPORAL FILTERING (Year-based)                    │
│ - Extract years from text                                   │
│ - Surgical removal of "prior year" clauses                  │
│ - Keep current-period evidence only                         │
└─────────────────────────────────────────────────────────────┘
      ↓
┌─────────────────────────────────────────────────────────────┐
│ PHASE 4: LINGUISTIC INTENT FILTERING                        │
│ - Remove potential/hypothetical language ("may", "might")    │
│ - Remove negative intent ("does not intend")                │
│ - Keep affirmative statements                               │
└─────────────────────────────────────────────────────────────┘
      ↓
┌─────────────────────────────────────────────────────────────┐
│ PHASE 5: TERMINATION FILTERING                              │
│ - Identify terminated/expired positions                      │
│ - Apply "salvation logic" (usage verbs override termination) │
│ - Remove zombie context                                     │
└─────────────────────────────────────────────────────────────┘
      ↓
┌─────────────────────────────────────────────────────────────┐
│ PHASE 6: QUANTITATIVE ZERO FILTERING                        │
│ - Extract notional/fair value amounts                        │
│ - Map years to values                                       │
│ - Discard if reporting year = $0                            │
└─────────────────────────────────────────────────────────────┘
      ↓
Active User Classifications
(IR, FX, CP, EQ, CR, or Inactive)
```

---

## Phase Descriptions

### PHASE 1: Extraction & Noise Removal

**File:** `filter_database.py` (main entry point) + `derivative_regex.py` (patterns)

**Goal:** Extract candidate sentences containing derivative language; remove obvious noise.

**Key Actions:**

1. **Keyword Matching:** Find all sentences mentioning derivatives
   ```
   SOFT_REGEX searches for: "swap", "forward", "option", "derivative", 
                             "hedging", derivative-specific language
   ```

2. **Entity Masking:** Remove regulatory/organizational false positives
   ```
   ENTITY_EXCLUSION_REGEX masks:
   - "CFTC", "SEC", "FASB" (regulatory bodies)
   - "ISDA", "SIFMA" (standards organizations)
   - "Chicago Mercantile Exchange" (exchanges)
   - "Hedge Fund", "Fund Managers" (fund names)
   
   Before: "The CFTC regulates interest rate swaps."
   After:  "_E regulates interest rate swaps." (filtered)
   ```

3. **Content Filtering:** Remove known noise categories
   ```
   Excluded: Litigation, regulatory discussions, employee compensation,
             plan assets (pension), competitors, hypothetical scenarios
   ```

4. **Table Extraction:** Convert tabular derivatives to text
   ```
   Table Row: | Interest Rate Swaps | Fair Value: $1.2M |
   Text:      "The Company held interest rate swaps 
               with a fair value of $1.2 million."
   ```

**Input:** Raw SEC filing text  
**Output:** Candidate paragraphs with category labels (if available)  
**Attrition:** ~70% of original sentences removed (mostly noise)

**Code Flow:**
```python
matches = find_derivative_mentions(filing_text)  # SOFT_REGEX
matches = remove_entity_noise(matches)            # ENTITY_EXCLUSION_REGEX
matches = exclude_policy_sections(matches)        # EXCLUDE_REGEX_*
matches = convert_tables_to_text(matches)         # table_processor.py
```

---

### PHASE 2: Category Detection & Disambiguation

**File:** `filter_database.py::get_sentence_categories()` + disambiguation logic

**Goal:** Assign precise category to each sentence; split multi-category statements.

**Key Actions:**

1. **Strict Context Detection** (Highest Priority)
   ```
   Check for specific category signals:
   - IR: "LIBOR", "pay-fixed-receive-floating", "interest rate"
   - FX: "Currency symbol" (USD, EUR), "Cross-currency"
   - CP: "Commodity name" (oil, copper), "Price"
   - EQ: "Convertible", "Warrant", "Embedded conversion"
   - CR: "Credit default", "CDS", "Default event"
   
   Score = 2000 (hard classification)
   ```

2. **Direct Instrument Detection**
   ```
   Match specific category regexes:
   - IR_REGEX:  interest rate[- ]swap
   - FX_REGEX:  foreign[- ]exchange[- ]forward
   - CP_REGEX:  commodity[- ](?:futures?|swaps?)
   - EQ_REGEX:  convertible[- ](?:debt|notes?)
   - CR_REGEX:  credit[- ]default[- ]swap
   
   Score = 1000 (strong classification) or 100 (weak)
   ```

3. **Priority Consumption** (for ambiguous sentences)
   ```
   Process in order: FX > CP > EQ > IR
   Reason: FX overrides CP ("currency price" → FX, not CP)
           EQ overrides IR ("convertible debt" → EQ, not IR)
   
   Masked text after FX matching to prevent IR false match
   ```

4. **Multi-Category Resolution**
   ```
   If sentence matches 2+ categories:
   
   Example: "We use interest rate swaps and FX forwards."
   
   Action: Create VARIANTS
     - IR variant: excise FX terminology
       Result: "We use swaps."
     - FX variant: excise IR terminology
       Result: "We use forwards."
   
   Both variants pass to next phases independently
   ```

**Input:** Candidate paragraphs  
**Output:** (Text, Category) pairs; multi-category → multiple variants  
**Attrition:** ~5% (rare multi-category collisions)

**Code Flow:**
```python
for sentence in paragraph:
    categories = get_sentence_categories(sentence)
    
    if len(categories) == 1:
        output.append((sentence, categories[0]))
    elif len(categories) > 1:
        for cat in categories:
            variant = generate_single_category_variant(sentence, cat)
            if variant:
                output.append((variant, cat))
```

---

### PHASE 3: Temporal Filtering (Year-based)

**File:** `year_deletion.py`

**Goal:** Remove evidence of historical derivative usage; keep only current-period activity.

**Key Actions:**

1. **Year Extraction**
   ```
   YEAR_REGEX matches: 1980-2049
   Example: "In 2022 we used swaps" → Extract: [2022]
   ```

2. **Reporting Year Comparison**
   ```
   Extracted Year < Reporting Year → DISCARD
   
   Example (Reporting Year = 2024):
   "In 2022 we held swaps..." → max_year = 2022 → 2022 < 2024 → DISCARD
   "We currently hold swaps..." → no year extracted → KEEP
   ```

3. **Surgical Prior-Year Removal**
   ```
   If sentence has no year but contains prior-year language:
   
   PRIOR_PATTERN removes clauses like:
   - "In [prior time]..."
   - "[Compared to last year]..."
   
   Before: "In 2022 we used swaps, but currently we use forwards."
   Action: Remove "In 2022 we used swaps, but"
   After:  "Currently we use forwards."
   ```

**Input:** (Text, Category) pairs with reporting year  
**Output:** Temporally-filtered pairs  
**Attrition:** ~10-15%

**Code Flow:**
```python
for sentence in text:
    years = YEAR_REGEX.findall(sentence)
    
    if not years:
        # Check for prior-year language
        if PRIOR_PATTERN.search(sentence):
            cleaned = PRIOR_PATTERN.sub(" ", sentence)
            if len(cleaned) > 10:
                output.append(cleaned)
        else:
            output.append(sentence)
    else:
        max_year = max(int(y) for y in years)
        if max_year >= reporting_year:
            output.append(sentence)
        # else: DISCARD
```

---

### PHASE 4: Linguistic Intent Filtering

**File:** `active_use_filter.py`

**Goal:** Remove potential/hypothetical language; keep affirmative statements.

**Key Actions:**

1. **Potential Modal Detection**
   ```
   POTENTIAL_REGEX matches: "may", "might", "could", "expect to use"
   
   Exception: "expect to continue" ← Keep (ongoing activity)
   
   Before: "The Company may enter into swaps to manage risk."
   Action: DISCARD (hypothetical)
   ```

2. **Negative Intent Detection**
   ```
   NEGATIVE_INTENT_REGEX matches: "does not intend", "has no plans"
   
   Before: "We do not intend to use commodity derivatives."
   Action: DISCARD (explicit non-user)
   ```

3. **Absence/Explicit Non-Holding**
   ```
   ABSENCE_REGEX matches: "no outstanding [derivatives]"
   
   Before: "We hold no derivative positions."
   Action: DISCARD (explicit absence)
   ```

**Input:** Filtered pairs from Phase 3  
**Output:** Intent-verified pairs  
**Attrition:** ~5-10%

**Code Flow:**
```python
for sentence in text:
    if POTENTIAL_REGEX.search(sentence):
        if not "continue" in sentence.lower():
            continue  # DISCARD
    
    if NEGATIVE_INTENT_REGEX.search(sentence):
        continue  # DISCARD
    
    if ABSENCE_REGEX.search(sentence):
        continue  # DISCARD
    
    output.append(sentence)
```

---

### PHASE 5: Termination Filtering

**File:** `termination_filter.py`

**Goal:** Remove evidence of expired/terminated positions while preserving positions that survived.

**Key Actions:**

1. **Termination Detection**
   ```
   TERMINATION_REGEX matches: "expired", "matured", "settled", 
                               "closed", "unwound", "exercised"
   
   Before: "All interest rate swaps expired in December 2023."
   Signal: "All" + "expired" = Total termination
   ```

2. **Salvation Logic** (The key insight)
   ```
   If sentence has termination keyword BUT also has:
   - Usage verb: "use", "hold", "maintain"
   - Active state: "outstanding", "active", "remaining"
   - New/Current: "new", "current", "continue"
   
   → Likely the company REPLACED the position
   → KEEP sentence
   
   Example:
   "The swaps expired in December, and we immediately 
    entered into new swaps to continue hedging."
   
   Signal: "expired" + "new" + "entered into"
   Decision: KEEP (new position replaces old)
   ```

3. **Orphan Detection**
   ```
   After removing termination clauses, check if remaining text 
   still contains evidence of the instrument category.
   
   Before: "The swaps expired, and we discontinued our hedging program."
   After Removal: "We discontinued our hedging program."
   Check: Still mentions "hedging"? YES (weak signal)
   
   If instrument completely removed: DISCARD
   ```

**Input:** Intent-verified pairs from Phase 4  
**Output:** Non-terminated pairs  
**Attrition:** ~3-8%

**Code Flow:**
```python
for sentence in text:
    has_termination = TERMINATION_REGEX.search(sentence)
    has_salvation = SALVATION_REGEX.search(sentence)
    
    if has_termination and not has_salvation:
        continue  # DISCARD
    
    # Surgical removal of termination clause
    if has_termination:
        cleaned = TERMINATION_REGEX.sub(" ", sentence)
        if check_for_instrument(cleaned):
            sentence = cleanup_fragment(cleaned)
    
    output.append(sentence)
```

---

### PHASE 6: Quantitative Zero Filtering

**File:** `notional_filter.py`

**Goal:** Remove sentences indicating zero exposure for the reporting year.

**Key Actions:**

1. **Year-to-Value Mapping**
   ```
   Extract both years and amounts from sentence:
   "The notional of interest rate swaps was $100M in 2023 
    and $0 in 2024."
   
   Years: [2023, 2024]
   Values: [$100M, $0]
   
   Parallel mapping: 2023 → $100M, 2024 → $0
   ```

2. **Zero Detection**
   ```
   ZERO_PATTERN matches: "nil", "none", "zero", "$0", "0.0M"
   
   Check: reporting_year value = $0?
   If YES → DISCARD (no exposure)
   ```

3. **Fallback: All-Zero Check**
   ```
   If mapping fails, check: Are ANY non-zero values present?
   
   If NO non-zero found → DISCARD
   If YES non-zero found → KEEP (assume current year is non-zero)
   ```

**Input:** Non-terminated pairs from Phase 5  
**Output:** Quantitatively-verified pairs  
**Attrition:** ~2-5%

**Code Flow:**
```python
for sentence in text:
    years, values = extract_values_and_years(sentence)
    
    if years and len(years) == len(values):
        year_value_map = dict(zip(years, values))
        if reporting_year in year_value_map:
            if year_value_map[reporting_year]["is_zero"]:
                continue  # DISCARD
    else:
        # Fallback: Check if ANY positive value exists
        has_positive = any(not v["is_zero"] for v in values)
        if not has_positive:
            continue  # DISCARD
    
    output.append(sentence)
```

---

## Overall System Metrics

### Attrition by Phase

| Phase | Filter Type | Typical Removal | Cumulative Removal |
|-------|-------------|-----------------|-------------------|
| Input | Raw filing | — | — |
| Phase 1 | Entity/policy noise | 70% | 70% |
| Phase 2 | Multi-category collision | 5% | 73.5% |
| Phase 3 | Year-based filtering | 10% | 76.9% |
| Phase 4 | Linguistic intent | 5% | 78.4% |
| Phase 5 | Termination | 5% | 80.1% |
| Phase 6 | Zero quantitative | 3% | 80.7% |

---

## Parallel Processing Architecture

Each phase processes **independently** for scalability:

```
Input: 100,000 filings × 50 sentences each = 5M sentences

Phase 1: ProcessPoolExecutor (16 workers)
  - Process 1,000-sentence batches
  - Flush results to database every 5 seconds
  - Expected runtime: ~30 minutes

Phase 2: ProcessPoolExecutor (16 workers)
  - Categorize remaining ~1.5M sentences
  - Runtime: ~20 minutes

Phases 3-7: Distributed filtering
  - Each phase reads from previous phase's database
  - Independent workers, no cross-phase dependencies
  - Total runtime for all phases: ~3-4 hours on 16-core machine
```

---

## Summary

The 6-phase system achieves **high precision** through sequential filtering:

1. **Phase 1:** Remove noise and extract candidate text
2. **Phase 2:** Assign precise categories
3. **Phase 3:** Verify current-period activity
4. **Phase 4:** Remove hypothetical language
5. **Phase 5:** Remove expired positions
6. **Phase 6:** Verify quantitative exposure

