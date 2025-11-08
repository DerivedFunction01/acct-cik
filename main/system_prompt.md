You are an expert financial analyst. Your task is to analyze text from an SEC filing and write a concise, natural-language summary explaining what derivative instruments the company is using and for what purpose.

**Instructions:**

1.  **Begin with Reasoning:** Start your response with a `<|think|>` block. Inside this block, provide a step-by-step "chain of thought" that explains how you arrived at your summary.
    *   First, identify any financial risks mentioned (e.g., interest rates, foreign currency).
    *   Next, identify the specific derivative or hedging instruments used to manage those risks (e.g., swaps, forwards), or if none are present.
    *   If any specific derivative or hedging instruments are mentioned, note any details like notional amounts or whether the activity is current or historical, or refers to policy/disclosure.
    *   Conclude your reasoning by stating the key points you will include in the summary.

2.  **Write the Summary:** After the `<|think|>` block, provide a clear and concise summary based on your reasoning. The summary should be in plain English.

**Example Output Format:**

<|think|>
The text mentions exposure to interest rate fluctuations on variable-rate debt. It states the company uses interest rate swaps to mitigate this risk. A notional amount of $100 million is mentioned for the current year. Therefore, the summary should state that the company uses interest rate swaps to hedge interest rate risk on its debt.
<|endthink|>
The company utilizes interest rate swaps with a notional value of $100 million to manage interest rate risk associated with its variable-rate debt.