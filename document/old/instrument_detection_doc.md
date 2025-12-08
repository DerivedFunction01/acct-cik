# INSTRUMENT DETECTION: Regex-Based Category Identification

## Why Campbell's Keyword Approach Has Limits

### The Fundamental Problem: Context Collapse

Campbell et al. searched for keywords like "swap," "forward," "option," "derivative" and counted them. This approach fails because:

#### Example 1: Entity Names
```
Text: "The SEC and CFTC regulate derivatives trading."
Campbell's Keyword Count: +1 "derivatives"
Your System: ENTITY_TOKEN = masked, no classification

Problem: The company isn't a user; the sentence just discusses regulation.
```

#### Example 2: Linguistic Variation & False Positives
```
Text: "We offer flexible option contracts to our employees in our 401(k) plan."
Campbell's Keyword Count: +1 "option contract"
Your System: Filtered by EXCLUDE_REGEX_EQUITY_COMP, no classification unless indication of hedging activities.

Problem: "Option Contract" here means employment benefits, not financial derivatives.
```

#### Example 3: Multi-Category Collision
```
Text: "We use interest rate swaps and foreign currency forwards."
Campbell's Approach: +1 "interest rate" (IR), +1 "swaps" (base), 
                     +1 "foreign currency" (FX), +1 "forwards" (base)
Your System: Creates IR_variant + FX_variant, counts both explicitly

Problem: Campbell can't distinguish whether this is 1 company using both, 
or whether "interest rate" modifies "swaps" or something else. If there are not enough mentions, then it is discarded.
Solution: Your system creates separate variants for each category. If the variant survives filtering, it is counted.
```

#### Example 4: Historical vs. Current
```
Text: "In 2022, we used interest rate swaps. We no longer do."
Campbell's Keyword Count: +1 "interest rate", +1 "swaps"
Your System: Filters "In 2022", removes entire clause

Problem: Campbell counts a position the company explicitly terminated.
```

#### Example 5: Hypothetical Language
```
Text: "The Company may enter into interest rate swaps to manage risk."
Campbell's Keyword Count: +1 "interest rate", +1 "swaps"
Your System: Filtered by POTENTIAL_REGEX (may enter)

Problem: "May enter" is not the same as "has entered" or "maintains."
```

---

## The Compositional Regex Approach

### Core Principle: Understand Relationships

Instead of counting keywords, your system recognizes **structured patterns** where terms relate to each other:

```
Pattern: [DESCRIPTOR] [SEPARATOR] [INSTRUMENT]
Example: "interest rate" [- or space] "swap"
```

### Max Munch Principle (Longest Match First)

The system orders patterns from longest to shortest to prevent substring collisions:

```
Patterns (in priority order):
1. "interest rate swap agreement"      (4 words) ← Highest priority
2. "interest rate swap"                (3 words)
3. "swap agreement"                    (2 words)
4. "swap"                              (1 word)  ← Lowest priority
```

**Without this ordering:**
```
Text: "interest rate swap agreement"

Bad (no ordering):
- Matches "swap" first
- Fails to capture "rate" as a modifier
- Loses category signal

Good (Max Munch):
- Matches "interest rate swap agreement" first
- Correctly identifies IR category
- Captures full instrument name
```

### Why This Matters for Each Category

---

## Category-Specific Patterns

### IR (Interest Rate): Compositional Detection

#### Core Pattern Structure
```
[Rate Descriptor] + [SEPARATOR] + [IR Instrument]

Rate Descriptors: "interest rate", "fixed", "variable", "floating", 
                  "LIBOR", "SOFR", "prime rate", "treasury"

IR Instruments: "swap", "cap", "floor", "collar", "forward rate agreement",
                "treasury lock"
```

#### Strict Patterns (High Confidence)
```regex
interest rate[- ]swap
pay[- ]fixed.*receive[- ]floating
SOFR|LIBOR|EURIBOR (rate benchmarks)
basis[- ]points?
interest[- ]payments?
```

#### Real Examples & Detection

**Example 1: ✅ Detected**
```
Text: "The Company entered into interest rate swaps to manage 
       exposure to fluctuations in LIBOR rates."

Pattern Match: "interest rate" + [space] + "swaps"
               + "LIBOR" (benchmark rate)
Classification: IR (High Confidence = 1000 points)
```

