# Labor Union Disclosure Extraction - Complete JSON Specification
## Expected Output Format with Examples and Rules

---

## OVERVIEW

This document specifies the expected JSON array output for `item1_details_json` and `item1a_details_json` extraction. It covers:
- Basic examples and edge cases
- Context inheritance across sentences
- Negation handling (flipping percentages)
- Temporal scope (current vs. historical vs. future)
- Data structure and field definitions

## Starter keywords to identify relevant sentences:
Assume labour = labor, bargain = bargaining, union = unionized

- collective + bargain
- bargaining + (agreement, contracts)
- union / unionized
- non-union(ized)
- employees/workers + represented by
- labor + (agreements, contracts, organizations)

---

## CORE PRINCIPLE: TEMPORAL SCOPE

**"Assume current unless stated otherwise (in the same sentence)"**

The filing year is passed as a parameter, allowing automatic detection and exclusion of purely historical statements.

---

# PART 1: ITEM 1 DETAILS JSON ARRAY

## Basic Examples

### Example 1: Simple Domestic Unionization with Percentage

**Input Sentence:**
```
"Approximately 12% of our U.S. workforce is represented by labor unions."
```

**Expected JSON Output:**
```json
{
  "sentence": "Approximately 12% of our U.S. workforce is represented by labor unions.",
  "keyword_matched": "labor unions",
  "geographic_context": {
    "region": "USA",
    "countries": [
      {
        "name": "United States",
        "code": "US"
      }
    ],
    "specificity": "explicit"
  },
  "coverage_data": {
    "percentage": 12,
    "percentage_raw_stated": null,
    "calculated_percentage": null,
    "type": "EXPLICIT_PERCENT",
    "percentage_qualifier": null,
    "employee_count_covered": null,
    "employee_count_not_covered": null,
    "employee_count_total": null,
    "negated": false,
    "negation_type": null,
    "temporal_scope": "CURRENT",
    "effective_date": null,
    "expected_date": null,
    "ambiguity": null,
    "note": null
  }
}
```

---

### Example 2: International Unionization with Multiple Countries

**Input Sentence:**
```
"Our operations in Germany, France, and the UK have collective bargaining agreements covering approximately 55% of employees in those regions."
```

**Expected JSON Output:**
```json
{
  "sentence": "Our operations in Germany, France, and the UK have collective bargaining agreements covering approximately 55% of employees in those regions.",
  "keyword_matched": "collective bargaining agreements",
  "geographic_context": {
    "region": "INTERNATIONAL",
    "countries": [
      {
        "name": "Germany",
        "code": "DE"
      },
      {
        "name": "France",
        "code": "FR"
      },
      {
        "name": "United Kingdom",
        "code": "GB"
      }
    ],
    "specificity": "explicit"
  },
  "coverage_data": {
    "percentage": 55,
    "percentage_raw_stated": null,
    "calculated_percentage": null,
    "type": "EXPLICIT_PERCENT",
    "percentage_qualifier": null,
    "employee_count_covered": null,
    "employee_count_not_covered": null,
    "employee_count_total": null,
    "negated": false,
    "negation_type": null,
    "temporal_scope": "CURRENT",
    "effective_date": null,
    "expected_date": null,
    "ambiguity": null,
    "note": null
  }
}
```

---

### Example 3: Qualitative Coverage (No Percentage)

**Input Sentence:**
```
"A significant portion of our manufacturing workforce is subject to collective bargaining agreements."
```

**Expected JSON Output:**
```json
{
  "sentence": "A significant portion of our manufacturing workforce is subject to collective bargaining agreements.",
  "keyword_matched": "collective bargaining agreements",
  "geographic_context": {
    "region": "UNKNOWN",
    "countries": [],
    "specificity": "implicit"
  },
  "coverage_data": {
    "percentage": null,
    "percentage_raw_stated": null,
    "calculated_percentage": null,
    "type": "QUALITATIVE",
    "percentage_qualifier": "SIGNIFICANT",
    "employee_count_covered": null,
    "employee_count_not_covered": null,
    "employee_count_total": null,
    "negated": false,
    "negation_type": null,
    "temporal_scope": "CURRENT",
    "effective_date": null,
    "expected_date": null,
    "ambiguity": null,
    "note": null
  }
}
```

---

### Example 3.5: Employee Counts Without Percentage

**Input Sentence:**
```
"Out of our 50,000 U.S. employees, approximately 6,000 are represented by unions."
```

**Expected JSON Output:**
```json
{
  "sentence": "Out of our 50,000 U.S. employees, approximately 6,000 are represented by unions.",
  "keyword_matched": "unions",
  "geographic_context": {
    "region": "USA",
    "countries": [
      {
        "name": "United States",
        "code": "US"
      }
    ],
    "specificity": "explicit"
  },
  "coverage_data": {
    "percentage": 12,
    "percentage_raw_stated": null,
    "calculated_percentage": 12,
    "type": "CALCULATED_FROM_COUNTS",
    "percentage_qualifier": null,
    "employee_count_covered": 6000,
    "employee_count_not_covered": 44000,
    "employee_count_total": 50000,
    "negated": false,
    "negation_type": null,
    "temporal_scope": "CURRENT",
    "effective_date": null,
    "expected_date": null,
    "ambiguity": null,
    "note": "Calculated percentage: 6,000 / 50,000 = 12%"
  }
}
```

**Calculation Rule:** When employee counts are provided (covered + not_covered + total), calculate the percentage and set `type: "CALCULATED_FROM_COUNTS"`. Store both the calculated percentage and the raw employee counts for downstream analysis/validation.

