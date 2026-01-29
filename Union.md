# Union Coverage Detection Strategy

## 1. Objective
Replicate and extend the methodology for identifying collective bargaining coverage in 10-K filings.

**Target Variables:**
- `Cover_Dummy` (0/1): Does the firm have collective bargaining agreements?
- `Cover_Percent` (Float): Percentage of workforce covered.
- `Cover_Count` (Int): Number of employees covered (extension of original paper).

---

## 2. The Pipeline

### Phase 1: Broad Filtering (The Net)
*Goal: Reduce the search space from all 10-Ks to likely candidates.*

Use the keywords defined in the research paper to flag filings for processing.
**Keywords:**
- `collective bargaining`
- `labor union` / `labour union`
- `labor agreement` / `labour agreement`
- `labor contract` / `labour contract`
- `labor organization` / `labour organization`
- `union agreement`
- `union contract`

### Phase 2: Section Extraction
*Goal: Isolate the signal.*

1.  Extract **Item 1 (Business)**.
2.  Locate the **"Employees"** or **"Human Capital"** subsection.
    *   *Note:* Modern 10-Ks often use "Human Capital Resources" as a header.

### Phase 3: Classification & Extraction (The Logic)
*Goal: Determine `Cover_Dummy` and extract stats.*

This is where we "borrow" from `template.py`. Instead of using the file to generate text, we use its lists to build our detection patterns.

#### A. The "No Coverage" Detector (Cover_Dummy = 0)
We need to explicitly identify the control group.

**Borrow from `template.py` -> `no_coverage_statements`**
Convert these templates into Regex patterns:
- *Template:* "None of our employees are represented by a union"
- *Regex:* `r"none of (?:our|the) employees are represented by a (?:labor )?union"`
- *Template:* "We are a non-union employer"
- *Regex:* `r"are a non-union employer"`
- *Template:* "not a party to any collective bargaining agreements"
- *Regex:* `r"not a party to any collective bargaining agreement"`

#### B. The "Coverage" Detector (Cover_Dummy = 1)
Identify positive assertions of coverage.

**Borrow from `template.py` -> `coverage_statements_*`**
- *Template:* "{pct}% of our employees are represented by unions"
- *Regex:* `r"(\d(?:\.\d)?)\s*%\s*of\s*(?:our|the)\s*employees\s*are\s*represented"`
- *Template:* "{cb_count} employees are covered by collective bargaining"
- *Regex:* `r"(\d{1,3}(?:,\d{3})*)\s*employees\s*are\s*covered"`

#### C. Entity Validation (Reducing False Positives)
Ensure the word "Union" refers to a labor body, not "European Union" or "Credit Union".

**Borrow from `template.py` -> `us_unions`, `international_unions`, `generic_unions`**
Create a "Union Entity Whitelist" for Named Entity Recognition (NER). If a sentence contains a number and a match from this list, confidence increases.
- *Examples to match:* "Teamsters", "UAW", "United Steelworkers", "Works Council".
- *Logic:* If `Cover_Dummy` is ambiguous, check if a specific union name from `us_unions` appears in the target paragraph.

---

## 3. What to Borrow vs. What to Ignore

| Resource in `template.py` | Action | Usage |
| :--- | :--- | :--- |
| `no_coverage_statements` | **Keep** | Essential for identifying the control group (0). |
| `coverage_statements_pct` | **Keep** | Primary source for `Cover_Percent` regex patterns. |
| `coverage_statements_count`| **Keep** | Primary source for `Cover_Count` regex patterns. |
| `us_unions` / `intl_unions`| **Keep** | Use as a lookup dictionary to validate specific union names. |
| `risk_intro_phrases` | **Context**| Use to *exclude* matches. If a match appears in a sentence with "could experience" or "may face", it is likely a Risk Factor (Item 1A) bleeding into Item 1, or hypothetical language. |
| `locations` / `facilities` | **Ignore** | Too granular. We don't need to know *where* (e.g., "Akron, Ohio") the union is, just that it exists. |
| `months` / `quarters` | **Ignore** | Standard date parsers are better for this. |

---

## 4. Implementation Strategy

1.  **Flatten the Lists**: Take the useful lists from `template.py` and flatten them into a single regex string joined by `|` (OR operator) for fast matching.
    *   *Example:* `union_pattern = r"(Teamsters|UAW|United Steelworkers|...)"`
2.  **Sentence Tokenization**: Split the "Employees" section into sentences.
3.  **Priority Scoring**:
    *   **Score 10**: Matches `coverage_statements` regex AND contains a number.
    *   **Score -10**: Matches `no_coverage_statements` regex.
    *   **Score 5**: Mentions a specific union from `us_unions`.
    *   **Score -5**: Contains "may", "could", "risk" (Hypothetical).

## 5. Extension: Expiration Dates
*Optional extension not in original paper.*

**Borrow from `template.py` -> `expiration_phrases`**
- Use these to extract *when* the contracts expire, adding a dimension of "Labor Risk" to the dataset.
- *Regex:* `r"expires\s*in\s*(\w\s*\d{4})"`

## 6. Next Steps
1.  Write the script to extract Item 1 "Employees" text.
2.  Develop the Regex library based on the mapping above.
3.  Run against the 200 random sample set (as per paper) to tune precision.
