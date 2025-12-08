# PHASE OVERVIEW: The 4-Phase Derivative Classification System

## What This System Does

This system reads company SEC filings and determines:
1. **Does this company use financial derivatives?** (Yes/No)
2. **What types?** (Interest Rate, Foreign Exchange, Commodity, Equity, Credit)
3. **What evidence proves it?** (Specific sentences from the filing)

The system is designed to be **conservative**: it would rather say "I'm not sure" than incorrectly claim a company uses derivatives when they don't.

---

## Why Four Phases?

Instead of trying to filter everything at once (which creates cascading errors), we process the data **four times**, each time removing a different type of noise:

```
SEC Filing (raw text)
    ↓
[PHASE 0: Remove obvious junk]
    ↓
[PHASE 1: Remove business logic that isn't about derivatives]
    ↓
[PHASE 2: Remove sentence-level noise]
    ↓
[PHASE 3: Classify what's left]
    ↓
Final Answer: Evidence + Attributes
```

This "reverse pipeline" approach means:
- ✅ We catch different types of problems at each stage
- ✅ We preserve context for when we need it
- ✅ We can debug each stage independently
- ✅ Definitions stay around to help later classification

---

## The Four Phases Explained

### PHASE 0: Structural Filtering
**What gets removed:** Obviously non-derivative content

**Examples of what gets filtered out:**
- Litigation paragraphs ("In Smith v. Corporation, the court ruled on...")
- Competitor discussions ("Our competitors use swaps, but we don't...")
- Regulatory boilerplate ("The SEC regulates derivatives trading...")
- Compensation stock option descriptions (unrelated to derivatives, but may mention "equity options" as a derivative)
- Definitions of what "swap" means (too general)
- Invalid or broken tables
- Company name confusion (the "Commodity Futures Trading Commission" is a government agency, not a company using derivatives)
- Accounting Standards updates. ("FASB issued SFAS No. 133 Derivatives and Hedging...")

**What survives:** Paragraphs that actually discuss the company's own derivative use or detailed financial structures. If there is no mention of derivatives or hedging language, the entire document may be discarded here at this stage.

---

### PHASE 1: Semantic Filtering
**What gets removed:** Business language that isn't about actual derivative holdings

**Examples:**
- "This company **may** use derivatives in the future" (hypothetical, not actual)
- "We **have no plans** to use derivatives" (explicit non-use)
- "This is **how derivatives are valued** under accounting rules" (methodology, not evidence)
- "Changes in **Other Comprehensive Income** due to derivatives" (accounting effect, not position evidence)
- "In **prior years** we held swaps" (historical, not current year)

**What survives:** Statements about derivatives currently held or actively managed

**Special handling:** When a paragraph is marked as "not evidence" (like pure policy language), we still keep it in the database because it might help define what terms mean. We just label it as "context only, not proof of active use."

**Output:** About 50-60% of Phase 0 output remains

---

### PHASE 2: Atomic Tagging
**What gets removed:** Individual sentences that are noise

**Examples:**
- "Swaps **expired in December** 2023" (dead position)
- "The **fair value** of derivatives was determined using **Level 2 inputs**" (valuation methodology, not position)
- "We maintain **zero** notional amount of swaps" (explicitly no position)
- "In **2023**, we used interest rate swaps" (when analyzing 2024 filing)

**How it works:** Unlike earlier phases that remove entire paragraphs, this phase:
1. Keeps the paragraph
2. Marks individual sentences with a tag like "_S<PAST_YEAR>" or "_S<METHODOLOGY>"
3. Preserves the sentence for context but doesn't count it as proof

**Why preserve instead of delete?** A sentence like "Swaps are instruments used to manage interest rate risk" helps us understand that the next sentence about the company's swaps is about interest rate derivatives, not other types.

**Output:** About 70% of Phase 1 output remains, but cleaner

---

### PHASE 3: Classification
**What happens:** Categorize the surviving evidence

**Process:**
1. **Read the clean evidence** (unmarked sentences from Phase 2)
2. **Categorize by type** using pattern matching:
   - "interest rate swap" → Interest Rate category
   - "currency forward" → Foreign Exchange category
   - "commodity futures" → Commodity category
   - "convertible note" → Equity category
   - "credit default swap" → Credit category

