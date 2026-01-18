from pathlib import Path
import sqlite3
import json
import re
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, asdict
import multiprocessing as mp
from tqdm import tqdm
from typing import Any, Tuple, Dict, Set, Optional, List

# --- IMPORTS ---
from defs.regex_lib import SENTENCE_SPLIT_PATTERN
from defs.ir_regex import IR_REGEX, IR_SOFT_REGEX
from defs.fx_regex import FX_REGEX, FX_SOFT_REGEX
from defs.cp_regex import CP_REGEX, CP_SOFT_REGEX, TRADING_VENUE_REGEX
from defs.cr_regex import CR_REGEX, CR_SOFT_REGEX
from defs.eq_regex import EQ_REGEX, EQ_SOFT_REGEX
from defs.gen_regex import GEN_REGEX, GEN_STRICT_CONTEXT_REGEX, HEDGING_CONTEXT_REGEX, PRECISE_LOOSE_GEN_REGEX
from defs.derivative_lib import CATEGORY_MAP, find_hedging_context
from defs.derivatives_core import BASE_REGEX, PRECISE_BASE_REGEX
from defs.shared_context import CURRENCY_NAMES_REGEX, all_currencies
from prefilter_tagging import extract_values_and_years
from table_processor import TABLE_ANCHOR
from defs.prefiltered_lib import DEADWEIGHT_TOKEN, SKIP_TOKEN, MinimalTextCleaner, NoiseReason, EvidenceReason, convertible_ir, is_sophisticated_content, is_sophisticated_target

# =============================================================================
# INSTRUMENT EVIDENCE STRUCTURES
# =============================================================================

@dataclass
class InstrumentAmount:
    type: str       # 'fv', 'notional', or 'value'
    amount: float   # Numeric value (calculated from text)
    currency: str    # ISO Code (USD, EUR, etc.)
    year: Optional[int] = None
    is_zero: bool = False   # Tracks "nil" or "$0" amounts
    explicit_multiplier: float = 1.0  # Multiplier found in text (1.0 if raw, 1_000_000 if "M")
    is_explicit: bool = False         # True if text had "M", "B", "million", etc.
    source_multiplier: Optional[float] = None  # Which explicit multiplier was used to derive this (for audit)
    inferred_amount: Optional[float] = None    # Final normalized value after context scanning
    inference_note: Optional[str] = None       # Why/how it was inferred (or None if not modified)

@dataclass
class InstrumentDetail:
    category: str
    name: str       # The specific phrase found (e.g. "Interest rate swap")
    amounts: List[InstrumentAmount]

# =============================================================================
# CONFIGURATION
# =============================================================================
NUM_WORKERS = max(1, mp.cpu_count() - 1)
BATCH_SIZE = 1000
SOURCE_DB_PATH = "evidence_data.db"
TARGET_DB_PATH = "classified_data.db"

# Tag Parsing
TAG_PARSER_STRICT = re.compile(r"^\s*(_[SD])<([^>]+)>\s+(.*)", re.DOTALL)
EVIDENCE_TAG_PARSER = re.compile(r"_E<([^>]+)>")

# Evidence that elevates soft mentions to strict (unambiguous subject)
UNAMBIGUOUS_EVIDENCE = {
    EvidenceReason.AS_YEAR.value,  # "Outstanding at Dec 31, 2024"
    EvidenceReason.MAT_FUT.value,  # "Matures in 2026"
    EvidenceReason.NVY.value,  # "Notional was $100M at Dec 31, 2024"
    EvidenceReason.FVY.value,  # "Fair Value was $5M at Dec 31, 2024"
    EvidenceReason.VY.value,  # "Value was $5M at Dec 31, 2024"
    EvidenceReason.ACT_YEAR.value,
    EvidenceReason.CONT_USE.value,  # "We hold/use Swaps" (No year)
    EvidenceReason.NVNY.value,  # "Notional is $100M"
    EvidenceReason.VNY.value,  # " Value is $5M"
    EvidenceReason.FVNY.value,  # "Fair Value is $5M"
    EvidenceReason.BS_LOC.value,  # "Recorded in Earnings"
    EvidenceReason.ACT_GEN.value,
}

_cleaner = MinimalTextCleaner()

# =============================================================================
# CURRENCY MAPPING
# =============================================================================
# Build currency mapping from Currency class for efficient lookup
CURRENCY_CODE_MAP = {}
CURRENCY_SYMBOL_MAP = {}
for currency in all_currencies:
    # Map full name -> code
    CURRENCY_CODE_MAP[currency.full_name.lower()] = currency.code
    # Map symbol -> code
    CURRENCY_SYMBOL_MAP[currency.symbol.lower()] = currency.code
    # Map code to itself
    CURRENCY_CODE_MAP[currency.code.lower()] = currency.code
    # Map adjective -> code (e.g., "U.S." -> "USD")
    CURRENCY_CODE_MAP[currency.adjective.lower()] = currency.code

# =============================================================================
# GLOBAL INSTRUMENT TRACKER
# =============================================================================