## Context Inheritance Across Sentences

### Example 4: Geographic Context Carries Forward

**Input Sentences (in sequence):**
```
Sentence 1: "Our international operations span Europe, particularly in Germany, France, and Spain."

Sentence 2: "Approximately 45% of our employees in these regions are covered by collective bargaining agreements."

Sentence 3: "We also have unionized operations in Japan with 30% coverage."
```

**Expected JSON Output:**

```json
[
  {
    "sentence": "Our international operations span Europe, particularly in Germany, France, and Spain.",
    "keyword_matched": null,
    "geographic_context": {
      "region": "INTERNATIONAL_EUROPE",
      "countries": [
        {
          "name": "Germany",
          "code": "DE"
        },
        {
          "name": "France",
          "code": "FR"
        },
        {
          "name": "Spain",
          "code": "ES"
        }
      ],
      "specificity": "explicit"
    },
    "coverage_data": null,
    "note": "Geographic context established, no coverage data in this sentence"
  },
  {
    "sentence": "Approximately 45% of our employees in these regions are covered by collective bargaining agreements.",
    "keyword_matched": "collective bargaining agreements",
    "geographic_context": {
      "region": "INTERNATIONAL_EUROPE",
      "countries": [
        {
          "name": "Germany",
          "code": "DE"
        },
        {
          "name": "France",
          "code": "FR"
        },
        {
          "name": "Spain",
          "code": "ES"
        }
      ],
      "specificity": "inherited_from_previous",
      "inherited_from_sentence_index": 0
    },
    "coverage_data": {
      "percentage": 45,
      "percentage_raw_stated": null,
      "calculated_percentage": null,
      "type": "EXPLICIT_PERCENT",
      "percentage_qualifier": null,
      "employee_count_covered": null,
      "employee_count_not_covered": null,
      "employee_count_total": null,
      "negated": false,
      "negation_type": null,
      "temporal_scope": "CURRENT",
      "effective_date": null,
      "expected_date": null,
      "ambiguity": null,
      "note": "Geographic context inherited from Sentence 1"
    }
  },
  {
    "sentence": "We also have unionized operations in Japan with 30% coverage.",
    "keyword_matched": "unionized",
    "geographic_context": {
      "region": "INTERNATIONAL_ASIA",
      "countries": [
        {
          "name": "Japan",
          "code": "JP"
        }
      ],
      "specificity": "explicit"
    },
    "coverage_data": {
      "percentage": 30,
      "percentage_raw_stated": null,
      "calculated_percentage": null,
      "type": "EXPLICIT_PERCENT",
      "percentage_qualifier": null,
      "employee_count_covered": null,
      "employee_count_not_covered": null,
      "employee_count_total": null,
      "negated": false,
      "negation_type": null,
      "temporal_scope": "CURRENT",
      "effective_date": null,
      "expected_date": null,
      "ambiguity": null,
      "note": null
    }
  }
]
```

**Inheritance Rule:** When a sentence mentions coverage data (%, count, qualifier) but NOT a geographic scope, inherit the most recent geographic context from a previous sentence. Flag the source sentence with `inherited_from_sentence_index`.

**Inheritance Boundary:** Inheritance stops when a new, explicit geographic scope is introduced. Within a paragraph, the most recently mentioned country/region carries forward.

---

## Geographic Context Inference from Union Names

### Example 4.5: Union Name Implies Region

**Input Sentence:**
```
"Approximately 30% of our employees are represented by the UAW (United Auto Workers)."
```

**Expected JSON Output:**
```json
{
  "sentence": "Approximately 30% of our employees are represented by the UAW (United Auto Workers).",
  "keyword_matched": "represented by the UAW",
  "geographic_context": {
    "region": "USA",
    "countries": ["USA"],
    "specificity": "inferred_from_union_name",
    "union_name_indicator": "UAW (United Auto Workers)",
    "note": "UAW is a US-based union; inferred USA region"
  },
  "coverage_data": {
    "percentage": 30,
    "type": "EXPLICIT_PERCENT",
    "percentage_qualifier": null,
    "negated": false,
    "temporal_scope": "CURRENT"
  }
}
```

**Inference Rule:** When a sentence mentions a specific union/labor organization name without explicit geographic context, use known union names to infer the region. Flag the inference source in `specificity: "inferred_from_union_name"` and record the union name in `union_name_indicator`.

---

### Example 4.6: Multiple Unions Indicate Multi-Region

**Input Sentence:**
```
"Our workforce is represented by the UAW in the United States, IG Metall in Germany, and Unite the Union in the UK."
```

**Expected JSON Output:**
```json
{
  "sentence": "Our workforce is represented by the UAW in the United States, IG Metall in Germany, and Unite the Union in the UK.",
  "keyword_matched": "represented by the UAW, IG Metall, Unite the Union",
  "geographic_context": {
    "region": "International",
    "countries": [
      {
        "name": "United States",
        "code": "US"
      },
      {
        "name": "Germany",
        "code": "DE"
      },
      {
        "name": "United Kingdom",
        "code": "GB"
      }
    ],
    "specificity": "explicit_and_inferred",
    "explicit_countries": ["United States", "Germany", "United Kingdom"],
    "inferred_countries": [],
    "union_names_mentioned": ["UAW", "IG Metall", "Unite the Union"],
    "note": "Multiple unions indicate multiple regions"
  },
  "coverage_data": {
    "percentage": null,
    "percentage_raw_stated": null,
    "calculated_percentage": null,
    "type": "QUALITATIVE",
    "percentage_qualifier": "UNSPECIFIED",
    "employee_count_covered": null,
    "employee_count_not_covered": null,
    "employee_count_total": null,
    "negated": false,
    "negation_type": null,
    "temporal_scope": "CURRENT",
    "effective_date": null,
    "expected_date": null,
    "ambiguity": null,
    "note": null
  }
}
```

