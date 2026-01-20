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
from defs.cp_regex import TRADING_VENUE_REGEX
from defs.gen_regex import GEN_REGEX, GEN_STRICT_CONTEXT_REGEX, HEDGING_CONTEXT_REGEX, NOTIONAL_REGEX, PRECISE_LOOSE_GEN_REGEX
from defs.derivative_lib import CATEGORY_MAP, find_hedging_context, GLUE_MAP
from defs.derivatives_core import BASE_REGEX, PRECISE_BASE_REGEX
from defs.shared_context import CURRENCY_NAMES_REGEX, all_currencies
from prefilter_tagging import extract_values_and_years
from table_processor import TABLE_ANCHOR
from defs.prefiltered_lib import DEADWEIGHT_TOKEN, SKIP_TOKEN, MinimalTextCleaner, NoiseReason, EvidenceReason, convertible_ir, is_sophisticated_content, is_sophisticated_target
from defs.ir_regex import IR_DO_NOT_MITIGATE_REGEX
from defs.fx_regex import FX_DO_NOT_MITIGATE_REGEX
from defs.cp_regex import CP_DO_NOT_MITIGATE_REGEX, COMMODITY_REGEX
from defs.eq_regex import EQ_DO_NOT_MITIGATE_REGEX
from defs.cr_regex import CR_DO_NOT_MITIGATE_REGEX
from defs.verb_regex import STRICT_DO_NOT_MITIGATE_REGEX

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
METADATA_TAG_PARSER = re.compile(r"_M<([^>]+)>")

# Evidence that overrides Global Exclusions (Safeguard)
# We use ONLY the Strict (Year-Anchored) evidence here.
# If a firm says "We do not use derivatives", we respect that unless we see a specific DATED transaction/position.
SAFEGUARD_EVIDENCE = {
    # active state for the current year
    EvidenceReason.AS_YEAR.value,
    EvidenceReason.MAT_FUT.value,
    EvidenceReason.MAT_FUT_NV.value,
    EvidenceReason.MAT_FUT_FV.value,
    EvidenceReason.MAT_FUT_V.value,
    EvidenceReason.NVY.value,
    EvidenceReason.FVY.value,
    EvidenceReason.VY.value,
    EvidenceReason.ACT_YEAR.value,
    # IR swap of a different paragraph is a different transaction (provided it survived)
    # even if one of them is terminated, they plainly state they have potential usage, or no swaps for a different subsidiary.
    EvidenceReason.ACT_NV_YEAR.value, 
    EvidenceReason.ACT_FV_YEAR.value,
    EvidenceReason.ACT_V_YEAR.value,
}