class GlobalInstrumentTracker:
    """Tracks instrument → category mappings from strict mentions."""
    STOPLIST = {
        "hedge",
        "hedges",
        "hedging",
        "derivative",
        "derivatives",
    }
    EMBEDDED_TERMS = {
        "embedded",
    }
    
    def __init__(self):
        self.instrument_map = defaultdict(set)

    def register_paragraph(self, sentence: str, category: str) -> None:
        """Register instruments found in sentence to category."""
        sentence_lower = sentence.lower()
        
        # Check for embedded terms
        for term in self.EMBEDDED_TERMS:
            if term in sentence_lower:
                self.instrument_map[term].add(category)

        specific_matches = [m.group(0) for m in BASE_REGEX.finditer(sentence)]

        if specific_matches:
            for instr in specific_matches:
                token = instr.lower().rstrip("s")
                if token not in self.STOPLIST:
                    self.instrument_map[token].add(category)

    def resolve_instrument(self, sentence: str) -> Optional[str]:
        """Returns category if sentence contains unambiguous known instrument."""
        matches = BASE_REGEX.findall(sentence)
        sentence_lower = sentence.lower()
        
        # Check for embedded terms
        for term in self.EMBEDDED_TERMS:
            if term in sentence_lower:
                matches.append(term)

        candidates = set()
        for m in matches:
            token = m.lower().rstrip("s")
            if token in self.instrument_map:
                candidates.update(self.instrument_map[token])

        if len(candidates) == 1:
            return list(candidates)[0]

        return None

# =============================================================================
# HELPERS
# =============================================================================

def parse_tags(text: str) -> Tuple[bool, Optional[str], str]:
    """Parse _D or _S tags. Returns (is_deadweight, tag_reason, clean_text)."""
    match = TAG_PARSER_STRICT.match(text)
    if match:
        tag_type = match.group(1)
        tag_reason = match.group(2)
        clean_text = match.group(3)
        is_deadweight = tag_type in [DEADWEIGHT_TOKEN, SKIP_TOKEN]
        return is_deadweight, tag_reason, clean_text

    return False, None, text


def has_unambiguous_evidence(sentence: str) -> bool:
    """Check if sentence has unambiguous evidence tags."""
    evidence_tags = set(EVIDENCE_TAG_PARSER.findall(sentence))
    return bool(evidence_tags.intersection(UNAMBIGUOUS_EVIDENCE))


def extract_categories_strict(sentence: str) -> Set[str]:
    """Extract STRICT category matches only."""
    cats = set()

    if IR_REGEX.search(sentence):
        cats.add("ir")
    if FX_REGEX.search(sentence):
        cats.add("fx")
    if CP_REGEX.search(sentence):
        cats.add("cp")
    if CR_REGEX.search(sentence):
        cats.add("cr")
    if is_sophisticated_target(sentence):
        cats.add("warr")
    elif EQ_REGEX.search(sentence):
        cats.add("eq")
    if not cats and TABLE_ANCHOR in sentence:
        if CURRENCY_NAMES_REGEX.search(sentence):
            cats.add("fx")
        if FX_SOFT_REGEX.search(sentence):
            cats.add("fx")
        if IR_SOFT_REGEX.search(sentence):
            cats.add("ir")
        if CP_SOFT_REGEX.search(sentence):
            cats.add("cp")
        if CR_SOFT_REGEX.search(sentence):
            cats.add("cr")
        if is_sophisticated_target(sentence):
            cats.add("warr")
        elif EQ_SOFT_REGEX.search(sentence):
            cats.add("eq")
        if not cats:
            cats.add("gen")
    return cats


def extract_categories_soft(sentence: str) -> Set[str]:
    """Extract SOFT category matches only."""
    cats = set()
    if IR_SOFT_REGEX.search(sentence):
        cats.add("ir")
    if FX_SOFT_REGEX.search(sentence):
        cats.add("fx")
    if CP_SOFT_REGEX.search(sentence):
        cats.add("cp")
    if CR_SOFT_REGEX.search(sentence):
        cats.add("cr")
    if is_sophisticated_target(sentence):
        cats.add("warr")
    elif EQ_SOFT_REGEX.search(sentence):
        cats.add("eq")

    if not cats:
        if GEN_REGEX.search(sentence) or GEN_STRICT_CONTEXT_REGEX.search(sentence):
            cats.add("gen")
        elif PRECISE_LOOSE_GEN_REGEX.search(sentence) and HEDGING_CONTEXT_REGEX.search(
            sentence
        ):
            cats.add("gen")

    return cats


def detect_currency(text: str) -> str:
    """
    Detect currency code from text using CURRENCY_CODE_MAP and CURRENCY_SYMBOL_MAP.
    Returns ISO currency code (default: USD).
    """
    # First try symbol matching (fastest)
    for symbol, code in CURRENCY_SYMBOL_MAP.items():
        if symbol in text.lower():
            return code
    
    # Then try name/code matching
    text_lower = text.lower()
    for name, code in CURRENCY_CODE_MAP.items():
        if name in text_lower:
            return code
    
    return "USD"  # Default fallback


