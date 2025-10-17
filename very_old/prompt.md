You are a financial analyst labeling **each sentence independently** for derivative usage during the reporting year in `<reportingYear>year</reportingYear>`. Use these classes and corresponding keywords:
<keywords>
{
  "id2label": {
    "0": "Confirmed Hedging Derivative Usage",
    "1": "Likely Hedging Derivative Usage (Not Confirmed Year)",
    "2": "Mentions Derivatives, Speculative/Policy",
    "3": "Irrelevant / Unrelated Context",
    "4": "Derivative Liabilities / Warrants",
    "5": "Likely Derivative Liabilities / Warrants (Not Confirmed Year)",
    "6": "Embedded Derivatives / Other",
    "7": "Likely Embedded Derivatives / Other (Not Confirmed Year)"
  },
  "MATCHING_KEYWORDS": {
    "0": [
      "interest rate swap",
      "interest rate hedge",
      "swap agreement",
      "cash flow hedge",
      "fair value hedge",
      "economic hedge",
      "swaption",
      "option contract",
      "option agreement",
      "purchased option",
      "written option",
      "commodity option",
      "forward contract",
      "foreign exchange contract",
      "forward foreign",
      "foreign currency forward",
      "forward currency contract",
      "foreign currency future",
      "futures contract",
      "commodity forward",
      "commodity future",
      "notional",
      "notional amount",
      "notional value",
      "designated as hedging",
      "designated as a hedging"
    ],
    "1": ["economic hedge", # and words in class 0],
    "2": [
      "derivative instrument",
      "financial derivative",
      "may use derivatives",
      "over-the-counter derivative",
      "otc derivative"
    ],
    "3": [],
    "4": ["warrants", "warrant derivative", "derivative liability"],
    "5": [ # and words in class 4],
    "6": ["embedded derivative", "derivative asset"],
    "7": [# and words in class 6]
  }
}
</keywords>

**0 – Confirmed Hedging Derivative Usage:** Mentions hedging derivatives for the reporting year with **quantitative evidence** (dollar amounts, notional, transaction counts). 
*Example:* `<reportingYear>2015</reportingYear> During 2015, the company held $50M in interest rate swaps.`
**1 – Likely Hedging Derivative Usage (Not Confirmed Year):** Mentions hedging derivatives (class 0) but year is ambiguous or mismatched, or usage implied without quantification.
*Example:* `<reportingYear>2015</reportingYear> In 2014, the company used foreign currency forward contract with a notional value of $10M.`

**2 – Mentions Derivatives, Speculative/Policy:** Discusses derivatives **without actual transactions**, including policies or potential usage.
*Example:* `<reportingYear>2015</reportingYear> Derivatives may be used to hedge risk exposures.`

**3 – Irrelevant / Unrelated Context:** Not about derivative usage. Keywords: none.
*Example:* `<reportingYear>2015</reportingYear> Warrants are classified as equity instruments.`

**4 – Derivative Liabilities / Warrants :** Mentions **warrant derivative liabilities** measured at fair value.
*Example:* `<reportingYear>2020</reportingYear> The warrant derivative liability was measured at fair value of $3.5M.`

**5 – Likely Derivative Liabilities / Warrants (Not Confirmed Year):** Mentions warrant derivative liabilities but year is ambiguous or mismatched.
*Example:* `<reportingYear>2020</reportingYear> In 2019, the company had $2M in warrant derivative liabilities.`

**6 – Embedded Derivatives / Other:** Mentions embedded derivatives.
*Example:* `<reportingYear>2022</reportingYear> Certain debt instruments contain embedded derivatives that require separate accounting.`

**7 – Likely Embedded Derivatives / Other (Not Confirmed Year):** Mentions embedded derivatives but year is ambiguous or mismatched.
*Example:* `<reportingYear>2022</reportingYear> The liability for the embedded derivative was reclassified to equity on May 20, 2021.`
### Output Instructions
* **Only one class per sentence**. Use the **most specific applicable class** (0 > 1) | (4 > 5) | (6 > 7) > 2 > 3. Label **3** if unrelated.
* Output as CSV with a single column (no headers) inside a code block.  
* End output with "N rows processed".  
* Consider each sentence independently. The <reportingYear> tags indicate the reporting year and are **not part of the sentence**.


You are a financial analyst verifying whether or not a local model labeled **each sentence independently** for derivative usage during the reporting year in `<reportingYear>year</reportingYear>`.Use these classes and corresponding keywords:
<keywords>
{
  "id2label": {
    "0": "Confirmed Hedging Derivative Usage",
    "1": "Likely Hedging Derivative Usage (Not Confirmed Year)",
    "2": "Mentions Derivatives, Speculative/Policy",
    "3": "Irrelevant / Unrelated Context",
    "4": "Derivative Liabilities / Warrants",
    "5": "Likely Derivative Liabilities / Warrants (Not Confirmed Year)",
    "6": "Embedded Derivatives / Other",
    "7": "Likely Embedded Derivatives / Other (Not Confirmed Year)"
  },
  "MATCHING_KEYWORDS": {
    "0": [
      "interest rate swap",
      "interest rate hedge",
      "swap agreement",
      "cash flow hedge",
      "fair value hedge",
      "economic hedge",
      "swaption",
      "option contract",
      "option agreement",
      "purchased option",
      "written option",
      "commodity option",
      "forward contract",
      "foreign exchange contract",
      "forward foreign",
      "foreign currency forward",
      "forward currency contract",
      "foreign currency future",
      "futures contract",
      "commodity forward",
      "commodity future",
      "notional",
      "notional amount",
      "notional value",
      "designated as hedging",
      "designated as a hedging"
    ],
    "1": ["economic hedge", # and words in class 0],
    "2": [
      "derivative instrument",
      "financial derivative",
      "may use derivatives",
      "over-the-counter derivative",
      "otc derivative"
    ],
    "3": [],
    "4": ["warrants", "warrant derivative", "derivative liability"],
    "5": [ # and words in class 4],
    "6": ["embedded derivative", "derivative asset"],
    "7": [# and words in class 6]
  }
}
</keywords>

**0 – Confirmed Hedging Derivative Usage:** Mentions hedging derivatives for the reporting year with **quantitative evidence** (dollar amounts, notional, transaction counts). 
*Example:* `<reportingYear>2015</reportingYear> During 2015, the company held $50M in interest rate swaps.`
**1 – Likely Hedging Derivative Usage (Not Confirmed Year):** Mentions hedging derivatives (class 0) but year is ambiguous or mismatched, or usage implied without quantification.
*Example:* `<reportingYear>2015</reportingYear> In 2014, the company used foreign currency forward contract with a notional value of $10M.`

**2 – Mentions Derivatives, Speculative/Policy:** Discusses derivatives **without actual transactions**, including policies or potential usage.
*Example:* `<reportingYear>2015</reportingYear> Derivatives may be used to hedge risk exposures.`

**3 – Irrelevant / Unrelated Context:** Not about derivative usage. Keywords: none.
*Example:* `<reportingYear>2015</reportingYear> Warrants are classified as equity instruments.`

**4 – Derivative Liabilities / Warrants :** Mentions **warrant derivative liabilities** measured at fair value.
*Example:* `<reportingYear>2020</reportingYear> The warrant derivative liability was measured at fair value of $3.5M.`

**5 – Likely Derivative Liabilities / Warrants (Not Confirmed Year):** Mentions warrant derivative liabilities but year is ambiguous or mismatched.
*Example:* `<reportingYear>2020</reportingYear> In 2019, the company had $2M in warrant derivative liabilities.`

**6 – Embedded Derivatives / Other:** Mentions embedded derivatives.
*Example:* `<reportingYear>2022</reportingYear> Certain debt instruments contain embedded derivatives that require separate accounting.`

**7 – Likely Embedded Derivatives / Other (Not Confirmed Year):** Mentions embedded derivatives but year is ambiguous or mismatched.
*Example:* `<reportingYear>2022</reportingYear> The liability for the embedded derivative was reclassified to equity on May 20, 2021.`

### Output Instructions
* **Only one class per sentence**. Use the **most specific applicable class** (0 > 1) | (4 > 5) | (6 > 7) > 2 > 3. Label **3** if unrelated.
* If the model's label is incorrect, output a line in the format:  
  `case_num: correct_label`  
* If the model is correct, output nothing.  
* Output a single JSON dictionary block, no extra text. Example:

```json
{
  1: 0,
  2: 4,
  3: 1,
  4: 2
}
```