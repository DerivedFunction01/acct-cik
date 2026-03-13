# Output Requirements Checklist (Country Array + Provenance)

Goal: keep `calculate_metrics` as-is for debugging/consistency checks, and emit a separate output focused on country-level results. The implementation of this provenance JSON will have simplified keys, while this document will have the full key names. Outputs omit empty keys to keep payloads compact.

## 1) Top-Level JSON

```jsonc
{
  "domestic_country_code": "US", // home country used for domestic/international split
  "countries": [], // one object per country
  "agg": [], // top-level aggregate provenance (parent-level, non-duplicated)
  "summary": { // Quick summary to see exactly which countries are considered covered or not covered. We only mention explicitly what is provided in the text, so if a country is not mentioned at all, it should not be in either list (e.g., AU in the example below)
    "cov": {
      "NA": ["US", "CA"],
      "EUR": ["DE", "FR", "IT", "CIS"], // CIS is a pseudo-country code representing covered countries in the Commonwealth of Independent States, if no specific country such as Russia is mentioned in text
      "APAC": ["APAC"], // If APAC is a pseudo-country with no children
      "MEA": [], // if no covered countries in MEA region
      "LATAM": ["MX"] // Mexico is part of LATAM region and not part of NA region
    }, 
    "not_cov": {
      "NA": [],
      "EUR": ["GB"], // GB was not explicitly covered in text
      "APAC": [],
      "MEA": ["GCC"], // GCC is a pseudo-country code representing non-covered countries in the Gulf Cooperation Council, if no specific country such as Saudi Arabia is mentioned in text
      "LATAM": ["BR"]
    },
    "dom_cov": true, // boolean indicating whether domestic country is covered
    "int_cov": true // boolean indicating whether any international employees are covered
  },
  "notes": [] // optional run-level notes/warnings
}
```

## 2) Countries Array (One object per country)

```jsonc
{
  "country_code": "DE",
  "union_indicator": 1, // 1 if any union coverage signal exists for this country, else null
  "country_totals": {
    "tot": 3100.0, // final resolved total for this country (all methods combined)
    "cov": 1224.0, // final resolved covered count (all methods combined)
    "not_cov": 1876.0, // final resolved non-covered count
    "pct": 39.48 // final country % (prefer covered/total when available)
  },
  "reported_totals": { // explicit only
    "tot": 3100.0, // final resolved total for this country (explicit only)
    "cov": 1224.0, // final resolved covered count (explicit methods combined)
    "not_cov": 1876.0, // final resolved non-covered count
    "pct": 39.48 // final country % (prefer covered/total when available)
  },

  "method_breakdown": {
    "EXPLICIT": {
      "tot": 3100.0, // counts explicitly stated in text
      "cov": 1224.0, // covered count explicitly stated in text
      "not_cov": null, // non-covered explicitly stated in text (null if not explicitly present)
      "pct_vals": [68.0], // percentages explicitly stated in text
      "n": 1 // number of contributing entries in this source type
    },
    "CALCULATED": {
      "tot": null, // totals computed from arithmetic over text-grounded values
      "cov": null, // covered counts computed from text-grounded values
      "not_cov": 1876.0, // e.g., total - covered
      "pct_vals": [39.48], // percentages computed from counts
      "n": 2
    },
    "INFERRED": {
      "tot": null, // inferred from qualitative/implicit logic (not fallback denominator)
      "cov": null,
      "not_cov": null,
      "pct_vals": [], // inferred/dummy qualitative percentages
      "n": 0
    },
    "WEIGHTED_DIVISION": {
      "tot": null, // weighted allocations derived from explicit/calculated upstream totals
      "cov": null, // covered counts produced by weighted split logic
      "not_cov": null,
      "pct_vals": [], // percentages produced by weighted split logic
      "n": 0
    },
    "VIRTUAL_POOL": {
      "tot": null, // synthetic virtual-pool denominator allocations
      "cov": null,
      "not_cov": null,
      "pct_vals": [],
      "n": 0
    },
    "FALLBACK": {
      "tot": null, // denominator synthesized via fallback
      "cov": null, // covered derived from % * fallback denominator
      "not_cov": null,
      "pct_vals": [], // only if the percentage itself was fallback-sourced
      "n": 0
    },
    "INHERITED": {
      "tot": null, // true carry-forward inheritance only (context transfer)
      "cov": null,
      "not_cov": null,
      "pct_vals": [],
      "n": 0
    }
  },

  "country_keywords": {
    "IG Metall": 1,
    "works council": 1
  }
}
```