def normalize_amount(text: str) -> Tuple[float, float, bool]:
    """
    Normalize abbreviated monetary values to numeric amounts.
    Returns (calculated_amount, multiplier_used, is_explicit).
    
    Examples:
        "$10M" -> (10,000,000, 1_000_000, True)
        "$10 M" -> (10,000,000, 1_000_000, True)
        "$1.5 billion" -> (1_500_000_000, 1_000_000_000, True)
        "$500K" -> (500,000, 1_000, True)
        "$10" -> (10, 1.0, False)
    
    Handles multipliers:
    - Abbreviated (with optional spaces): K/k, M/m, B/b, T/t
    - Full words: thousand, million, billion, trillion
    """
    # Extract the numeric part
    num_str = re.sub(r'[^\d.]', '', text)
    if not num_str:
        return 0.0, 1.0, False
    
    try:
        base_value = float(num_str)
    except ValueError:
        return 0.0, 1.0, False
    
    text_upper = text.upper()
    
    # 1. Try full word multipliers first (e.g., "million", "billion")
    word_multipliers = {
        'TRILLION': 1_000_000_000_000,
        'BILLION': 1_000_000_000,
        'MILLION': 1_000_000,
        'THOUSAND': 1_000,
    }
    for word, mult in word_multipliers.items():
        if word in text_upper:
            return base_value * mult, float(mult), True
    
    # 2. Try abbreviated multipliers (K, M, B, T with optional spaces)
    multiplier_match = re.search(r'\d\s*([KMBT])\b', text_upper)
    if multiplier_match:
        suffix = multiplier_match.group(1)
        multipliers = {
            'K': 1_000,
            'M': 1_000_000,
            'B': 1_000_000_000,
            'T': 1_000_000_000_000,
        }
        mult = float(multipliers.get(suffix, 1.0))
        return base_value * mult, mult, True

    # 3. No explicit multiplier found
    return base_value, 1.0, False


def extract_instrument_keywords(sentence: str) -> Dict[str, Set[str]]:
    """
    Extract actual matched instrument text from category regexes.
    Returns a dict mapping category -> set of matched instrument keywords.
    
    Only captures matches from the category regexes (strict_inst, soft_inst).
    Used ONLY for valid evidence cases to avoid noise.
    """
    instruments = defaultdict(set)

    for cat, (strict_inst, soft_inst, _, _, _) in CATEGORY_MAP.items():
        # Try strict instrument first (higher confidence)
        if strict_inst:
            for match in strict_inst.finditer(sentence):
                instruments[cat].add(match.group(0).strip())

        # Then soft instrument (if no strict found)
        if soft_inst and cat not in instruments:
            for match in soft_inst.finditer(sentence):
                instruments[cat].add(match.group(0).strip())

    # Clean up empty categories
    return {cat: kw for cat, kw in instruments.items() if kw}

# In classify_users.py


def extract_instrument_evidence(
    sentence: str,
    category: str,
    reporting_year: int,
    local_tracker: Optional[GlobalInstrumentTracker] = None,
    global_tracker: Optional[GlobalInstrumentTracker] = None,
    context_cats: Optional[Set[str]] = None,
    accumulated_cats: Optional[Set[str]] = None,
    global_cats: Optional[Set[str]] = None,
) -> List[InstrumentDetail]:
    """
    Links detected instruments with their quantitative data found in the same sentence.
    Returns a list of InstrumentDetail objects—one per matched instrument.

    Enhancements:
    1. Uses evidence tags (FVY, NVY, etc.) to determine accounting type
    2. Captures full instrument names from matched phrases (all of them, not just longest)
    3. Uses Currency class mapping for currency detection
    4. Creates separate InstrumentDetail for each instrument to avoid consolidation
    5. Resolves generic categories using trackers and context
    """
    target_category = category

    # Resolve generic category if possible
    if target_category == "gen":
        resolved = None
        # 1. Local Tracker
        if local_tracker:
            resolved = local_tracker.resolve_instrument(sentence)

        # 2. Global Tracker
        if not resolved and global_tracker:
            resolved = global_tracker.resolve_instrument(sentence)

        # 3a. Accumulated Context (if exactly one)
        if not resolved and accumulated_cats and len(accumulated_cats) == 1:
            resolved = list(accumulated_cats)[0]

        # 3b. Paragraph Context (if exactly one)
        if not resolved and context_cats and len(context_cats) == 1:
            resolved = list(context_cats)[0]

        # 4. Global Context (if exactly one strict category exists globally)
        if not resolved and global_cats and len(global_cats) == 1:
            resolved = list(global_cats)[0]

        if resolved:
            target_category = resolved

    # 1. Determine Accounting Context from Evidence Tags (Primary)
    evidence_tags = set(EVIDENCE_TAG_PARSER.findall(sentence))
    val_type = "value"

    # Map evidence tags to accounting types
    fv_tags = {
        EvidenceReason.FVY.value,  # Fair Value was $X at Year
        EvidenceReason.FVNY.value,  # Fair Value is $X
        EvidenceReason.FVAIY.value,  # Fair Value at inception was $X
        EvidenceReason.FVAINY.value,  # Fair Value at inception is $X
    }
    notional_tags = {
        EvidenceReason.NVY.value,  # Notional was $X at Year
        EvidenceReason.NVNY.value,  # Notional is $X
    }
    value_tags = {
        EvidenceReason.VY.value,  # Value was $X at Year
        EvidenceReason.VNY.value,  # Value is $X
    }

    if evidence_tags.intersection(fv_tags):
        val_type = "fv"
    elif evidence_tags.intersection(notional_tags):
        val_type = "notional"
    elif evidence_tags.intersection(value_tags):
        val_type = "value"
    else:
        val_type = "unknown"

    # 2. Extract numeric data and years
    years, values = extract_values_and_years(sentence)

    # 3. Find ALL Instrument Names (using category-specific keywords first)
    inst_keywords = extract_instrument_keywords(sentence)
    instrument_names = []

    if inst_keywords and target_category in inst_keywords:
        # Get ALL matched instruments for this category (not just the longest)
        matched = list(inst_keywords[target_category])
        if matched:
            # Sort by length (longest/most specific first) for predictable ordering
            instrument_names = sorted(matched, key=len, reverse=True)
    else:
        # Fallback to BASE_REGEX for generic instrument detection
        name_matches = [
            m.group(0).strip() for m in PRECISE_BASE_REGEX.finditer(sentence)
        ]
        instrument_names = name_matches if name_matches else ["unresolved"]

    # If no values, return empty list (no evidence to capture)
    if not values:
        return []

    # 4. Map Values to InstrumentAmount structures (shared across all instruments)
    amounts = []
    for val_tok in values:
        # Extract numeric float from text and normalize with multipliers
        raw_text = val_tok["text"]
        final_amt, mult, explicit = normalize_amount(raw_text)

        # 5. Detect Currency using Currency class mapping
        currency = detect_currency(raw_text)

        # Heuristic Year Mapping: Use reporting year if mentioned, else first year found
        mapped_year = (
            reporting_year if reporting_year in years else (years[0] if years else None)
        )

        amounts.append(
            InstrumentAmount(
                type=val_type,
                amount=final_amt,
                currency=currency,
                year=mapped_year,
                is_zero=val_tok["is_zero"],
                explicit_multiplier=mult,
                is_explicit=explicit,
                source_multiplier=mult if explicit else None,
            )
        )

    # 6. Create one InstrumentDetail per matched instrument (all share the same amounts)
    details = []
    for inst_name in instrument_names:
        details.append(
            InstrumentDetail(category=target_category, name=inst_name, amounts=amounts)
        )

    return details


