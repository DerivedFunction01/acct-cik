# Union Coverage Brief

Return JSON only. No prose. Emit only signal-bearing keys.

## Shape

```jsonc
{
  "summary": { "cov": [], "not_cov": [] },
  "domestic_country_code": "US",
  "global": { "pcts": [] },
  "dom_region": { "label": "NA", "children": [] },
  "international": { "scope": "xdr", "children": [] },
  "shared": [],
  "conflicts": []
}
```

## Keys

- `summary.cov`: covered country / region codes
- `summary.not_cov`: explicit no-coverage country / region codes
- `domestic_country_code`: domestic country code
- `global`: global rollup
- `dom_region`: domestic-region node
- `international`: international root
- `shared`: only for shared counts that include the domestic country
- `conflicts`: notes / conflicts, omit if empty

## Node Keys

- `scope`: `region`, `pseudo_region`, or `country`
- `label`: region or pseudo-region label
- `country_codes`: country codes for country nodes
- `mapped_to`: parent region for pseudo-regions
- `covered`: `1` when coverage is stated but count/pct is absent
- `domestic`: `1` only on the domestic country node
- `inferred`: `1` only when domestic is inferred from context
- `calculated`: `1` only when derived by arithmetic from text values
- `count`: covered count
- `pcts`: percentage array
- `relation`: `add` or `non`
- `concepts`: optional concept tags, e.g. `union`, `cb`
- `children`: nested nodes

## Rules

1. Emit only supported nodes. Drop geographic mentions with no coverage signal.
2. `0` only means explicit no coverage. Silence is not zero.
3. `shared` is only for counts that include `domestic_country_code`.
4. Shared counts that do not include domestic stay in `international`.
5. One count may be shared by multiple non-domestic codes. Keep them together in one node when the text supports that.
6. `dom_region` is the domestic region bucket. `international` is the international root.
7. Never sum a parent and its children together.
8. Keep repeated facts once.
9. `pcts` may hold multiple values. If they are not summable, set `relation:"non"`; if they are additive parts of one metric, collapse to one pct.
10. If pct values are for different concepts, keep both and add `concepts` if useful.
11. For union text, US/CA may cluster; Mexico is explicit-only.
12. North America is a region node, not automatic US.
13. Pseudo-regions nest under their mapped region; drop unsupported child countries.
14. If a country or region is covered but no number or pct is stated, emit the node with `covered:1` and no metrics.
15. Omit `count` when absent. Omit `pcts` when empty. Keep `count:0` only for explicit no coverage.

## Scope

- `international.scope = "xdr"` when international excludes the domestic region
- `international.scope = "xd"` when international excludes only the domestic country
- `international.scope = "unk"` when the split is unclear

## Input Hints

Pass cleaned text plus a small lookup bundle if available:

```jsonc
{
  "domestic_country_code": "US",
  "text": "cleaned SEC paragraph",
  "lookups": {
    "countries": { "Germany": "DE", "France": "FR", "United States": "US" },
    "regions": { "Europe": ["DE", "FR"], "Asia/Pacific": ["JP", "CN"] },
    "union_names": { "IG Metall": "DE", "UAW": "US" },
    "phrases": { "domestic": "US", "international": "INT", "global": "GLO" }
  }
}
```

## Examples

### 1) Parent only, unsupported children dropped

```jsonc
{"summary":{"cov":["EU"],"not_cov":[]},"domestic_country_code":"US","international":{"scope":"xdr","children":[{"scope":"region","label":"EU","covered":1,"pcts":[45]}]}}
```

### 2) One count shared by multiple non-domestic codes

```jsonc
{"summary":{"cov":["DE","FR"],"not_cov":[]},"domestic_country_code":"US","international":{"scope":"xdr","children":[{"scope":"country","country_codes":["DE","FR"],"count":1000,"pcts":[68],"relation":"non"}]}}
```

### 3) Shared count that includes domestic

```jsonc
{"summary":{"cov":["NA"],"not_cov":[]},"domestic_country_code":"US","shared":[{"label":"NA","count":1000,"spans":["dom_region","international"]}]}
```

### 4) Non-additive percentages on one node

```jsonc
{"summary":{"cov":["DE"],"not_cov":[]},"domestic_country_code":"US","international":{"scope":"xdr","children":[{"scope":"country","country_codes":["DE"],"pcts":[68,40],"relation":"non","concepts":["union","cb"]}]}}
```

Keep both pcts and do not sum them when `relation:"non"`.

### 5) No coverage

```jsonc
{"summary":{"cov":[],"not_cov":["US"]},"domestic_country_code":"US","dom_region":{"label":"NA","children":[{"scope":"country","country_codes":["US"],"domestic":1,"count":0,"pcts":[0],"covered":1}]}}
```

Zero pct means explicit no coverage. Do not treat it as missing data.

### 6) Covered, but no numbers or pcts

```jsonc
{"summary":{"cov":["EU"],"not_cov":[]},"domestic_country_code":"US","international":{"scope":"xdr","children":[{"scope":"region","label":"EU","covered":1}]}}
```

## Final reminder

- Do not double count
- Do not guess unsupported children
- Do not split shared domestic aggregates
- Do not split permitted shared non-domestic counts
- Do not sum non-additive percentages
- Keep the tree only as deep as the text supports