## 2c) Risk Summary (Compact + Conditional)

```jsonc
{
  "n": 3,
  "typ": {
    "UNION_RISK": 2
  },
  "sig": {
    "RISK_EVENT": 1
  },
  "temp": {
    "CURRENT": 3
  },
  "act": {
    "ACTUAL": 1,
    "POTENTIAL": 2
  },
  "rel": {
    "POSITIVE": 1
  },
  "kw_r": {
    "risk": 1
  },
  "kw_l": {
    "union": 2
  },
  "kw_rel": {
    "relationship": 1
  },
  "kw_g": ["union", "risk", "relationship"],
  "cov_t": {
    "cov": 1200.0,
    "not_cov": 800.0,
    "tot": 2000.0,
    "bu": 14.0,
    "pct": 60.0
  }
}
```

Notes:
- Keys are omitted if they are empty/zero to keep payload compact.
- `by_activity_class` and `coverage_totals` appear only when Item 1A risk items include `activity_class` and `coverage_data` with signal.

## 2d) Suppressed Counts (Per-Country)

Suppressed clause numerics are attached to each country as `suppressed_counts`.
These are explicit numbers from legal requirement, legal process, boilerplate, or
contract clause mechanics sentences. They are not used in coverage math and are
intended as a last-resort quantitative signal. Counts are aggregated, and the
suppression type is resolved by priority when multiple types overlap:
`CONTRACT_CLAUSE` > `LEGAL_PROCESS` > `LEGAL_REQUIREMENT` > `BOILERPLATE`.

```jsonc
{
  "country_code": "GB",
  "suppressed_counts": {
    "CONTRACT_CLAUSE": {
      "tot": 0.0, // sum of worker_counts (fallback to numbers)
      "pct_vals": [52.0], // collected percentage values
      "bu": 0.0, // sum of bargaining unit counts
      "n": 1 // number of suppressed items contributing
    }
  }
}
```

## 2b) Top-Level `agg` Array (Parent Aggregate Provenance)

```jsonc
{
  "aggregate_key": "EU", // aggregate parent context code (always code, never region name)
  "aggregate_scope": "AGGREGATE", 
  "tot": 1000.0, // original parent count
  "cov": 1000.0,
  "not_cov": 0.0,
  "pct": 100.0,
  "source_type": "WEIGHTED_DIVISION",
  "children": {
    "DE": {
      "tot": 368.0, // allocated from parent using weighted division basis
      "cov": 368.0,
      "not_cov": 0.0,
      "w_tot": 368.0 // basis used for weighting (country total)
    },
    "FR": {
      "tot": 331.0,
      "cov": 331.0,
      "not_cov": 0.0,
      "w_tot": 331.0
    },
    "IT": {
      "tot": 301.0,
      "cov": 301.0,
      "not_cov": 0.0,
      "w_tot": 301.0
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
      "pct_vals": [25.0], // 25% explicitly appears in text
      "tot": null,
      "cov": null,
      "not_cov": null,
      "n": 1
    },
    "FALLBACK": {
      "tot": 120.0, // no UK total in text, so fallback denominator applied
      "cov": 30.0, // derived from explicit 25% * fallback denominator
      "not_cov": 90.0,
      "pct_vals": [],
      "n": 1
    }
  }
}
```

## 2e) Bargaining Report (Bargaining Unit Counts)

Lean report: summary plus the list of entities (countries/regions).

```jsonc
{
  "tot": 14.0,
  "entities": ["GB", "US"]
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
9. Optional keys are omitted when empty (`language_fallback_country`, `reported_totals`, `country_keywords`, `country_table_keywords`, `method_breakdown`).
10. `risk_summary` omits empty sections and zero-count fields; `coverage_totals` appears only if Item 1A actual risk items include coverage data.

## 4) Inheritance Clarification

To distinguish true inheritance vs computed use of inherited context:

- True carry-forward/context inheritance -> `source_type = INHERITED`
- Inherited denominator used to compute values -> `source_type = CALCULATED`

This must follow the `DETAIL_TO_SOURCE_TYPE` mapping in `output_enums.py`.
