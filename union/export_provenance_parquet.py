import argparse
import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from defs.region_regex import (
    DOMESTIC_SET,
    INT_SET,
    NON_G20_SIGNIFICANT_ECOS,
    REGION_NAME_MAP,
    _CODE_TO_REGION,
    is_contained,
    IGNORED_REGIONS,
    AGG_SET,
    COMPOSITE_REGION_MAP,
    get_composite_constituents,
    G20_CODES,
)

SOURCE_DB_DEFAULT = "union_provenance_risk.db"
TARGET_PARQUET_DEFAULT = "union_provenance_risk.parquet"
SOURCE_TABLE = "provenance_risk"
TEMP_SAMPLE_COLUMNS = [
    "dom_pct_bucket",
    "tot_count_bucket",
    "int_count_bucket",
    "kw_bucket",
    "dom_code_bucket",
    "lang_fallback_bucket",
    "year_mismatch_bucket",
]


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


def _safe_json_loads(raw: Optional[str]) -> Dict[str, Any]:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def _safe_json_dumps(obj: Any) -> Optional[str]:
    if obj is None:
        return None
    try:
        return json.dumps(obj)
    except TypeError:
        return None


def _entry_field(entry: Dict[str, Any], field: str) -> Optional[float]:
    bucket = entry.get("reported_totals") or {}
    val = bucket.get(field)
    if val is not None:
        try:
            return float(val)
        except (TypeError, ValueError):
            return None
    return None


def _normalize_count_pct_pair(
    count: Optional[float], pct: Optional[float]
) -> Tuple[Optional[float], Optional[float]]:
    """
    Keep zero-style count/pct pairs consistent without forcing fake positive data.
    """
    if count is None and pct == 0:
        count = 0.0
    if count == 0 and pct is None:
        pct = 0.0
    if count is not None and count > 0 and pct == 0:
        pct = None
    if count == 0 and pct is not None and pct > 0:
        count = None
    return count, pct


def _resolve_total_count(
    dom_count: Optional[float],
    int_count: Optional[float],
    global_covered_count: Optional[float],
    fallback_total: Optional[float] = None,
) -> Optional[float]:
    """
    Select the export total count using the simplified rule:
    prefer dom + int, then let a larger global covered count override it.
    """
    total = None
    if dom_count is not None and int_count is not None:
        total = float(dom_count) + float(int_count)
    elif fallback_total is not None:
        total = float(fallback_total)

    if global_covered_count is not None:
        global_covered_count = float(global_covered_count)
        if total is None:
            total = global_covered_count
        else:
            total = max(total, global_covered_count)

    return total


def _report_pcts(report: Dict[str, Any]) -> List[Tuple[str, float]]:
    out: List[Tuple[str, float]] = []
    for entry in report.get("countries") or []:
        code = entry.get("country_code")
        pct = _entry_field(entry, "pct")
        if code and pct is not None:
            out.append((code, pct))

    global_entry = report.get("global") or {}
    global_pct = global_entry.get("pct")
    if global_pct is not None:
        try:
            out.append((str(global_entry.get("country_code") or "GLO"), float(global_pct)))
        except (TypeError, ValueError):
            pass
    return out


def _single_report_pct(report: Dict[str, Any]) -> Optional[float]:
    pcts = []
    seen = set()
    for _, pct in _report_pcts(report):
        key = round(float(pct), 6)
        if key in seen:
            continue
        seen.add(key)
        pcts.append(float(pct))
    if len(pcts) == 1:
        return pcts[0]
    return None


def _int_reported_pct(report: Dict[str, Any]) -> Optional[float]:
    dom_code = report.get("domestic_country_code")
    international_entry = report.get("international") or {}
    international_pct = _entry_field(international_entry, "pct")
    if international_pct is not None:
        return float(international_pct)

    global_source_code = (report.get("global") or {}).get("global_source_code")

    for entry in report.get("countries") or []:
        code = entry.get("country_code")
        pct = _entry_field(entry, "pct")
        if pct is None:
            continue
        if code in INT_SET:
            return float(pct)

    if global_source_code in INT_SET:
        global_pct = (report.get("global") or {}).get("pct")
        if global_pct is not None:
            return float(global_pct)

    # If only one percent exists in the report, treat it as the international pct.
    single_pct = _single_report_pct(report)
    if single_pct is not None:
        return single_pct

    # Last-resort fallback: if there is a non-domestic pct and no domestic pct,
    # surface the first non-domestic one.
    for code, pct in _report_pcts(report):
        if code != dom_code:
            return float(pct)
    return None


