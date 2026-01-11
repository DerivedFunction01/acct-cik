# PHASE OVERVIEW: The 4-Phase Derivative Classification System

## Terminology Glossary

| Term | Meaning |
|------|---------|
| **Active User** | Company currently holds derivatives (as of filing date) |
| **Soft Mention** | Financial instrument that may not be a derivative without proper context (e.g. `natural gas contracts`) |
| **Strict Mention** | Financial instrument that always refer to a derivative (e.g. `swap agreement`) |
| **Deadweight** | Paragraph marked as "context only, not evidence" but preserved |
| **Tag** | Label added to text (e.g., `_S<TIME>`) to mark a sentence |
| **Evidence** | A marked sentence that proves a company's positions within the reporting year |
| **Noise** | A marked sentence that is not evidence |
| **Soft Count** | Ambiguous evidence or an unmarked sentence that may not be a derivative position, or is an uncategorized derivative statement. |
| **Strict Count** | Unambiguous evidence of a marked sentence stating derivative positions |

---

## What This System Does

This system reads company SEC filings and determines:
1. **Does this company use financial derivatives?** (Yes/No)
2. **What types?** (Interest Rate, Foreign Exchange, Commodity, Equity, Credit)
3. **What evidence proves it?** (Specific sentences from the filing, with tag annotations)

The system is designed to be **conservative but wide reaching**: Instead of "N hard-coded keyword hits" that clearly has bias for heavy reports from major firms such as Abbott, we capture any possible mention of a derivative instrument. Additionally, different firms can report them slightly differently. We also do not want to bias against earlier year reporting. For example, the update of SFAS 133 in 2001 (and other standards) that require more disclosures, so before the adoption of SFAS 133, there may be firms with minimal mentions of derivatives. As a result, the smallest firm with earlier year reporting can still be correctly classified as a active user if such mention exists. *The possibility of soft mentions mean that not all paragraphs will refer to derivative and hedging activities.*

## Assumptions and constraints
Since we are not using any modern LLM such as ChatGPT to perform semantic analysis, there are several constraints to follow:

1. All derivative mentions captured within the initial script are assumed to be "noise" until proven otherwise. This is due to the need to be conservative but wide reaching.
2. We follow common "SEC grammar heuristics" for derivative disclosures. All filings have a certain "formal" writing pattern that can be exploited using common regex patterns. This means that we will capture the majority of common sentences found for such disclosures, but uncommon variants may not be captured or be tagged incorrectly.
3. We do not individually distinguish what instruments are used, just the category (e.g. IR swap and IR call option within the same paragraph relate to IR), although we have such ability from such regex patterns.
4. Not all disclosures distinguish between active or past use. We consider the "heavy exiter" scenario of a major firm: A major firm that have expired or historical positions with no active positions with extensive documentation.
5. Major events or topics warrants its own paragraph. For example:
  - If a company terminates an interest rate swap, that paragraph should only mention that specific instrument and no other positions.
  - "Noise" topics are distinct from "Usage" topics and are distinct paragraphs. For example, a paragraph on the valuation nature of a derivative and the notional value of such derivative are distinct. 
6. Multiple categories can be present in the same paragraph, such as a major international firm stating both IR and FX risk and deriatives used. This can lead to certain edge cases:
  - Mention non-use/termination for the IR category, which will dominate over weaker evidence in the FX category.
7. We apply rules assuming we read "top down" paragraph by paragraph at the paragraph level first, and then the document level. If there is a standalone "forward contract" that can refer to both FX or CP (it seen both at the document level), then we look at it at the paragraph level to see if the paragraph have context clues/key phrases to distinctly refer to a category. On the other hand, if an IR swap is mentioned earlier, then a standalone "swap liability" refer to the IR swap, not the currency swap in later paragraphs since it hasn't "seen" it yet. 
8. Time-Sensitive Noise Rules and Evidence Tagging must be strict enough to only capture relevant sentences. Else, a poorly thought out noise regex will invalidate valid usage statements, or an evidence regex will match for a non user.
9. We have to be aware of soft vs strict mentions: soft mentions are ambiguous, and without proper "hedging/derivative context", it is not a derivative. For example (soft mentions):
  - `interest rate cap` may refer to percentage, a debt feature
  - `natural gas contract` is a supply contract unless it mentions derivatives -> "We use derivatives, such as natural gas contracts, to hedge risk"