def mine_attributes(tag_reason: Optional[str], attributes: Dict) -> Dict:
    """
    Extract user attributes from tags using a mapped lookup.
    Consolidates redundant state indicators into unified attributes.
    """
    if not tag_reason:
        return attributes

    # 1. Historical Special Case (Group of Noise Tags)
    if tag_reason in {
        NoiseReason.TIME.value,
        NoiseReason.TERM.value,
        NoiseReason.HIST_BLOCK.value,
    }:
        attributes["is_historical"] = True
        return attributes


    # 2. Attribute Mapping
    # Maps Tag Reason -> Attribute Key
    TAG_MAP = {
        # --- NOISE (Identity Signals) ---
        NoiseReason.TRADING.value: "is_hedger",
        NoiseReason.DOC.value: "documents_hedge_accounting",
        NoiseReason.AOCI.value: "has_aoci_activity",
        NoiseReason.CREDIT.value: "manages_credit_risk",
        # --- EVIDENCE (Reporting Signals) ---
        # A. POSITIONS (The "We Have It" Merge)
        # Merges: Active State (Anchored), Continuous Usage (General), and Location (Accounting)
        EvidenceReason.AS_YEAR.value: "reports_positions",
        EvidenceReason.ASAIY.value: "reports_positions",
        EvidenceReason.CONT_USE.value: "reports_positions",
        EvidenceReason.CONT_USE_AMB.value: "reports_positions",
        EvidenceReason.BS_LOC.value: "reports_positions",
        # B. TRANSACTIONS (The "Flow" Merge)
        EvidenceReason.ACT_YEAR.value: "reports_transactions",
        EvidenceReason.ACT_AMB_YEAR.value: "reports_transactions",
        EvidenceReason.ACT_GEN.value: "reports_transactions",
        # C. QUANTITATIVE (Kept distinct for granularity)
        EvidenceReason.NVY.value: "reports_notional",
        EvidenceReason.NVNY.value: "reports_notional",
        EvidenceReason.FVY.value: "reports_fair_value",
        EvidenceReason.FVNY.value: "reports_fair_value",
        EvidenceReason.FVAIY.value: "reports_fair_value",
        EvidenceReason.FVAINY.value: "reports_fair_value",
        # D. DETAILS
        EvidenceReason.MAT_FUT.value: "reports_maturity",
        EvidenceReason.MAT_AMB_FUT.value: "reports_maturity",
        EvidenceReason.VAL_MODEL.value: "eq_valuation_model",
    }

    # 3. Apply
    if target_attr := TAG_MAP.get(tag_reason):
        attributes[target_attr] = True
    return attributes


