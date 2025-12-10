# PHASE OVERVIEW: The 4-Phase Derivative Classification System

## What This System Does

This system reads company SEC filings and determines:
1. **Does this company use financial derivatives?** (Yes/No)
2. **What types?** (Interest Rate, Foreign Exchange, Commodity, Equity, Credit)
3. **What evidence proves it?** (Specific sentences from the filing, with tag annotations)
4. **What attributes characterize their use?** (Hedging vs. trading, sophisticated vs. simple, etc.)

The system is designed to be **conservative**: it would rather say "I'm not sure" than incorrectly claim a company uses derivatives when they don't.

---

## Architecture: Four Phases

```
SEC Filing (raw text)
         ↓
[PHASE 0: Structural Filtering & Entity Masking]
  (prefilter_database.py)
  Remove obvious junk, mask entities, parse tables
         ↓
[PHASE 1: Semantic Filtering & Token Injection]
  (prefilter_simple_nonuse.py)
  Add sentence-level noise tags, safeguard quantitative evidence
         ↓
[PHASE 2: Fine-Grained Sentence Classification]
  (prefilter_tagging.py)
  Apply reason-based checks, mark evidence, evaluate dominance
         ↓
[PHASE 3: Category Assignment & Attributes]
  (classify_users.py)
  Categorize by type, resolve ambiguities, mine user attributes
         ↓
Final Answer: Categories + Evidence + Attributes
```

Each phase **preserves all text** but adds metadata (tags) to indicate what should count as "proof" vs. "context."

---

## The Four Phases Explained

### PHASE 0: Structural Filtering & Entity Masking
**File**: `prefilter_database.py`

**What gets removed:** Obviously non-derivative content

**Key actions:**

1. **Keyword Detection** - Find paragraphs mentioning derivatives
   - Uses SOFT_REGEX (soft terms like "natural gas contracts", "equity option") and STRICT_REGEX (full confidence it is a derivative)
   - Extracts candidate text

2. **Entity Masking** - Replace company/org names with placeholders
   - "The CFTC regulates swaps" → "The _E regulates swaps"
   - Prevents false positives from regulatory/competitor mentions
   - Keeps company data (JPM, Goldman) for final output

3. **Hard Exclusions** - Delete entire paragraphs
   - Litigation: "In Smith v. Corporation, the court ruled..."
   - Regulatory boilerplate: "The SEC regulates derivatives..."
   - Employee compensation: Stock option grant descriptions
   - Pension plans: "Pension plan assets held derivatives..."
   - Competitors: "Our competitors use swaps, but we don't..."

4. **Dual Buffer System** - Route text strategically
   - **Clean buffer**: Standard derivatives (IR, FX, CP, CR)
   - **Sophisticated buffer**: Equity derivatives (convertibles, warrants)
   - Sophisticated content requires additional validation

5. **Table Processing** - Convert tabular derivatives to prose
   - Extracts data from HTML tables
   - Converts to sentences: "The Company held swaps with fair value $1.2M"

6. **Sophisticated Content Validation**
   - Convertibles/Warrants require equity derivative context (not general mentions)
   - Uses `is_sophisticated_target()` to prevent false positives
   - Example: "convertible debt" is kept, "convertible fund" is not

**What survives:** Paragraphs likely about the company's actual derivative use

**Output**: 
- Paragraphs marked with tags or clean text

---

### PHASE 1: Semantic Filtering & Token Injection
**File**: `prefilter_simple_nonuse.py`

### Refinement Exclusions Deep Dive

**How it works:**

Refinement Exclusions runs in two stages:

**Stage 1: Counter Accumulation**
```
Loop through each sentence:
  - Count hedging sentences with derivative keywords
  - Count how many of those are "negative" (potential, absence, termination, trading denial)
  - Count quantitative amounts
  - Count temporal markers (past years only)
  - Count AOCI/PnL references
```