3. **Handle ambiguous cases** using three strategies:
   - **Strategy 1 (Best):** Look for specific phrases like "interest rate" + "swap"
   - **Strategy 2 (Good):** Track what types of instruments the company already mentioned (if they discussed interest rate swaps earlier, a later vague reference to "swaps" probably means interest rate)
   - **Strategy 3 (Fallback):** Use a machine learning model that reads the surrounding context and guesses

4. **Mine attributes** from the deadweight paragraphs (ones marked as "context only"):
   - Is this a hedging company? (vs. trading company)
   - Do they explicitly use hedge accounting?
   - Do they track P&L from derivatives?
   - Do they manage credit risk?

**Output:** Final decision:
```
Company: Apple Inc.
Is Active User: YES

Evidence by Type:
- Interest Rate: 2 sentences
- Foreign Exchange: 1 sentence
- Commodity: 0 sentences
- Equity: 0 sentences
- Credit: 0 sentences

Attributes:
- Uses hedging: YES
- Uses hedge accounting: YES
- Has P&L activity: NO
- Manages credit risk: NO
- Is sophisticated user: YES
```

---

## Key Concepts

### What Gets Tagged, What Gets Deleted?

This system uses **tags** rather than deletion to preserve context:

| Content Type | Marked As | Used For Evidence? | Kept For Context? |
|--------------|-----------|-------------------|-------------------|
| "We use interest rate swaps to manage exposure" | (unmarked) | ✅ YES | ✅ YES |
| "In 2022, we used swaps" | _S<PAST_YEAR> | ❌ NO | ✅ YES |
| "Swap fair values use Level 2 inputs" | _S<METHODOLOGY> | ❌ NO | ✅ YES |
| "We may use swaps in future" | _S<HYPOTHETICAL> | ❌ NO | ✅ YES |
| "Litigation about swaps..." | (deleted) | ❌ NO | ❌ NO |
| "Our competitor uses swaps..." | (deleted) | ❌ NO | ❌ NO |

**Why preserve with tags?** Because a methodology sentence helps us understand the company is sophisticated enough to measure derivatives accurately. A definition of what a swap is helps us categorize later sentences.

---

### The Safeguard Principle

At each phase, we protect certain content from being filtered out:

**Phase 1 Safeguard:**
- Rule: "If a sentence mentions a specific dollar amount, keep it regardless of other signals"
- Reason: "$50 million in swaps" is direct proof of a position, even if surrounded by policy language

**Phase 2 Safeguard:**
- Rule: "If a sentence contains a strong action verb like 'hold' or 'maintain', keep it"
- Reason: "We maintain these contracts" is proof of active use even without an amount

**Phase 3 Safeguard:**
- Rule: "If we find any proof of actual use, upgrade this company from 'maybe uses' to 'definitely uses'"
- Reason: One piece of solid evidence outweighs uncertain indicators

These safeguards prevent over-filtering. We'd rather keep something ambiguous than accidentally filter out proof of derivative use.

---

## How Phases Connect

### Information Flow

Each phase **passes information forward**:

| From Phase | Information | How Used in Next Phase |
|-----------|-----------|----------------------|
| Phase 0 | Definitions of instruments | Phase 3 uses these to categorize ambiguous references |
| Phase 1 | Paragraph-level deadweight tags | Phase 2 knows which paragraphs are "context only" |
| Phase 2 | Sentence-level noise tags | Phase 3 ignores tagged sentences but reads their context |
| Phase 3 | Categorization | Final report structure |

### Example: How a Definition Helps

```
Phase 0: Company mentions "derivatives per ASC 815"
         → Marked as "definition," kept in database

Phase 1: No deadweight filtering removes it

Phase 2: Tagged as "definition paragraph" but kept

Phase 3: Later, we see "maintained $100M of these"
         → We don't know what "these" refers to
         → We look back at definition paragraph
         → We see "swaps" → know it's interest rate category
         → Classify correctly as IR
```

Without preserving Phase 0 definitions, Phase 3 would be stuck.

