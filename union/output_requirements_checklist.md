# Output Requirements Checklist (Country Array + Provenance)

Goal: keep `calculate_metrics` as-is for debugging/consistency checks, and emit a separate output focused on country-level results. The implementation of this provenance JSON will have simplified keys, while this document will have the full key names.

## 1) Top-Level JSON

```jsonc
{
  "schema_version": "3.0", // output schema version
  "domestic_country_code": "US", // home country used for domestic/international split
  "countries": [], // one object per country
  "agg": [], // top-level aggregate provenance (parent-level, non-duplicated)
  "summary": { // Quick summary to see exactly which countries are considered covered or not covered. We only mention explicitlh of what is provided in the text, so if a country is not mentioned at all, it should not be in either list (e.g., AU in the example below)
    "covered": {
      "NA": ["US", "CA"],
      "EUR": ["DE", "FR", "IT", "CIS"], // CIS is a pseudo-country code representing covered countries in the Commonwealth of Independent States, if no specific country such as Russia is mentioned in text
      "APAC": ["APAC"], // If APAC is a pseudo-country with no children
      "MEA": [], // if no covered countries in MEA region
      "LATAM": ["MX"] // Mexico is part of LATAM region and not part of NA region
    }, 
    "not_covered": {
      "NA": [],
      "EUR": ["GB"], // GB was not explicitly covered in text
      "APAC": [],
      "MEA": ["GCC"], // GCC is a pseudo-country code representing non-covered countries in the Gulf Cooperation Council, if no specific country such as Saudi Arabia is mentioned in text
      "LATAM": ["BR"]
    },
    "domestic_is_covered": true, // boolean indicating whether domestic country is covered
    "international_is_covered": true // boolean indicating whether any international employees are covered
  },
  "notes": [] // optional run-level notes/warnings
}
```

## 2) Countries Array (One object per country)

```jsonc
{
  "country_code": "DE",
  "is_domestic": false, // true only for domestic_country_code
  "union_indicator": 1, // 1 if any union coverage signal exists for this country, else null
  "country_totals": {
    "employee_count_total": 3100.0, // final resolved total for this country (all methods combined)
    "employee_count_covered": 1224.0, // final resolved covered count (all methods combined)
    "employee_count_not_covered": 1876.0, // final resolved non-covered count
    "coverage_percent": 39.48, // final country % (prefer covered/total when available)
    
  },

  "method_breakdown": {
    "EXPLICIT": {
      "employee_count_total": 3100.0, // counts explicitly stated in text
      "employee_count_covered": 1224.0, // covered count explicitly stated in text
      "employee_count_not_covered": null, // non-covered explicitly stated in text (null if not explicitly present)
      "coverage_percent_values": [68.0], // percentages explicitly stated in text
      "entry_count": 1 // number of contributing entries in this source type
    },
    "CALCULATED": {
      "employee_count_total": null, // totals computed from arithmetic over text-grounded values
      "employee_count_covered": null, // covered counts computed from text-grounded values
      "employee_count_not_covered": 1876.0, // e.g., total - covered
      "coverage_percent_values": [39.48], // percentages computed from counts
      "entry_count": 2
    },
    "INFERRED": {
      "employee_count_total": null, // inferred from qualitative/implicit logic (not fallback denominator)
      "employee_count_covered": null,
      "employee_count_not_covered": null,
      "coverage_percent_values": [], // inferred/dummy qualitative percentages
      "entry_count": 0
    },
    "WEIGHTED_DIVISION": {
      "employee_count_total": null, // weighted allocations derived from explicit/calculated upstream totals
      "employee_count_covered": null, // covered counts produced by weighted split logic
      "employee_count_not_covered": null,
      "coverage_percent_values": [], // percentages produced by weighted split logic
      "entry_count": 0
    },
    "VIRTUAL_POOL": {
      "employee_count_total": null, // synthetic virtual-pool denominator allocations
      "employee_count_covered": null,
      "employee_count_not_covered": null,
      "coverage_percent_values": [],
      "entry_count": 0
    },
    "FALLBACK": {
      "employee_count_total": null, // denominator synthesized via fallback
      "employee_count_covered": null, // covered derived from % * fallback denominator
      "employee_count_not_covered": null,
      "coverage_percent_values": [], // only if the percentage itself was fallback-sourced
      "entry_count": 0
    },
    "INHERITED": {
      "employee_count_total": null, // true carry-forward inheritance only (context transfer)
      "employee_count_covered": null,
      "employee_count_not_covered": null,
      "coverage_percent_values": [],
      "entry_count": 0
    }
  },

  "country_keywords": {
    "IG Metall": 1,
    "works council": 1
  }
}
```