**Stage 2: Decision Matrix**
```
IF quantitative evidence found:
  RETURN: None (SAFEGUARD: Keep the paragraph)

ELSE IF all hedging sentences are negative:
  RETURN: _D<ANLZ> (all evidence tagged as noise)

ELSE IF (AOCI or PnL) AND (Termination):
  RETURN: _D<ANLZ> (realized gains from terminated positions)

ELSE IF (AOCI and PnL both present):
  RETURN: _D<ANLZ> (boilerplate about accounting effects)

ELSE IF potential found AND (trading denial OR absence):
  RETURN: _D<ANLZ> (hypothetical discussion, confirmed non-use)

ELSE IF potential found AND (termination):
  RETURN: _D<ANLZ> (used to plan, then terminated)

ELSE IF only past years found:
  RETURN: _D<ANLZ> (purely historical)

ELSE:
  RETURN: None (Pass to next stage)
```

**Key insight:** Refinement Exclusions catches **combinations** of signals that individually might seem innocent but together indicate deadweight:
- "We use swaps" (positive) + "but we liquidated all in December" (termination) = deadweight
- "Fair value in AOCI" (methodology) + "swaps expired" (termination) = deadweight
- "We may enter swaps" (potential) + "we don't trade" (trading denial) = deadweight

**Output:** Either `_D<ANLZ>` tag or None

---

1. **Sentence-Level Analysis**
   - Splits paragraphs into sentences
   - Checks each sentence for noise patterns
   - Injects tags without deleting original text

2. **Noise Pattern Detection**
   - **Potential/Hypothetical**: "The Company **may** use derivatives in the future"
     - Tag: `_S<HYPO>` (Mark but preserve for context)
   - **Negative Intent**: "We **have no plans** to use derivatives"
     - Tag: `_S<NEG>`
   - **Termination**: "Swaps that **expired in December** 2023"
     - Tag: `_S<TERM>`
   - **AOCI References**: "**Changes in Other Comprehensive Income** due to derivatives"
     - Tag: `_S<AOCI>`
   - **Trading Denial**: "We **do not trade** derivatives"
     - Tag: `_S<TRADING>`

3. **Quantitative Safeguards** - Override all noise logic
   - "We maintain $100M notional of swaps" → **KEEP** (no tags)
   - "Fair value was $0" → Tag: `_S<ZERO>` (explicit zero)
   - Quantitative evidence forces survival regardless of other signals

4. **Refinement Exclusions** - Early paragraph-level deadweight detection
   - Runs **before** sentence-by-sentence tagging
   - Detects patterns where the entire paragraph should be marked as deadweight
   - Examples:
     - **All sentences tagged + no instrument**: Paragraph is pure noise
     - **Quantitative safeguard overrides**: If ANY sentence has `$amount`, paragraph survives
     - **Historical + Termination**: "In 2022 we used swaps. Liquidated in December."
     - **AOCI + Termination**: "Recorded in AOCI. Swaps expired in 2023."
     - **Potential + Trading**: "We may use swaps. We do not trade."
   - Returns: `(tag, modified_text)` where tag is `_D<REASON>` or None
   - If tag is None, paragraph passes to normal processing
   - If tag is set, paragraph marked deadweight: `_D<REASON> [text with sentence tags]`

5. **Gatekeeper Logic** - Final validation
   - Checks paragraph-level deadweight decision from Refinement Exclusions
   - Applies additional deadweight checks (policy, methodology, counterparty risk)
   - Ensures quantitative evidence can't be overridden

5. **Tag Format** - Preserved for Phase 2
   - `_S<REASON>` = Sentence-level noise tag
   - `_D<REASON>` = Paragraph-level deadweight tag
   - Tags appear **before** original text: `_S<TIME> In 2021 we used swaps...`

**What survives:** Statements that likely represent actual holdings, plus context

**Output**: 
- Same paragraphs with tags injected

---

### PHASE 2: Fine-Grained Sentence Classification
**File**: `prefilter_tagging.py`

**What gets removed:** Individual sentences that are noise or fluff

**Key actions:**

1. **Masking for Logic Checks**
   - Keeps years (needed for temporal checks)
   - Removes entities (prevents name-based false positives)
   - Cleans layout for regex safety

