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
[PHASE 1: Fine-Grained Sentence Classification]
  (prefilter_tagging.py)
  Apply reason-based checks, mark evidence, evaluate dominance
         ↓
[PHASE 2: Category Assignment & Attributes]
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
   - Pension plans/Hedge Funds: "Pension plan assets held derivatives..."
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
   - Example: "convertible debt" is kept if and only if there is a derivative mention related.

**What survives:** Paragraphs likely about the company's actual derivative use. Note: convertible debt/warrants "steals" embedded derivative sentences.

**Output**: 
- Paragraphs marked with tags or clean text

---

### PHASE 1: Fine-Grained Sentence Classification
**File**: `prefilter_tagging.py`

**What gets removed:** Individual sentences that are noise or fluff

**Key actions:**

1. **Masking for Logic Checks**
   - Keeps years (needed for temporal checks)
   - Removes entities (prevents name-based false positives)
   - Cleans layout for regex safety
   - Tagging based hierarchy: Certain tags dominates over others

2. **Reason-Based Sentence Checks**
   - **Structural Noise**: "See Note 5", "Swap shall mean..." (definitions)
   - **Temporal Noise**: "In 2022 we used swaps" (historical, if reporting year is 2024)
   - **Intent Noise**: "We may enter into swaps", "We do not intend to use..."
   - **Termination Noise (Present)**: "Swaps expired in December"
   - **Quantitative Noise**: "Notional value was $0"
   - **Other**: "We do not use derivatives for trading"

3. **Tagging Logic**
   - Find all applicable tags for this sentence
   - Apply: `_S<REASON1> Original text...`
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
### PHASE 2: Category Assignment & Attributes** 
**File**: `classify_users.py`
The process is now structured as a **Four-Gate System**, where evidence quality determines how a mention contributes to the final score.

### PHASE 2: Category Assignment & Attributes (Revised Flow)

| Component | Goal | Status |
| :--- | :--- | :--- |
| **Input** | Paragraphs tagged with **Noise** (`_S<...>`, `_D<...>` from Stage 2) and **Evidence** (`_E<...>` from Stage 3). | |
| **Output** | Final categories (`ir`, `fx`, etc.) and user attributes (`reports_notional`, `is_hedger`). | |

---

### Process Stages

#### 1. Pre-Processing & Tag Extraction (Filtering)

* **Action:** For every sentence, parse the tags to determine if it is "active" (meaning it has survived the filtering stages).
* **Dominance Decision:** A sentence is considered **Active** if it is **not** marked as paragraph-level Deadweight (`_D<...>`, `_S<...>` inherited from paragraph noise) or sentence-level Deadweight (`_S<...>` sentence noise).
* **Attribute Mining:** Extract all `_S<...>` (Noise) and `_E<...>` (Evidence) tags and map them to permanent user attributes (`is_hedger`, `reports_positions`, etc.).

---

#### 2. The Four-Gate Category Assignment (Strict vs. Soft)

The core classification occurs through four sequential gates. A sentence stops at the first gate it passes.

| Gate | Condition | Action & Rationale |
| :--- | :--- | :--- |
| **Gate 1: Strict Anchor (Evidence Required)** | Sentence contains an **unambiguous strict match** (e.g., `IR_REGEX` hits "Interest Rate Swap") **AND** is marked with **any evidence tag** (`_E<...>`, including `_E<OTHER>`). | **ACTION:** Immediately classify as **Strict**. Increment `strict_counts`. **CRITICAL:** Register instrument in the **Global Tracker**. |
| **Gate 2: Strong Promotion (Evidence Dominates)** | Sentence is **active** (survived filtering) **AND** is marked with **Unambiguous Evidence** (Tier 1/1.5/2, e.g., `_E<NOTIONAL_VALUE_YEAR>`, `_E<AS_YEAR>`). | **ACTION:** Elevate Soft Mentions (e.g., "Contracts") to **Strict**. Increment `strict_counts`. Register instrument in the **Global Tracker**.  |
| **Gate 3: Tracker Resolution** | Sentence is **active** and contains a **generic instrument word** (e.g., "swap") that was **previously registered** by the **Global Tracker** (Gate 1 or 2). | **ACTION:** Classify as **Soft** based on the tracker's learned category (e.g., "swap" → `ir`). Increment `soft_categories`. |
| **Gate 4: Standard Soft Match (Contextual Density)** | All previous gates failed. Sentence is **active** and contains **soft category mentions** (e.g., "commodity price risk"). | **ACTION:** Classify as **Soft** using **Priority Consumption** (FX > CP > EQ > CR > IR). Increment `soft_categories`. |

---

#### 3. Final Aggregation & Outlier Removal

* **Final Candidate Pool:** Combine all successfully classified **Strict** categories (which are already anchored) with the high-frequency **Soft** categories.
* **Outlier Removal Logic:** 
    1.  **Anchor Magnitude:** Calculate the total weight of all Strict Anchors (Strict Count + Soft Count for that same category).
    2.  **Threshold:** Determine the threshold as $10\%$ of the largest Anchor's magnitude (minimum of 3 mentions).
    3.  **Filtration:** Any Soft-Only category (e.g., `warr`) that falls below this dynamic threshold is removed.
* **Final Classification:** The resulting set of categories forms the final classification for the user.

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
- Rule: "If surviving sentences contain actual derivative keywords, don't mark entire paragraph as deadweight"
- Reason: One good sentence outweighs boilerplate

**Phase 2 Safeguard:**
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