**Example 2: ✅ Detected (Linguistic Variation)**
```
Text: "We maintain pay-fixed, receive-floating interest rate derivatives."

Pattern Match: "pay[- ]fixed" + "receive[- ]floating" (directional structure)
Classification: IR (High Confidence = 1000 points)
```

**Example 3: ❌ Correctly Rejected (False Positive)**
```
Text: "The interest rate environment remains challenging."

Pattern Match: "interest rate" found, but NO instrument detected
               (no "swap", "cap", "floor", "derivative", "contract")
Classification: NOT IR (correctly filtered)
```

**Example 4: ⚠️ Partial Match (Requires Context)**
```
Text: "We maintain swaps to manage rate risk."

Pattern Match: "swap" found (base term, low confidence = 100 points)
               "rate" found (context word)
Classification: Likely IR, but requires context window or downgraded to "gen"
```

---

### FX (Foreign Exchange): Currency + Relationship Detection

#### Core Pattern Structure
```
[Currency Descriptor] + [SEPARATOR] + [FX Instrument]

Currency Descriptors: "foreign exchange", "currency", "foreign currency",
                      "USD", "EUR", "GBP", "Japanese Yen",
                      "cross-currency", "currency risk"

FX Instruments: "forward", "option", "swap", "collar", "non-deliverable forward"
```

#### Strict Patterns (High Confidence)
```regex
foreign[- ]exchange[- ]forward
currency[- ]swap
cross[- ]currency.*interest[- ]rate
(?:denominated in)[- ](currency codes)
USD/EUR|EUR/GBP  (currency pairs)
```

#### Real Examples & Detection

**Example 1: ✅ Detected (Clear Currency Context)**
```
Text: "The Company uses foreign exchange forwards to hedge the risk 
       of fluctuations in exchange rates."

Pattern Match: "foreign exchange" + [space] + "forwards"
Classification: FX (High Confidence = 1000 points)
```

**Example 2: ✅ Detected (Currency-Specific Modifiers)**
```
Text: "We entered into USD/EUR forward contracts to manage 
       exposure to foreign currency fluctuations."

Pattern Match: "USD/EUR" (ISO currency pair)
               "forward" + "contracts"
Classification: FX (High Confidence = 950 points)
```

**Example 3: ❌ Correctly Rejected (Debt Context)**
```
Text: "Our foreign currency debt obligates us to repay 
       €50 million at maturity."

Pattern Check: "foreign currency" + "debt" (NOT a derivative)
               Negative Lookahead: (?<!convertible\s)debt
Classification: NOT FX derivative (correctly filtered)
               This is a foreign currency liability, not a derivative hedge
```

**Example 4: ⚠️ Collision Resolved (FX vs. IR)**
```
Text: "We hold cross-currency interest rate swaps to manage both 
       FX and interest rate exposure."

Pattern Matches: "cross-currency" (FX signal)
                 "interest rate" (IR signal)
                 "swaps" (ambiguous base)
Resolution: Creates TWO variants:
  - FX variant: "We hold cross-currency interest rate swaps to manage exposure."
  - IR variant: "We hold __ to manage interest rate exposure." <-- excised FX terms, and since IR no longer mentions any instrument, it is discarded.
```

---

### CP (Commodity/Physical): Commodity Name + Financial Context

#### Core Pattern Structure
```
[Commodity Name] + [Financial Modifier]

Commodity Names: "crude oil", "natural gas", "copper", "gold", "corn",
                 "coffee", "wheat", "electricity", "power"

Financial Modifiers: "price", "cost", "risk", "futures", "swap", "option",
                     "forward", "hedge", "exposure"
```

#### Strict Patterns (High Confidence)
```regex
crude[- ]oil[- ](?:futures?|swaps?|options?)
copper[- ](?:futures?|forwards?)
natural[- ]gas[- ](?:price|risk|hedge)
commodity[- ](?:swap|forward|option)
(?:spark|crack|dark)[- ]spread  (energy spreads)
```

#### Real Examples & Detection

**Example 1: ✅ Detected (Commodity + Financial)**
```
Text: "We use crude oil futures to hedge our fuel cost exposure."

Pattern Match: "crude oil" (commodity name)
               "futures" (financial instrument)
               "hedge" (hedging context)
Classification: CP (High Confidence = 950 points)
```