def _tot_reported_pct(
    report: Dict[str, Any],
    total_count: Optional[float],
    total_covered: Optional[float],
) -> Optional[float]:
    international_entry = report.get("international") or {}
    international_pct = _entry_field(international_entry, "pct")
    if international_pct is not None:
        return float(international_pct)

    global_entry = report.get("global") or {}
    global_pct = global_entry.get("pct")
    if global_pct is not None:
        try:
            return float(global_pct)
        except (TypeError, ValueError):
            pass

    global_cov = global_entry.get("cov")
    global_tot = global_entry.get("tot")
    if global_cov is not None and global_tot not in (None, 0):
        try:
            return round((float(global_cov) / float(global_tot)) * 100.0, 2)
        except (TypeError, ValueError, ZeroDivisionError):
            pass

    dom_code = report.get("domestic_country_code")
    countries = report.get("countries") or []
    dom_pct = None
    has_int_signal = False
    for entry in countries:
        code = entry.get("country_code")
        pct = _entry_field(entry, "pct")
        if code == dom_code and pct is not None and dom_pct is None:
            dom_pct = float(pct)
        elif code in INT_SET and pct is not None:
            has_int_signal = True

    if not has_int_signal and dom_pct is not None:
        return dom_pct

    single_pct = _single_report_pct(report)
    if single_pct is not None:
        return single_pct
    return None


def _domestic_explicit(report: Dict[str, Any]) -> Tuple[Optional[float], Optional[float]]:
    dom_code = report.get("domestic_country_code")
    if not dom_code:
        return None, None

    for entry in report.get("countries") or []:
        if entry.get("country_code") == dom_code:
            reported = entry.get("reported_totals") or {}
            cov = reported.get("cov")
            pct = reported.get("pct")
            return cov, pct
    return None, None

def _domestic_parent_pct(report: Dict[str, Any]) -> Optional[float]:
    dom_code = report.get("domestic_country_code")
    if not dom_code:
        return None

    # 1) Prefer aggregate parents that explicitly list the domestic code.
    for agg in report.get("agg") or []:
        pct = agg.get("pct")
        if pct is None:
            continue
        children = agg.get("children") or {}
        if dom_code in children:
            return float(pct)

    def _parent_pct_for_codes(codes: List[str]) -> Optional[float]:
        for entry in report.get("countries") or []:
            c_code = entry.get("country_code")
            if not c_code or c_code == dom_code:
                continue
            if c_code not in codes:
                continue
            if c_code in IGNORED_REGIONS:
                continue
            if not is_contained(
                container_key=c_code,
                item_key=dom_code,
                domestic_country_code=dom_code,
            ):
                continue
            reported = entry.get("reported_totals") or {}
            pct = reported.get("pct")
            if pct is not None:
                return float(pct)
        return None

    # 2) Composite containers (e.g., CIS, EMEA composites)
    composite_codes = list(COMPOSITE_REGION_MAP.keys())
    pct = _parent_pct_for_codes(composite_codes)
    if pct is not None:
        return pct

    # 3) Region containers (e.g., EUR)
    region_codes = list(REGION_NAME_MAP.values())
    pct = _parent_pct_for_codes(region_codes)
    if pct is not None:
        return pct

    return None


