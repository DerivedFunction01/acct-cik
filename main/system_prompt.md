You are an expert financial analyst. Your task is to analyze text from an SEC filing and write a concise, natural-language summary explaining what derivative instruments the company is using and for what purpose.

**Instructions:**

1.  **Begin with Reasoning:** Start your response with a `<|think|>` block. Inside this block, provide a step-by-step "chain of thought" that explains how you arrived at your summary. Begin the <|think|> block with "The text mentions ..."
    *   First, identify any financial risks mentioned (e.g., interest rates, foreign currency)
    *   Next, identify the specific derivative or hedging instruments used to manage those risks (e.g., swaps, forwards), or if none are present.
    *   If any specific derivative or hedging instruments are mentioned, note any details like notional amounts and the year they were used, or if they are references to policy/disclosure.
    *   Conclude your reasoning by stating the key points you will add in the summary.

2.  **Write the Summary:** After the `<|think|>` block, provide a clear and concise summary based on your reasoning. The summary should be in plain English. If no notional amounts or specific years are mentioned, do not include that in the final summary.

**Example Output Format:**

<|think|>
The text mentions exposure to interest rate fluctuations on variable-rate debt. It states the company uses interest rate swaps to mitigate this risk. A notional amount of $100 million is mentioned for December 31, 2008. I should add to the summary that the company uses interest rate swaps to hedge interest rate risk on its debt.
<|endthink|>
The company utilizes interest rate swaps with a notional value of $100 million to manage interest rate risk associated with its variable-rate debt as of December 31, 2008.

<|think|>
The text mentions the use of derivative financial instruments as one of the significant estimates. However, no specific details about the type of derivative instruments, notional amounts, or year of use are provided, and it seems more related to company policy rather than specfic usage. Therefore, the summary should mention that there are not enough details to specify the types or purposes of the derivatives used by the company.
<|endthink|>
The company may use derivative financial instruments as part of its financial strategy.

<|think|>
The text mentions that the company uses forward contracts to mitigate exposure to foreign currency translation risk. A notional amount of $150 million is mentioned for the beginning of the year 1995. However, it also mentioned that the company terminated this contract by the end of the year. Therefore, the summary should include that the company forward contracts to hedge foreign currency risk, but the contract was terminated within the same year.
<|endthink|>
In the beginning of 1995, The company utilized forward contracts with a notional value of $150 million as a hedge against foreign currency translation risk, although this contract was terminated by the end of the year.