# Evidence that promotes Soft matches to Strict (Unambiguous)
# This includes No-Year values because they are strong indicators of type if not excluded.
UNAMBIGUOUS_EVIDENCE = SAFEGUARD_EVIDENCE | {
    EvidenceReason.NVNY.value,
    EvidenceReason.FVNY.value,
    EvidenceReason.VNY.value,
    EvidenceReason.CONT_USE.value,
    EvidenceReason.BS_LOC.value,
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

    def resolve_instrument(self, sentence: str, context_scores: Optional[Dict[str, int]] = None) -> Optional[str]:
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

        if not candidates:
            return None

        if len(candidates) == 1:
            return list(candidates)[0]

        # Disambiguate using context scores if available
        if context_scores:
            # Find candidate with highest context score
            best_cat = max(candidates, key=lambda c: context_scores.get(c, 0))
            if context_scores.get(best_cat, 0) > 0:
                return best_cat

        return None

class GlobalExclusionTracker:
    """Tracks categories and commodities that the firm explicitly states it does NOT hedge."""
    def __init__(self):
        self.excluded_categories = set()
        self.excluded_commodities = set()
        self.negated_instruments = defaultdict(set)

    def add_exclusion(self, text: str, reason: Optional[str] = None):
        # Check categories
        if IR_DO_NOT_MITIGATE_REGEX.search(text):
            self.excluded_categories.add("ir")
        if FX_DO_NOT_MITIGATE_REGEX.search(text):
            self.excluded_categories.add("fx")
        if EQ_DO_NOT_MITIGATE_REGEX.search(text):
            self.excluded_categories.add("eq")
        if CR_DO_NOT_MITIGATE_REGEX.search(text):
            self.excluded_categories.add("cr")
        
        # Check CP and extract commodities
        # Use finditer to scope commodity extraction to the negation phrase only
        # This prevents "Unlike corn, we do not hedge wheat" from banning corn.
        for match in CP_DO_NOT_MITIGATE_REGEX.finditer(text):
            match_text = match.group(0)
            commodities = COMMODITY_REGEX.findall(match_text)
            
            generics = [c for c in commodities if c.lower() in ("commodity", "commodities")]
            specifics = [c for c in commodities if c.lower() not in ("commodity", "commodities")]
            
            if specifics:
                for c in specifics:
                    self.excluded_commodities.add(c.lower())
            
            if generics and not specifics:
                self.excluded_categories.add("cp")
            elif not commodities:
                self.excluded_categories.add("cp")

        # Check NEG logic (Specific Instrument Negation) - The "Exclusion Killers"
        # These signals create a global presumption of non-use for the mentioned instruments.
        if reason in (NoiseReason.NEG.value, NoiseReason.POT.value, NoiseReason.TERM.value, NoiseReason.ZERO.value):
            for cat, (strict_inst, soft_inst, _, _, weak_inst, _) in CATEGORY_MAP.items():
                # Check all instrument patterns to capture what is being negated
                for pat in [strict_inst, soft_inst, weak_inst]:
                    if pat:
                        for m in pat.finditer(text):
                            self.negated_instruments[cat].add(m.group(0).lower())

    def is_excluded(self, category: str, text_match: str = "", match_type: str = "strict") -> Tuple[bool, bool]:
        """Returns (is_excluded, is_blocked)."""
        # 1. Global category exclusion (downgrade)
        if category in self.excluded_categories:
            return True, False

        # 2. Specific Commodity Block
        if category == "cp" and text_match:
            text_lower = text_match.lower()
            for comm in self.excluded_commodities:
                if comm in text_lower:
                    return True, True
        
        # 3. Specific Instrument Negation
        if text_match:
            text_lower = text_match.lower()
            if text_lower in self.negated_instruments[category]:
                return True, True
            
            if match_type == "weak":
                for neg_inst in self.negated_instruments[category]:
                    if "derivative" in neg_inst:
                        return True, True

        return False, False

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


def extract_instrument_keywords(sentence: str, target_categories: Optional[Set[str]] = None) -> Dict[str, Set[str]]:
    """
    Extract actual matched instrument text from category regexes.
    Returns a dict mapping category -> set of matched instrument keywords.
    
    Only captures matches from the category regexes (strict_inst, soft_inst).
    Used ONLY for valid evidence cases to avoid noise.
    
    Args:
        sentence: The text to scan.
        target_categories: Optional set of categories to restrict scanning to.
    """
    instruments = defaultdict(set)

    cats_to_scan = target_categories if target_categories is not None else CATEGORY_MAP.keys()

    for cat in cats_to_scan:
        if cat not in CATEGORY_MAP:
            continue
        strict_inst, soft_inst, _, _, weak_inst, _ = CATEGORY_MAP[cat]
        # Try strict instrument first (higher confidence)
        if strict_inst:
            for match in strict_inst.finditer(sentence):
                instruments[cat].add(match.group(0).strip())

        # Then soft instrument (if no strict found)
        if soft_inst and cat not in instruments:
            for match in soft_inst.finditer(sentence):
                instruments[cat].add(match.group(0).strip())

        # Then weak instrument (if no strict/soft found)
        if weak_inst and cat not in instruments:
            for match in weak_inst.finditer(sentence):
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
    context_scores: Optional[Dict[str, int]] = None,
    accumulated_cats: Optional[Set[str]] = None,
    global_cats: Optional[Set[str]] = None,
    sent_scores: Optional[Dict[str, int]] = None,
    exclusion_tracker: Optional[GlobalExclusionTracker] = None,
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
        
        # 1. Sentence Level (New)
        if sent_scores:
            specific_sent = {k: v for k, v in sent_scores.items() if k not in ("gen", "other")}
            if specific_sent:
                resolved = max(specific_sent, key=specific_sent.get) # type: ignore

        # 2. Local Tracker
        if not resolved and local_tracker:
            resolved = local_tracker.resolve_instrument(sentence, context_scores)

        # 3. Accumulated Context (if exactly one)
        if not resolved and accumulated_cats and len(accumulated_cats) == 1:
            resolved = list(accumulated_cats)[0]

        # 4. Paragraph Context (Score based)
        if not resolved and context_scores:
            resolved = max(context_scores, key=context_scores.get) # type: ignore

        # 5. Global Tracker
        if not resolved and global_tracker:
            resolved = global_tracker.resolve_instrument(sentence, context_scores)

        # 6. Global Context (if exactly one strict category exists globally)
        if not resolved and global_cats and len(global_cats) == 1:
            resolved = list(global_cats)[0]

        if resolved:
            target_category = resolved

    # Check Global Exclusion for the Category
    if exclusion_tracker:
        is_excl, is_block = exclusion_tracker.is_excluded(target_category)
        if is_block:
            return []

    # 1. Determine Accounting Context from Evidence Tags (Primary)
    evidence_tags = set(EVIDENCE_TAG_PARSER.findall(sentence))
    val_type = "value"

    fv_tags = {
        EvidenceReason.FVY.value,  # Fair Value was $X at Year
        EvidenceReason.FVNY.value,  # Fair Value is $X
        EvidenceReason.ACT_FV_YEAR.value,
        EvidenceReason.FVAIY.value,  # Fair Value at inception was $X
        EvidenceReason.FVAINY.value,  # Fair Value at inception is $X
        EvidenceReason.MAT_FUT_FV.value,
    }
    notional_tags = {
        EvidenceReason.NVY.value,  # Notional was $X at Year
        EvidenceReason.NVNY.value,  # Notional is $X
        EvidenceReason.ACT_NV_YEAR.value,
        EvidenceReason.MAT_FUT_NV.value,
    }
    value_tags = {
        EvidenceReason.VY.value,  # Value was $X at Year
        EvidenceReason.VNY.value,  # Value is $X
        EvidenceReason.ACT_V_YEAR.value,
        EvidenceReason.MAT_FUT_V.value,
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
    inst_keywords = extract_instrument_keywords(sentence, target_categories={target_category})
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

    # Filter specific instruments against exclusion tracker
    if exclusion_tracker:
        filtered_names = []
        for name in instrument_names:
            is_excl, is_block = exclusion_tracker.is_excluded(target_category, name, match_type="strict")
            if not is_block:
                filtered_names.append(name)
        instrument_names = filtered_names

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
    strict_counts: Dict[str, float],  # Changed from Set[str] to Dict[str, int]
    soft_counts: Dict[str, float],
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
CONJ = re.compile(r"\b(?:and|or)\b", re.IGNORECASE)
FULL_CONJ = re.compile(r"[,;]|\b(?:and|or)\b", re.IGNORECASE)
WHITESPACE = re.compile(r"\s+", re.IGNORECASE)
def get_text_categories(text: str, is_nst: bool, exclusion_tracker: Optional[GlobalExclusionTracker] = None) -> Dict[str, int]:
    """
    Determines category using Weighted Scoring and Map Iteration.

    Phases:
    1. Strict Check (Instrument + Context): High Score (Bypass).
    2. Soft Check (Context Density): Low Score (Requires volume).
       - Uses Priority Consumption (FX eats 'Currency' before IR sees it).
    Returns a dictionary of {category: score} for categories meeting the threshold.
    """
    scores = defaultdict(int)
    notional_multiplier = NOTIONAL_REGEX.search(text)
    sent_count = len(SENTENCE_SPLIT_PATTERN.split(text))
    
    # Check for conjunctions for chained instrument logic
    has_conjunction = bool(CONJ.search(text))

    # Special Handling for Equity -> Warrants (Moved to top)
    if is_sophisticated_content(text) and not is_nst:
        scores["warr"] += 6000
        text = _cleaner.clean_soph_targets(text)
    
    def check_exclusion(cat, text_match, match_type):
        if exclusion_tracker:
            return exclusion_tracker.is_excluded(cat, text_match, match_type)
        return False, False

    # ═══════════════════════════════════════════════════════════
    # PHASE 1: STRICT SIGNALS (Non-Destructive)
    # ═══════════════════════════════════════════════════════════
    # We check Strict Instruments (Index 0) and Strict Context (Index 2)

    for cat, (strict_inst, soft_inst, strict_ctx, _, weak_inst, risk_mgmt) in CATEGORY_MAP.items():
        cat_blocked = False
        inst_score = 0

        # A. Strict Instrument ("Interest Rate Swap")
        if strict_inst:
            matches = list(strict_inst.finditer(text))
            
            # --- Chained Instrument Logic ---
            if not matches and has_conjunction:
                # Attempt to reconstruct chained instruments
                # 1. Remove conjunctions and commas
                temp_text = FULL_CONJ.sub(" ", text)
                
                # 2. Remove glue from other categories
                for other_cat, glue_regex in GLUE_MAP.items():
                    if other_cat == cat:
                        continue
                    temp_text = glue_regex.sub(" ", temp_text)
                
                # 3. Normalize spaces and check strict_inst
                temp_text = WHITESPACE.sub(" ", temp_text).strip()
                matches = list(strict_inst.finditer(temp_text))
            
            if matches:
                # Check exclusions for each match
                for m in matches:
                    is_excl, is_block = check_exclusion(cat, m.group(0), "strict")
                    
                    if is_block:
                        scores['gen'] = -1
                        cat_blocked = True
                        continue # Blocked completely (Score 0 contribution)
                    
                    score = 60 if is_excl else 2000
                    inst_score = max(inst_score, score)

        # B. Soft Instrument (if no strict score yet)
        if inst_score == 0 and not cat_blocked and soft_inst:
            match = soft_inst.search(text)
            if match:
                match_text = match.group(0)
                is_excl, is_block = check_exclusion(cat, match_text, "soft")
                
                if is_block:
                    scores['gen'] = -1
                    cat_blocked = True
                else:
                    base = 2000 if notional_multiplier else 500
                    if is_excl:
                        base = 60 if notional_multiplier else 15
                    inst_score = max(inst_score, base)

        # C. Weak Instrument (if no strict/soft score yet)
        if inst_score == 0 and not cat_blocked and weak_inst:
            match = weak_inst.search(text)
            if match:
                match_text = match.group(0)
                is_excl, is_block = check_exclusion(cat, match_text, "weak")
            
                if is_block:
                    scores['gen'] = -1
                    cat_blocked = True
                else:
                    base = 200
                    if sent_count == 1 or notional_multiplier:
                        base = 6000
                    if is_excl:
                        base = 15
                    inst_score = max(inst_score, base)
        
        scores[cat] += inst_score

        if cat_blocked:
            continue

        # D. Risk Management ("Hedging of Interest Rate Risk")
        ctx_score = 0
        if risk_mgmt and risk_mgmt.search(text):
            is_excl, _ = check_exclusion(cat, "", "strict")
            ctx_score = max(ctx_score, 60 if is_excl else 2000)

        # E. Strict Context ("Interest Rate Risk")
        elif strict_ctx and strict_ctx.search(text):
            is_excl, _ = check_exclusion(cat, "", "strict")
            ctx_score = max(ctx_score, 60 if is_excl else 800)
        
        scores[cat] += ctx_score

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
    threshold = 800 if max_score >= 1000 else 45

    final_scores = {cat: s for cat, s in scores.items() if s >= threshold}
    return final_scores


def derive_strict_categories(scores: Dict[str, int], text: str) -> Set[str]:
    """Derive strict categories from scores and text checks, updating scores for 'warr'."""
    strict_cats = {c for c, s in scores.items() if s >= 2000}
    if is_sophisticated_target(text):
        strict_cats.add("warr")
        scores["warr"] = max(scores.get("warr", 0), 2000)
    return strict_cats


def salvage_instruments(text: str, valid_instruments: Dict[str, Set[str]], is_nst: bool = True, exclusion_tracker: Optional[GlobalExclusionTracker] = None) -> None:
    """Helper to salvage instruments from deadweight text if hedging context exists."""
    if find_hedging_context(text):
        clean_text = _cleaner.clean(text, is_nst=is_nst)
        clean_text = _cleaner.clean_gen_hedges(clean_text)
        scores = get_text_categories(clean_text, is_nst=is_nst, exclusion_tracker=exclusion_tracker)
        strict_salvage_cats = derive_strict_categories(scores, clean_text)

        if strict_salvage_cats:
            instrument_keywords = extract_instrument_keywords(clean_text, target_categories=strict_salvage_cats)
            for cat, keywords in instrument_keywords.items():
                if cat in strict_salvage_cats:
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
    context_scores: Dict[str, int],
    accumulated_cats: Set[str],
    strict_categories: Set[str],
    strict_counts: Dict[str, float],
    soft_counts: Dict[str, float],
    valid_instruments: Dict[str, Set[str]],
    evidence_details: List[InstrumentDetail],
    sent_scores: Optional[Dict[str, int]] = None,
    exclusion_tracker: Optional[GlobalExclusionTracker] = None,
) -> None:
    """Helper to process confirmed evidence (strict matches or promoted soft matches)."""
    # Capture instruments from valid evidence
    instrument_keywords = extract_instrument_keywords(clean_sent, target_categories=categories)
    for kw_cat, keywords in instrument_keywords.items():
        valid_instruments[kw_cat].update(keywords)

    for cat in categories:
        if exclusion_tracker:
            is_excl, is_block = exclusion_tracker.is_excluded(cat)
            if is_block:
                continue
        strict_categories.add(cat)
        strict_counts[cat] += 1

        details = extract_instrument_evidence(
            sent_content,
            cat,
            year,
            local_tracker=local_tracker,
            global_tracker=global_tracker,
            context_scores=context_scores,
            accumulated_cats=accumulated_cats,
            global_cats=strict_categories,
            sent_scores=sent_scores,
            exclusion_tracker=exclusion_tracker,
        )
        evidence_details.extend(details)

        for d in details:
            if d.category != cat:
                if context_scores.get(d.category, 0) >= 2000:
                    strict_counts[d.category] += 1
                    strict_categories.add(d.category)
                else:
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
    soft_counts = defaultdict(float)
    strict_counts = defaultdict(float)
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
    
    # --- PRE-PASS: Build Exclusion Tracker ---
    exclusion_tracker = GlobalExclusionTracker()
    for p in paragraphs:
        # Quick scan for NO_HEDGE tags in the raw paragraph text
        # We split by sentence to ensure we catch tags applied at sentence level
        sentences = [s.strip() for s in SENTENCE_SPLIT_PATTERN.split(p) if s.strip()]
        for sent in sentences:
            _, tag_reason, sent_content = parse_tags(sent)
            if tag_reason in (NoiseReason.NO_HEDGE.value, NoiseReason.NEG.value, NoiseReason.POT.value):
                exclusion_tracker.add_exclusion(sent_content, tag_reason)

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
            salvage_instruments(para_content, valid_instruments, is_nst=effective_nst, exclusion_tracker=exclusion_tracker)

        # 1. PARAGRAPH PRE-SCAN (Contextual Dominance)
        # Use the scoring classifier to determine what this paragraph is ABOUT.
        context_scores = get_text_categories(
            para_content, is_nst=effective_nst, exclusion_tracker=exclusion_tracker
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
            
            # Extract Metadata Tags (Debug info)
            meta_tags_found = METADATA_TAG_PARSER.findall(sent_content)
            if meta_tags_found:
                if "debug_events" not in attributes:
                    attributes["debug_events"] = []
                attributes["debug_events"].extend(meta_tags_found)

            is_active = not (is_para_deadweight or is_sent_deadweight)

            # --- SENTENCE-LEVEL INSTRUMENT SALVAGE ---
            # Even if sentence is deadweight, capture instruments if it has strict matches + hedging context
            if is_sent_deadweight:
                salvage_instruments(sent_content, valid_instruments, is_nst=effective_nst, exclusion_tracker=exclusion_tracker)
            sent_content_no_evidence = EVIDENCE_TAG_PARSER.sub(" ", sent_content)
            sent_content_no_meta = METADATA_TAG_PARSER.sub(" ", sent_content_no_evidence)
            clean_sent = _cleaner.clean(sent_content_no_meta, effective_nst)
            clean_sent = _cleaner.clean_gen_hedges(clean_sent)
            
            # Check for Safeguard Evidence (Overrides Exclusions)
            evidence_tags_set = {tag for tag in evidence_tags_found}
            is_safeguarded = not evidence_tags_set.isdisjoint(SAFEGUARD_EVIDENCE)
            
            # If safeguarded, disable exclusion tracker for this sentence
            current_exclusion_tracker = None if is_safeguarded else exclusion_tracker

            sent_scores = get_text_categories(clean_sent, is_nst=effective_nst, exclusion_tracker=current_exclusion_tracker)

            # Handle explicit block signal
            explicit_block = sent_scores.get('gen', 0) == -1
            if explicit_block:
                if 'gen' in sent_scores:
                    del sent_scores['gen']

            # Derive Strict Categories (Score >= 2000)
            strict_cats = derive_strict_categories(sent_scores, clean_sent)

            # Table Anchor Fallback (Promote soft matches if in table)
            if not strict_cats and TABLE_ANCHOR in clean_sent:
                strict_cats.update({c for c, s in sent_scores.items() if s >= 500})
                if CURRENCY_NAMES_REGEX.search(clean_sent):
                    strict_cats.add("fx")

            # Derive Soft Categories
            soft_cats = set(sent_scores.keys())
            if not soft_cats and not explicit_block:
                if GEN_REGEX.search(clean_sent) or GEN_STRICT_CONTEXT_REGEX.search(clean_sent):
                    soft_cats.add("gen")
                elif PRECISE_LOOSE_GEN_REGEX.search(clean_sent) and HEDGING_CONTEXT_REGEX.search(clean_sent):
                    soft_cats.add("gen")

            accumulated_cats.update({c for c in soft_cats if c not in ("gen", "other")})

            # -------------------------------------------------------------
            # A. Check Strict Matches (Gate 1 - Modified)
            # -------------------------------------------------------------

            if strict_cats:
                # 1. Always learn Definitions from Strict matches (e.g. Headers)
                register_trackers(clean_sent, strict_cats, tracker, local_tracker)

            # -------------------------------------------------------------
            # Active Check (Gatekeeper for Soft Logic)
            # -------------------------------------------------------------
            if not is_active:
                continue

            # -------------------------------------------------------------
            # B. Check Unambiguous Promotion (Soft -> Strict via Strong Evidence)
            # -------------------------------------------------------------
            if has_unambiguous_evidence(sent_content):
                # Prioritize strict categories if available; otherwise promote soft categories
                target_cats = strict_cats if strict_cats else soft_cats

                if target_cats:
                    # If promoting soft categories, register them now (strict already registered)
                    if not strict_cats:
                        register_trackers(clean_sent, target_cats, tracker, local_tracker)

                    process_confirmed_evidence(
                        sent_content,
                        clean_sent,
                        target_cats,
                        year,
                        local_tracker,
                        tracker,
                        context_scores,
                        accumulated_cats,
                        strict_categories,
                        strict_counts,
                        soft_counts,
                        valid_instruments,
                        evidence_details,
                        sent_scores=sent_scores,
                        exclusion_tracker=current_exclusion_tracker,
                    )
                    continue

            # -------------------------------------------------------------
            # NEW: Explicit Soft Extraction (Catching fall-through Strict)
            # -------------------------------------------------------------
            # This catches "Interest Rate Swaps" (Strict) that fell through above.

            if soft_cats and soft_cats != {"gen"}:
                register_trackers(clean_sent, soft_cats, tracker, local_tracker)
                for cat in soft_cats:
                    if context_scores.get(cat, 0) >= 2000:
                        soft_counts[cat] += 1.0
                    else:
                        soft_counts[cat] += 0.5
                continue

            # -------------------------------------------------------------
            # C. Tracker Resolution (Token Matching)
            # -------------------------------------------------------------
            tracker_cat = local_tracker.resolve_instrument(clean_sent, context_scores)

            # Priority 2: Check Global Context (If Local failed/was empty)
            if not tracker_cat:
                tracker_cat = tracker.resolve_instrument(clean_sent, context_scores)

            if tracker_cat:
                if context_scores.get(tracker_cat, 0) >= 2000:
                    soft_counts[tracker_cat] += 1.0
                else:
                    soft_counts[tracker_cat] += 0.5
                continue
            # -------------------------------------------------------------
            # D. Standard Soft Extraction with Local Resolution
            # -------------------------------------------------------------
            # (soft_cats already computed above, reused here if needed)
            found_soft = soft_cats

            # If we found ONLY "gen" (e.g. "The instruments")
            # and we have valid local contexts, resolve to ALL of them.
            if local_contexts and "gen" in found_soft and len(found_soft) == 1:
                for ctx in local_contexts:
                    score = context_scores.get(ctx, 0)
                    if score >= 2000:
                        soft_counts[ctx] += 1.0
                        register_trackers(clean_sent, {ctx}, tracker, local_tracker)
                    else:
                        soft_counts[ctx] += 0.5
            else:
                for cat in found_soft:
                    if context_scores.get(cat, 0) >= 2000:
                        soft_counts[cat] += 1.0
                    else:
                        soft_counts[cat] += 0.5

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