def _domestic_parent_cov_remainder(report: Dict[str, Any]) -> Optional[float]:
    dom_code = report.get("domestic_country_code")
    if not dom_code:
        return None
    dom_is_g20 = dom_code in G20_CODES
    dom_has_exception = dom_code in NON_G20_SIGNIFICANT_ECOS

    countries = report.get("countries") or []
    countries_by_code = {
        c.get("country_code"): c for c in countries if c.get("country_code")
    }

    def _entry_cov(code: str) -> Optional[float]:
        entry = countries_by_code.get(code) or {}
        reported = entry.get("reported_totals") or {}
        cov = reported.get("cov")
        return float(cov) if cov is not None else None

    def _sibling_cov_sum(
        parent_code: str, child_codes: List[str]
    ) -> float:
        total = 0.0
        for code in child_codes:
            if not code or code == parent_code:
                continue
            # Skip any child container that contains the domestic country.
            if is_contained(
                container_key=code,
                item_key=dom_code,
                domestic_country_code=dom_code,
            ):
                continue
            cov = _entry_cov(code)
            if cov is not None:
                total += float(cov)
        return total

    def _has_missing_g20_sibling(
        parent_code: str, child_codes: Optional[List[str]] = None
    ) -> bool:
        if dom_is_g20 or dom_has_exception:
            return False

        # Aggregate: explicit child list
        if child_codes is not None:
            for code in child_codes:
                if not code or code == dom_code:
                    continue
                if code in G20_CODES and _entry_cov(code) is None:
                    return True
            return False

        # Composite parent
        if parent_code in COMPOSITE_REGION_MAP:
            constituents = get_composite_constituents(parent_code) or []
            for code in constituents:
                if code == dom_code:
                    continue
                if code in G20_CODES and _entry_cov(code) is None:
                    return True
            return False

        # Region parent
        if parent_code in REGION_NAME_MAP.values():
            region_name = _CODE_TO_REGION.get(parent_code)
            if not region_name:
                return False
            for code in G20_CODES:
                if code == dom_code:
                    continue
                if _CODE_TO_REGION.get(code) == region_name and _entry_cov(code) is None:
                    return True
            return False

        return False

    # 1) Aggregate parents: explicit child list.
    for agg in report.get("agg") or []:
        parent_code = agg.get("aggregate_key")
        if not parent_code:
            continue
        parent_cov = agg.get("cov")
        if parent_cov is None:
            continue
        children = agg.get("children") or {}
        child_codes = list(children.keys())
        # Ensure domestic is within this aggregate scope.
        if not any(
            is_contained(
                container_key=parent_code,
                item_key=dom_code,
                domestic_country_code=dom_code,
            )
            or c == dom_code
            for c in child_codes
        ):
            continue
        if _has_missing_g20_sibling(parent_code, child_codes):
            continue
        sibling_sum = _sibling_cov_sum(parent_code, child_codes)
        remainder = float(parent_cov) - sibling_sum
        if remainder >= 0:
            return remainder

    # 2) Composite containers.
    for parent_code in COMPOSITE_REGION_MAP.keys():
        if parent_code not in countries_by_code:
            continue
        if not is_contained(
            container_key=parent_code,
            item_key=dom_code,
            domestic_country_code=dom_code,
        ):
            continue
        parent_cov = _entry_cov(parent_code)
        if parent_cov is None:
            continue
        if _has_missing_g20_sibling(parent_code):
            continue
        child_codes = [
            code
            for code in countries_by_code.keys()
            if code != parent_code
            and is_contained(
                container_key=parent_code,
                item_key=code,
                domestic_country_code=dom_code,
            )
        ]
        sibling_sum = _sibling_cov_sum(parent_code, child_codes)
        remainder = float(parent_cov) - sibling_sum
        if remainder >= 0:
            return remainder

    # 3) Region containers.
    for parent_code in REGION_NAME_MAP.values():
        if parent_code not in countries_by_code:
            continue
        if not is_contained(
            container_key=parent_code,
            item_key=dom_code,
            domestic_country_code=dom_code,
        ):
            continue
        parent_cov = _entry_cov(parent_code)
        if parent_cov is None:
            continue
        if _has_missing_g20_sibling(parent_code):
            continue
        child_codes = [
            code
            for code in countries_by_code.keys()
            if code != parent_code
            and is_contained(
                container_key=parent_code,
                item_key=code,
                domestic_country_code=dom_code,
            )
        ]
        sibling_sum = _sibling_cov_sum(parent_code, child_codes)
        remainder = float(parent_cov) - sibling_sum
        if remainder >= 0:
            return remainder

    return None

def test_domestic_parent_remainder(
    dom_code: str, cov_by_code: Dict[str, float]
) -> Optional[float]:
    """
    Adapter test helper: supply a domestic code and a dict of coverage counts
    by code, and return the inferred domestic remainder (if any).
    """
    countries = []
    for code, cov in cov_by_code.items():
        countries.append(
            {
                "country_code": code,
                "reported_totals": {"cov": float(cov)},
            }
        )

    report = {
        "domestic_country_code": dom_code,
        "countries": countries,
        "agg": [],
    }
    return _domestic_parent_cov_remainder(report)

def _int_reported_totals(report: Dict[str, Any]) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    dom_code = report.get("domestic_country_code")
    countries = report.get("countries") or []
    
    total_cov = 0.0
    total_tot = 0.0
    total_not_cov = 0.0
    has_cov = False
    has_tot = False
    has_not_cov = False
    
    for entry in countries:
        if entry.get("country_code") == dom_code:
            continue
        # Skip sub-allocations to avoid double-counting
        if entry.get("is_sub_allocation"):
            continue
        reported = entry.get("reported_totals") or {}
        cov = reported.get("cov")
        tot = reported.get("tot")
        not_cov = reported.get("not_cov")
        
        if cov is not None:
            total_cov += float(cov)
            has_cov = True
        if tot is not None:
            total_tot += float(tot)
            has_tot = True
        if not_cov is not None:
            total_not_cov += float(not_cov)
            has_not_cov = True
            
    int_cov = total_cov if has_cov else None
    int_tot = total_tot if has_tot else None
    int_not_cov = total_not_cov if has_not_cov else None
    
    return int_cov, int_tot, int_not_cov