---

## Major Unions Reference (Quick Lookup)

### High-Confidence Union Names (Known Origin)

**USA:**
- UAW (United Auto Workers)
- IBT (Teamsters)
- SEIU (Service Employees)
- Steelworkers / USW

**Canada:**
- Unifor
- CUPE (Canadian Union of Public Employees)

**Europe:**
- IG Metall (Germany)
- Unite the Union (UK)
- CFDT (France)

**Asia-Pacific:**
- AMWU (Australian Manufacturing Workers Union)

**Multi-Regional:**
- International Transport Federation (ITF)

---

**Rule:** Only use unions you are confident about mapping to a specific region. For unfamiliar unions, rely on regional language/phrase patterns instead (see below).

---

## Regional Language & Phrase Patterns

When a union name is unfamiliar or not in the major list, look for regional language patterns or descriptive phrases in the sentence:

### USA/North America Indicators
**Phrases:**
- "U.S." / "USA" / "United States"
- "American" / "American workers"
- "domestic" / "domestic operations"
- "domestic and international" (domestic = USA unless otherwise stated)
- "(United)" in union name → likely USA (e.g., United Steelworkers)
- "across the United States" / "throughout the US"

**Examples:**
```
"Our U.S. workforce is 12% unionized."
→ Explicit: USA

"American workers in our operations..."
→ Phrase: "American" → USA

"United Rubber Workers represent..."
→ Union name pattern: "United" (USA-origin union)
```

---

### Canada Indicators
**Phrases:**
- "Canada" / "Canadian"
- "North America" (if Canada specifically mentioned in context)
- "our Canadian subsidiaries"
- "Canada and the United States" (indicates both, with Canada explicit)

**Examples:**
```
"Our Canadian operations have 25% unionization."
→ Explicit: Canada

"Unifor represents our workforce."
→ Known major union: Unifor → Canada
```

---

### Europe Indicators
**Phrases:**
- "Europe" / "European" / "European operations"
- "European Union"
- Country names: Germany, France, UK, Netherlands, Spain, Italy, Sweden, etc.
- Language patterns: German words (Metall, Arbeiter, Verband), French words (Confédération), British English (Unite)
- "Central Europe" / "Eastern Europe" / "Southern Europe"
- "across our European sites"

**Specific Country Clues:**
- German union characteristics: "Metall", "IG", "Verdi" (German words/unions)
- French union characteristics: "CFDT", "CGT", "Confédération"
- UK union characteristics: "Unite", "Unison", "British"
- Dutch union characteristics: "FNV", "CNV" (Dutch abbreviations)

**Examples:**
```
"Our workforce in Germany and France is unionized."
→ Explicit countries: Germany, France → Europe

"IG Metall represents our workforce."
→ Known: IG Metall → Germany

"Central European operations are unionized."
→ Phrase: "Central European" → Europe (region unknown)

"Works councils under German law..."
→ Phrase: "German law" → Germany
```

---

### Asia-Pacific Indicators
**Phrases:**
- "Asia" / "Asia Pacific" / "APAC"
- "Japan" / "Japanese" / "our Japan facility"
- "Australia" / "Australian"
- "China" / "Chinese"
- "India" / "Indian"
- "Singapore" / "South Korea"
- "Far East"
- "our Asian operations"

**Examples:**
```
"Our Asia Pacific operations have limited unionization."
→ Phrase: "Asia Pacific" → INTERNATIONAL_ASIA

"Japanese labor law requires..."
→ Phrase: "Japanese" → Japan (Asia-Pacific)

"Our APAC workforce..."
→ Phrase: "APAC" → Asia-Pacific
```

---

### Other/Unknown Region Indicators
**Phrases that suggest international but unclear:**
- "our international operations" (without country specifics) → INTERNATIONAL (region unknown)
- "other countries" (when USA/Canada mentioned previously) → INTERNATIONAL
- "global workforce"
- "Latin America" / "South America"
- "Middle East"
- "Africa"

---

## Pattern Matching Rules

### Rule 1: Explicit Country/Region Mention (Highest Priority)
Any sentence mentioning country names or region names directly → use those explicitly.

```
"Germany, France, and UK operations..."
→ Explicit: Germany, France, UK
```

---

### Rule 2: Language/National Adjectives (Medium-High Priority)
Words like "German", "French", "British", "Japanese", "American", "Australian" → infer region.

```
"German workers under collective agreements..."
→ German → Germany (Europe)
```

---

### Rule 3: Union Name (Medium Priority)
- If union is in the "Major Unions" list → use known region
- If union name contains country/language clues → infer from those clues

```
"IG Metall represents..." 
→ Known: IG Metall → Germany

"Our workers in some_unknown_union..."
→ Union not recognized, fall back to other patterns
```

---

### Rule 4: Contextual Phrases (Medium Priority)
Phrases like "European operations", "APAC facilities", "international subsidiaries" → infer broader region.

```
"Our European manufacturing subsidiaries..."
→ "European" → INTERNATIONAL_EUROPE (country unknown)
```

---

### Rule 5: Industry/Regulation Clues (Lower Priority)
References to specific national laws or industries.

```
"Works councils under German labor law..."
→ "German labor law" → Germany

"Australian Fair Work Commission..."
→ "Australian" → Australia
```