---

## Output Quality: What Constitutes Proof?

The system finds evidence that proves a company uses derivatives. Different levels of proof:

### STRONG PROOF (Always Counted)
- "We hold $50 million in interest rate swaps" (specific amount + type)
- "Fair value of foreign currency forwards: $2.1 million" (number + category)
- "Warrants outstanding: 500,000 shares" (specific count)

### MODERATE PROOF (Counted if Sophisticated)
- "We maintain hedging instruments to manage exposure" (action verb + hedging context)
- "Derivative liabilities due to adjustment features" (accounting language + specific feature)
- "Designated as cash flow hedges" (hedge accounting language)

### WEAK PROOF (Not Counted)
- "We may use derivatives" (hypothetical)
- "Derivatives are used in financial markets" (general statement, not about this company)
- "In 2022, we held swaps" (historical, not current year)

The system leans toward STRONG and MODERATE, and rejects WEAK by default.

---

## Common Problems the System Solves

### Problem 1: "Competitor Company"
```
Raw text: "Commodity Futures Trading Commission regulates swaps."
Naive approach: "Found 'Commodity Futures' and 'swaps'" → False positive
Our approach: Recognizes "Commodity Futures Trading Commission" is a government agency, masks it out
Result: Correctly ignores this sentence
```

### Problem 2: "Hypothetical Language"
```
Raw text: "The Company may enter into interest rate swaps to manage risk."
Phase 1 Filter: Removes as hypothetical (word "may")
Result: Not counted as evidence
```

### Problem 3: "Historical Activity"
```
Raw text: "In 2022, we used currency forwards. We liquidated all in December."
Phase 2 Filter: Marks "In 2022" as past year
Phase 3: Sees "liquidated all" → recognized as terminated position
Result: Not counted as current year active use
```

### Problem 4: "Pure Methodology"
```
Raw text: "Derivative positions are valued using Level 2 valuation inputs."
Phase 2 Filter: Marks as methodology (no action verb, no amount)
Result: Tagged but not counted as proof
```

### Problem 5: "Ambiguous Reference"
```
Raw text: Company earlier said "interest rate swap agreement" (clear)
          Later says "We maintain these instruments" (vague)
Phase 3: Global Instrument Tracker remembers the company mentioned interest rate swaps
         Resolves "these" → "interest rate swaps"
Result: Correctly categorized as Interest Rate
```

---

## Accuracy & Limitations

### What This System Does Well

✅ **Finds deliberate disclosure** - If a company explicitly says "we use swaps," we find it  
✅ **Avoids false positives** - We don't count competitor mentions or hypothetical language  
✅ **Preserves context** - Definitions help resolve ambiguous later references  
✅ **Handles complexity** - Companies that use multiple types are categorized separately  

### What This System Might Miss

⚠️ **Vague disclosure** - If a company says "we manage exposures" without naming instruments, we might miss it  
⚠️ **Implicit use** - If all derivatives are mentioned only in accounting discussions, we might filter them out  
⚠️ **Implicit categories** - If a company says "we use forwards" (plural, generic) we might not know what type  

### Comparison to Manual Review

This system is designed to **match or exceed human reviewers** at:
- Finding explicit derivative disclosures
- Avoiding false positives from competitor/regulatory mentions
- Categorizing by type

But it's not designed to:
- Infer derivative use from indirect language
- Distinguish between hedging and trading from ambiguous context alone
- Make business judgment calls about materiality

---

## The Big Picture

### Why This Matters

Financial regulators, investors, and researchers need to know which companies use derivatives. Reading thousands of SEC filings manually would take months.

This system automates that:
1. In seconds per document
2. Consistently (no human fatigue or bias)
3. With an audit trail (you can see exactly which sentences were marked as evidence)

### What Success Looks Like

For a company that uses derivatives:
- System finds 80%+ of their derivative mentions
- System categorizes them correctly by type
- System avoids counting non-evidence (policy, methodology, competitors)
- Output can be verified by reading the original filing

For a company that doesn't use derivatives:
- System finds zero evidence
- Output clearly states "No active derivative use found"

---

## Next Steps for Understanding