2. **Reason-Based Sentence Checks**
   - **Structural Noise**: "See Note 5", "Swap shall mean..." (definitions)
   - **Temporal Noise**: "In 2022 we used swaps" (historical, if reporting year is 2024)
   - **Intent Noise**: "We may enter into swaps", "We do not intend to use..."
   - **Termination Noise**: "Swaps expired in December"
   - **Quantitative Noise**: "Notional value was $0"
   - **Methodology**: "Fair values use Level 2 valuation inputs"

3. **Tagging Logic**
   - Find all applicable tags for this sentence
   - Apply: `_S<REASON1> _S<REASON2> Original text...`
   - Later phases read these tags to decide survival

4. **Fluff Detector** - Final safeguard
   - If all sentences in paragraph are tagged as noise
   - AND no derivative keywords survive
   - Mark entire paragraph: `_D<ANLZ>` (requires attributes mining)
   - Prevents false "inactive" classifications

**What survives:** Sentences with proof of actual derivative use

**Output**:
- Paragraphs with sentence-level tags
- Audit trail: tags show exactly why sentences were marked

---

### PHASE 3: Category Assignment & Attributes
**File**: `classify_users.py`

**What happens:** Categorize by derivative type and extract user attributes

**Process:**

1. **Parse Existing Tags** - Extract noise/evidence from earlier phases
   - Read `_S<REASON>` and `_D<REASON>` tags
   - Use them to make dominance decisions

2. **Two-Pass Category Matching**
   
   **Pass 1: Strict Matching** (Instrument + Context)
   - "Interest Rate Swap" (instrument) + "interest rate risk" (context) → IR
   - "Currency Forward" (instrument) + "currency exposure" (context) → FX
   - Score: 1000 points (immediate classification)
   
   **Pass 2: Soft Matching** (Context-only, with Priority Consumption)
   - Uses priority order: FX > CP > EQ > CR > IR
   - FX gets first access to "currency" mentions
   - After FX consumes text, IR doesn't see "currency" anymore
   - Prevents double-counting when categories overlap
   - Score: 50 points per mention (requires volume to survive)

3. **Global Instrument Tracker** - Learn from strict mentions
   - When you see "interest rate swap" (strict), register: "swap" → "ir"
   - Later, if you see just "we maintain swaps" (soft), look up in tracker
   - If tracker says all prior mentions were IR, classify as IR

4. **Outlier Removal** - Filter weak soft categories
   - If IR has 20 mentions total (strict + soft)
   - And CP has only 1 mention (soft-only)
   - Threshold: 10% of max = 2
   - CP (1 mention) < threshold (2) → Remove CP
   - Keeps solid evidence, discards noise

5. **Attributes Mining** - Extract user characteristics from tags
   - `_D<POLICY>` → "documents_hedge_accounting"
   - `_S<AOCI>` / `_S<PNL>` → "has_aoci_activity"
   - `_S<TRADING>` → "is_hedger" (trading denial signals hedging company)
   - `_S<TIME>` / `_S<TERM>` → "is_historical" (used to use derivatives, no longer does)
   - Evidence tags → "reports_positions", "reports_notional", "reports_fair_value"

**Output**: Final decision
```json
{
  "url": "https://sec.gov/...",
  "categories": ["ir", "fx"],
  "attributes": {
    "is_hedger": true,
    "documents_hedge_accounting": true,
    "has_aoci_activity": true,
    "manages_credit_risk": false,
    "reports_positions": true,
    "reports_notional": true,
    "reports_fair_value": true
  },
  "cik": 12345,
  "year": 2024
}
```

---

## Key Concepts

### Tag System

**Evidence Tags** (`_E<REASON>`)
- Applied in Phase 2, mined in Phase 3
- Examples: `_E<NVY>` (Notional Value Year), `_E<AS_YEAR>` (Active State with Year)
- Used to establish dominance in evidence hierarchy

**Noise/Skip Tags** (`_S<REASON>`)
- Applied in Phase 1 or Phase 2
- Examples: `_S<TIME>` (historical), `_S<HYPO>` (hypothetical), `_S<TERM>` (terminated)
- Mark sentences as non-evidence but preserve for context

