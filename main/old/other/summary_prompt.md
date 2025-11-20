You are summarizing text extracted from an SEC filing. The text may be incomplete or fragmented.

TASK:
Produce a 2–4 sentence summary describing any derivative/risk exposure-related information in this chunk.

COVER:
- Whether the company uses derivatives and the primary purpose (hedging or otherwise).
- The specific risks mentioned (interest rate, foreign currency, commodity, etc.).
- The instruments mentioned (swaps, forwards, options, etc.).
- Whether usage:
 - use
 - historical
 - terminated
 - potential ("may use", "periodically", "from time to time", "in the future").
 - non use
- Any significant notional amounts or maturities if stated.

RULES:
- Do not invent information. Only use what appears in the text. Give numerical figures if either year or amounts are present.
- Keep the output as a single paragraph with no bullet points.
- Each text is treated independently, and they are from different filings.
- If no derivative information is present, still summarize the text briefly and state why it doesn't relate to derivatives and hedging.