def aggregate_and_normalize(evidence_details: List[InstrumentDetail]) -> Tuple[Dict[str, Dict], Dict[str, List[str]]]:
    """
    Context-aware normalization with type-specific range validation.
    
    PRESCAN PHASE:
    1. Scan for ANY explicit multiplier (FV, notional, value - doesn't matter for multiplier).
    2. Determine global multiplier per category (mode of explicit multipliers).
    3. Build type-specific range maps (max FV, max notional, etc.).
    
    APPLICATION PHASE:
    4. For each orphan value (< 5000, non-explicit, non-zero):
       - Infer it using the category multiplier
       - Validate against type-specific range (can't exceed 10x max explicit of that type)
       - Update InstrumentAmount.inferred_amount with result
    5. Aggregate using inferred_amount (or original if validation failed)
    
    Returns:
        (aggregated_totals, validation_warnings)
        where evidence_details are MODIFIED IN PLACE with inferred_amount populated
    """
    if not evidence_details:
        return {}, {}
    
    # --- PHASE 1: PRESCAN FOR EXPLICIT MULTIPLIERS & RANGES BY TYPE ---
    global_multipliers = []
    category_multipliers = defaultdict(list)
    explicit_amounts_by_type = defaultdict(lambda: defaultdict(list))  # {category: {type: [amounts]}}
    
    for det in evidence_details:
        for amt in det.amounts:
            if amt.is_explicit and amt.explicit_multiplier > 1.0:
                category_multipliers[det.category].append(amt.explicit_multiplier)
                global_multipliers.append(amt.explicit_multiplier)
            # Track explicit amounts by category AND type
            if amt.is_explicit:
                explicit_amounts_by_type[det.category][amt.type].append(amt.amount)

    # Determine Global Default (Mode of explicit multipliers, fallback to 1M)
    global_default = 1_000_000.0  # Standard SEC filing convention
    if global_multipliers:
        global_default = max(set(global_multipliers), key=global_multipliers.count)

    # --- PHASE 2: NORMALIZE & AGGREGATE WITH TYPE-SPECIFIC RANGE VALIDATION ---
    aggregated = defaultdict(lambda: {"notional": 0.0, "fair_value": 0.0, "value": 0.0})
    validation_warnings = defaultdict(list)
    
    for det in evidence_details:
        # Determine category-specific default multiplier (any explicit multiplier applies to all types)
        if det.category in category_multipliers and category_multipliers[det.category]:
            cat_default = max(set(category_multipliers[det.category]), key=category_multipliers[det.category].count)
        else:
            cat_default = global_default
        
        # Get type-specific range bounds for this category
        cat_type_amounts = explicit_amounts_by_type[det.category]
        max_by_type = {
            amt_type: max(amounts) if amounts else None 
            for amt_type, amounts in cat_type_amounts.items()
        }

        for amt in det.amounts:
            final_val = amt.amount
            inference_note = None
            
            # Logic: If amount was not explicit AND is small (< 5000) AND not zero, apply inferred multiplier
            if not amt.is_explicit and not amt.is_zero and 0 < abs(amt.amount) < 5000:
                inferred_val = amt.amount * cat_default
                
                # Range validation: Check against max explicit of THE SAME TYPE
                max_explicit_for_type = max_by_type.get(amt.type)
                if max_explicit_for_type and inferred_val > max_explicit_for_type * 10:
                    validation_warnings[det.category].append(
                        f"{amt.type.upper()} inference for ${amt.amount} using multiplier {cat_default} "
                        f"(=${inferred_val:.0f}) exceeds max {amt.type} by 10x (max={max_explicit_for_type:.0f}). "
                        f"Keeping raw value ${amt.amount}."
                    )
                    # Validation failed, keep raw value but note it
                    final_val = amt.amount
                    inference_note = f"REJECTED: inference ${inferred_val:.0f} exceeds max by 10x"
                else:
                    # Validation passed, use inferred
                    final_val = inferred_val
                    inference_note = f"Inferred using multiplier {cat_default:.0f}"
            
            # Update the InstrumentAmount object with inferred value
            amt.inferred_amount = final_val
            amt.inference_note = inference_note
            
            # Summation by type (use inferred_amount)
            if amt.type == 'notional':
                aggregated[det.category]['notional'] += final_val
            elif amt.type == 'fv':
                aggregated[det.category]['fair_value'] += final_val
            elif amt.type == 'value':
                aggregated[det.category]['value'] += final_val

    return dict(aggregated), dict(validation_warnings)


def remove_outlier_categories(
    strict_counts: Dict[str, int],  # Changed from Set[str] to Dict[str, int]
    soft_counts: Dict[str, int],
    threshold_pct: float = 0.25,
    min_mentions: int = 5,
) -> Set[str]:
    """
    Remove soft categories that are outliers relative to the dominant strict category.

    1. Strict categories are 'Anchors'. Their weight = Strict + Soft.
    2. Soft-only categories are 'Candidates'. Their weight = Soft only.
    3. Candidates are removed if they don't meet the % threshold of the largest Anchor.
    """

    # 1. Calculate the "True Magnitude" of strict categories
    # If a category is strict, its dominance is Strict + Soft mentions.
    anchor_magnitudes = {}

    for cat, s_count in strict_counts.items():
        # Add the strict count plus any soft mentions for this same category
        anchor_magnitudes[cat] = s_count + soft_counts.get(cat, 0)

    # If we have no strict anchors, we fall back to absolute min_mentions logic
    if not anchor_magnitudes:
        return {cat for cat, count in soft_counts.items() if count >= min_mentions}

    # 2. Determine the baseline (largest anchor)
    max_anchor_count = max(anchor_magnitudes.values())

    # Calculate threshold based on the "heaviest" user category
    # Example: If IR has 22 total, threshold is 2.2
    dynamic_threshold = max(min_mentions, max_anchor_count * threshold_pct)

    valid_soft_cats = set()

    for cat, count in soft_counts.items():
        # If this soft cat is ALSO a strict cat, it's already kept by default.
        # But for the sake of returning a clean set of "surviving softs":
        if cat in strict_counts:
            valid_soft_cats.add(cat)
            continue

        # 3. Filter Soft-Only categories against the threshold
        if count >= dynamic_threshold:
            valid_soft_cats.add(cat)

    return valid_soft_cats