**Deadweight Tags** (`_D<REASON>`)
- Applied when paragraph is marked as deadweight but worth preserving
- Examples: `_D<ANLZ>` (generic analysis), `_D<HIST_BLOCK>` (all historical)
- Attributes are still mined from deadweight paragraphs

### The Safeguard Principle

At each phase, certain content is protected from being filtered:

**Phase 0 Safeguard:**
- Rule: "If a paragraph mentions a specific derivative instrument, keep it"
- Reason: "Interest rate swap" is proof of position, even in regulatory context

**Phase 1 Safeguard:**
- Rule: "If a sentence contains a quantitative amount (notional, fair value), keep it regardless of other noise"
- Reason: "$50M in swaps" is direct proof of a position

**Phase 2 Safeguard:**
- Rule: "If surviving sentences contain actual derivative keywords, don't mark entire paragraph as deadweight"
- Reason: One good sentence outweighs boilerplate

**Phase 3 Safeguard:**
- Rule: "If any evidence tags exist, upgrade soft matches to strict"
- Reason: Evidence (like "at year-end 2024") disambiguates weak instrument references

### Evidence Hierarchy

Different evidence types survive different noise patterns:

```
STRONG EVIDENCE (Immune to all noise)
- AS_YEAR: "Swaps outstanding at Dec 31, 2024"
- NVY: "Notional was $100M in 2024"
- MAT_FUT: "Swaps mature in 2026"
- FVY: "Fair value of swaps was $5M in 2024"

FLOW EVIDENCE (Dies only to TERM)
- ACT_YEAR: "Entered into swaps in 2024"

TIME_KILLED EVIDENCE (Dies to TIME, TERM, NEG, etc.)
- CONT_USE: "We use swaps"
- NVNY: "Notional is $100M"
- BS_LOC: "Recorded in earnings"

POLICY_KILLED EVIDENCE (Dies to POLICY, DEF)
- ACT_GEN: "We enter into..."
- CONT_USE_AMB: "We use contracts..."
```

A company can survive if it has ANY STRONG evidence, even if surrounded by noise.

---

## Common Problems the System Solves

### Problem 1: Entity Name Confusion
```
Raw text: "The Commodity Futures Trading Commission regulates swaps."
Phase 0: Masks "CFTC" → "_E regulates swaps"
Phase 1: No company activity found → Likely deadweight
Result: Not counted as company derivative use ✓
```

### Problem 2: Hypothetical Language
```
Raw text: "The Company may enter into interest rate swaps to manage risk."
Phase 1: Tags: `_S<HYPO> The Company may enter...`
Phase 2: Reason check: "may" = potential/hypothetical
Phase 3: Marked as deadweight → Not counted ✓
```

### Problem 3: Historical Activity
```
Raw text: "In 2022, we used currency forwards. We liquidated all in December."
Phase 1: Tags: `_S<TIME> In 2022...` and `_S<TERM> liquidated...`
Phase 2: Temporal check: all years < reporting_year
Phase 3: Marked as deadweight (historical) → Not counted ✓
```

### Problem 4: Pure Methodology
```
Raw text: "Derivative positions are valued using Level 2 valuation inputs."
Phase 1: No quantitative amount found
Phase 2: No action verb (hold, maintain, etc.)
Phase 3: No evidence tags → Marked as deadweight ✓
```

### Problem 5: Ambiguous Reference
```
Company earlier disclosed: "interest rate swap agreement"
Later says: "We maintain these instruments to manage floating rate risk"
Phase 3: Global Instrument Tracker learned "instruments" can mean "swaps"
Result: Correctly classified as Interest Rate ✓
```

### Problem 6: Multi-Category Collision
```
Raw text: "We use interest rate swaps and foreign exchange forwards."
Phase 3: Strict matches: IR (swap) + FX (forwards)
Result: Two categories assigned ✓
Soft context: "We manage interest rate and currency exposure"
Result: Ambiguous alone, but confirmed by strict matches ✓
```

---

## Data Flow & Tag Preservation

### Example: Full Journey

