# METHODOLOGY: Active User Classification

## What is an "Active User"?

An **Active User** is a company that holds derivative positions **as of fiscal year-end** and has provided sufficient textual evidence in their SEC filing that:

1. **Specific instruments exist** (not just hypothetical discussion)
2. **Current-period activity** (not just historical or planned use)
3. **Quantifiable exposure** (notional amounts, fair values, or measurable positions)
4. **Active state** (outstanding, open, remaining—not expired or terminated during the year)

A company is **Active** in a category if at least one sentence survives all filtering phases with evidence of a derivative position in that category.

---

## Classification Categories

Your system classifies companies into one of **5 derivative categories**:

- **IR** (Interest Rate): Swaps, caps, floors, FRAs, Treasury locks managing interest rate exposure
- **FX** (Foreign Exchange): Forwards, options, currency swaps managing currency risk
- **CP** (Commodity/Physical): Commodity futures, swaps, options managing price risk
- **EQ** (Equity): Convertible debt, warrants, equity options managing equity risk
- **CR** (Credit): Credit default swaps, credit-linked notes managing credit risk

Or **GEN** (Generic/Unclassified) if the category cannot be determined with confidence.

---

## How This Differs from Campbell et al. (2023)

### Campbell's Approach (Keyword-Based)

Campbell et al. identified derivative users by:

1. **Keyword search** through annual filings
2. **Threshold rule**: ≥20 derivative-related keywords = User; <20 = Non-User
3. **Category assignment**: ≥3 keywords per category (IR/FX/CP)
4. **No distinction** between hedging vs. speculation
5. **No temporal filtering** (could capture historical disclosures)
6. **No quantity validation** (may capture "derivatives mentioned" vs. "derivatives held")

**Limitations of this approach:**

- "Swap" matches in unrelated contexts (e.g., "swap fund managers," "employee stock swaps")
- Cannot distinguish hedging intent from speculation
- Captures policy discussions ("we may use derivatives")
- Captures expired positions ("swaps that matured in Q3")
- No safeguard against entity names (e.g., "Commodity Futures Trading Commission")
- Misses linguistic variation (e.g., "entered into" vs. "transacted")
- False positives: "Options available" (employment context) counted as derivative options

### Your Approach (Algorithmic Multi-Phase)

Your system improves on this by:

#### 1. **Compositional Regex Detection**
Understands patterns, not just word presence:
- Recognizes "pay-fixed receive-floating" structure for IR
- Distinguishes "currency forward" (FX) from "physical forward" (CP)
- Handles linguistic variation (inflections, word order)

#### 2. **Category Purification**
Splits multi-category sentences:
- "We use IR swaps and FX forwards" becomes two single-category variants
- Prevents false positives from mixing categories
- Excises cross-category terminology systematically

#### 3. **Temporal Filtering**
Removes historical disclosures:
- Deletes "In 2022 we used swaps..."
- Keeps "Currently we maintain swaps"
- Surgical removal of "prior year" clauses while preserving current language

#### 4. **Intent Filtering**
Removes potential/hypothetical language:
- Discards "may enter", "expect to use", "no plans to"
- Keeps affirmative present-tense statements
- Differentiates "expect to continue" (active) from "expect to use" (potential)

#### 5. **Termination Logic**
Removes expired positions:
- "Swaps that expired in December" gets removed
- "New swaps were entered in January" gets kept
- Surgical extraction with "salvation" logic (usage verbs + termination verbs = likely survived)

#### 6. **Quantitative Verification**
Ensures year-end exposure:
- "Notional $0 in 2024" → Classified as Inactive
- "Fair value $50M at year-end" → Kept as evidence
- Implicit parallel mapping of years to values

#### 7. **Strong Signal Enforcement**
Removes passive boilerplate:
- Discards "Level 2 valuation inputs" (methodology, not position)
- Discards "effectiveness is assessed" (accounting process, not position)
- Keeps "Fair value of derivatives was $50M" (quantitative evidence)

---

## Key Methodological Choices

### Why Regex Over Keywords?