10. Aliases: A firm may mention the strict variant `interest rate cap contract", only to refer it as a "interest rate cap", "cap", or "contract" for natural grammatical flow. For example:
  - "We primarily use interest rate swaps. The notional value of these contracts is $10M."
  - "The company enters into currency swaps ("Swap")."  
11. A singular report refers to one singular entity, even if there are multiple child companies (e.g. power companies operating in multiple states each with its own section).
12. Made for early startup firms such as BioTech: all derivative liability, embedded conversion/derivative mentions automatically validate warrants and convertible financing. Therefore, an edge case exist if an embedded derivative is linked to FX but the firm has convertible debt that is not a derivative. Else, warrants and convertible financings are not treated as derivatives. These derivative liability, embedded conversion/derivative mentions may be categorized as generic if not enough context clues remain.
13. Rule of "equal" reporting: If a firm extensively mentions a particular category, and an outlier category soft count exist, it does not get upgraded to active usage if there are not enough counts of that category. For example: A major firm extensively uses IR derivatives but mentions FX derivatives very briefly as soft counts: FX is removed from the pool.

## SEC Filing (raw text)

Since fetching raw filings over the internet is the main bottleneck of the program, we want to "cast a wide net" by including soft mentions along with strict mentions, and then perform filtering later.

## Instrument Detection Regex

### Core Principle: Understand Relationships

Instead of using hardcoded keywords (e.g. `interest rate swap`), we use **structured patterns** where terms relate to each other. While it is complex for this use case, it was originally used for instrument extraction but the program has evolved to use rules-based tagging. Using a regex allows us to use both the singular or plural form, and allows nearly almost all variations of deriative reporting. Note that some variations will result in a very unlikely and awkward derivative namea, as well as soft mentions.

> Note: Strict mentions (true derivatives) is a subset of soft mentions.

```
[PATTERN] = ( [DESCRIPTOR] AND ) [BASE] AND/OR [SUFFIX]
```

| Term | Meaning |
|------|---------|
| **DESCRIPTOR** | Keywords that describes the category of a derivative instrument (IR, FX, CP, EQ, CR). Without a descriptor, it is unknown/generic (GEN) |
| **BASE** | Keywords that describe the mechanics of the derivative instrument (e.g. swap, forward, futures, options, hedging, ...) |
| **SUFFIX** | Select Keywords that usually pair after a BASE (e.g. commitment, contract, agreement, arrangement, options, ...) |

| Instrument | Why it is valid |
|------|---------|
| `interest rate swap arrangement` | [DESCRIPTOR] AND [BASE] AND [SUFFIX] |
| `foreign currency contracts` | [DESCRIPTOR] AND [SUFFIX] |
| `commodity call options` | [DESCRIPTOR] AND [BASE] AND [SUFFIX] |
| `currency option agreement` | [DESCRIPTOR] AND [BASE] AND [SUFFIX]  |


---

## Category-Specific DESCRIPTOR

### IR (Interest Rate)

#### Core Pattern Structure

```
[RATES] = [TYPE] AND ["RATE"]

TYPE: "interest", "fixed", "variable", "floating", "prime", "treasury", ...

OUTPUT EXAMPLE: fixed rate swap

```

#### Special Mechanics

```
[PAY_MECH] = ["PAY"] AND [TYPE], ["RECIEVE"] [TYPE] ( AND [RATES] )

TYPE: "fixed", "variable", "floating"

OUTPUT EXAMPLE: pay fixed, receive variable swap; pay floating, receive floating interest rate swap 

```

#### Special Benchmarks

```
[SPEC] = [BENCH] ( AND [RELATION] )

BENCH: LIBOR, SONIA, ...
RELATION: linked, based

OUTPUT EXAMPLE: LIBOR contract, SONIA-linked swap