## 2b) Top-Level `agg` Array (Parent Aggregate Provenance)

```jsonc
{
  "aggregate_key": "EU", // aggregate parent context code (always code, never region name)
  "aggregate_scope": "AGGREGATE",
  "sentence_index": 0,
  "employee_count_total": 1000.0, // original parent count
  "employee_count_covered": 1000.0,
  "employee_count_not_covered": 0.0,
  "coverage_percent": 100.0,
  "source_type": "WEIGHTED_DIVISION",
  "children": {
    "DE": {
      "employee_count_total": 368.0, // allocated from parent using weighted division basis
      "employee_count_covered": 368.0,
      "employee_count_not_covered": 0.0,
      "allocation_weight_total": 368.0 // basis used for weighting (country total)
    },
    "FR": {
      "employee_count_total": 331.0,
      "employee_count_covered": 331.0,
      "employee_count_not_covered": 0.0,
      "allocation_weight_total": 331.0
    },
    "IT": {
      "employee_count_total": 301.0,
      "employee_count_covered": 301.0,
      "employee_count_not_covered": 0.0,
      "allocation_weight_total": 301.0
    }
  }
}
```

### Mixed Provenance Example (Important)

```jsonc
{
  "country_code": "GB",
  "method_breakdown": {
    "EXPLICIT": {
      "coverage_percent_values": [25.0], // 25% explicitly appears in text
      "employee_count_total": null,
      "employee_count_covered": null,
      "employee_count_not_covered": null,
      "entry_count": 1
    },
    "FALLBACK": {
      "employee_count_total": 120.0, // no UK total in text, so fallback denominator applied
      "employee_count_covered": 30.0, // derived from explicit 25% * fallback denominator
      "employee_count_not_covered": 90.0,
      "coverage_percent_values": [],
      "entry_count": 1
    }
  }
}
```

## 3) Aggregation Rules

1. `countries[]` should include every country code present in resolved entries.
2. `country_totals` uses resolved final values (same arithmetic basis as tracker entries).
3. `method_breakdown` groups contributions by `*_source_type` (`EXPLICIT`, `CALCULATED`, `INFERRED`, `WEIGHTED_DIVISION`, `VIRTUAL_POOL`, `FALLBACK`, `INHERITED`).
4. `coverage_percent_values` stores raw percent contributions by method; final `country_totals.coverage_percent` is computed from final covered/total where available.
5. If percentage exists but counts are missing, keep percentage in its method bucket and keep missing count fields as `null`.
6. `country_keywords` should come directly from tracker keyword tallies for that country code.
7. Mixed provenance is valid: percent can be `EXPLICIT` while counts for that same record are `FALLBACK`.
8. Default for missing numeric fields is `null` (never `0` unless the value is explicitly/derived as zero).

## 4) Inheritance Clarification

To distinguish true inheritance vs computed use of inherited context:

- True carry-forward/context inheritance -> `source_type = INHERITED`
- Inherited denominator used to compute values -> `source_type = CALCULATED`

This must follow the `DETAIL_TO_SOURCE_TYPE` mapping in `output_enums.py`.