PRIORITY_ORDER = ["fx", "cp", "eq", "cr", "ir"]
def get_text_categories(text: str, is_nst: bool) -> Dict[str, int]:
    """
    Determines category using Weighted Scoring and Map Iteration.

    Phases:
    1. Strict Check (Instrument + Context): High Score (Bypass).
    2. Soft Check (Context Density): Low Score (Requires volume).
       - Uses Priority Consumption (FX eats 'Currency' before IR sees it).
    Returns a dictionary of {category: score} for categories meeting the threshold.
    """
    scores = defaultdict(int)

    # ═══════════════════════════════════════════════════════════
    # PHASE 1: STRICT SIGNALS (Non-Destructive)
    # ═══════════════════════════════════════════════════════════
    # We check Strict Instruments (Index 0) and Strict Context (Index 2)

    for cat, (strict_inst, soft_inst, strict_ctx, _, weak_inst) in CATEGORY_MAP.items():
        # A. Strict Instrument ("Interest Rate Swap")
        if strict_inst and strict_inst.search(text):
            scores[cat] += 1000
        elif soft_inst and soft_inst.search(text): # Interest rate cap
            scores[cat] += 500

        # B. Strict Context ("Interest Rate Risk")
        if strict_ctx and strict_ctx.search(text):
            # Special Handling for Equity -> Warrants
            if cat == "eq" and is_sophisticated_content(text) and not is_nst:
                scores["warr"] += 6000  # Immediate override
            else:
                scores[cat] += 2000
        if weak_inst and weak_inst.search(text): # Interest rate agreement
            scores[cat] += 200
                

    # ═══════════════════════════════════════════════════════════
    # PHASE 2: SOFT CONTEXT (Priority Consumption)
    # ═══════════════════════════════════════════════════════════
    # Only run if we haven't found a "Smoking Gun" (Score < 2000)
    # or if we want to resolve ties.

    remaining_text = text

    for cat in PRIORITY_ORDER:
        # Get Soft Context Regex (Index 3)
        soft_ctx = CATEGORY_MAP[cat][3]

        if soft_ctx:
            # Find all matches
            matches = list(soft_ctx.finditer(remaining_text))
            if matches:
                # Score based on density (15 pts per mention)
                scores[cat] += 15 * len(matches)

                # CRITICAL: Consume text to prevent double-counting
                # e.g. FX eats "Foreign Currency" so IR doesn't match "Currency"
                remaining_text = soft_ctx.sub(" ", remaining_text)

    # ═══════════════════════════════════════════════════════════
    # PHASE 3: THRESHOLDING
    # ═══════════════════════════════════════════════════════════
    if not scores:
        return {}

    max_score = max(scores.values())

    # If we have a massive strict hit (>1000), raise threshold to kill weak noise
    threshold = 1000 if max_score >= 1000 else 45

    final_scores = {cat: s for cat, s in scores.items() if s >= threshold}
    return final_scores


def salvage_instruments(text: str, valid_instruments: Dict[str, Set[str]]) -> None:
    """Helper to salvage instruments from deadweight text if hedging context exists."""
    if find_hedging_context(text):
        strict_salvage_cats = extract_categories_strict(text)
        if strict_salvage_cats:
            instrument_keywords = extract_instrument_keywords(text)
            for cat, keywords in instrument_keywords.items():
                valid_instruments[cat].update(keywords)


def register_trackers(
    text: str,
    categories: Set[str],
    tracker: GlobalInstrumentTracker,
    local_tracker: GlobalInstrumentTracker,
) -> None:
    """Helper to register categories with trackers."""
    for cat in categories:
        tracker.register_paragraph(text, cat)
        local_tracker.register_paragraph(text, cat)


def process_confirmed_evidence(
    sent_content: str,
    clean_sent: str,
    categories: Set[str],
    year: int,
    local_tracker: GlobalInstrumentTracker,
    global_tracker: GlobalInstrumentTracker,
    local_contexts: Set[str],
    accumulated_cats: Set[str],
    strict_categories: Set[str],
    strict_counts: Dict[str, int],
    soft_counts: Dict[str, int],
    valid_instruments: Dict[str, Set[str]],
    evidence_details: List[InstrumentDetail],
) -> None:
    """Helper to process confirmed evidence (strict matches or promoted soft matches)."""
    # Capture instruments from valid evidence
    instrument_keywords = extract_instrument_keywords(clean_sent)
    for kw_cat, keywords in instrument_keywords.items():
        valid_instruments[kw_cat].update(keywords)

    for cat in categories:
        strict_categories.add(cat)
        strict_counts[cat] += 1

        details = extract_instrument_evidence(
            sent_content,
            cat,
            year,
            local_tracker=local_tracker,
            global_tracker=global_tracker,
            context_cats=local_contexts,
            accumulated_cats=accumulated_cats,
            global_cats=strict_categories,
        )
        evidence_details.extend(details)

        for d in details:
            if d.category != cat:
                strict_categories.add(d.category)
                soft_counts[d.category] += 1