```

#### Special Phrases

zero-coupon swap, treasury locks, ...

---

### FX (Foreign Exchange)

For FX related derivatives, we use a dynamic pattern to capture both the longest form along with the normal regex variations by using a "bag of words" approach.

#### Dynamic Pattern Structure
| Position | Words |
|------|---------|
| Prefix | forward, foreign |
| Compound | cross/multi-currency |
| Middle/End | currency, exchange |
| End | rate |

Using a list of dynamic templates with careful safeguards against invalid combinations, we can generate the following:
Forward foreign currency exchange rate contract, forward currency exchange rate swaps, ...

#### Currency linked Derivatives

```
[CC] = [ISO] OR [NAME] ( AND [RELATION] )

ISO: JPY, AUD, ... along with ISO-PAIRS -> USD/EUR, ...
NAME: Swedish Krona, Bulgarian Lev, ...

OUTPUT EXAMPLE: JPY/CHF call option, US Dollar swap, ... ILS-denominated contract

```

#### Special Phrases

Note that CCIRS count for both IR and FX:

cross-currency interest rate swap, non-deliverable forward, ...

---

### CP (Commodity/Physical)

By listing out over 40 common commodities, we aim to capture a majority of firms that do not mention commodity derivatives, but rather describe what they are using as the derivative. It is likely to have false positives since all regexes share a common pool of base and suffixes. Note that numerous safeguards are considered to prevent false positives, since it can be mixed in with physical supply contracts (e.g. natural gas agreements, jet fuel forward shipment)

#### Core Pattern Structure
```
[CP] = ( ["Fixed"] AND ) [COMMODITY] (AND [MODIFIER])

COMMODITY: corn, copper, crude oil, commodity, ...
MODIFIER: price, spread, linked, index, capacity, ...

OUTPUT EXAMPLE: fixed-commodity contracts, natural gas linked swap, ...

```
#### Special Phrases

weather derivatives, fixed-price swaps, power purchase agreements, crack spreads,  ...

---

### EQ (Equity), Convertible + Warrant Detection (WARR)

Due to the nature of using the regex system, it is highly likely to have false positives since all regexes share a common pool of base and suffixes. Similar to CP derivatives, we employ numerous safeguards to prevent unrelated terms due to regex matching, such as "stock option agreement" from appearing.

Additionally, the legacy method had both convertibles and warrants (WARR) under the same category, although later scripts will apply logic to distinguish between them.

Therefore, the pool for equity linked derivatives are not as expansive as other regexes

#### Core Pattern Structure: EQ
To prevent unwanted false positives and potentially more complicated filtering, equity derivatives are minimal, even as it shared common bases and suffixes (with several restrictions): equity-linked swap, market index option contract 

#### Core Pattern Structure: WARR
For warrants, we require a mention of `warrant` along with either `deriative` or `liability` within the same sentence.
For convertible financing, `convertible debt/security, ...` as well as any reference to conversion features are included.

In this cases, derivatives may be marked as `GEN` if derivative liability, embedded derivative phrases are mentioned, but we do not have `WARR` phrases within the same sentence.

---


### CR (Credit)

Due to the nature of counterparty credit risk being mentioned in the same paragraph/sentence, only a select few without counterparty risk terms will be classified as CR_USER in the tagging stage.

#### Core Pattern Structure:
```
[CR] = [PREFIX] AND [MODIFIER]

PREFIX: credit, basket, first-to-
MODIFIER: linked, default, based

OUTPUT EXAMPLE: credit default swap, basket linked options, ...

```
#### Special Phrases

credit swaps, credit-linked debt, ...

### GEN (Generic/Unknown)

If no other regex captured the full term (soft or strict), then it likely does not have a descriptor. In the filtering stage, strict generics do not need hedging/derivative context, while soft generics do.

```
STRICT: swap contracts, forward contracts, hedging instruments, ...
SOFT: swap, collar, contract, ...

```

## Architecture: Four Phases

```
SEC Filing (raw text)
         ↓
[PHASE 0: Structural Filtering & Entity Masking]
  (prefilter_database.py)
  Remove obvious noise, mask entities, parse tables
         ↓
[PHASE 1 and 2: Fine-Grained Sentence Classification]
  (prefilter_tagging.py)
  Apply reason-based checks, mark evidence, evaluate dominance
         ↓