---

## Implementation Approach

Rather than maintain a massive union database, use a **tiered pattern matching**:

1. **Tier 1 (High Confidence):** Check against major unions list (UAW, Unifor, IG Metall, etc.)
2. **Tier 2 (Medium Confidence):** Extract explicit country/region mentions and language patterns
3. **Tier 3 (Low Confidence):** Use generic regional descriptors ("European", "APAC", "international")
4. **Tier 4 (Fallback):** Mark as UNKNOWN with a note: "Union name not recognized; no explicit geography"

**Example Flow:**
```
Sentence: "15% of our workers are represented by the FNV."

Step 1: Is FNV in major unions list? No
Step 2: Does sentence mention explicit countries? No
Step 3: Does FNV have language clues? 
   → FNV = Dutch abbreviation → infer Netherlands/Europe
Step 4: Mark as: 
   specificity: "inferred_from_union_language"
   region: "INTERNATIONAL_EUROPE"
   countries: ["Netherlands"]
   note: "FNV is Dutch union; inferred from abbreviation"
```

---

## Union Inference Rules

### Rule 1: Major Union Lookup First
If the union name is in the "Major Unions Reference" list → use known region immediately.

**Example:**
```
"15% represented by IG Metall"
→ IG Metall in major list → Germany
→ specificity: "inferred_from_union_name"
```

---

### Rule 2: Unfamiliar Union? Use Regional Language Patterns
If union name is not in the major list, look for country/region language clues in the sentence.

**Example:**
```
"15% represented by FNV"
→ FNV not in major unions list
→ FNV is a Dutch abbreviation (Federatie Nederlandse Vakbeweging)
→ Infer: Netherlands (Europe)
→ specificity: "inferred_from_union_language" or "inferred_from_phrase_pattern"
```

---

### Rule 3: Explicit Geography Takes Priority
If sentence mentions both a union AND explicit country/region, use explicit geography.

**Example:**
```
"Our German operations have collective bargaining through local unions."
→ "German operations" is explicit
→ Use: Germany (Europe)
→ specificity: "explicit"
```

---

### Rule 4: Multiple Unions = Multiple Regions
If multiple union names are mentioned, each union may imply a different region.

**Example:**
```
"UAW represents our US operations; IG Metall our German operations."
→ UAW → USA, IG Metall → Germany
→ region: "MIXED"
→ countries: ["USA", "Germany"]
```

---

### Rule 5: Unknown Union + No Geographic Clues = Unknown Region
If union is unknown AND sentence has no explicit geography or language clues:

**Example:**
```
"15% represented by the ABC Labor Coalition"
→ ABC Labor Coalition not in major list
→ No country/region clues in sentence
→ Mark: region: "UNKNOWN", ambiguity: "UNION_ORIGIN_UNKNOWN"
```

---

## Negation Handling

### Example 5: Negation - NOT Unionized (Flip to Positive)

**Input Sentence:**
```
"60% of our workforce is NOT covered by collective bargaining agreements."
```

**Expected JSON Output:**
```json
{
  "sentence": "60% of our workforce is NOT covered by collective bargaining agreements.",
  "keyword_matched": "collective bargaining agreements",
  "geographic_context": {
    "region": "UNKNOWN",
    "countries": [],
    "specificity": "implicit"
  },
  "coverage_data": {
    "percentage": 40,
    "percentage_raw_stated": 60,
    "calculated_percentage": null,
    "type": "EXPLICIT_PERCENT",
    "percentage_qualifier": null,
    "employee_count_covered": null,
    "employee_count_not_covered": null,
    "employee_count_total": null,
    "negated": true,
    "negation_type": "NOT_COVERED",
    "temporal_scope": "CURRENT",
    "effective_date": null,
    "expected_date": null,
    "ambiguity": null,
    "note": "Original statement: 60% NOT covered. Inverted to: 40% covered"
  }
}
```

**Negation Rule:** If "X% are NOT covered", automatically invert to "(100 - X)% are covered". Store the original stated percentage in `percentage_raw_stated` for audit trail. Flag `negated: true`.

---

### Example 6: Negation - Zero Coverage Stated

**Input Sentence:**
```
"We have no employees covered by collective bargaining agreements."
```

**Expected JSON Output:**
```json
{
  "sentence": "We have no employees covered by collective bargaining agreements.",
  "keyword_matched": "collective bargaining agreements",
  "geographic_context": {
    "region": "UNKNOWN",
    "countries": [],
    "specificity": "implicit"
  },
  "coverage_data": {
    "percentage": 0,
    "percentage_raw_stated": null,
    "calculated_percentage": null,
    "type": "EXPLICIT_PERCENT",
    "percentage_qualifier": null,
    "employee_count_covered": 0,
    "employee_count_not_covered": null,
    "employee_count_total": null,
    "negated": true,
    "negation_type": "ZERO_COVERAGE",
    "temporal_scope": "CURRENT",
    "effective_date": null,
    "expected_date": null,
    "ambiguity": null,
    "note": "Explicitly states zero unionization"
  }
}
```

---

### Example 7: Negation - Qualitative

**Input Sentence:**
```
"None of our workforce is unionized."
```