# =============================================================================
# MAIN PROCESSING
# =============================================================================
def process_row(row: Tuple) -> Tuple:
    url, matches_json, cik, year = row

    try:
        paragraphs = json.loads(matches_json)
    except (json.JSONDecodeError, TypeError):
        return (url, json.dumps([]), json.dumps({}), cik, year)

    # Initialize
    strict_categories = set()
    soft_counts = defaultdict(int)
    strict_counts = defaultdict(int)
    valid_instruments = defaultdict(set)  # Track instrument keywords by category
    evidence_details: List[InstrumentDetail] = []  # Track detailed instrument evidence
    attributes: Dict[str, Any] = {
        "is_hedger": False,
        "documents_hedge_accounting": False,
        "has_aoci_activity": False,
        "manages_credit_risk": False,
        "is_historical": False,
        "is_trader": False,
    }
    mentions_venue = False
    tracker = GlobalInstrumentTracker()
    is_nst = True
    if paragraphs and paragraphs[0].startswith('{"type": "metadata"'):
        try:
            metadata_str = paragraphs.pop(0)  # Safely remove the first element
            metadata = json.loads(metadata_str)
            is_nst = metadata.get("NST", False)
            attributes["metadata"] = metadata
        except (json.JSONDecodeError, KeyError):
            pass
    # --- SINGLE PASS Processing ---
    for p in paragraphs:
        local_tracker = GlobalInstrumentTracker()
        effective_nst = is_nst
        if convertible_ir(p):
            effective_nst = True
        if not mentions_venue and TRADING_VENUE_REGEX.search(p):
            mentions_venue = True

        is_para_deadweight, para_tag_reason, para_content = parse_tags(p)
        attributes = mine_attributes(para_tag_reason, attributes)

        # --- INSTRUMENT SALVAGE: Check for strict mentions even in deadweight ---
        # Even if this paragraph is tagged as noise, if it contains strict instrument mentions
        # with hedging context, we still want to record those instruments as known.
        if is_para_deadweight:
            salvage_instruments(para_content, valid_instruments)

        # 1. PARAGRAPH PRE-SCAN (Contextual Dominance)
        # Use the scoring classifier to determine what this paragraph is ABOUT.
        context_scores = get_text_categories(
            para_content, is_nst=effective_nst
        )  # Allow full original text, while stripping convertible debt as standard debt if it is not a derivative

        # We allow multiple contexts if they are strong enough to survive get_text_categories
        local_contexts = set(context_scores.keys())
        accumulated_cats = set()

        sentences = [
            s.strip() for s in SENTENCE_SPLIT_PATTERN.split(p) if s.strip()
        ]

        for sent in sentences:
            is_sent_deadweight, sent_tag_reason, sent_content = parse_tags(sent)
            attributes = mine_attributes(sent_tag_reason, attributes)

            evidence_tags_found = EVIDENCE_TAG_PARSER.findall(sent_content)
            for etag in evidence_tags_found:
                attributes = mine_attributes(etag, attributes)

            is_active = not (is_para_deadweight or is_sent_deadweight)

            # --- SENTENCE-LEVEL INSTRUMENT SALVAGE ---
            # Even if sentence is deadweight, capture instruments if it has strict matches + hedging context
            if is_sent_deadweight:
                salvage_instruments(sent_content, valid_instruments)
            sent_content_no_evidence = EVIDENCE_TAG_PARSER.sub(" ", sent_content)
            clean_sent = _cleaner.clean(sent_content_no_evidence, effective_nst)
            clean_sent = _cleaner.clean_gen_hedges(clean_sent)

            # Update accumulated contexts with specific categories found in this sentence
            _temp_strict = extract_categories_strict(clean_sent)
            _temp_soft = extract_categories_soft(clean_sent)
            accumulated_cats.update({c for c in _temp_strict | _temp_soft if c not in ("gen", "other")})

            # -------------------------------------------------------------
            # A. Check Strict Matches (Gate 1 - Modified)
            # -------------------------------------------------------------
            strict_cats = _temp_strict

            if strict_cats:
                # 1. Always learn Definitions from Strict matches (e.g. Headers)
                register_trackers(clean_sent, strict_cats, tracker, local_tracker)

                # 2. If Verified Evidence exists, Lock it in as an ANCHOR.
                if is_active and evidence_tags_found:
                    process_confirmed_evidence(
                        sent_content,
                        clean_sent,
                        strict_cats,
                        year,
                        local_tracker,
                        tracker,
                        local_contexts,
                        accumulated_cats,
                        strict_categories,
                        strict_counts,
                        soft_counts,
                        valid_instruments,
                        evidence_details,
                    )
                    continue  # Done. We trust this sentence.

                # 3. If NO Evidence, fall through!
                # We do NOT increment strict_counts. This demotes the strict match
                # to a "Soft Candidate" which must pass the frequency threshold (3+).

            # -------------------------------------------------------------
            # Active Check (Gatekeeper for Soft Logic)
            # -------------------------------------------------------------
            if not is_active:
                continue

            # -------------------------------------------------------------
            # B. Check Unambiguous Promotion (Soft -> Strict via Strong Evidence)
            # -------------------------------------------------------------
            if has_unambiguous_evidence(sent_content):
                promoted_cats = _temp_soft.copy()
                promoted_cats.update(_temp_strict)
                if promoted_cats:
                    register_trackers(clean_sent, promoted_cats, tracker, local_tracker)
                    process_confirmed_evidence(
                        sent_content,
                        clean_sent,
                        promoted_cats,
                        year,
                        local_tracker,
                        tracker,
                        local_contexts,
                        accumulated_cats,
                        strict_categories,
                        strict_counts,
                        soft_counts,
                        valid_instruments,
                        evidence_details,
                    )
                    continue

            # -------------------------------------------------------------
            # NEW: Explicit Soft Extraction (Catching fall-through Strict)
            # -------------------------------------------------------------
            # This catches "Interest Rate Swaps" (Strict) that fell through above.
            soft_cats = _temp_soft
            if strict_cats:
                soft_cats.update(strict_cats)

            if soft_cats and soft_cats != {"gen"}:
                register_trackers(clean_sent, soft_cats, tracker, local_tracker)
                for cat in soft_cats:
                    soft_counts[cat] += 1
                continue

            # -------------------------------------------------------------
            # C. Tracker Resolution (Token Matching)
            # -------------------------------------------------------------
            tracker_cat = local_tracker.resolve_instrument(clean_sent)

            # Priority 2: Check Global Context (If Local failed/was empty)
            if not tracker_cat:
                tracker_cat = tracker.resolve_instrument(clean_sent)

            if tracker_cat:
                soft_counts[tracker_cat] += 1
                continue
            # -------------------------------------------------------------
            # D. Standard Soft Extraction with Local Resolution
            # -------------------------------------------------------------
            # (soft_cats already computed above, reused here if needed)
            found_soft = soft_cats if soft_cats else _temp_soft

            # If we found ONLY "gen" (e.g. "The instruments")
            # and we have valid local contexts, resolve to ALL of them.
            if local_contexts and "gen" in found_soft and len(found_soft) == 1:
                for ctx in local_contexts:
                    score = context_scores.get(ctx, 0)
                    if score >= 1000:
                        strict_counts[ctx] += 1
                        register_trackers(clean_sent, {ctx}, tracker, local_tracker)
                    else:
                        soft_counts[ctx] += 1
            else:
                for cat in found_soft:
                    soft_counts[cat] += 1

    # --- REMOVE OUTLIERS ---
    valid_soft_cats = remove_outlier_categories(
        strict_counts, 
        soft_counts,
    )

    final_categories = strict_categories.union(valid_soft_cats)

    if mentions_venue and not attributes["is_hedger"]:
        attributes["is_trader"] = True

    # Add valid instruments as category -> list mapping
    attributes["instruments"] = {cat: sorted(list(keywords)) for cat, keywords in valid_instruments.items()}

    # Add detailed evidence with quantitative data
    # Group evidence_details by category for easier querying
    evidence_by_category = defaultdict(list)
    for detail in evidence_details:
        evidence_by_category[detail.category].append(asdict(detail))
    attributes["evidence_details"] = dict(evidence_by_category)

    # Normalize implicit values based on context (explicit multipliers in the document)
    # Type-aware: FV uses FV multipliers, notional/value use notional multipliers
    aggregated_totals, validation_warnings = aggregate_and_normalize(evidence_details)
    attributes["aggregated_totals"] = aggregated_totals
    if validation_warnings:
        attributes["normalization_warnings"] = validation_warnings

    attributes["debug"] = {"soft_counts": soft_counts, "strict_counts": strict_counts}

    return (url, json.dumps(sorted(list(final_categories))), json.dumps(attributes), cik, year)