To understand how each phase works in detail:
1. **Read "Methodology" document** - Why we design each phase this way
2. **Read "Instrument Detection" document** - How the categorization patterns work
3. **Look at sample output** - See real examples of what the system produces
4. **Review discards log** - Understand what was filtered out and why

To run the system yourself:
1. Prepare SEC filings as input text
2. Run the 4-phase pipeline (Phase 0 → Phase 1 → Phase 2 → Phase 3)
3. Read the final output database
4. Review marked-up filing to verify evidence sentences
5. Audit any discards you disagree with

---

## Technical Notes (For System Operators)

### Database Structure

Each phase outputs a database:
- **Phase 0 output:** `prefiltered_data.db` - Structural noise removed
- **Phase 1 output:** `refined_data.db` - Semantic deadweight tagged
- **Phase 2 output:** `tagged_data.db` - Sentence-level noise tagged
- **Phase 3 output:** `classified_data.db` - Final evidence + attributes

Each database preserves the previous phase's tags, creating an audit trail.

### Performance

- **Phase 0:** ~2-3 seconds per document (table processing is slowest)
- **Phase 1:** ~1 second per document (regex matching)
- **Phase 2:** ~1-2 seconds per document (sentence processing)
- **Phase 3:** ~0.5-1 second per document (classification)

**Total:** ~5-7 seconds per document on standard hardware

### Quality Checks Built In

- **Array alignment:** Text and categories stay synchronized through all phases
- **Safeguard checks:** If a sentence has numbers, it's protected from filtering
- **Deadweight preservation:** Definitions stay for context even if marked as "not evidence"
- **Audit trail:** Every filtered sentence is logged with reason why

---

## Terminology Glossary

| Term | Meaning |
|------|---------|
| **Active User** | Company currently holds derivatives (as of filing date) |
| **Derivative** | Financial contract whose value depends on another asset (interest rates, currencies, commodities, etc.) |
| **Hedge** | Using a derivative to reduce risk from another exposure |
| **Notional** | The underlying amount a derivative contract is based on (e.g., $50M notional swap) |
| **Fair Value** | The estimated market price of a derivative |
| **Deadweight** | Paragraph marked as "context only, not evidence" but preserved for reference |
| **Tag** | Label added to a sentence (e.g., "_S<PAST_YEAR>") to mark it as noise but preserve it |
| **Evidence** | An unmarked sentence that proves the company uses derivatives |
| **Attribute** | A characteristic mined from deadweight paragraphs (hedger vs. trader, etc.) |

---

## Questions & Answers

**Q: Why not just search for "swap" in the document?**  
A: Because "swap" appears in many non-derivative contexts ("we swapped vendors", "the CFTC regulates swaps", "in 2020 we held swaps"). Our system distinguishes between these cases.

**Q: What if a company deliberately hides derivative use?**  
A: Our system only finds disclosed derivatives. If a company doesn't disclose something in the SEC filing, we can't detect it. Our job is to accurately read what *is* disclosed.

**Q: Why preserve deadweight instead of deleting it?**  
A: Because one company's "methodology" paragraph is another company's "proof." A sentence like "swaps are valued using the following method" helps us categorize later sentences about actual holdings.

**Q: Can I trust the output?**  
A: You can verify it by reading the original filing. Every sentence in the output points to a specific location in the original SEC document. If you disagree with a classification, you can audit why it was made and adjust the system.

**Q: What's a false positive? What's a false negative?**  
A: 
- **False positive:** System says "company uses IR swaps" but they don't (Type I error)
- **False negative:** Company uses IR swaps but system says they don't (Type II error)
- Our system is designed to minimize false positives (better to miss something than claim use when there's none)

---

## Reading Order for Different Users

**If you're a regulator:**  
Phase Overview → Methodology → Review sample outputs → Run on your target companies

**If you're an investor:**  
Phase Overview → Run system on your portfolio → Review evidence → Compare to company disclosures

**If you're a researcher:**  
Phase Overview → Instrument Detection → Methodology → Full pipeline documentation → Reproduce study

**If you're a system operator:**  
Phase Overview → Each phase's technical guide → Troubleshooting → Maintenance procedures