**Expected JSON Output:**
```json
{
  "sentence": "None of our workforce is unionized.",
  "keyword_matched": "unionized",
  "geographic_context": {
    "region": "UNKNOWN",
    "countries": [],
    "specificity": "implicit"
  },
  "coverage_data": {
    "percentage": 0,
    "percentage_raw_stated": null,
    "calculated_percentage": null,
    "type": "QUALITATIVE",
    "percentage_qualifier": "NONE",
    "employee_count_covered": 0,
    "employee_count_not_covered": null,
    "employee_count_total": null,
    "negated": true,
    "negation_type": "QUALITATIVE_ZERO",
    "temporal_scope": "CURRENT",
    "effective_date": null,
    "expected_date": null,
    "ambiguity": null,
    "note": "Qualitative expression of zero coverage"
  }
}
```

---

### Example 8: Region + Negation

**Input Sentences (in sequence):**
```
Sentence 1: "Our operations in the United States and Canada employ union-represented workers."

Sentence 2: "However, 80% of employees in other countries are not covered by collective bargaining."
```

**Expected JSON Output:**

```json
[
  {
    "sentence": "Our operations in the United States and Canada employ union-represented workers.",
    "keyword_matched": "union-represented",
    "geographic_context": {
      "region": "DOMESTIC",
      "countries": ["USA", "Canada"],
      "specificity": "explicit"
    },
    "coverage_data": {
      "percentage": null,
      "type": "QUALITATIVE",
      "percentage_qualifier": "UNSPECIFIED",
      "negated": false,
      "temporal_scope": "CURRENT"
    }
  },
  {
    "sentence": "However, 80% of employees in other countries are not covered by collective bargaining.",
    "keyword_matched": "collective bargaining",
    "geographic_context": {
      "region": "INTERNATIONAL",
      "countries": [],
      "specificity": "implicit",
      "note": "'Other countries' = international, excluding USA/Canada"
    },
    "coverage_data": {
      "percentage": 20,
      "percentage_raw_stated": 80,
      "type": "EXPLICIT_PERCENT",
      "percentage_qualifier": null,
      "negated": true,
      "negation_type": "NOT_COVERED",
      "temporal_scope": "CURRENT"
    }
  }
]
```

---

## Coverage Data: Employee Counts

### Example 9: Count-Based Coverage (Calculated Percentage)

**Input Sentence:**
```
"Approximately 2,500 of our 8,000 U.S. employees are represented by unions."
```

**Expected JSON Output:**
```json
{
  "sentence": "Approximately 2,500 of our 8,000 U.S. employees are represented by unions.",
  "keyword_matched": "represented by unions",
  "geographic_context": {
    "region": "USA",
    "countries": ["USA"],
    "specificity": "explicit"
  },
  "coverage_data": {
    "percentage": null,
    "calculated_percentage": 31.25,
    "type": "CALCULATED_FROM_COUNTS",
    "employee_count_covered": 2500,
    "employee_count_total": 8000,
    "percentage_qualifier": null,
    "negated": false,
    "temporal_scope": "CURRENT",
    "note": "Calculated: (2,500 / 8,000) * 100 = 31.25%"
  }
}
```

---

### Example 10: Count-Based with Negation

**Input Sentence:**
```
"Of our 10,000 employees, 1,000 are not subject to collective bargaining."
```

**Expected JSON Output:**
```json
{
  "sentence": "Of our 10,000 employees, 1,000 are not subject to collective bargaining.",
  "keyword_matched": "collective bargaining",
  "geographic_context": {
    "region": "UNKNOWN",
    "countries": [],
    "specificity": "implicit"
  },
  "coverage_data": {
    "percentage": null,
    "calculated_percentage": 90,
    "type": "CALCULATED_FROM_COUNTS",
    "employee_count_not_covered": 1000,
    "employee_count_total": 10000,
    "employee_count_covered_calculated": 9000,
    "percentage_qualifier": null,
    "negated": true,
    "negation_type": "NOT_COVERED",
    "temporal_scope": "CURRENT",
    "note": "Inverted: 1,000 NOT covered → 9,000 covered out of 10,000 = 90%"
  }
}
```

---

## Ambiguous Geographic Scope

### Example 11: No Clear Geographic Scope

**Input Sentence:**
```
"Substantially all of our workforce is covered by collective bargaining agreements."
```

**Expected JSON Output:**
```json
{
  "sentence": "Substantially all of our workforce is covered by collective bargaining agreements.",
  "keyword_matched": "collective bargaining agreements",
  "geographic_context": {
    "region": "UNKNOWN",
    "countries": [],
    "specificity": "implicit",
    "note": "No geographic qualifier provided. Could be global or domestic (unclear)."
  },
  "coverage_data": {
    "percentage": null,
    "type": "QUALITATIVE",
    "percentage_qualifier": "SUBSTANTIALLY_ALL",
    "negated": false,
    "temporal_scope": "CURRENT",
    "ambiguity": "SCOPE_UNCLEAR"
  }
}
```

**Ambiguity Flag:** When the geographic scope is genuinely unclear (no country/region mentioned), include `"ambiguity": "SCOPE_UNCLEAR"` for later manual review.

---

## False Positives and Exclusions

### Example 12: Reference to Item 1A (EXCLUDE)

**Input Sentence:**
```
"For a detailed discussion of unionization risks, refer to Item 1A."
```

**Expected JSON Output:**
```json
null
```

**Exclusion Rule:** Sentences that are references or cross-references to other items should be excluded entirely. They don't contain actual coverage information.

---

## Temporal Scope: Historical References

### Example 13: Pure Historical Reference (EXCLUDE)

**Input Sentence (in 2005 filing):**
```
"We decertified our union agreements in 2002."
```

**Expected JSON Output:**
```json
null
```

**Temporal Rule:** When a sentence mentions only a PAST event/year with NO statement of current unionization status, exclude it entirely. The filing year parameter allows automatic detection of past dates.

