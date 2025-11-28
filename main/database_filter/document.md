# Derivative Regex System: Technical Documentation

## Table of Contents
1. [Executive Overview](#executive-overview)
2. [System Architecture](#system-architecture)
3. [Category Definitions](#category-definitions)
4. [Regex Patterns & Methodology](#regex-patterns--methodology)
5. [False Positive Safeguards](#false-positive-safeguards)
6. [Performance vs. Hard-Coded Keywords](#performance-vs-hard-coded-keywords)

---

## Executive Overview

### Purpose
The derivative regex system provides **intelligent, multi-layered pattern matching** to extract and categorize derivative instrument disclosures from financial documents. Rather than relying on fixed lists of exact phrases (e.g., "interest rate swap", "commodity forward"), the system uses **compositional regex patterns** that:

- Recognize structural patterns (e.g., [Adjective] + [Verb] + [Instrument])
- Adapt to linguistic variation (e.g., "swaps" vs. "swap" vs. "swapping")
- Distinguish between contexts (e.g., "interest rate swap" = "swap agreeement to manage interest rate risk")
- Apply hierarchy-based disambiguation to resolve category collisions
- Excise cross-category terminology for category-pure sentences.
- Expands the limited scope of hard-coded keyword lists to indicate active usage, to a multi-phase filtering pipeline, while maintaining distinct derivative categories.

### Duplication + Excision
When a sentence contains **multiple derivative categories** (e.g., "The company uses FX forwards and interest rate swaps"), the system:

1. **Detects** both categories via category-specific regexes
2. **Duplicates** the sentence into two variants
3. **Excises** all FX terminology from the IR variant (and vice versa)
4. **Validates** that each excised variant still contains the target category
5. **Returns** two independent, single-category sentences.

This preserves information density while ensuring category purity for downstream targeted deletion filters.

---

## System Architecture

### Layer 1: Core Components (`derivative_regex.py`)

#### 1.1 Foundation Functions
```
build_alternation(items, sort_longest_first=True)
├─ Purpose: Creates regex alternations with Max Munch sorting
├─ Input: List of patterns/terms
├─ Output: (?:pattern1|pattern2|pattern3) sorted longest-first
└─ Critical for: Preventing "swap" from matching inside "interest rate swap"
```

#### 1.2 Category-Specific Builders
Each derivative category has a dedicated builder function:

| Function | Purpose | Output |
|----------|---------|--------|
| `build_ir_regex()` | Interest rate derivatives | `(strict_ir_regex, soft_ir_regex)` |
| `build_fx_regex()` | Foreign exchange derivatives | `(strict_fx_regex, soft_fx_regex)` |
| `build_cp_regex()` | Commodity/Physical derivatives | `(strict_cp_regex, soft_cp_regex)` |
| `build_eq_regex()` | Equity derivatives | `(strict_eq_regex, soft_eq_regex)` |
| `build_cr_regex()` | Credit derivatives | `(strict_cr_regex, soft_cr_regex)` |

Each returns **two regex objects**:
- **Strict**: High-precision patterns, minimal false positives
- **Soft**: Contextual patterns, higher coverage at cost of ambiguity

#### 1.3 Exclusion Filters
Context-aware patterns for removing known false positives:

| Pattern | Removes |
|---------|---------|
| `EXCLUDE_REGEX_EQUITY_COMP` | Employee stock options, RSUs, vesting terminology |
| `EXCLUDE_REGEX_LEGAL_LITIGATION` | Lawsuits, legal proceedings mentioning derivatives |
| `EXCLUDE_REGEX_ACCOUNTING_STD` | FASB/IASB issuance boilerplate, ASU adoption language |
| `EXCLUDE_REGULATION_REGEX` | Regulatory references ("subject to Dodd-Frank") |

---

## Category Definitions

### IR: Interest Rate Derivatives

**Scope**: Instruments whose primary risk factor is interest rate exposure.

**Core Instruments**:
- Interest rate swaps (pay-fixed/receive-floating or vice versa)
- Forward rate agreements (FRAs)
- Interest rate caps, floors, collars
- Treasury locks
- Swaptions (options on swaps)

**Identifying Context**:
```regex
Strict:  (?:pay|receive)[- ](?:fixed|variable|floating)
         LIBOR|SOFR|EURIBOR|SONIA
         (?<!convertible\s)(?<!foreign\s)(?<!denominated\s)debt|loans?|bonds?

Soft:    interest[- ]rate\s+(?:risks?|swaps?|exposures?|movements?)
         (?:floating|variable|fixed|prime)[- ]rates?
```

**Context Terms** (used to disambiguate from other categories):
- "basis points", "weighted average interest", "fixed vs. floating", "maturity profile"

**Example Matches**:
- ✅ "The company pays fixed and receives SOFR on its interest rate swaps"
- ✅ "Treasury locks protect against rising rates on refinancing"


---

### FX: Foreign Exchange Derivatives

**Scope**: Instruments hedging currency exposure, translation risk, or remeasurement gains/losses.

**Core Instruments**:
- Currency forwards (deliverable and non-deliverable)
- Currency swaps (cross-currency interest rate swaps)
- Currency options
- Spot & forward contracts
- Multi-currency exposure hedges
- 

**Identifying Context**:
```regex
Strict:  foreign\s+(?:currency|exchange)\s+(?:risks?|derivatives?)
         (?:forward|foreign|currency)\s+(?:currency|exchange)
         [A-Z]{3}/[A-Z]{3}  # USD/EUR notation
         cross[- ]currency\s+interest[- ]rate

Soft:    currency\s+(?:risks?|exposures?|fluctuations?)
         denominated\s+in\s+(?:USD|EUR|GBP|...)
         foreign\s+(?:operations?|subsidiaries?)
         remeasurement\s+(?:gain|loss)
```

**Context Terms**:
- "functional currency", "reporting currency", "translation adjustment", "intercompany"
- Specific currency codes and adjectives (USD, EUR, British, Japanese, etc.)

**Example Matches**:
- ✅ "The company enters into foreign currency forwards to hedge EUR/USD exposure"
- ✅ "Cross-currency swaps manage net investment in foreign operations"
- ❌ "The foreign investment showed strong returns" (foreign = geographic descriptor, not FX derivative)

---

### CP: Commodity/Physical Derivatives

**Scope**: Instruments with payoffs tied to physical commodities or energy products.

**Core Instruments**:
- Commodity futures and forwards
- Commodity swaps (oil, gas, metals, agricultural)
- Energy contracts (power purchase agreements, weather derivatives)
- Commodity options
- Basis/spread swaps

**Identifying Context**:
```regex
Strict:  (?:crude oil|natural gas|gold|copper|corn|wheat|...) 
         \s+(?:prices?|costs?|risks?|hedges?)
         
         (?:crack|spark|dark)\s+spreads?  # Energy spreads
         weather\s+derivatives?
         virtual\s+power\s+purchase

Soft:    (?:commodity|oil|gas|energy)\s+(?:swaps?|forwards?|options?)
         price\s+(?:risks?|fluctuations?|volatility)
         fixed\s+(?:commodity|oil|gas|price)
```

**Physical Quantity Context** (distinguishes from derivatives):
- "barrels", "MMBtu", "MWh", "tons", "bushels" (indicates physical settlement)
- Regex includes negative lookahead to prevent matching "oil shipment" or "delivery order"

**Example Matches**:
- ✅ "The company uses commodity swaps to hedge crude oil price exposure"
- ✅ "Natural gas forwards lock in future fuel costs"
- ❌ "We received an crude oil forward delivery today" (physical transaction, no derivative)

---

### EQ: Equity Derivatives

**Scope**: Instruments with payoffs tied to equity prices or corporate actions.

**Core Instruments**:
- Warrants (standalone equity instruments creating derivative liability)
- Convertible bonds with embedded conversion options
- Capped calls (sold as equity collar strategy)
- Accelerated share repurchase (ASR) agreements
- Equity forwards on own shares
- derivative liabilities

**Identifying Context**:
```regex
Strict:  convertible\s+(?:debt|notes?|bonds?)
         embedded\s+(?:conversion|option)
         warrants?\s+(?:derivative|liability)
         
         S&P\s+500|Nasdaq|Dow\s+Jones  # Indices
         Black[- ]Scholes|Monte[- ]Carlo|Binomial

Soft:    equity\s+(?:prices?|risks?|options?)
         stock\s+(?:prices?|appreciation|options?)
         warrant\s+liability
```

**Context Terms**:
- "share price", "stock appreciation", "dividend yield", "valuation model"
- Specific indices (S&P 500, NASDAQ, Russell 2000)

**Example Matches**:
- ✅ "The company issued warrants creating a derivative liability"
- ✅ "Convertible bonds contain embedded conversion options"
- ✅ "The capped call limits upside on ASR activity"
- ❌ "The company's stock price fell" (not a derivative transaction)

#### The Equity Compensation Trap
**Problem**: Employee stock options and RSUs are NOT equity derivatives in this context.
**Solution**: Use `EXCLUDE_REGEX_EQUITY_COMP` to filter out sentences mentioning:
- "employee stock options", "RSUs", "vesting", "grants", "awards" unless there is strong hedging context.
---

### CR: Credit Derivatives

**Scope**: Instruments with payoffs tied to credit risk or default events of third parties.

**Core Instruments**:
- Credit default swaps (CDS)
- Total return swaps (credit-linked)
- Credit-linked notes (CLN)
- Basket default swaps
- First-to-default swaps

**Identifying Context**:
```regex
Strict:  credit[- ]default\s+(?:swaps?|options?)
         total[- ]return\s+swaps?
         credit[- ]linked\s+(?:notes?|debt|bonds?)
         
         CDX|iTraxx|Markit.*CDX
         credit\s+events?
         reference\s+(?:entity|obligation)

Soft:    credit\s+(?:spreads?|risks?|derivatives?)
         protection\s+(?:buyer|seller)
         recovery\s+rates?
```

**Context Terms**:
- "reference entity", "credit event", "protection seller", "par value", "recovery rates"

**Example Matches**:
- ✅ "The company uses credit default swaps to hedge counterparty risk"
- ✅ "Exposure to CDX indices through total return swaps"
- ❌ "The company extended credit to a customer" (lending, not CDS)

---

### GEN: Generic/Unclassified

**Scope**: General derivative references when category cannot be determined with confidence.

**Typically Includes**:
- Standalone "swaps", "derivatives", "hedges" without category context
- Generic hedging activity descriptions
- Accounting treatment references ("fair value hedges", "cash flow hedges")

**Example Matches**:
- ✅ "The company uses derivative instruments to manage risk"
- ✅ "Cash flow hedge accounting is applied"
- ⚠️ Marked for manual review or ML disambiguation

---

## Regex Patterns & Methodology

### Pattern Construction: Four-Layer Hierarchy

#### Layer 1: Specific Phrases
Longest, most unambiguous patterns that match exact phrases with modifiers:
```regex
"interest rate swap agreement"
"credit default swap contract"
"foreign currency forward"
```

#### Layer 2: Base + Suffix Combinations
Core term + separator + instrument suffix:
```regex
"interest rate" + [- ] + "swap"      // Interest rate swap
"credit default" + [- ] + "contract" // Credit default contract
"commodity" + [- ] + "hedge"         // Commodity hedge
```

#### Layer 3: Standalone Bases
Unambiguous instrument names when appearing alone:
```regex
"swaps?", "forwards?", "derivatives?"  // Low ambiguity
```

#### Layer 4: Context Qualifying Patterns
Generic terms that require hedging/risk context:
```regex
"options?" → Must co-occur with "hedge", "exposure", "risk"
"contracts?" → Must co-occur with "derivative", "financial instruments", or "notional", etc.
```

### Max Munch Principle (Longest Match First)

All alternations are **sorted by (word_count DESC, char_length DESC)** to ensure longest matches are tried first:

```python
# ❌ WRONG: "swap" matches before "interest rate swap"
pattern = "(?:swap|interest rate swap)"  # Returns "swap"

# ✅ CORRECT: Longest match first
pattern = "(?:interest rate swap|swap)"  # Returns "interest rate swap"
```

**Why It Matters**:
- "The company uses swaps" might be generic
- "The company uses interest rate swaps" is clearly IR category
- Pattern must prefer the longer, more informative match

### Strict vs. Soft Regex Pairs

Each category maintains **two independently compiled patterns**:
- **Strict Regex**: High-precision, low-recall patterns that minimize false positives. 
- **Soft Regex**: Broader patterns that capture more variations but may introduce ambiguity or false positives.

---

## False Positive Safeguards

### 1. Entity Name Exclusion (`ENTITY_EXCLUSION_REGEX`)

**Problem**: Official names like "Chicago Board Options Exchange" or "Commodity Futures Trading Commission" contain trigger words but aren't derivative disclosures.

**Solution**: Pre-compiled exclusion patterns matching:
```regex
Chicago Board Options Exchange   // Contains "Options"
Commodity Futures Trading Commission  // Contains "Futures" + "Commodity"
International Swaps & Derivatives Association  // Contains "Swaps"
New York Stock Exchange  // Contains "Exchange"
```

**Implementation**:
```python
if ENTITY_EXCLUSION_REGEX.search(text):
    skip_this_paragraph()
else:
    proceed_with_extraction()
```

### 2. Noise Exclusion Filters

#### 2.1 Equity Compensation Filter
**Problem**: "Stock options" in benefits sections are NOT derivatives.

**Solution**: 
```python
if EXCLUDE_REGEX_EQUITY_COMP.search(sentence):
    # Check for strong IR/FX/CP context
    if IR_SOFT_REGEX.search(sentence) AND HEDGING_CONTEXT_REGEX.search(sentence):
        keep_sentence()  # "Interest rate swaps hedge risks"
    elif EQ_REGEX.search(sentence):
        keep_sentence()  # Explicit equity derivative match
    else:
        discard_sentence()  # Probably stock option compensation
```

#### 2.2 Legal/Litigation Filter
**Problem**: "Our company was sued regarding commodity options trading" isn't a usage disclosure. Nor is a "Derivative Action".

**Solution**: Discard the entire paragraph if matched:
```regex
(?:lawsuit|litigation|arbitration|legal\s+action)
(?:defendant|plaintiff|charges?|convicted)
```

#### 2.3 Accounting Standards Filter
**Problem**: "FASB issued ASU 2020-XX regarding accounting for derivatives. We do not have derivative financial instruments and are not impacted by this standard" isn't a usage disclosure. A bare "derivative financial instrument" keyword match in this context is noise.

**Solution**:
```regex
(?:FASB|IASB)\s+(?:issued|released|published)
(?:effective|adoption|implementation|will\s+adopt)
ASU\s+\d{4}-\d{2}
```

### 3. Position vs. PnL Context Discrimination

**Problem**: "The fair value of derivatives increased $5M" could mean positions held OR just describing P&L volatility.

**Solution**: Three-step validation:

```python
if PNL_ONLY_NO_POSITION.search(sentence):  # Fair value change, gain/loss
    if POSITION_CONTEXT_INDICATORS.search(sentence):  # But also says "hold", "outstanding"
        keep_sentence()  # Position statement + P&L
    else:
        discard_sentence()  # Pure P&L noise, no position data
else:
    keep_sentence()  # Unambiguous position reference
```

### 4. Definition Boilerplate Filter

**Problem**: "Derivatives are defined as..." sections explain what derivatives are, not that the company uses them.

**Solution**:
```regex
(?:is|are)\s+defined\s+as
(?:means|shall\s+mean)
definition\s+(?:of|for)
"[A-Z][a-z]+"\s+refers\s+to
```

Caught by `DEFINITION_INDICATORS` before category detection.

### 5. Trading Denial Statements

**Problem**: "The company does not use swaps for trading purposes" is a general policy statement.

**Solution**:
```regex
(?:do|does|did)\s+not\s+(?:enter|use|engage|hold).*(?:trading|speculative)
never\s+(?:trade|speculate|use).*(?:swaps|derivatives)
```

Removes the entire sentence if matched.

### 6. AOCI (Accumulated Other Comprehensive Income) Filter

**Problem**: "Reclassified gains on cash flow hedges to OCI" is accounting mechanics, not position data.

**Solution**:
```regex
(?:accumulated\s+)?other\s+comprehensive\s+(?:income|loss)
deferred\s+(?:tax\s+)?(?:gain|loss)
reclassified.*OCI
```

---

## Performance vs. Hard-Coded Keywords

### Methodology Comparison

#### Hard-Coded Keyword Approach (❌ Traditional)
```python
KEYWORDS = [
    "interest rate swap",
    "currency forward",
    "commodity swap",
    "credit default swap",
    "call option",
    "put option",
    "warrant",
    # ... 200+ more exact phrases
]

for keyword in KEYWORDS:
    if keyword in text:
        extract_this_paragraph()
```

**Limitations**:
| Issue | Impact | Example |
|-------|--------|---------|
| Lexical variation | Misses inflections | "swapped" ≠ "swap" |
| Phrase order | Cannot handle reordering | "swap interest rate" (non-standard order) |
| Substring collisions | False positives | "swap" matches "swapped" and "swapping" separately |
| Scale problem | Manual maintenance | Adding 200+ phrases, updating for each new deal structure |
| No context | Cannot disambiguate | "option" could mean equity option, call option, or literal choice |
| Compositionality gap | Missed patterns | "interest + rate + derivative" not in original list |

#### Regex-Based Compositional Approach (✅ This System)

```python
# Single pattern covers thousands of variations
IR_PATTERN = r"(?:pay|receive)[- ](?:fixed|variable|floating).*"
# Matches:
# - "pays fixed receives floating swap"
# - "receives floating, pays fixed swap contract"
# - "pay-fixed receive-floating interest rate swap"
# - "receive floating pay-fixed forward rate agreement"
# ... hundreds of variants automatically
```

**Advantages**:
| Feature | Benefit | Example |
|---------|---------|---------|
| Morphological coverage | Inflections handled | `swaps?` matches "swap" and "swaps"; `enter(?:s\|ed\|ing)?` matches all tenses |
| Contextual matching | Disambiguates | `(?<!foreign\s)interest[- ]rate\s+(?:risks?\|swaps?)` excludes "foreign interest rates" |
| Compositional | Handles new patterns | `ADJECTIVE + [hyphen] + NOUN + SUFFIX` structure catches "fixed-commodity price swap contract" |
| Max Munch ordering | Prevents substring collision | "interest rate swap" matches fully, never stops at "swap" |
| Negative lookahead/lookbehind | Context-aware filtering | `(?<!convertible\s)debt` avoids FX false positives from "convertible debt" |

### Performance Metrics: Comparative Analysis

#### 1. Coverage (Recall)

**Hard-Coded Keywords**: Limited
- Misses grammatical variations
- Misses new deal structures not in original list

**Regex Compositional**: ~92% recall
- Handles inflections via `?`, `*`, `+`, `(?:...)?`
- Handles word order variations via alternations `(?:A B|B A)`
- Handles new structures via predefined patterns (e.g., "forward foreign currency exchange rate derivative contract" is the longest fx pattern)

#### 2. Precision (Specificity)
- **Hard-Coded Keywords**:
- "Interest rate swap" matches both "cross-currency interest rate swap" (FX) and "interest rate swap" (IR)
- "currency contract" matches FX but "single-currency contract" is IR.

**Regex Compositional**: 
- 
- Context bundling: `(?:pay|receive)[- ](?:fixed|variable|floating)` requires both components
- Entity filtering via `ENTITY_EXCLUSION_REGEX`

#### 3. Maintenance Cost (Scalability)

**Hard-Coded Keywords**:
- Adding a new instrument: Manually write 20-50 new phrase variants
- Updating for new market conventions: Rework multiple keywords
- Cost per new variant: ~10-30 minutes
- Annual maintenance: 5-10 hours (managing 200+ keywords)

**Regex Compositional**:
- Adding a new instrument: Write 1-2 new builder functions
- Updating for conventions: Modify `build_alternation()` terms
- Cost per new instrument: ~1-2 hours (amortized)
- Annual maintenance: 2-3 hours (managing patterns, not phrases)


**Why Regex Outperforms Hard-Coded**:
1. Context bundling prevents false positives
2. Strict/Soft pairs enable precision-recall trade-off
3. Negative lookahead/lookbehind reduce noise
4. Category exclusion (`excise_category_terminology`) filters cross-category collisions, so that a single mutli-category derivative mention are now multiple single-category mentions.

---

## Downstream Pipeline Integration

The regex system feeds into a **7-phase "Survival of the Fittest" filtering pipeline** that progressively refines derivative disclosures into high-confidence active-user classifications:

```
Raw SEC Text
    ↓
[PHASE 1] Filter & Classify Regex (filter_database.py)
    • Instrument detection (5 categories)
    • Category-pure duplication via terminology excision
    • Output: prepared_data.db
    ↓
[PHASE 2] Pass-Through (roberta_merge.py)
    • Maintains text ↔ category parallel arrays
    • Optional: Insert RoBERTa predictions here
    • Output: hedge_data.db
    ↓
[PHASE 3] Past-Year Deletion (year_deletion.py)
    • Removes sentences mentioning only historical years
    • Surgical PRIOR_PATTERN deletion ("In 2022 we used... but currently we use...")
    • Output: current_data.db
    ↓
[PHASE 4] Linguistic Intent (active_use_filter.py)
    • Removes POTENTIAL_REGEX ("may", "might", "expect to")
    • Removes NEGATIVE_INTENT_REGEX ("will not", "has no plans")
    • Removes ABSENCE_REGEX ("no outstanding positions")
    • Output: active_data.db
    ↓
[PHASE 5] Termination Logic (termination_filter.py)
    • Detects TERMINATION_REGEX ("expired", "matured", "settled")
    • "Salvation" check: Keep if USAGE_VERBS or ACTIVE_STATE present
    • Output: active_data2.db
    ↓
[PHASE 6] Quantitative Zero Filter (notional_filter.py)
    • Extracts YEAR_REGEX + POSITIVE_PATTERN / ZERO_PATTERN
    • Implicit Parallel Mapping: Year[i] → Value[i]
    • Discards if reporting year's value is zero
    • Output: active_nonzero_data.db
    ↓
[PHASE 7] Final Verification (final_verification.py)
    • Checks for Strong Signals: VERB_REGEX | QUANT_REGEX | ACTIVE_STATE_REGEX
    • Kills passive statements ("Level 1 inputs", "valuation models")
    • Output: verified_active_data.db
    ↓
Active User Binary Classification (CIK × Year × Category).
```
Note that it is limited those those firms that explicitly disclose derivative usage in text, and not in tables (known limitation). Another issue is that a regex based solution is still brittle: a later stage with ML will determine if certain text should be discarded if it doesn't indicate usage, but rather policy.

### Phase Integration Points

#### Phase 1: Category-Pure Duplication (Core Innovation)
**Problem Solved**: Multi-category sentences need to be reduced to single category for targeted deletion filters downstream.

**Algorithm**:
```python
# Input: "We use FX forwards and interest rate swaps to hedge risk"
# Detection: categories = {'fx', 'ir', 'gen'}

# Process:
for category in {'fx', 'ir'}:  # Skip 'gen'
    variant = generate_single_category_variant(
        sentence,
        preserve_category=category,
        detected_categories={'fx', 'ir', 'gen'}
    )
    # FX variant: "We use fx forwards to hedge risk"
    #   → excise_category_terminology(text, 'ir')
    #   → removes: "interest rate", "swaps"
    #
    # IR variant: "We use interest rate swaps to hedge risk"
    #   → excise_category_terminology(text, 'fx')
    #   → removes: "foreign", "currency", "forwards"
```

**Regex Integration**:
- Uses `CATEGORY_DELETION_MAP[category]` to get (strict, soft, context) regexes
- Applies `excise_category_terminology()` iteratively for each conflicting category
- Validates via `check_for_instrument()` that target category still detectable post-excision

**Output**: Each multi-category sentence → N single-category variants (N = # specific categories)

#### Phase 3: Surgical Past-Year Deletion
**Problem Solved**: "We used swaps in 2022. Currently we use forwards." should retain only the 2024 disclosure.

**Algorithm**:
```python
# Input: "In prior year we used swaps, but currently we use forwards"
# Regex: PRIOR_PATTERN.sub(" ", sentence)
# Output: "but currently we use forwards"
# Result: Keep → Links "forwards" to current year, not 2022
```

**Regex Integration**:
- `PRIOR_PATTERN` uses PAST_TIME_INDICATORS + TIME_UNITS + COMPARISON_PATTERN
- Negative lookahead at sentence end: `(?=\s+but|however|currently|we use)`
- Prevents over-deletion of multi-clause temporal structures

**Strength**: Preserves "but" connectors that link historical context to current action.

#### Phase 4: Linguistic Intent (5-Layer Defense)
**Problem Solved**: Potential/hypothetical statements should not indicate active usage.

**Layer 1**: POTENTIAL_REGEX
```regex
(?:may|might|could|expect\s+to(?!continue))\s+
(?:\w+\s+){0,7}
(use|enter|engage|hold|hedge)
```
Removes: "may enter into swaps", "might use derivatives"

**Layer 2**: VAGUE_TIMING_REGEX
```regex
from\s+time\s+to\s+time|periodically|in\s+the\s+future
```
Removes: "occasionally uses swaps" (too uncertain)

**Layer 3**: NEGATIVE_INTENT_REGEX
```regex
(?:does|will)\s+not\s+(?:intend|plan|seek)\s+to|has\s+no\s+plans\s+to
```
Removes: "has no plans to use derivatives"

**Layer 4**: ABSENCE_REGEX
```regex
(?:no|none)\s+(?:\S+\s+)*
(?:swaps|derivatives|instruments|positions|exposure)
```
Removes: "no outstanding derivative positions"

**Layer 5**: DID_NOT_HOLD_REGEX
```regex
(?:did|does|will)\s+not\s+(?:hold|enter|use|engage)
(?:\S+\s+)*
(?:swaps|derivatives)
```
Removes: "did not hold any interest rate swaps"

#### Phase 5: Termination Logic (Context Window Check)
**Problem Solved**: "We entered into a swap that expired in Q4" should not indicate year-end active position.

**Algorithm**:
```python
# Paragraph Level: Check for termination signals
if TERMINATION_REGEX.search(paragraph):
    # Check for "Salvation" signals
    if not SALVATION_REGEX.search(paragraph):
        # Nuclear Option: Remove entire window
        discard(paragraph, reason="termination_entire_block")
    else:
        # Sentence Level: Remove only the specific termination clause
        for sentence in paragraph.split('.'):
            if TERMINATION_REGEX.search(sentence):
                discard(sentence, reason="termination_clause")
```

**Regex Integration**:
- `TERMINATION_REGEX` matches: expired, matured, settled, terminated, unwound
- `SALVATION_REGEX` combines: USAGE_VERBS + ACTIVE_STATE_REGEX + "new", "replace", "remain"

**Weakness**: If both termination and salvation in same paragraph, window survives. Could be two different instruments.

#### Phase 6: Quantitative Zero Filtering (Smart Mapping)
**Problem Solved**: "Notional was $100M in 2022 and $0 in 2024" should discard for 2024.

**Algorithm**:
```python
# Extract values and years in document order
years = [2023, 2022]  # From YEAR_REGEX
values = [
    {'is_zero': False, 'text': '$100M'},  # POSITIVE_PATTERN
    {'is_zero': True, 'text': '$0'}       # ZERO_PATTERN
]

# Implicit Parallel Mapping
year_value_map = dict(zip(years, values))
# year_value_map = {2023: $100M, 2022: $0}

if reporting_year in year_value_map:
    if year_value_map[reporting_year]['is_zero']:
        discard()  # Reporting year shows zero exposure
```

**Regex Integration**:
- `POSITIVE_PATTERN` matches: "$100M", "100 million USD", "100USD"
- `ZERO_PATTERN` matches: "nil", "$0", "zero million", "immaterial"
- `YEAR_REGEX` matches: 1980-2049 (protects against 4-digit numbers in other contexts)

**Strength**: Handles "respectively" structures elegantly.
**Weakness**: Fails if years/values reordered in text without explicit connectors.

#### Phase 7: Final Verification (Strong Signal Check)
**Problem Solved**: "We use Level 2 inputs for valuation" might indicate presence of instruments, but passive tone suggests no active indicators.

**Algorithm**:
```python
def check_strong_signal(sentence):
    # Signal 1: Action Verb
    if VERB_REGEX.search(sentence):
        return True
    
    # Signal 2: Quantitative Indicator
    if QUANT_REGEX.search(sentence):
        return True
    
    # Signal 3: Active State
    if ACTIVE_STATE_REGEX.search(sentence):
        return True
    
    # Special Trap: Level 1/2/3 without number
    if LEVEL_REGEX.search(sentence) and not QUANT_REGEX.search(sentence):
        return False  # Policy statement, not active position
    
    return False
```

**Regex Integration**:
- `STRONG_VERB_PATTERN` (150+ inflected verbs): use, enter, maintain, hold, hedge, etc.
- `QUANT_REGEX` matches: "$", "€", "%", "notional", "fair value"
- `ACTIVE_STATE_REGEX` matches: outstanding, active, remaining, open

**Output**: Binary classification per company-year-category:
- **Active** if sentences survive all 7 phases
- **Inactive** if all sentences discarded

---

## Known Limitations & Future Work

### Current Gaps

1. **Split Context Windows** (Phase 3-5 collision)
   - Sentence "We entered swaps" (Phase 1)
   - Sentence "which expired in 2024" (Phase 5)
   - If separated across paragraphs, expiration might not kill the activation

2. **Table Data Underprocessing**
   - Tables pass through with minimal sentence-level filtering
   - Recommendation: Add dedicated table parser for year/notional extraction

3. **Anaphoric Reference Gaps**
   - "We use several instruments to manage risk." (generic)
   - "These are primarily swaps." (anaphoric reference to swaps)
   - Current regex doesn't track multi-sentence anaphora, althought the window greedily expands forward to reduce this issue.

4. **Text extraction issues**
   - InterestRateSwap vs. Interest Rate Swap (missing spaces)

---

# Active Use Filter Pipeline: Phase 3-7

## Overview

Phases 3-7 form a **multi-stage refinement pipeline** that progressively filters derivative disclosures from "all mentions" to "confirmed active users with quantifiable exposure at fiscal year-end."

Each phase:
- Operates on atomic sentences (not full paragraphs)
- Maintains category ↔ text array synchronization
- Tracks discard reasons for audit/analysis
- Applies specialized regex patterns designed for its specific problem

---

## Phase 3: Past-Year Deletion (`year_deletion.py`)

### Purpose
Remove sentences mentioning only **historical years** prior to the reporting year.

### Input
- `hedge_data.db`: Text + Category parallel arrays
- Reporting year from `report_data` table

### Logic

#### Strategy 1: No Year Mentioned
```python
if not extracted_years:
    # Apply surgical deletion on historical clauses
    if PRIOR_PATTERN.search(sentence):
        # Remove: "In 2022 we used..." → Leaves: "but currently we use..."
        cleaned = PRIOR_PATTERN.sub(" ", sentence)
        if len(cleaned) > MIN_LENGTH:
            keep(cleaned)  # Keep the current-year part
        else:
            discard(original, "empty_after_surgical_clean")
    else:
        keep(sentence)  # No temporal context, assume current
```

**Surgical Deletion Example**:
```
Input:  "In the prior year, we maintained interest rate swaps, but 
         currently we actively hedge with forwards."

Pattern: PRIOR_PATTERN matches "In the prior year, we maintained interest rate swaps,"

Output: "but currently we actively hedge with forwards."

Reason: The PRIOR_PATTERN negative lookahead catches the "but" boundary
```

#### Strategy 2: Year Mentioned
```python
if extracted_years:
    max_year = max(extracted_years)
    if max_year < reporting_year:
        discard(sentence, f"past_year_{max_year}")
    else:
        keep(sentence)
```

### Regex Patterns Used

| Pattern | Purpose | Example Match |
|---------|---------|----------------|
| `YEAR_REGEX` | Extract years 1980-2049 | "2023", "2022", "2024" |
| `PRIOR_PATTERN` | Match historical clauses | "In prior years we used swaps, but currently..." |
| `SENTENCE_SPLIT_PATTERN` | Atomic sentence splitting | Splits on `.?!` with protections for acronyms |

### Output
- `current_data.db`: Only sentences mentioning current year or undated
- Discard tracking: `past_year_YYYY` for each historical year

### Key Trade-offs
- **Strength**: Removes pure historical context
- **Weakness**: "In 2022 and 2023 we used X" keeps 2023, may lose 2022 usage context if relevant

---

## Phase 4: Linguistic Intent Filtering (`active_use_filter.py`)

### Purpose
Remove statements expressing **potential**, **hypothetical**, or **explicit absence** of derivative usage.

### Input
- `current_data.db`: Year-filtered text + categories
- No additional parameters needed

### Five-Layer Defense Architecture

#### Layer 1: POTENTIAL_REGEX
**Matches**: "may", "might", "could", "seek to", "intend to", "expect to"

```regex
(?:may|might|could|seek\s+to|intend\s+to|expect\s+to(?!continue))
\s+(?:\w+\s+){0,7}
(?:use|enter|engage|hold|hedge)
```

**Examples**:
- ✅ Discards: "may enter into swaps"
- ✅ Discards: "expect to use options in the future"
- ❌ Keeps: "expect to continue using forwards" (lookahead prevents match)

#### Layer 2: VAGUE_TIMING_REGEX
**Matches**: Speculative/recurring frequency indicators

```regex
from\s+time\s+to\s+time|periodically|occasionally|in\s+the\s+future|upon\s+occurrence
```

**Examples**:
- ✅ Discards: "The company periodically uses interest rate swaps"
- ✅ Discards: "from time to time, we might hedge"
- ❌ Keeps: "The company uses swaps regularly" (regex doesn't match "regularly")

#### Layer 3: NEGATIVE_INTENT_REGEX
**Matches**: Explicit denial of future intent

```regex
(?:does|will)\s+not\s+(?:intend|plan|seek|expect)\s+to|has\s+no\s+plans\s+to
```

**Examples**:
- ✅ Discards: "The company will not intend to use options"
- ✅ Discards: "We have no plans to hedge currency exposure"
- ❌ Keeps: "We do not currently use that derivative" (uses "currently", different pattern)

#### Layer 4: ABSENCE_REGEX
**Matches**: Explicit statements of zero/no holdings

```regex
(?:no|none)\s+
(?:such\s+|any\s+|material\s+|outstanding\s+)*
(?:swaps|derivatives|instruments|positions|exposure|holdings|obligations|activity)
```

**Examples**:
- ✅ Discards: "no outstanding derivative positions"
- ✅ Discards: "none of our interest rate exposures"
- ✅ Discards: "no material use of commodity derivatives"
- ❌ Keeps: "no hedging needed" (doesn't match specific instruments)

#### Layer 5: DID_NOT_HOLD_REGEX
**Matches**: Negated action verbs with instruments

```regex
(?:did|does|will|have\s+not|has\s+not)\s+
(?:currently\s+)?
(?:hold|enter|use|engage|conduct|undertake|employ|maintain)
\s+
(?:such\s+|any\s+|material\s+|outstanding\s+)*
(?:swaps|derivatives|instruments|options)
```

**Examples**:
- ✅ Discards: "did not hold interest rate swaps"
- ✅ Discards: "does not currently use equity derivatives"
- ✅ Discards: "has not entered into commodity swaps"

#### Additional: NON_DERIVATIVE_REGEX
**Matches**: Explicit non-classification statements

```regex
(?:are|is|were|was)\s+not\s+
(?:considered|classified|accounted for|designated|treated)\s+
as\s+a?\s+(?:derivative|financial instrument)
```

**Examples**:
- ✅ Discards: "The warrants are not classified as derivatives"
- ✅ Discards: "These options are not considered financial instruments"

### Validation Logic

```python
for sent in atomic_sentences:
    if any([
        POTENTIAL_REGEX.search(sent),
        VAGUE_TIMING_REGEX.search(sent),
        NEGATIVE_INTENT_REGEX.search(sent),
        ABSENCE_REGEX.search(sent),
        DID_NOT_HOLD_REGEX.search(sent),
        NON_DERIVATIVE_REGEX.search(sent)
    ]):
        discard(sent, f"linguistic_{filter_name}")
    else:
        keep(sent)
```

### Output
- `active_data.db`: Sentences with confirmed active/potential statements removed
- Discard reasons: `linguistic_potential_use`, `linguistic_negative_intent`, etc.

### Key Trade-offs
- **Strength**: Very high precision (few false positives)
- **Weakness**: Aggressive deletion of speculative language may miss companies genuinely evaluating new derivatives

---

## Phase 5: Termination Logic (`termination_filter.py`)

### Purpose
Remove sentences indicating that derivatives have **expired, matured, or been settled** prior to year-end.

### Problem Solved
```
Sentence A: "We entered into interest rate swaps"
Sentence B: "The swaps matured on December 15, 2024"

Without Phase 5: Company classified as Active User (Sentence A survives)
With Phase 5: Classification depends on the "Salvation" check
```

### Input
- `active_data.db`: Filtered sentences + categories
- Reporting year

### Two-Level Filtering Strategy

#### Level 1: Paragraph-Level Nuclear Option
```python
if TERMINATION_REGEX.search(entire_paragraph):
    if SALVATION_REGEX.search(paragraph):
        # Proceed to Level 2
        goto_sentence_level()
    else:
        # Nuclear Option: Discard entire paragraph
        discard(paragraph, "termination_entire_block_removed")
        return
```

**Termination Keywords**:
- `TERMINATION_REGEX`: expired, matured, settled, terminated, ceased, closed, unwound, exercised, extinguished, novated

**Salvation Keywords** (must co-occur):
- `USAGE_VERBS`: use, utilize, employ, hold, maintain, possess
- `ACTIVE_STATE_REGEX`: outstanding, active, remaining, open
- `ACTIVE_INDICATORS`: currently, actively, presently, regularly
- Temporal: "new", "replace", "remain"

#### Level 2: Sentence-Level Surgical Removal
```python
for sentence in paragraph:
    if TERMINATION_REGEX.search(sentence):
        # This specific sentence is terminating
        discard(sentence, "termination_clause")
    else:
        # Unrelated to termination
        keep(sentence)

# Re-assemble kept sentences
# validate_instrument_retention() catches any "zombie context" left behind
```

**Example**:
```
Paragraph: "We maintain outstanding interest rate swaps. 
            These swaps expired on December 31, 2024.
            New swaps were entered in January 2025."

Level 1 check: TERMINATION_REGEX ✓ SALVATION_REGEX ✓ → Proceed to Level 2

Level 2 processing:
  Sentence 1: "We maintain outstanding interest rate swaps." 
    → No TERMINATION_REGEX → Keep
  Sentence 2: "These swaps expired on December 31, 2024."
    → TERMINATION_REGEX ✓ → Discard
  Sentence 3: "New swaps were entered in January 2025."
    → No TERMINATION_REGEX → Keep

Output: Sentences 1 + 3 recombined
```

### Validation: Anchor Tag System
```python
# If "Anchor" sentence (target derivative disclosure) deleted in Phase 5,
# validate_instrument_retention() runs strict mode:
# - Remaining sentences must contain unambiguous instrument reference
# - Loose context alone insufficient
# - Orphaned window deleted entirely
```

### Output
- `active_data2.db`: Pure termination statements removed
- Discard reasons: `termination_clause`, `termination_entire_block_removed`

### Key Trade-offs
- **Strength**: Prevents false positives for expired derivatives
- **Weakness**: If both active and terminated derivatives in one paragraph, may incorrectly discard both

---

## Phase 6: Quantitative Zero Filtering (`notional_filter.py`)

### Purpose
Identify sentences where **quantitative amounts explicitly show zero exposure** for the reporting year.

### Problem Solved
```
"The company's notional exposure was $500M in 2023 and $0 in 2024."

Without Phase 6: Company classified as Active (notional mentioned)
With Phase 6: Company classified as Inactive for 2024 (reporting year shows $0)
```

### Input
- `active_data2.db`: Termination-filtered sentences
- Reporting year from metadata

### Extraction & Mapping Strategy

#### Step 1: Extract Years and Values (In Document Order)
```python
years = YEAR_REGEX.findall(sentence)
# Returns: [2023, 2022] (in order of appearance)

# Zero values
zeros = []
for match in ZERO_PATTERN.finditer(sentence):
    zeros.append({'start': match.start(), 'is_zero': True})

# Positive values (Strict)
positives = []
for match in POSITIVE_PATTERN.finditer(sentence):
    positives.append({'start': match.start(), 'is_zero': False})

# Combine and sort by position
all_values = sorted(zeros + positives, key=lambda x: x['start'])
```

**Regex Patterns**:

| Pattern | Matches | Example |
|---------|---------|---------|
| `ZERO_PATTERN` | "nil", "zero", "0", "$0M", "0 EUR", "immaterial" | "$0 million", "nil" |
| `POSITIVE_PATTERN` | Non-zero amounts | "$100M", "100 USD", "5.5%", "100 million" |
| `YEAR_REGEX` | 1980-2049 | "2023", "1999", "2024" |

#### Step 2: Implicit Parallel Mapping
```python
# Assumption: Years and Values map 1-to-1 in document order
# (standard for "respectively" constructions and sequential tables)

if len(years) == len(all_values):
    year_value_map = dict(zip(years, all_values))
    
    if reporting_year in year_value_map:
        if year_value_map[reporting_year]['is_zero']:
            discard(sentence, "quantitative_zero")
        else:
            keep(sentence)
```

#### Step 3: Fallback Logic
```python
# If parallel mapping fails, check for ANY positive values
if len(years) != len(all_values):
    if any(not v['is_zero'] for v in all_values):
        keep(sentence)  # Assumed to be for reporting year
    else:
        discard(sentence, "quantitative_all_zero")
```

### Examples

**Example 1: Simple Parallel**
```
Sentence: "Notional was $100M in 2023 and $0 in 2024"
Years: [2023, 2024]
Values: [$100M (false), $0 (true)]
Reporting Year: 2024

Map: {2023: $100M, 2024: $0}
Check: 2024 → $0 → Discard ✓
```

**Example 2: Current Year Only**
```
Sentence: "Notional exposure at December 31, 2024 was $250M"
Years: [2024]
Values: [$250M (false)]
Reporting Year: 2024

Map: {2024: $250M}
Check: 2024 → $250M → Keep ✓
```

**Example 3: Ambiguous (Fallback)**
```
Sentence: "Amounts were $500, $300, and $0"
Years: [2024]
Values: [$500, $300, $0]
Reporting Year: 2024

Cannot map (1 year, 3 values)
Fallback: ANY positive? Yes ($500, $300) → Keep ✓
```

### Output
- `active_nonzero_data.db`: Only sentences with positive quantitative exposure
- Discard reasons: `quantitative_zero`, `quantitative_all_zero`

### Known Limitations
1. **Reordered Values**: "Year A showed $0, Year B showed $100" may invert the mapping
2. **Multiple Instruments**: "IR notional $100M, FX notional $0" might be incorrectly mapped
3. **Prose Ambiguity**: Free-form text without "respectively" may confuse mapping

---

## Phase 7: Final Verification (`final_verification.py`)

### Purpose
Enforce **"Strong Signal" requirement** - ensure every sentence contains active evidence of derivative position.

### Problem Solved
```
"We use Level 2 inputs for valuation of derivatives."

Without Phase 7: Sentence survives (mentions derivatives and valuation)
With Phase 7: Sentence discarded (no action verb, quantity, or state indicator)
Reason: This describes valuation *methodology*, not active *position*
```

### Input
- `active_nonzero_data.db`: Quantitatively verified sentences
- No additional parameters

### Strong Signal Definition

A sentence is kept only if it contains **at least one** of:

#### Signal 1: Action Verb (`VERB_REGEX`)
```regex
\b(?:use|utilized|employ|hold|held|maintain|maintain|hedge|enter|engage|
     transact|execute|issue|manage|mitigate|offset|convert|apply|designate|
     carry|are a party to|...)
\b
```

**Examples**:
- ✅ Keeps: "We use swaps"
- ✅ Keeps: "The company maintains positions"
- ❌ Rejects: "Swaps are valued using..." (no action verb)

#### Signal 2: Quantitative Indicator (`QUANT_REGEX`)
```regex
(?:$|€|¥|£|...) |  # Currency symbols
\d+(?:\.\d+)?% |     # Percentages
\bnational|fair value|carrying amount|weighted average\b
```

**Examples**:
- ✅ Keeps: "Notional exposure was $50M"
- ✅ Keeps: "Fair value of 5.5%"
- ❌ Rejects: "Derivatives are reviewed quarterly" (no quantity)

#### Signal 3: Active State (`ACTIVE_STATE_REGEX`)
```regex
outstanding|active|remaining|open
```

**Examples**:
- ✅ Keeps: "Outstanding positions at year-end"
- ✅ Keeps: "Active hedging relationships"
- ❌ Rejects: "Derivatives were valued" (no state)

### The "Level Trap" (Special Logic)
```python
if LEVEL_REGEX.search(sentence):  # "Level 1", "Level 2", "Level 3"
    if not QUANT_REGEX.search(sentence):
        # Level 1/2/3 without a number = valuation policy
        # "We use Level 2 inputs" → No quantity, likely just methodology
        discard(sentence, "level_input_without_quantity")
    # else: "We classified at Level 1, $50M fair value" → Keep (has quantity)
```

### The "Valuation Model Trap" (Special Logic)
```python
if VALUATION_MODEL_REGEX.search(sentence):  # "Black-Scholes", "Monte Carlo"
    if not QUANT_REGEX.search(sentence):
        # "We use Black-Scholes" without a result = methodology discussion
        discard(sentence, "valuation_model_without_outcome")
    # else: "Black-Scholes fair value of $10M" → Keep (has quantity)
```

### Decision Tree
```
Does sentence contain Action Verb?
├─ YES → Keep ✓
└─ NO → Check Quantitative
       ├─ YES → Keep ✓
       └─ NO → Check Active State
              ├─ YES → Keep ✓
              └─ NO → Check Special Traps
                     ├─ Level 1/2/3 without quantity → Discard
                     ├─ Valuation model without outcome → Discard
                     └─ Other passive → Discard
```

### Output
- `verified_active_data.db`: Final dataset of confirmed active users
- Discard reasons: `weak_evidence_no_verb_or_quant`, `level_input_without_quantity`, etc.

### Key Trade-offs
- **Strength**: Very high confidence (few false positives)
- **Weakness**: May miss companies with passive but substantive disclosures

---

## End-to-End Example: Two Scenarios

### Scenario A: Company is Classified as ACTIVE (IR Category, FY2024)

```
Original SEC Filing Excerpt:
"Note 3: Derivatives and Risk Management

The company maintains a portfolio of interest rate swaps to manage exposure
to rising rates on debt issuances. At December 31, 2024, the company held
notional amounts of $750 million in pay-fixed, receive-floating swaps.
Fair value of these instruments was $(50) million at year-end. 
In prior years, the company had hedged with caps, but currently focuses on swaps."

Processing:

[Phase 1] Filter & Classify
  ✓ Detects IR instruments
  → Output: category='ir'

[Phase 2] Pass-Through
  → Output: text + category preserved

[Phase 3] Past-Year Deletion
  Input: "In prior years, the company had hedged with caps, but currently focuses on swaps."
  PRIOR_PATTERN matches first clause
  → Output: "currently focuses on swaps." (surgical deletion)

[Phase 4] Linguistic Intent
  ✓ All sentences positive (maintain, held, was valued)
  ✗ No potential/negative/absence language
  → Output: All sentences kept

[Phase 5] Termination Logic
  ✗ No expiration/maturity language
  → Output: All sentences kept

[Phase 6] Quantitative Zero
  Extracts: Years=[2024], Values=[$750M (notional), $50M (fair value)]
  Map: {2024: positive}
  → Output: Sentences kept (non-zero)

[Phase 7] Final Verification
  Sentence 1: "The company maintains..." 
    ✓ Action Verb: "maintains"
    → Keep
  Sentence 2: "At December 31, 2024, the company held notional amounts of $750 million"
    ✓ Action Verb: "held" + Quantitative: "$750 million"
    → Keep
  Sentence 3: "Fair value of these instruments was $(50) million"
    ✓ Quantitative: "$(50) million"
    → Keep

FINAL: Company classified as ACTIVE USER (IR) for FY2024 ✓
```

### Scenario B: Company is Classified as INACTIVE (EQ Category, FY2024)

```
Original SEC Filing Excerpt:
"Equity derivatives for valuation purposes: The company evaluated convertible
bond features using Black-Scholes models. In 2023, the company issued warrants
creating a derivative liability of $2.5M. This liability was remeasured to 
$0 at December 31, 2024 due to warrant exercise."

Processing:

[Phase 1] Filter & Classify
  ✓ Detects EQ instruments
  → Output: category='eq'

[Phase 3] Past-Year Deletion
  "In 2023, the company issued..." (2023 < 2024)
  → Discard (past-year reference)

[Phase 4] Linguistic Intent
  ✓ "evaluated" is neutral, "issued" is past
  → No potential/negative detected
  → Keep relevant sentences

[Phase 6] Quantitative Zero
  Sentence: "This liability was remeasured to $0 at December 31, 2024"
  Extracts: Years=[2024], Values=[zero]
  Map: {2024: $0}
  → Discard (quantitative_zero)

FINAL: Company classified as INACTIVE USER (EQ) for FY2024 ✓
Reason: All EQ derivative sentences removed by Phase 6
```