# =============================================================================
# DATABASE
# =============================================================================

def setup_target_db(path: str) -> None:
    """Create target database schema."""
    conn = sqlite3.connect(path)
    c = conn.cursor()
    
    c.execute(
        "CREATE TABLE IF NOT EXISTS category (url TEXT PRIMARY KEY, categories TEXT NOT NULL)"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS attributes (url TEXT PRIMARY KEY, attributes TEXT NOT NULL, FOREIGN KEY (url) REFERENCES category(url))"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS report_data (url TEXT PRIMARY KEY, cik INTEGER, year INTEGER, FOREIGN KEY (url) REFERENCES category(url))"
    )
    
    c.execute("CREATE INDEX IF NOT EXISTS url_idx ON category (url)")
    c.execute("PRAGMA journal_mode=WAL")
    conn.commit()
    conn.close()


def get_processed_urls(path: str) -> set:
    """Get URLs already processed."""
    if not Path(path).exists():
        return set()
    conn = sqlite3.connect(path)
    try:
        return {row[0] for row in conn.execute("SELECT url FROM category")}
    except:
        return set()
    finally:
        conn.close()


def data_generator(source_db: str, processed_urls: set, batch_size: int = BATCH_SIZE):
    """Stream unprocessed rows from source database."""
    conn = sqlite3.connect(source_db)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT w.url, w.matches, r.cik, r.year FROM webpage_result w LEFT JOIN report_data r ON w.url = r.url WHERE w.matches IS NOT NULL"
    )

    while True:
        rows = cursor.fetchmany(batch_size)
        if not rows:
            break
        for row in rows:
            if row[0] not in processed_urls:
                yield row

    conn.close()


def write_batch(conn, buffer: List) -> None:
    """Write batch of results to database."""
    if not buffer:
        return
    
    c = conn.cursor()
    try:
        c.execute("BEGIN TRANSACTION")
        c.executemany(
            "INSERT OR IGNORE INTO category (url, categories) VALUES (?, ?)",
            [(r[0], r[1]) for r in buffer],
        )
        c.executemany(
            "INSERT OR IGNORE INTO attributes (url, attributes) VALUES (?, ?)",
            [(r[0], r[2]) for r in buffer],
        )
        c.executemany(
            "INSERT OR IGNORE INTO report_data (url, cik, year) VALUES (?, ?, ?)",
            [(r[0], r[3], r[4]) for r in buffer],
        )
        conn.commit()
    except Exception as e:
        print(f"Write Error: {e}")
        conn.rollback()

# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    print(f"🚀 Starting Classification ({NUM_WORKERS} workers)")
    
    setup_target_db(TARGET_DB_PATH)
    processed_urls = get_processed_urls(TARGET_DB_PATH)
    print(f"📋 Found {len(processed_urls)} already processed URLs")
    
    conn = sqlite3.connect(TARGET_DB_PATH, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    
    buffer = []
    
    with ProcessPoolExecutor(max_workers=NUM_WORKERS) as executor:
        source = list(data_generator(SOURCE_DB_PATH, processed_urls))
        
        for result in tqdm(
            executor.map(process_row, source, chunksize=NUM_WORKERS),
            total=len(source),
            desc="Classifying",
        ):
            if result:
                buffer.append(result)
                if len(buffer) >= BATCH_SIZE:
                    write_batch(conn, buffer)
                    buffer = []
    
    if buffer:
        write_batch(conn, buffer)
    
    conn.close()
    print("✅ Classification complete")