**Logic:**
- Contains past year (2002) and filing year (2005) where 2002 < 2005
- No mention of current unionization status in the same sentence
- Result: EXCLUDE (pure history)

---

### Example 13b: Historical + Current Status (INCLUDE)

**Input Sentence (in 2008 filing):**
```
"Although we decertified our union agreements in 2002, we have since re-unionized and currently 18% of our workforce is union-represented."
```

**Expected JSON Output:**
```json
{
  "sentence": "Although we decertified our union agreements in 2002, we have since re-unionized and currently 18% of our workforce is union-represented.",
  "keyword_matched": "union-represented",
  "geographic_context": {
    "region": "UNKNOWN",
    "countries": [],
    "specificity": "implicit"
  },
  "coverage_data": {
    "percentage": 18,
    "type": "EXPLICIT_PERCENT",
    "percentage_qualifier": null,
    "negated": false,
    "temporal_scope": "CURRENT",
    "note": "Current status stated in same sentence with explicit percentage"
  }
}
```

**Temporal Rule:** If a sentence mentions PAST events but also explicitly states CURRENT unionization status in the same sentence, include it with `temporal_scope: "CURRENT"`.

---

### Example 14: Vague Past Only (EXCLUDE)

**Input Sentence (in 2005 filing):**
```
"Several years ago, we had unionized operations in Europe."
```

**Expected JSON Output:**
```json
null
```

**Temporal Rule:** Vague past references ("several years ago", "previously", "historically") without current status are excluded.

---

### Example 15: Vague Past + Current Status (INCLUDE)

**Input Sentence (in 2005 filing):**
```
"Although we previously had unionized operations in Europe, we now maintain 8% unionization in our current operations."
```

**Expected JSON Output:**
```json
{
  "sentence": "Although we previously had unionized operations in Europe, we now maintain 8% unionization in our current operations.",
  "keyword_matched": "unionization",
  "geographic_context": {
    "region": "INTERNATIONAL_EUROPE",
    "countries": ["Europe"],
    "specificity": "explicit"
  },
  "coverage_data": {
    "percentage": 8,
    "type": "EXPLICIT_PERCENT",
    "percentage_qualifier": null,
    "negated": false,
    "temporal_scope": "CURRENT"
  }
}
```

**Temporal Rule:** Inclusion is triggered by explicit current status markers ("now", "currently", "at present") in the same sentence.

---

## Future-Dated Unionization

### Example 16: Future Date with Effective Date (INCLUDE)

**Input Sentence (2023 filing):**
```
"Effective January 2024, 25% of our workforce will be unionized under a new collective bargaining agreement."
```

**Expected JSON Output:**
```json
{
  "sentence": "Effective January 2024, 25% of our workforce will be unionized under a new collective bargaining agreement.",
  "keyword_matched": "unionized",
  "geographic_context": {
    "region": "UNKNOWN",
    "countries": [],
    "specificity": "implicit"
  },
  "coverage_data": {
    "percentage": 25,
    "type": "EXPLICIT_PERCENT",
    "percentage_qualifier": null,
    "negated": false,
    "temporal_scope": "FUTURE",
    "effective_date": "2024-01",
    "note": "Future unionization effective date specified"
  }
}
```

**Future Rule:** Announced unionization with future effective dates is included with `temporal_scope: "FUTURE"` and the effective date recorded.

---

### Example 17: Future Date Expected/Anticipated (INCLUDE)

**Input Sentence (2006 filing):**
```
"After decertifying our union in 2005, we expect to re-negotiate unionization in 2007, with an estimated 30% of workforce covered."
```

**Expected JSON Output:**
```json
{
  "sentence": "After decertifying our union in 2005, we expect to re-negotiate unionization in 2007, with an estimated 30% of workforce covered.",
  "keyword_matched": "unionization",
  "geographic_context": {
    "region": "UNKNOWN",
    "countries": [],
    "specificity": "implicit"
  },
  "coverage_data": {
    "percentage": 30,
    "type": "EXPLICIT_PERCENT",
    "percentage_qualifier": null,
    "negated": false,
    "temporal_scope": "FUTURE",
    "expected_date": "2007",
    "note": "Expected future unionization with estimated coverage"
  }
}
```

**Uncertainty Rule:** Use `temporal_scope: "FUTURE"` for anticipated/forecasted future unionization.

---

# PART 2: ITEM 1A DETAILS JSON ARRAY

## Basic Risk Examples

### Example 18: General Labor Risk (Not Union-Specific)

**Input Sentence:**
```
"We face risks from increasing labor costs and wage pressures."
```

**Expected JSON Output:**
```json
{
  "type": "LABOR_RISK",
  "sentence": "We face risks from increasing labor costs and wage pressures.",
  "labor_keywords": ["labor costs", "wage pressures"],
  "risk_keywords": ["face risks", "increasing"],
  "specific_to_unions": false,
  "union_mention": null,
  "temporal_scope": "CURRENT",
  "note": "General labor market risk, not union-specific"
}
```

**Labor Risk Definition:** Any risk related to labor, employees, workforce, wages, benefits, etc. combined with risk language ("risks", "could", "may", "adverse", "could result in").

---

### Example 19: Union-Specific Risk

**Input Sentence:**
```
"Union organizing efforts in key markets could increase our labor expenses and disrupt operations."
```