**Original filing text:**
```
"In 2022, we used interest rate swaps with a notional 
 of $50M to manage LIBOR exposure. The fair value 
 of these positions was $2M at year-end 2024."
```

**Phase 0 (Structural):**
```
Passes through (no entity names, has instruments)
Output: [original paragraph]
```

**Phase 1 (Semantic):**
```
Sentence 1: "In 2022, we used..." 
  - Check: Contains "2022" (past year, if reporting year is 2024)
  - Tag: _S<TIME>

Sentence 2: "The fair value of these positions was $2M at year-end 2024."
  - Check: Contains quantitative evidence ($2M) + year
  - No tag (SAFEGUARD: Quantitative evidence)

Output: 
_S<TIME> In 2022, we used interest rate swaps with a notional of $50M...
The fair value of these positions was $2M at year-end 2024.
```

**Phase 2 (Tagging):**
```
Sentence 1 (with _S<TIME> tag):
  - Already marked as historical
  - Still tagged as _S<TIME>

Sentence 2 (no tag):
  - Check: Strict match on "interest rate" + valuation language
  - Evidence: Fair value + year → _E<FVY>
  - Output: _E<FVY> The fair value of these positions was $2M at year-end 2024.

Paragraph decision: Has evidence tag and derivative keywords
  - NOT marked as _D<ANLZ> (not deadweight)
```

**Phase 3 (Classification):**
```
Parse tags:
  - _S<TIME> on sentence 1 → "is_historical": true
  - _E<FVY> on sentence 2 → "reports_fair_value": true

Category matching:
  - Strict: "interest rate swap" → IR (1000 points)

Final output:
{
  "categories": ["ir"],
  "attributes": {
    "is_historical": true,
    "reports_fair_value": true,
    ...
  }
}
```

---

## Quality Checks Built In

✅ **Array alignment**: Text and categories stay synchronized through all phases  
✅ **Safeguard checks**: Quantitative evidence can't be overridden  
✅ **Tag preservation**: Every filtered decision is logged  
✅ **Audit trail**: Read the tags to understand why each sentence was classified  
✅ **Priority consumption**: FX eats "currency" so IR doesn't double-count  
✅ **Outlier removal**: Soft categories that are <10% of anchors are discarded  

---

## Accuracy & Limitations

### What This System Does Well

✅ **Finds explicit disclosure** - If a company clearly states "we use swaps," system finds it  
✅ **Avoids false positives** - Doesn't count regulatory/competitor mentions  
✅ **Preserves context** - Deadweight paragraphs help resolve later ambiguities  
✅ **Handles complexity** - Multi-category companies are categorized separately  
✅ **Quantitative verification** - Can't claim "no use" if $100M notional is reported  

### What This System Might Miss

⚠️ **Vague disclosure** - If a company says "we manage exposures" without naming instruments, might not classify  
⚠️ **Implicit categories** - If a company says "we use forwards" without specifying type, categorizes as generic  
⚠️ **Pure methodology** - If all mentions are in accounting policy sections, might classify as deadweight  

### Comparison to Manual Review

This system is designed to **match or exceed** human reviewers at:
- Finding explicit derivative disclosures
- Avoiding false positives from non-company mentions
- Categorizing by type with precision

It's not designed to:
- Infer derivative use from indirect language
- Distinguish hedging from trading without explicit signals
- Make business judgment calls about materiality

---

## Terminology Glossary

| Term | Meaning |
|------|---------|
| **Active User** | Company currently holds derivatives (as of filing date) |
| **Derivative** | Financial contract whose value depends on another asset |
| **Hedge** | Using a derivative to reduce risk from another exposure |
| **Notional** | The underlying amount a derivative is based on |
| **Fair Value** | The estimated market price of a derivative |
| **Deadweight** | Paragraph marked as "context only, not evidence" but preserved |
| **Tag** | Label added to text (e.g., `_S<TIME>`) to mark it without deleting |
| **Evidence** | An unmarked sentence that proves the company uses derivatives |
| **Attribute** | A characteristic about how the company uses derivatives |
| **Priority Consumption** | FX gets to match "currency" before IR does |