**Example 2: ❌ Correctly Rejected (Physical Contract)**
```
Text: "We entered into an agreement to purchase 1,000 barrels 
       of crude oil forward delivery shipment in Q2."

Pattern Check: "crude oil" found, but "purchase...for delivery"
               suggests NPNS (Normal Purchases and Normal Sales) exemption
Regex Match: EXCLUDE_NON_DERIVATIVE_COMMERCIAL_REGEX
Classification: NOT CP derivative (correctly filtered)
Reason: Physical supply contract, not financial derivative
```

**Example 3: ✅ Detected (Implicit Commodity Context)**
```
Text: "We hedge electricity price risk using forward contracts."

Pattern Match: "electricity" (commodity)
               "price risk" (financial exposure)
               "forward" (derivative instrument)
Classification: CP (High Confidence = 900 points)
```

---

### EQ (Equity): Convertible + Warrant Detection

#### Core Pattern Structure
```
[Equity Feature] + [Instrument Type]

Equity Features: "convertible", "embedded conversion", "warrant",
                 "call option", "equity option", "share price",
                 "stock option"

Instrument Types: "debt", "note", "bond", "liability", "derivative"
```

#### Strict Patterns (High Confidence)
```regex
convertible[- ](?:debt|notes?|bonds?)
embedded[- ]conversion[- ](?:option|feature)
warrant[- ](?:liability|derivative)
call[- ](?:spread|option)
capped[- ]call
accelerated[- ]share[- ]repurchase
```

#### Real Examples & Detection

**Example 1: ✅ Detected (Explicit Convertible)**
```
Text: "The Company issued $100 million of convertible notes 
       with an embedded call option."

Pattern Match: "convertible" + "notes"
               "embedded" + "call" + "option"
Classification: EQ (High Confidence = 1000 points)
```

**Example 2: ❌ Correctly Rejected (Noise)**
```
Text: "We grant stock options to employees under our 
       equity compensation plan."

Pattern Check: "stock" + "options" found
               EXCLUDE_REGEX_EQUITY_COMP match (equity compensation)
               No derivative accounting mentioned
Classification: NOT EQ derivative (correctly filtered)
Reason: Employee compensation, not financial derivative
```

**Example 3: ✅ Detected (Warrant Liability)**
```
Text: "We classified outstanding warrants as a derivative liability 
       because the exercise price adjusts for certain corporate events."

Pattern Match: "warrants" + "derivative" + "liability"
               "exercise price" (financial mechanics)
Classification: EQ (High Confidence = 950 points)
```

---

### CR (Credit): Credit-Specific Mechanics

#### Core Pattern Structure
```
[Credit Event] + [Credit Instrument]

Credit Events: "default", "bankruptcy", "credit event", "restructuring"
Credit Instruments: "credit default swap", "CDS", "credit-linked",
                    "total return swap", "first-to-default"
```

#### Strict Patterns (High Confidence)
```regex
credit[- ]default[- ]swap
credit[- ](?:linked|linked notes?)
(?:total[- ])?return[- ]swap[- ]credit
basket[- ]default
first[- ]to[- ]default
protection[- ](?:buyer|seller)
```

#### Real Examples & Detection

**Example 1: ✅ Detected (Explicit CDS)**
```
Text: "The Company enters into credit default swaps to hedge 
       credit risk on our loan portfolio."

Pattern Match: "credit default" + "swaps"
Classification: CR (High Confidence = 1000 points)
```

**Example 2: ❌ Correctly Rejected (Noise)**
```
Text: "We monitor credit quality of our counterparties."

Pattern Check: "credit" found, but NO derivative instrument
               No "swap", "CDS", "default", or "credit-linked"
Classification: NOT CR derivative (correctly filtered)
```

---

## False Positive Safeguards

### Safeguard 1: Entity Masking

**Problem:**
```
Text: "In accordance with ISDA guidelines, 
       the Commodity Futures Trading Commission regulates swaps."
```

**Solution:**
```regex
ENTITY_EXCLUSION_REGEX matches:
  - "CFTC" (regulatory body)
  - "Commodity Futures Trading Commission" (regulatory body)
  - "ISDA" (standards organization)

Action: Replace with _E token
Result: "_E regulates swaps." (no false positive)
```