**Expected JSON Output:**
```json
{
  "type": "UNION_RISK",
  "sentence": "Union organizing efforts in key markets could increase our labor expenses and disrupt operations.",
  "labor_keywords": ["labor expenses"],
  "risk_keywords": ["could", "disrupt"],
  "specific_to_unions": true,
  "union_mention": "union organizing efforts",
  "temporal_scope": "CURRENT",
  "note": "Specific union risk mentioned"
}
```

**Union Risk Definition:** Explicit mention of "union", "collective bargaining", "unionization", "union organizing", etc. combined with risk language in the same sentence or nearby context.

---

### Example 20: Collective Bargaining Risk

**Input Sentence:**
```
"Ongoing collective bargaining negotiations may result in higher wages and benefits, which could adversely affect profitability."
```

**Expected JSON Output:**
```json
{
  "type": "UNION_RISK",
  "sentence": "Ongoing collective bargaining negotiations may result in higher wages and benefits, which could adversely affect profitability.",
  "labor_keywords": ["collective bargaining", "wages", "benefits"],
  "risk_keywords": ["may result in", "could adversely affect"],
  "specific_to_unions": true,
  "union_mention": "collective bargaining negotiations",
  "temporal_scope": "CURRENT",
  "note": "Collective bargaining explicitly tied to business risk"
}
```

---

## Item 1A Edge Cases

### Example 21: Negated Risk (EXCLUDE)

**Input Sentence:**
```
"We do not face significant risks from union organizing in our current operations."
```

**Expected JSON Output:**
```json
null
```

**Negated Risk Rule:** Risk statements that are explicitly negated ("do not face", "no risks") should not trigger `labor_risk_dummy` or `union_risk_dummy`. Exclude entirely.

---

### Example 22: Conditional/Speculative Risk

**Input Sentence:**
```
"If labor market conditions tighten and unionization activities increase, we could face significant cost pressures."
```

**Expected JSON Output:**
```json
{
  "type": "LABOR_RISK",
  "sentence": "If labor market conditions tighten and unionization activities increase, we could face significant cost pressures.",
  "labor_keywords": ["labor market conditions", "unionization activities", "cost pressures"],
  "risk_keywords": ["could"],
  "specific_to_unions": true,
  "union_mention": "unionization activities",
  "temporal_scope": "CONDITIONAL",
  "conditional": true,
  "note": "Speculative/forward-looking risk tied to union activity"
}
```

**Conditional Rule:** Speculative "if...then" or "could...if" risk statements are included with `conditional: true` and `temporal_scope: "CONDITIONAL"`.

---

# COMPLETE JSON STRUCTURE REFERENCE

## Item 1 Details Array - Full Structure

```json
{
  "sentence": "string - the exact sentence from the filing",
  "keyword_matched": "string or null - the union keyword that triggered inclusion",
  "geographic_context": {
    "region": "US and Canada | Latin America | Europe | Middle East & Africa | Asia Pacific | International | UNKNOWN",
    "countries": [
      {
        "name": "string - full country name (e.g., 'United States', 'Germany')",
        "code": "string - ISO 3166-1 alpha-2 code (US, DE, FR, GB, JP, etc.) or custom code"
      }
    ],
    "specificity": "explicit | inherited_from_previous | inferred_from_union_name | inferred_from_language | explicit_and_inferred | implicit",
    "inherited_from_sentence_index": "number (only if specificity is inherited_from_previous)",
    "union_name_indicator": "string (the union name that inferred the region, if applicable)",
    "explicit_countries": ["array (only if specificity is explicit_and_inferred)"],
    "inferred_countries": ["array (only if specificity is inferred_from_union_name or explicit_and_inferred)"],
    "union_names_mentioned": ["array (if union names mentioned in sentence)"],
    "unusual_union_region_combo": "boolean (true if union name doesn't match expected region)",
    "note": "string (optional explanation)"
  },
  "coverage_data": {
    "percentage": "number (0-100) or null",
    "percentage_raw_stated": "number (if negated, original stated value)",
    "calculated_percentage": "number (if from employee counts, the calculated %)",
    "type": "EXPLICIT_PERCENT | CALCULATED_FROM_COUNTS | QUALITATIVE",
    "percentage_qualifier": "SIGNIFICANT | MAJORITY | PORTION | SUBSTANTIAL | SUBSTANTIALLY_ALL | UNSPECIFIED | NONE | null",
    "employee_count_covered": "number or null",
    "employee_count_not_covered": "number or null",
    "employee_count_total": "number or null",
    "negated": "boolean",
    "negation_type": "NOT_COVERED | ZERO_COVERAGE | QUALITATIVE_ZERO | null",
    "temporal_scope": "CURRENT | FUTURE | FUTURE_EXPECTED | CONDITIONAL",
    "effective_date": "YYYY-MM or YYYY format (only for FUTURE)",
    "expected_date": "YYYY format (only for FUTURE_EXPECTED)",
    "ambiguity": "SCOPE_UNCLEAR | null",
    "note": "string (optional explanation)"
  }
}
```

---

## Item 1A Details Array - Full Structure

```json
{
  "type": "LABOR_RISK | UNION_RISK",
  "sentence": "string - the exact sentence from the filing",
  "labor_keywords": ["array of labor-related keywords matched"],
  "risk_keywords": ["array of risk-related keywords matched"],
  "specific_to_unions": "boolean - true if union/collective bargaining mentioned",
  "union_mention": "string or null - the specific union keyword matched",
  "temporal_scope": "CURRENT | CONDITIONAL",
  "conditional": "boolean (true if speculative/if-then)",
  "note": "string (optional explanation)"
}
```

---

# COUNTRY CODES REFERENCE

## Standard ISO 3166-1 Alpha-2 Codes