[PHASE 3: Category Assignment & Attributes]
  (classify_users.py)
  Categorize by type, resolve ambiguities
         ↓
Final Answer: Categories + Evidence
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
   - "The Commodity Futures Trading Commision regulates swaps" → "The _E regulates swaps"
   - Prevents false positives from regulatory/competitor mentions

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
   - Extracts data from HTML tables, which have been converted to SEC plain table text format for pre-2000 filings.
   - Converts to sentences: "The Company held swaps with fair value $1.2M"

6. **Sophisticated Content Validation**
   - Convertibles/Warrants require equity derivative context (not general mentions)
   - Example: "convertible debt" is kept if and only if there is a derivative mention related.

**What survives:** Paragraphs likely about the company's actual derivative use. Note: convertible debt/warrants "steals" embedded derivative or deriative liability sentences.

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
   - Mark entire paragraph: `_D<REASON1>`
   - Prevents false "inactive" classifications

**What survives:** Sentences with proof of high likely proof of actual derivative use

**Output**:
- Paragraphs with sentence-level tags
- Audit trail: tags show exactly why sentences were marked


### PHASE 2: Fine-Grained Sentence Classification
**File**: `prefilter_evidence.py`

**What gets tagged:** Individual sentences that are evidence of usage, with time-sensitive checking on the paragraph level.

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
- Reason: "Interest rate swap" is proof of instrument, even in regulatory context. If a paragraph is poisonous, we discard it (e.g. a lawsuit on commodity options trading must have been a dinstinct paragraph separate from usage positions).

**Phase 1 Safeguard:**
- Rule: "If surviving sentences contain actual derivative keywords, don't mark entire paragraph as deadweight"
- Reason: One good sentence outweighs boilerplate

**Phase 2 Safeguard:**
- Rule: "Apply time-sensitive rules to all evidence, but remove likely footnotes"
- Reason: One strong sentence outweighs rules within a category, and remaining unmarked sentences have skipped passed all noise and evidence rules, so it is likely to be "garbage."

**Phase 3 Safeguard:**
- Rule: "If any strict evidence tags exist, upgrade soft matches to strict"
- Reason: If there are 1 strict evidence of IR usage and we have 100 IR "soft" matches and 1 CP "soft" match, the firm likely is not a CP user, and there might have been unmarked sentences within a paragraph. 

#### Evidence Hierarchy

Different evidence types survive different Time-Senstive noise patterns. Note that weaker tiered can "piggyback" stronger tiered evidence such that the paragraph is marked as valid and not discarded.

#### Tier I time-sensitive noise
TERM: Current year termination of a derivative. 

#### Tier II time-sensitive noise
NEG: Explicit mention of non-use with or without the year
ZERO: Zero or nil value current year reporting. "The notional value is nil and $10M"
POT: Potential use with or without the year. "We periodically use"
TIME: Previous year mention

### Other noise
Other noise tags would not affect the majority of the evidence except for the weakest link.