def _agg_is_purely_international(
    agg_entry: Dict[str, Any], domestic_country_code: Optional[str]
) -> bool:
    if not domestic_country_code:
        return False

    children = agg_entry.get("children") or {}
    child_codes = list(children.keys())

    if not child_codes:
        agg_key = agg_entry.get("aggregate_key")
        return bool(agg_key in INT_SET)

    dom_region_name = _CODE_TO_REGION.get(domestic_country_code)
    dom_region_code = REGION_NAME_MAP.get(dom_region_name) if dom_region_name else None

    for code in child_codes:
        if code == domestic_country_code:
            return False
        if dom_region_code and code == dom_region_code:
            return False
        if dom_region_name and code == dom_region_name:
            return False
        if code in DOMESTIC_SET:
            return False
    return True


def _agg_international_totals(
    report: Dict[str, Any],
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    dom_code = report.get("domestic_country_code")
    agg_entries = report.get("agg") or []

    total_cov = 0.0
    total_tot = 0.0
    total_not_cov = 0.0
    has_cov = False
    has_tot = False
    has_not_cov = False

    for agg in agg_entries:
        if not _agg_is_purely_international(agg, dom_code):
            continue
        cov = agg.get("cov")
        tot = agg.get("tot")
        not_cov = agg.get("not_cov")

        if cov is not None:
            total_cov += float(cov)
            has_cov = True
        if tot is not None:
            total_tot += float(tot)
            has_tot = True
        if not_cov is not None:
            total_not_cov += float(not_cov)
            has_not_cov = True

    return (
        total_cov if has_cov else None,
        total_tot if has_tot else None,
        total_not_cov if has_not_cov else None,
    )

def _merge_counts(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(a)
    for k, v in b.items():
        if isinstance(v, dict):
            if k not in out or not isinstance(out[k], dict):
                out[k] = dict(v)
            else:
                if k == "cov_t_meta":
                    for sk, sv in v.items():
                        if isinstance(sv, bool):
                            out[k][sk] = bool(out[k].get(sk, False)) or sv
                        else:
                            out[k][sk] = out[k].get(sk, 0) + sv
                else:
                    for sk, sv in v.items():
                        out[k][sk] = out[k].get(sk, 0) + sv
        elif isinstance(v, list):
            if k not in out or not isinstance(out[k], list):
                out[k] = list(v)
            else:
                for item in v:
                    if item not in out[k]:
                        out[k].append(item)
        elif isinstance(v, (int, float)):
            out[k] = out.get(k, 0) + v
        else:
            if k not in out:
                out[k] = v
    return out


def _flatten_summary_dict(d: Optional[Dict[str, Any]]) -> List[str]:
    if not isinstance(d, dict):
        return []
    flat = set()
    for v in d.values():
        if isinstance(v, list):
            flat.update(v)
    return sorted(list(flat))


def _mark_sub_allocations(
    countries: List[Dict[str, Any]], 
    domestic_country_code: Optional[str] = None
) -> None:
    """
    Mark countries as sub-allocations of their parents when:
    parent_reported_cov >= sum(direct_children_reported_cov)
    
    This prevents double-counting in hierarchies like:
    - EUR: 2000 (parent)
      ├─ CIS: 1000 (child)
      │   └─ RU and others
      └─ DE: 500 (child)
    
    Modifies countries list in-place, adding:
    - "is_sub_allocation": True
    - "parent_allocation_code": <parent_code>
    """
    if not countries:
        return
    
    countries_by_code = {c.get("country_code"): c for c in countries if c.get("country_code")}
    if not countries_by_code:
        return
    
    # Build parent-child relationships using COMPOSITE_REGION_MAP and containment
    parent_map = {}  # child_code -> parent_code
    children_map = {}  # parent_code -> list of direct children
    
    for child_code in countries_by_code.keys():
        if child_code in IGNORED_REGIONS or child_code in AGG_SET or child_code in DOMESTIC_SET:
            continue
        
        # Find potential parents
        potential_parents = []
        
        for parent_code in countries_by_code.keys():
            if parent_code == child_code or parent_code in IGNORED_REGIONS or parent_code in AGG_SET:
                continue
            
            # Check if parent is a composite region containing child's constituents
            if parent_code in COMPOSITE_REGION_MAP and child_code in COMPOSITE_REGION_MAP:
                parent_constituents = set(get_composite_constituents(parent_code) or [])
                child_constituents = set(get_composite_constituents(child_code) or [])
                
                # If child's constituents are a subset of parent's, it's a parent-child relationship
                if child_constituents and child_constituents.issubset(parent_constituents):
                    potential_parents.append(parent_code)
            elif parent_code in COMPOSITE_REGION_MAP:
                # Parent is composite, check if child_code is in its constituents
                parent_constituents = set(get_composite_constituents(parent_code) or [])
                if child_code in parent_constituents:
                    potential_parents.append(parent_code)
            elif child_code in COMPOSITE_REGION_MAP:
                # Child is composite, check if parent_code contains it
                child_constituents = set(get_composite_constituents(child_code) or [])
                if parent_code in COMPOSITE_REGION_MAP:
                    parent_constituents = set(get_composite_constituents(parent_code) or [])
                    if child_constituents.issubset(parent_constituents):
                        potential_parents.append(parent_code)
        
        # If no composite mapping found, fall back to is_contained
        if not potential_parents:
            for parent_code in countries_by_code.keys():
                if parent_code == child_code or parent_code in IGNORED_REGIONS or parent_code in AGG_SET:
                    continue
                if is_contained(container_key=parent_code, item_key=child_code, domestic_country_code=domestic_country_code):
                    potential_parents.append(parent_code)
        
        if not potential_parents:
            continue
        
        # Choose the most-specific (smallest) parent
        # by finding the one that is not contained in any other potential parent
        for candidate in potential_parents:
            is_smallest = True
            for other in potential_parents:
                if other != candidate:
                    # Check if candidate is contained in other (meaning other is larger)
                    if candidate in COMPOSITE_REGION_MAP and other in COMPOSITE_REGION_MAP:
                        candidate_constituents = set(get_composite_constituents(candidate) or [])
                        other_constituents = set(get_composite_constituents(other) or [])
                        if candidate_constituents and candidate_constituents.issubset(other_constituents) and candidate_constituents != other_constituents:
                            is_smallest = False
                            break
                    elif is_contained(
                        container_key=other,
                        item_key=candidate,
                        domestic_country_code=domestic_country_code,
                    ):
                        is_smallest = False
                        break
            
            if is_smallest:
                parent_map[child_code] = candidate
                if candidate not in children_map:
                    children_map[candidate] = []
                children_map[candidate].append(child_code)
                break
    
    # Mark sub-allocations: for each parent, check if sum(children) <= parent
    processed = set()
    
    def mark_subtree(parent_code):
        """Recursively mark a parent's children as sub-allocations if appropriate."""
        if parent_code in processed:
            return
        processed.add(parent_code)
        
        direct_children = children_map.get(parent_code, [])
        if not direct_children:
            return
        
        parent_entry = countries_by_code.get(parent_code)
        if not parent_entry:
            return
        
        # Get parent's reported coverage
        parent_cov = (parent_entry.get("reported_totals") or {}).get("cov")
        if parent_cov is None:
            return
        
        # Sum direct children's reported coverage
        children_cov_sum = 0.0
        for child_code in direct_children:
            child_entry = countries_by_code.get(child_code)
            if child_entry:
                child_cov = (child_entry.get("reported_totals") or {}).get("cov")
                if child_cov is not None:
                    children_cov_sum += float(child_cov)
        
        # If parent >= sum(direct_children), mark children as sub-allocations
        if float(parent_cov) >= children_cov_sum:
            for child_code in direct_children:
                child_entry = countries_by_code.get(child_code)
                if child_entry:
                    child_entry["is_sub_allocation"] = True
                    child_entry["parent_allocation_code"] = parent_code
                    # Continue processing grandchildren under this child
                    mark_subtree(child_code)
    
    # Start from all entries
    for country_code in countries_by_code.keys():
        mark_subtree(country_code)

def generate_stratified_sample(df: pd.DataFrame, target_size: int, explicit_csv: Optional[str] = None) -> pd.DataFrame:
    sampled_accessions = set()

    if explicit_csv and Path(explicit_csv).exists():
        explicit_df = pd.read_csv(explicit_csv)
        if "accession" in explicit_df.columns:
            explicit_accs = set(explicit_df["accession"].astype(str))
            sampled_accessions.update(explicit_accs)
            logging.info("Added %d explicit accessions from %s", len(explicit_accs), explicit_csv)

    if target_size <= 0:
        return (
            df[df["accession"].astype(str).isin(sampled_accessions)]
            .drop_duplicates(subset=["accession"])
            .copy()
        )

    # Drop duplicated accessions up front so the sampler does not waste quota
    # on repeated candidates from the same filing.
    df_sample = df.drop_duplicates(subset=["accession"]).copy()

    def print_and_sample(column_name: str, num_per_group: int):
        if len(sampled_accessions) >= target_size:
            return
        remaining_mask = ~df_sample["accession"].astype(str).isin(sampled_accessions)
        series_col = df_sample.loc[remaining_mask, column_name]
        counts = series_col.value_counts(dropna=False)
        logging.info("--- Category: %s ---", series_col.name)
        for val, count in counts.items():
            logging.info("  %s: %d candidates", val, count)

        # Sample
        for val in counts.index:
            if pd.isna(val):
                mask = series_col.isna()
            else:
                mask = series_col == val

            pool = df_sample.loc[remaining_mask & mask]
            if len(pool) > 0:
                k = min(num_per_group, len(pool), target_size - len(sampled_accessions))
                if k <= 0:
                    return
                chosen = pool.sample(n=k, random_state=42)
                sampled_accessions.update(chosen["accession"].astype(str))

    # Calculate rough distribution to hit the target target_size (~8 dimensions = ~40 buckets)
    n_per_stratum = max(1, target_size // 40)

    # Setup stratified buckets for numeric and keyword variables
    df_sample["dom_pct_bucket"] = pd.cut(
        df_sample["dom_pct"].fillna(-1), 
        bins=[-2, -0.1, 0.1, 25, 50, 75, 100], 
        labels=["Null", "0", "1-25", "26-50", "51-75", "76-100"]
    )

    df_sample["tot_count_bucket"] = pd.cut(
        df_sample["tot_count"].fillna(-1), 
        bins=[-2, -0.1, 0.1, 1000, 10000, 100000, float("inf")], 
        labels=["Null", "0", "1-1K", "1K-10K", "10K-100K", ">100K"]
    )

    df_sample["int_count_bucket"] = pd.cut(
        df_sample["int_count"].fillna(-1), 
        bins=[-2, -0.1, 0.1, 1000, 10000, 100000, float("inf")], 
        labels=["Null", "0", "1-1K", "1K-10K", "10K-100K", ">100K"]
    )

    df_sample["kw_bucket"] = pd.cut(
        df_sample["global_keyword_count"].fillna(-1), 
        bins=[-2, -0.1, 0.1, 5, 20, float("inf")], 
        labels=["Null", "0", "1-5", "6-20", ">20"]
    )

    # Domestic code (Top 5 + Rest)
    top_codes = df_sample["domestic_country_code"].value_counts().nlargest(5).index
    df_sample["dom_code_bucket"] = df_sample["domestic_country_code"].where(
        df_sample["domestic_country_code"].isin(top_codes), "OTHER"
    )

    df_sample["lang_fallback_bucket"] = (
        df_sample["has_language_fallback"]
        .map({True: "fallback", False: "no_fallback"})
        .fillna("no_fallback")
    )
    print_and_sample("lang_fallback_bucket", n_per_stratum)
    if "year_mismatch" in df_sample.columns:
        df_sample["year_mismatch_bucket"] = (
            df_sample["year_mismatch"]
            .map({True: "mismatch", False: "no_mismatch"})
            .fillna("no_mismatch")
        )
        print_and_sample("year_mismatch_bucket", n_per_stratum)
    print_and_sample("year", n_per_stratum)
    print_and_sample("dom_cov", n_per_stratum)
    print_and_sample("int_cov", n_per_stratum)
    print_and_sample("dom_pct_bucket", n_per_stratum)
    print_and_sample("tot_count_bucket", n_per_stratum)
    print_and_sample("int_count_bucket", n_per_stratum)
    print_and_sample("dom_code_bucket", n_per_stratum)
    print_and_sample("kw_bucket", n_per_stratum)

    # Fill any remaining samples with random selection to hit target size exactly
    remaining = target_size - len(sampled_accessions)
    if remaining > 0:
        pool = df_sample[~df_sample["accession"].astype(str).isin(sampled_accessions)]
        if len(pool) > 0:
            chosen = pool.sample(n=min(remaining, len(pool)), random_state=42)
            sampled_accessions.update(chosen["accession"].astype(str))

    logging.info("Total unique sampled accessions: %d", len(sampled_accessions))
    return df_sample[df_sample["accession"].astype(str).isin(sampled_accessions)].copy()


def _drop_temp_sample_columns(df: pd.DataFrame) -> pd.DataFrame:
    cols = [c for c in TEMP_SAMPLE_COLUMNS if c in df.columns]
    if cols:
        return df.drop(columns=cols)
    return df


def export_parquet(
    source_db: str, 
    output_path: str, 
    sample_size: int = 0, 
    explicit_csv: Optional[str] = None
) -> None:
    source_path = Path(source_db)
    if not source_path.exists():
        logging.error("Source DB not found: %s", source_db)
        return

    conn = sqlite3.connect(source_db)
    try:
        query = f"""
            SELECT
                p.accession,
                r.cik,
                r.url,
                r.year,
                p.item1_country_report,
                p.item1a_country_report,
                p.item1_risk_summary,
                p.item1a_risk_summary,
                p.item1_bargaining_report,
                p.item1a_bargaining_report
            FROM {SOURCE_TABLE} p
            LEFT JOIN report_data r ON p.accession = r.accession
        """
        df = pd.read_sql_query(query, conn)
    finally:
        conn.close()

    def extract_fields(row) -> Dict[str, Any]:
        item1_report = _safe_json_loads(row.get("item1_country_report"))
        item1a_report = _safe_json_loads(row.get("item1a_country_report"))
        country_report = item1_report or item1a_report or {}

        # Mark countries as sub-allocations of their parents to prevent double-counting
        countries = country_report.get("countries") or []
        if countries:
            _mark_sub_allocations(
                countries, 
                domestic_country_code=country_report.get("domestic_country_code")
            )

        summary = country_report.get("summary") or {}
        summary_cov = summary.get("cov") if isinstance(summary, dict) else None
        summary_not_cov = summary.get("not_cov") if isinstance(summary, dict) else None

        summary_cov_flat = _flatten_summary_dict(summary_cov)
        summary_not_cov_flat = _flatten_summary_dict(summary_not_cov)

        item1_risk = _safe_json_loads(row.get("item1_risk_summary"))
        item1a_risk = _safe_json_loads(row.get("item1a_risk_summary"))
        item1_barg = _safe_json_loads(row.get("item1_bargaining_report"))
        item1a_barg = _safe_json_loads(row.get("item1a_bargaining_report"))

        risk_summary = {}
        if item1_risk or item1a_risk:
            risk_summary = _merge_counts(item1_risk or {}, item1a_risk or {})
            if "n" in risk_summary:
                risk_summary["n"] = (
                    (item1_risk or {}).get("n", 0)
                    + (item1a_risk or {}).get("n", 0)
                )

        dom_domestic_count, dom_domestic_pct = _domestic_explicit(country_report)

        if dom_domestic_pct is None:
            dom_domestic_pct = _domestic_parent_pct(country_report)

        if dom_domestic_count is None:
            dom_domestic_count = _domestic_parent_cov_remainder(country_report)

        dom_pulled_from_risk = False
        # Note: 'not dom_domestic_count' is True if count is 0.0 or None
        if dom_domestic_count in (None, 0, 0.0) and risk_summary:
            risk_cov = risk_summary.get("cov_t", {}).get("cov")
            risk_pct = risk_summary.get("cov_t", {}).get("pct")
            risk_meta = risk_summary.get("cov_t_meta", {}) or {}
            risk_cov_has_count = bool(risk_meta.get("cov_has_count"))
            risk_pct_from_counts = bool(risk_meta.get("pct_from_counts"))
            risk_pct_has_qual = bool(risk_meta.get("pct_has_qualitative"))
            if risk_cov is not None:
                if risk_cov_has_count:
                    dom_domestic_count = float(risk_cov)
                    dom_pulled_from_risk = True
            if risk_pct is not None and float(risk_pct) != 100.0:
                pct_val = float(risk_pct)
                if risk_pct_from_counts and not risk_pct_has_qual and 0.0 <= pct_val <= 100.0:
                    dom_domestic_pct = pct_val
                    dom_pulled_from_risk = True

        if summary.get("dom_cov") is False and not dom_pulled_from_risk:
            dom_domestic_count = 0.0
            dom_domestic_pct = 0.0

        int_cov, int_tot, int_not_cov = _int_reported_totals(country_report)

        agg_int_cov, agg_int_tot, agg_int_not_cov = _agg_international_totals(
            country_report
        )
        if agg_int_cov is not None:
            int_cov = (int_cov or 0.0) + agg_int_cov
        if agg_int_tot is not None:
            int_tot = (int_tot or 0.0) + agg_int_tot
        if agg_int_not_cov is not None:
            int_not_cov = (int_not_cov or 0.0) + agg_int_not_cov

        # If domestic coverage exists and international totals include a parent container
        # that contains the domestic country, subtract domestic once to avoid double-counting.
        if dom_domestic_count is not None and int_cov is not None:
            dom_code = country_report.get("domestic_country_code")
            if dom_code:
                has_parent_container = False
                for entry in country_report.get("countries") or []:
                    c_code = entry.get("country_code")
                    if not c_code or c_code == dom_code:
                        continue
                    if c_code in IGNORED_REGIONS:
                        continue
                    if entry.get("is_sub_allocation"):
                        continue
                    reported = entry.get("reported_totals") or {}
                    if reported.get("cov") is None:
                        continue
                    if is_contained(
                        container_key=c_code,
                        item_key=dom_code,
                        domestic_country_code=dom_code,
                    ):
                        has_parent_container = True
                        break
                if has_parent_container:
                    int_cov = max(0.0, float(int_cov) - float(dom_domestic_count))

        summary_int_false = summary.get("int_cov") is False
        if summary_int_false and agg_int_cov is None:
            int_cov = 0.0

        if int_cov is not None and int_cov > 0 and int_tot == 0:
            int_tot = None
        if (not summary_int_false) and int_cov == 0 and int_tot == 0 and (
            int_not_cov in (0, None)
        ):
            int_cov = None
            int_tot = None
            int_not_cov = None

        # Calculate total explicit coverage (dom + int + non-intl agg),
        # only when both dom and int are known (int can be 0.0).
        total_cov = None
        if dom_domestic_count is not None and int_cov is not None:
            total_cov_val = float(dom_domestic_count) + float(int_cov)
            for a in (country_report.get("agg") or []):
                if _agg_is_purely_international(
                    a, country_report.get("domestic_country_code")
                ):
                    continue
                acov = a.get("cov")
                if acov is not None:
                    total_cov_val += float(acov)
            total_cov = total_cov_val

        # Prefer explicit global coverage when available to avoid double counting
        global_entry = country_report.get("global") or {}
        global_cov = global_entry.get("cov")
        if global_cov is None:
            g_tot = global_entry.get("tot")
            g_pct = global_entry.get("pct")
            if g_tot is not None and g_pct is not None:
                try:
                    global_cov = (float(g_pct) / 100.0) * float(g_tot)
                except (TypeError, ValueError):
                    global_cov = None
        if global_cov is not None:
            total_cov = float(global_cov)

        global_cov_candidate = global_entry.get("cov")
        if global_cov_candidate is None:
            g_tot = global_entry.get("tot")
            g_pct = global_entry.get("pct")
            if g_tot is not None and g_pct is not None:
                try:
                    global_cov_candidate = (float(g_pct) / 100.0) * float(g_tot)
                except (TypeError, ValueError, ZeroDivisionError):
                    global_cov_candidate = None

        tot_count = _resolve_total_count(
            dom_domestic_count,
            int_cov,
            global_cov_candidate,
            fallback_total=total_cov,
        )

        int_pct = _int_reported_pct(country_report)
        int_cov, int_pct = _normalize_count_pct_pair(int_cov, int_pct)

        tot_pct = _tot_reported_pct(country_report, tot_count, total_cov)
        tot_count, tot_pct = _normalize_count_pct_pair(tot_count, tot_pct)

        lang_fallback_codes = [
            c.get("country_code")
            for c in (country_report.get("countries") or [])
            if c.get("language_fallback_country") is True and c.get("country_code")
        ]
        return {
            "domestic_country_code": country_report.get("domestic_country_code"),
            "dom_cov": summary.get("dom_cov") if isinstance(summary, dict) else None,
            "int_cov": summary.get("int_cov") if isinstance(summary, dict) else None,
            "year_mismatch": bool(country_report.get("year_mismatch")),
            "summary_cov": _safe_json_dumps(summary_cov_flat),
            "summary_not_cov": _safe_json_dumps(summary_not_cov_flat),
            "has_language_fallback": bool(lang_fallback_codes),
            "language_fallback_codes": _safe_json_dumps(lang_fallback_codes),
            "countries": _safe_json_dumps(country_report.get("countries") or []),
            "agg": _safe_json_dumps(country_report.get("agg") or []),
            "global": _safe_json_dumps(country_report.get("global") or {}),
            "global_keywords": _safe_json_dumps(
                country_report.get("global_keywords") or []
            ),
            "global_keyword_count": country_report.get("global_keyword_count"),
            "risk_summary": _safe_json_dumps(risk_summary or {}),
            "bargaining_report": _safe_json_dumps(item1_barg or item1a_barg or {}),
            "dom_count": dom_domestic_count,
            "dom_pct": dom_domestic_pct,
            "int_count": int_cov,
            "int_pct": int_pct,
            "tot_count": tot_count,
            "tot_pct": tot_pct,
        }

    extracted = df.apply(extract_fields, axis=1, result_type="expand")
    out = pd.concat([df[["accession", "cik", "url", "year"]], extracted], axis=1)

    if sample_size > 0 or explicit_csv:
        out = generate_stratified_sample(out, target_size=sample_size, explicit_csv=explicit_csv)

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Drop temporary stratification columns before writing the parquet.
    out = _drop_temp_sample_columns(out)
    # Drop unneeded cols
    out = out.drop(columns=["has_language_fallback"])
    out.to_parquet(out_path, index=False)
    logging.info("Wrote parquet: %s (rows: %s)", out_path, len(out))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export provenance DB into a compact parquet file."
    )
    parser.add_argument("--source", default=SOURCE_DB_DEFAULT, help="Source DB path")
    parser.add_argument(
        "--output", default=TARGET_PARQUET_DEFAULT, help="Output parquet path"
    )
    parser.add_argument(
        "--sample-size", type=int, default=0, help="If > 0, randomly sample this many rows across stratified buckets"
    )
    parser.add_argument(
        "--explicit-sample-csv", type=str, default=None, help="Path to CSV containing an 'accession' column to include in sample"
    )
    args = parser.parse_args()

    export_parquet(args.source, args.output, args.sample_size, args.explicit_sample_csv)


if __name__ == "__main__":
    main()