### Safeguard 2: Negative Lookahead (Debt Context)

**Problem:**
```
Text: "Our convertible debt carries an embedded derivative."
```

**Challenge:** "Debt" could be:
- IR derivative (interest rate debt) ← WRONG
- EQ derivative (convertible debt) ← CORRECT

**Solution:**
```regex
IR_DEBT_LOOKBEHIND = r"(?<!convertible\s)debt"

Text: "convertible debt" 
  - Lookahead: (?<!convertible\s) checks "is 'debt' preceded by 'convertible'?"
  - Result: YES, so DON'T match
  - Classification: NOT IR (correctly rejected)

Text: "we maintain debt"
  - Lookahead: (?<!convertible\s) checks for 'convertible'
  - Result: NO, so MATCH
  - Classification: Likely IR (likely correct)
```

### Safeguard 3: Noise Exclusion (Policy + Methodology)

**Problem:**
```
Text: "We value derivative positions using Level 2 valuation inputs."
```

**Classification Issue:** "Derivative" + "value" could suggest a position, 
but this is just methodology.

**Solution:**
```regex
LEVEL_REGEX = r"\bLevel\s+[123]\b"
POLICY_REGEX = "designated as hedge", "hedge documentation", etc.

Detection: "Level 2" found
           "valuation inputs" (methodology language)
Action: Discard sentence in Phase 7 (Strong Signal Enforcement)
Result: Correctly rejected as passive boilerplate
```

### Safeguard 4: Quantitative Verification

**Problem:**
```
Text: "The Company held derivatives with a notional value of $0."
```

**Issue:** $0 notional = no actual position

**Solution:**
```
ZERO_PATTERN = r"nil|none|zero|$0"

Extraction: Year=2024, Value="$0"
Implicit Mapping: 2024 → $0
Check: Is reporting_year value $0? YES
Action: Discard in Phase 6 (Quantitative Zero Filtering)
Result: Correctly rejected
```

---

## Priority & Conflict Resolution

### When Multiple Categories Match

Your system applies a **priority hierarchy**:

```
Priority Order: FX > EQ > CP > CR > IR

Example:
Text: "We hold convertible bonds with an embedded currency option."

Matches: EQ (convertible) + FX (currency option)
Priority Resolution: EQ > FX in multi-category context
  Reason: Convertibility is primary structural feature;
          currency option is secondary

Result: Creates variants but EQ is "primary" classification
```

### Context Window Tie-Breaking

If multiple categories have equal scores:

```
Text: "We maintain positions to manage risk."
(No specific instrument, just generic + context)

Score: IR=10, FX=10, CP=5, EQ=5 (all low)

Resolution: Within-paragraph lookback
  - ML resolver: append prior sentence context
  - Previous sentence: "We hedge interest rate exposure with swaps"
  - Inherits: IR classification
  - Result: Generic sentence classified as IR based on context
```

---

## Validation: Did It Work?

### Common Patterns That Survive All Filters

These patterns have proven robust across thousands of filings:

```
✅ "The Company maintains interest rate swaps with a notional 
   of $50 million, with a fair value of $2.1 million at 
   year-end [2024]."

✅ "We entered into foreign exchange forwards to hedge 
   our European subsidiary's revenue exposure."

✅ "The Company designated commodity futures as cash flow hedges 
   to manage crude oil price volatility."

✅ "We classified outstanding warrants as derivative liabilities 
   due to adjustment features."

✅ "Outstanding credit default swaps protect our loan portfolio 
   against counterparty default."
```

### Common Patterns That Are Correctly Rejected

```
❌ "The SEC regulates derivatives used by financial institutions." 
   (Entity name: SEC)

❌ "We may consider using interest rate swaps in the future." 
   (Hypothetical: "may consider")

❌ "In 2022, we held interest rate swaps, but we liquidated 
   all positions in December." 
   (Terminated: "liquidated all positions")

❌ "Our derivative positions are valued using Level 2 inputs." 
   (Methodology, not position evidence)

❌ "We grant stock options to employees under our 
   equity compensation program." 
   (Employee compensation, not derivative)
```