```
STRONG EVIDENCE (Immune to all noise) -> "If I have it at the year-end of the reporting year, nothing else matters
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

**What survives:** Sentences and paragraphs with proof of actual derivative use. A company can survive if it has ANY STRONG evidence, even if surrounded by noise.

**Output**:
- Paragraphs with sentence-level tags
- Audit trail: tags show exactly why sentences were marked

---

### PHASE 3: Category Assignment & Attributes** 
**File**: `classify_users.py`
The process is a **Three-Gate System**, where evidence quality determines how a mention contributes to the final score.

| Component | Goal |
| :--- | :--- | 
| **Input** | Paragraphs tagged with **Noise** (`_S<...>`, `_D<...>` from Stage 2) and **Evidence** (`_E<...>` from Stage 3). | 
| **Output** | Final categories (`ir`, `fx`, etc.) | 

---

### Process Stages

#### 1. Pre-Processing & Tag Extraction (Filtering)

* **Action:** For every sentence, parse the tags to determine if it is "active" (meaning it has survived the filtering stages).
* **Dominance Decision:** A sentence is considered **Active** if it is **not** marked as paragraph-level Deadweight (`_D<...>`, `_S<...>` inherited from paragraph noise) or sentence-level Deadweight (`_S<...>` sentence noise).

---

#### 2. The Three-Gate Category Assignment (Strict vs. Soft)

## Evidence "Gating" – How Sentences Get Classified

The core of `process_row` is a **three‑step gating pipeline** that decides whether a sentence should be counted as a *strict* instrument reference or merely a *soft* hint.  
A sentence stops at the first gate it satisfies; if no gate matches, the sentence is ignored for categorisation.

---

### 1. Gate 1 – Strict Anchor (Evidence‑Required)

| Condition | What happens | Why it matters |
|-----------|--------------|----------------|
| The sentence contains at least one *strict* category **and** the sentence is *active* (not flagged deadweight). | • All strict categories are registered in both the global and local trackers. Also, if the same sentence also contains any unambiguous evidence tags, each strict category is *locked in as a strict anchor*: added to `strict_categories` **and** counted once in `strict_counts`. | Strict anchors give us a highly reliable signal that the instrument is being discussed. |

> **If no evidence tags are present** the sentence still registers the strict categories in the trackers, but it *does not* increment `strict_counts`.  
> These "no‑evidence" strict matches fall through to the soft logic (they become *soft candidates* that must meet a frequency threshold later).

---

### 2. Gate 2 – Unambiguous Evidence Promotion

| Condition | What happens | Why it matters |
|-----------|--------------|----------------|
| The sentence contains an **unambiguous evidence tag**. | All categories that appear in the sentence (both strict and soft) are treated as *strict*: added to `strict_categories`, registered in trackers, and counted in `strict_counts`. | This gate is a "catch‑all" for sentences that explicitly state the role of the instrument (e.g., "We use this swap as a hedge"). Even if no strict header was present, the presence of an unambiguous evidence tag guarantees a strong association. |

> After this gate the sentence is **done** – no further processing occurs.

---

### 3. Gate 3 – Soft Extraction & Tracker Resolution

If the sentence has passed through Gates 1 and 2 without being locked in as strict, it moves into the soft‑side of the pipeline.

| Step | Condition | What happens | Why it matters |
|------|-----------|--------------|----------------|
| **Soft Candidate from Strict Match** | A *strict* match existed earlier but lacked evidence (see Gate 1 note). | The same categories are now added to `soft_counts` and registered in trackers. | Allows us to keep "weak" strict matches as soft candidates that can still be counted if they appear frequently enough across the document. |
| **Explicit Soft Extraction** | We use a function to heuristically count the category specific keywords within the paragraph. | All those categories are added to `soft_counts` and registered in trackers. | Handles phrases like "interest rate swaps" where no strict header exists but the wording is unmistakable. |
| **Tracker Resolution** | No soft categories matched, but the local or global tracker can resolve a generic instrument word (e.g., "swap") to a known category. | The resolved category is added to `soft_counts`. | Leverages earlier strict anchors to infer meaning for later generic mentions. |
| **Context‑Based Soft Expansion** | After all previous checks, the only match found is the generic token `"gen"` (e.g., "the instruments"), and the sentence has *local context*. | Every local context category gets a soft count. | If a sentence only says "the instruments", we infer its meaning from the surrounding context that was already identified as, say, `ir` or `eq`. |

> **All of these soft steps increment `soft_counts`, not `strict_counts`.**  
> The counts are later filtered which enforces a minimum mention threshold and removes statistically insignificant categories.

---

#### 3. Final Aggregation & Outlier Removal

* **Final Candidate Pool:** Combine all successfully classified **Strict** categories (which are already anchored) with the high-frequency **Soft** categories.
* **Outlier Removal Logic:** 
    1.  **Anchor Magnitude:** Calculate the total weight of all Strict Anchors (Strict Count + Soft Count for that same category).
    2.  **Threshold:** Determine the threshold as 25% of the largest Anchor's magnitude (minimum of 3 mentions).
    3.  **Filtration:** Any Soft-Only category (e.g., `warr`) that falls below this dynamic threshold is removed.
* **Final Classification:** The resulting set of categories forms the final classification for the user.