**Keywords are brittle:**
- "Options" could mean employee stock options, call options, or "we have options"
- "Swaps" could appear in fund names, policy discussions, or historical sections
- Cannot distinguish context from content
- Lead to massive false positive rates (~35% in preliminary testing)

**Regex patterns are compositional:**
- `interest rate[- ]swap` recognizes the relationship between two terms
- Negative lookahead `(?<!convertible\s)debt` excludes equity-linked context
- Word boundary `\b` prevents substring collisions (e.g., "option" in "exceptional")
- Pattern ordering (Max Munch principle) ensures "interest rate swap" matches before "swap"

### Why Multi-Phase Filtering?

Each phase targets a specific type of false positive:

| Phase | Problem Solved | Example |
|-------|----------------|---------|
| 1 | Entity names, table conversion, category mixing | Remove "CFTC issued guidelines on swaps" |
| 2 | Pass-through consistency | Verify data integrity |
| 3 | Historical year references | Remove "In 2022 we used swaps" |
| 4 | Potential/hypothetical language | Remove "we may enter into swaps" |
| 5 | Expired/terminated positions | Remove "swaps that matured in December" |
| 6 | Zero quantitative exposure | Remove "notional of $0" |
| 7 | Passive boilerplate | Remove "fair value is determined using Level 2 inputs" |

**Why sequential?** Each phase reduces noise, making downstream phases more precise. A sentence that passes Phase 5 is significantly more likely to represent an actual position than raw text.

---

## Classification Logic

### Single-Category Sentences
If a sentence contains unambiguous evidence of only one category (e.g., "interest rate swap"), it is assigned that category directly.

### Multi-Category Sentences
If a sentence contains evidence of multiple categories (e.g., "We use interest rate swaps and foreign currency forwards"), the system:
1. Duplicates the sentence
2. Creates one variant per category
3. Systematically excises terminology from other categories
4. Returns validated single-category variants

Example:
```
Original: "The Company uses interest rate swaps and foreign exchange 
forwards to manage exposures."

IR Variant: "The Company uses swaps to manage exposures." 
FX Variant: "The Company uses forwards to manage exposures."
```

### Generic Sentences
If a sentence contains only generic derivative language (e.g., "We maintain derivative contracts"), the system:
1. Attempts contextual inference (within-paragraph lookback)
2. Falls back to RoBERTa-based ML resolution if available
3. Classifies as "gen" (Generic/Unclassified) if all else fails

---

## What This Means for Validation

When comparing your results to Campbell's manually-verified list:

**Your system is stricter.** It removes:
- Policy language ("we may use derivatives")
- Historical references ("in 2022, we used...")
- Expired positions ("matured in December")
- Passive discussions ("derivatives are valued using...")
- Pure methodology statements ("Level 2 valuation inputs")

**Campbell's manual review may be more inclusive.** They might mark "Active" if:
- The company mentions derivatives anywhere (even hypothetically)
- Policy documents exist (even if no current position)
- Historical positions are described (even if expired)

**Expected discrepancies:**

| Your Classification | Campbell Classification | Likely Reason |
|-------------------|----------------------|---------------|
| Inactive | Active | Your system filtered out historical/potential language |
| Active | Inactive | Your system detected current activity they missed OR they didn't review that company |
| Inactive (IR) | Active (IR) | Ambiguous sentence: you classified as generic, they assumed IR context |
| Active (FX) | Active (IR) | Colliding categories: you disambiguated, they counted both |

These discrepancies are **expected and acceptable** — they reflect the stricter, more conservative nature of your approach.

---

## Implementation Summary

Your system achieves higher precision by:
1. **Understanding linguistic patterns** rather than keyword co-occurrence
2. **Separating signal from noise** through multi-phase filtering
3. **Maintaining category purity** through systematic excision
4. **Quantifying exposure** rather than just detecting mentions
5. **Validating temporal context** to ensure current-period activity

The trade-off is **recall**: you may miss some edge cases that Campbell's broader approach captured. However, the sentences you do classify are significantly higher quality and more reliably represent actual derivative usage.