**North America:**
- US = United States
- CA = Canada
- MX = Mexico

**Europe:**
- GB = United Kingdom
- DE = Germany
- FR = France
- IT = Italy
- ES = Spain
- SE = Sweden
- NO = Norway
- DK = Denmark
- CH = Switzerland
- NL = Netherlands
- BE = Belgium
- AT = Austria
- PL = Poland
- IE = Ireland
- PT = Portugal
- GR = Greece
- CZ = Czech Republic
- HU = Hungary
- RO = Romania
- BG = Bulgaria

**Asia Pacific:**
- JP = Japan
- CN = China
- IN = India
- AU = Australia
- NZ = New Zealand
- SG = Singapore
- KR = South Korea
- TW = Taiwan
- TH = Thailand
- MY = Malaysia
- ID = Indonesia
- PH = Philippines
- VN = Vietnam

**Latin America:**
- BR = Brazil
- AR = Argentina
- CL = Chile
- CO = Colombia
- PE = Peru
- VE = Venezuela
- MX = Mexico

**Middle East & Africa:**
- SA = Saudi Arabia
- AE = United Arab Emirates
- ZA = South Africa
- EG = Egypt
- IL = Israel
- NG = Nigeria
- KE = Kenya

## Custom Codes

For regions or entities not covered by ISO 3166-1, use custom codes:
- INT = International operations (no specific country)
- EU = European Union (multi-country EU operations)
- [CUSTOM] = Any other custom regional code you define
- INT_ES = International Spanish (Latin America/Spain ambiguous)
- INT_PT = International Portuguese (Brazil/Portugal ambiguous)
- INT_FR = International French (France/Canada/Belgium ambiguous)

---

# TEMPORAL INDICATORS REFERENCE

## Temporal Markers to Detect

**Past Tense (Exclude unless current status also stated):**
- "was", "were"
- "had"
- "decertified"
- "dissolved"
- "[past year]"
- "through [past year]"

**Current Tense (Include):**
- "is", "are"
- "have"
- "currently"
- "today"
- "at present"
- "as of [current year]"
- No temporal qualifier (default to current)

**Future Tense (Include):**
- "will be"
- "expect to"
- "planned"
- "anticipated"
- "[future year]"
- "Effective [future date]"

**Vague Past (Exclude unless current status stated):**
- "previously"
- "historically"
- "in the past"
- "several years ago"
- "once"

---

# SUMMARIZED EXTRACTION RULES

## For Inclusion/Exclusion:

1. **Union mention required** → Sentence must contain a union/collective bargaining keyword
2. **Current status priority** → Include if current unionization status is stated
3. **Pure history excluded** → Exclude statements about past unionization with no current info
4. **Same sentence rule** → Temporal context must be in the same sentence as the coverage data
5. **Inheritance allowed** → Geographic context can carry forward from previous sentences within a logical paragraph

## For Coverage Data:

1. **Explicit percentage first** → "X% are covered"
2. **Count-based calculation** → "X of Y employees" → calculate percentage
3. **Qualitative fallback** → "significant", "majority", "portion" if no explicit %
4. **Negation handling** → "NOT X%" → flip to opposite percentage
5. **Employee counts** → Store both raw counts and calculated/stated percentages

## For Geographic Context:

1. **Explicit mention** → Country or region specifically named
2. **Inheritance** → Carry forward from most recent previous mention
3. **UNKNOWN fallback** → If no geographic context available
4. **Ambiguity flag** → Mark when scope is genuinely unclear

## For Risk Classification (Item 1A):

1. **Labor risk** → Labor keyword + risk keyword in same context
2. **Union risk** → Union keyword + risk keyword in same context
3. **Negation excluded** → "do NOT face risks" → exclude entirely
4. **Conditional included** → "if...could..." statements included with flag

---

# QUICK DECISION GUIDE

| Scenario | Include? | Notes |
|----------|----------|-------|
| "15% unionized" (no date) | YES | Assume current |
| "Decertified in 2005" (in 2008 filing) | NO | Pure history |
| "Decertified 2005, now 10% unionized" | YES | Current status stated |
| "Expected to unionize in 2024" (2023 filing) | YES | Future announced |
| "60% NOT covered" | YES | Flip to 40% covered |
| "Significant portion unionized" | YES | Qualitative, no % |
| "30% represented by UAW" | YES | Infer USA from union name |
| "Workers in IG Metall" | YES | Infer Germany from union name |
| "Unite the Union members" | YES | Infer UK from union name |
| "UAW in our Tokyo plant" | YES | Flag unusual combo (USA union + Japan) |
| "Represented by UAW, IG Metall, Unite" | YES | Multiple unions = multiple regions |
| "Risks from labor costs" | ITEM 1A only | General labor risk |
| "Union organizing threatens operations" | ITEM 1A only | Union-specific risk |
| "We don't face union risks" | NO (1A) | Negated risk |
| "Refer to Item 1A for details" | NO | Reference/cross-reference |
| "Suppliers are unionized" | NO | Third-party, not company |

---

# FINAL CHECKLIST BEFORE CODING

- ✅ JSON structure matches specification above
- ✅ Temporal handling: past/current/future properly categorized
- ✅ Negation: percentages flipped with audit trail
- ✅ Inheritance: geographic context carries forward with source tracking
- ✅ Ambiguity: SCOPE_UNCLEAR flag for manual review
- ✅ Exclusions: References, pure history, negated risks excluded
- ✅ Filing year parameter: Passed to extraction function for temporal detection
- ✅ No code/regex: Only rules and examples provided

**Ready to implement extraction functions.**