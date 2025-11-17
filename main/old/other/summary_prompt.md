You are summarizing text extracted from an SEC filing. The text may be incomplete or fragmented.

TASK:
Produce a concise 2–3 sentence summary describing any derivative-related information in this chunk.

COVER:
- Whether the company uses derivatives and the primary purpose (hedging or otherwise).
- The specific risks mentioned (interest rate, foreign currency, commodity, etc.).
- The instruments mentioned (swaps, forwards, options, etc.).
- Whether usage is active, historical, terminated, or only potential ("may use", "periodically").
- Any significant notional amounts or maturities if stated.
- A brief statement of confidence about whether the firm explicitly and actively uses derivatives, based only on this fragment.

RULES:
- Do not invent information. Only use what appears in the text.
- Keep the output as a single paragraph with no bullet points.
- If no derivative information is present, output exactly: "No derivative information."
