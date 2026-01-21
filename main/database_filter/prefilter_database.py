from concurrent.futures import ProcessPoolExecutor
import sqlite3
import json
import re
import multiprocessing as mp
from pathlib import Path
from typing import List, Tuple, Optional
from tqdm import tqdm

from defs.regex_lib import SENTENCE_SPLIT_PATTERN
from defs.prefiltered_lib import (
    DEADWEIGHT_TOKEN,
    SKIP_TOKEN, 
    SOPHISTICATED_CONTEXT_REGEX, 
    SOPHISTICATED_TARGETS, 
    Stage, 
    is_sophisticated_content, 
    is_sophisticated_target
)
from defs.derivative_lib import STRICT_REGEX, SOFT_REGEX, find_hedging_context
from defs.cp_regex import COMMODITY_REGEX, CP_REGEX, CP_SOFT_REGEX
from defs.eq_regex import EQ_CONTEXT_REGEX, EQ_REGEX, EQ_SOFT_REGEX, EXCLUDE_REGEX_EQUITY_COMP
from defs.gen_regex import GEN_STRICT_CONTEXT_REGEX, HEDGING_CONTEXT_REGEX
from defs.shared_context import CURRENCY_NAMES_REGEX, VALUATION_MODELS_REGEX
from defs.ir_regex import EXCLUDE_REGEX_LIBOR_TRANSITION, is_bank_list_noise
from defs.exclusion_regex import (
    EXCLUDE_REGEX_FORWARD_LOOKING,
    ENTITY_EXCLUSION_REGEX,
    ENTITY_TOKEN,
    EXCLUDE_REGEX_FILING,
    EXCLUDE_REGEX_LEGAL_LITIGATION,
    EXCLUDE_COMPETITOR_REGEX,
    EXCLUDE_NON_FINANCIAL_REGEX,
    EXCLUDE_BANKRUPTCY_REGEX,
    NON_DERIVATIVE_TREATMENT_REGEX,
    aggregate_discards,
)
from defs.acct_std import EXCLUDE_REGEX_ACCOUNTING_STD
from defs.contract import is_contractual_noise
from defs.hypo import is_hypothetical_noise
from defs.regul import is_regulatory_noise

# =============================================================================
# CONFIGURATION
# =============================================================================
NUM_WORKERS = max(1, mp.cpu_count() - 1)
BATCH_SIZE = 250
CHUNK_SIZE = 20
SOURCE_DB_PATH = "web_data.db"
TARGET_DB_PATH = "prefiltered_data.db"

# --- IMPORTS ---
from table_processor import TABLE_ANCHOR, TableToTextConverter
from defs.prefiltered_lib import NoiseReason, get_tag, QUANT_REGEX

# =============================================================================
# CURRENCY & COMMODITY COUNTING
# =============================================================================
def count_currencies_and_commodities(text: str) -> dict:
    """
    Count occurrences of currencies and commodities in text.
    
    Args:
        text: Combined text from all paragraphs
        
    Returns:
        Dictionary with structure:
        {
            "currencies": {"USD": 5, "EUR": 3, ...},
            "commodities": {"gold": 2, "oil": 1, ...},
            "currency_total": 8,
            "commodity_total": 3
        }
    """
    result = {
        "currencies": {},
        "commodities": {},
        "currency_total": 0,
        "commodity_total": 0
    }
    
    # Count currencies
    if CURRENCY_NAMES_REGEX:
        for match in CURRENCY_NAMES_REGEX.finditer(text):
            currency = match.group().upper()
            result["currencies"][currency] = result["currencies"].get(currency, 0) + 1
            result["currency_total"] += 1
    
    # Count commodities
    if COMMODITY_REGEX:
        for match in COMMODITY_REGEX.finditer(text):
            commodity = match.group().lower()
            result["commodities"][commodity] = result["commodities"].get(commodity, 0) + 1
            result["commodity_total"] += 1
    
    return result


# =============================================================================
# TABLE CLEANUP HELPERS
# =============================================================================

FOOTNOTE_PATTERN = re.compile(r"<FN>(.*?)</FN>\s*</TABLE>", re.DOTALL | re.IGNORECASE)
INDIVIDUAL_FOOTNOTE_PATTERN = re.compile(
    r"<F\s+(\d+)>\s*(.*?)(?=<F\s+\d+>|$)", re.DOTALL
)
TRADING_CONTEXT_REGEX = re.compile(r"\b(?:trad(?:e|es|ing|ed)|speculat(?:e|ion|ing|ive))\b", re.IGNORECASE)

TAG_PATTERN = re.compile(r"<[^>]+>")

def is_standard_debt(text: str) -> bool:
    """
    Returns True if a paragraph mentions sophisticated targets (convertible/warrant)
    but LACKS the necessary equity or derivative context.
    
    Logic:
    1. Check if Target exists (e.g. "convertible notes").
    2. If found, strictly require either:
       - Sophisticated Context (e.g. "embedded", "bifurcation", "derivative liability")
       - Equity Context (e.g. "common stock", "share price", "conversion option")
    3. If neither context exists, it is likely just standard debt reporting.
    """
    # Quick exit: if it doesn't mention convertibles/warrants, it's not "Standard Convertible Debt"
    if not SOPHISTICATED_TARGETS.search(text):
        return False

    # Guard 1: Sophisticated Derivative Context (Strongest Signal)
    if SOPHISTICATED_CONTEXT_REGEX.search(text):
        return False
        
    # Guard 2: Equity Context (Necessary for valid Convertibles)
    if EQ_CONTEXT_REGEX.search(text):
        return False
    
    # If we are here, we have "convertible" without "equity" or "derivative" context.
    # Result: Treat as Standard Debt (Noise).
    return bool(STRICT_REGEX.search(text) or GEN_STRICT_CONTEXT_REGEX.search(text))

def check_hard_exclusions(text: str) -> Optional[str]:
    """
    Checks text against 'Dead Weight' filters.
    Returns the discard reason string (from Enum) if matched, otherwise None.
    """

    # --- TIER 1: HIGH FREQUENCY BOILERPLATE ---
    if EXCLUDE_REGEX_FILING.search(text):
        return NoiseReason.FILING.value

    if EXCLUDE_REGEX_FORWARD_LOOKING.search(text):
        return NoiseReason.FORWARD.value
    if EXCLUDE_REGEX_LIBOR_TRANSITION.search(text):
        return NoiseReason.LIBOR.value

    # --- TIER 2: SPECIFIC TOPIC FILTERS ---
    if EXCLUDE_BANKRUPTCY_REGEX.search(text):
        return NoiseReason.BANKRUPTCY.value
    if EXCLUDE_REGEX_LEGAL_LITIGATION.search(text):
        return NoiseReason.LEGAL.value

    if EXCLUDE_NON_FINANCIAL_REGEX.search(text):
        return NoiseReason.NON_FIN.value

    if EXCLUDE_COMPETITOR_REGEX.search(text):
        return NoiseReason.COMP.value

    if NON_DERIVATIVE_TREATMENT_REGEX.search(text):
        return NoiseReason.NON_DERIV.value

    if VALUATION_MODELS_REGEX.search(text):  # To save for convertibles
        return None
    if TABLE_ANCHOR in text:
        return None

    # --- TIER 3: SCORING / DENSITY CHECKS (Heavier Ops) ---
    if is_bank_list_noise(text):
        return NoiseReason.BANK.value
    if is_regulatory_noise(text):
        return NoiseReason.REG.value
    if is_contractual_noise(text):
        return NoiseReason.CONTRACT.value
    if is_hypothetical_noise(text):
        # Return the Enum value string to match process_item check
        return NoiseReason.HYP_SCORE.value
    # Convertible debt check: Is it just standard debt issuance/mechanics or is it really a derivative
    if is_standard_debt(text):
        return NoiseReason.DEBT.value
        # Commodity check: is it refering to a derivative?
    if CP_SOFT_REGEX.search(text) and not CP_REGEX.search(text):
        if not find_hedging_context(text) and not TRADING_CONTEXT_REGEX.search(text):
            return NoiseReason.NC.value
    return None


def extract_and_separate_footnotes(table_text: str) -> Tuple[str, List[str]]:
    footnotes = []
    fn_match = FOOTNOTE_PATTERN.search(table_text)
    if fn_match:
        fn_content = fn_match.group(1)
        individual_fns = INDIVIDUAL_FOOTNOTE_PATTERN.findall(fn_content)
        for fn_num, fn_text in individual_fns:
            cleaned = fn_text.strip()
            cleaned = re.sub(r"\s+", " ", cleaned)
            if cleaned:
                footnotes.append(f"Footnote {fn_num}: {cleaned}")
        cleaned_table = FOOTNOTE_PATTERN.sub("</TABLE>", table_text)
        return cleaned_table, footnotes
    return table_text, []


def strip_table_formatting(
    table_text: str
) -> List[str]:
    text = TAG_PATTERN.sub("", table_text)
    lines = text.split("\n")
    cleaned_lines = []
    
    for line in lines:
        stripped = line.strip()
        if not stripped or all(c in "-=\t " for c in stripped):
            continue
        cleaned_lines.append(stripped)
    return cleaned_lines


# =============================================================================
# WORKER LOGIC
# =============================================================================
def process_accounting_standards_paragraph(
    paragraph: str, url: str
) -> Tuple[List[str], List[Tuple[str, str, str]]]:
    """
    Process a paragraph that contains accounting standards boilerplate.

    Logic:
    1. Keep all sentences BEFORE the first boilerplate trigger
    2. Once we hit boilerplate, only keep sentences with quantifiable amounts
    3. Also keep sentences that precede quantifiable sentences (lookahead)

    Args:
        paragraph: Full original paragraph text
        url: Document URL (for discard logging)

    Returns:
        (kept_sentences: List[str], discards: List[(url, text, reason)])
    """
    kept = []
    sentences = SENTENCE_SPLIT_PATTERN.split(paragraph)
    in_accounting_boilerplate = False

    for sent_idx, sent in enumerate(sentences):
        if not in_accounting_boilerplate:
            # Haven't hit boilerplate yet - keep all non-boilerplate sentences
            if not EXCLUDE_REGEX_ACCOUNTING_STD.search(sent):
                kept.append(sent)
            else:
                # We've entered the accounting standards zone
                in_accounting_boilerplate = True
                # Check if this sentence has quantifiable amounts
                if QUANT_REGEX.search(sent):
                    kept.append(sent)
                # else: discard it, and everything after
        else:
            # Already in boilerplate zone
            if QUANT_REGEX.search(sent):
                # Current sentence is quantifiable - keep it, or mention derivative classification for warrants, etc
                kept.append(sent)
            if SOPHISTICATED_CONTEXT_REGEX.search(sent):
                if not EXCLUDE_REGEX_ACCOUNTING_STD.search(sent):
                    kept.append(sent)
                else:
                    sent = f"{get_tag(SKIP_TOKEN, NoiseReason.ACCT_STD)} {sent}"
                    kept.append(sent)

            elif sent_idx + 1 < len(sentences):
                # Look ahead: keep this sentence if next sentence is quantifiable
                # and not another boilerplate trigger
                next_sent = sentences[sent_idx + 1]
                if QUANT_REGEX.search(
                    next_sent
                ) and not EXCLUDE_REGEX_ACCOUNTING_STD.search(next_sent):
                    kept.append(sent)

    # Process discards
    discards = []
    discarded_text = " ".join(set(sentences) - set(kept))
    if discarded_text:
        discards.append((url, discarded_text, NoiseReason.ACCT_STD.value))

    return kept, discards


def validate_sophisticated_buffer(
    sophisticated_buffer: List[str], clean_paragraphs: List[str]
) -> bool:
    """
    Independent validation for Convertibles/Warrants.
    Now uses is_sophisticated_target() and is_sophisticated_content() for consistency.

    Args:
        sophisticated_buffer: List of masked texts from sophisticated buffer
        clean_paragraphs: List of masked texts from standard buffer

    Returns:
        True if sophisticated buffer passes validation, False otherwise
    """
    if not sophisticated_buffer:
        return False

    # 1. Check for Free Pass (Gated Target in standard text)
    # Use is_sophisticated_target() to ensure equity context
    for p in clean_paragraphs:
        if EQ_REGEX.search(p) and is_sophisticated_target(p):
            return True
        if SOPHISTICATED_CONTEXT_REGEX.search(p) and EQ_SOFT_REGEX.search(p):
            return True
    return False


def process_table(
    p: str,
    url: str,
    idx: int,
    append_to_buffer,
    local_discards: List[Tuple[str, str, str]],
) -> bool:
    """
    Process a table paragraph.

    Args:
        p: Original paragraph text (with <TABLE> markup)
        url: Document URL
        idx: Paragraph index
        append_to_buffer: Function to append to clean/sophisticated buffers
        local_discards: List to accumulate discards

    Returns:
        True if table was processed (regardless of outcome)
        False if table was invalid and discarded early
    """
    try:
        cleaned_table, footnotes = extract_and_separate_footnotes(p)
    except Exception as e:
        local_discards.append((url, p[:100], "table_footnote_extraction_failed"))
        return False

    try:
        converter = TableToTextConverter(
            cleaned_table, narrative_context=" ".join(footnotes), is_sophisticated=True
        )
        sentences, should_unwrap = converter.process()
    except Exception:
        local_discards.append((url, p[:100], "table_analysis_failed"))
        return False

    if should_unwrap:
        # CASE 1: Invalid/container table (no numerical cells)
        sentences = strip_table_formatting(p)

    if not sentences:
        # Valid table but no sentences generated → Discard
        local_discards.append((url, p, "valid_table_no_sentences"))
        return False

    # Process each sentence individually through salvaging checks
    for sent in sentences:
        sent_masked = ENTITY_EXCLUSION_REGEX.sub(ENTITY_TOKEN, sent)

        # Apply hard exclusions to each sentence
        exclusion_reason = check_hard_exclusions(sent_masked)
        if exclusion_reason:
            local_discards.append((url, sent, exclusion_reason))
            continue

        # Route to appropriate buffer based on content
        if is_sophisticated_content(sent_masked):
            append_to_buffer("sophisticated", idx, sent, sent_masked)
        else:
            append_to_buffer("clean", idx, sent, sent_masked)

    # Add footnotes if present
    if footnotes:
        for fn in footnotes:
            fn_masked = ENTITY_EXCLUSION_REGEX.sub(ENTITY_TOKEN, fn)
            if is_sophisticated_content(fn_masked):
                append_to_buffer("sophisticated", idx, fn, fn_masked)
            else:
                append_to_buffer("clean", idx, fn, fn_masked)

    return True

# Regex for page artifacts (e.g., "17 <PAGE>" or "<PAGE>")
PAGE_ARTIFACT_REGEX = re.compile(r'\d*\s*<PAGE>', re.IGNORECASE)
# Regex to find the pattern: Period + Space + (ALL CAPS HEADER) + Space + (Capitalized Word not No.)
MEGA_SPLIT_REGEX = re.compile(r"(\.\s+)([A-Z][A-Z\s]+)(?=\s+(?!No\.)[A-Z][a-z])")
# Regex for table protection
TABLE_PROTECT_REGEX = re.compile(r"(<TABLE>.*?</TABLE>)", re.IGNORECASE | re.DOTALL)


def split_mega_paragraph(paragraphs: List[str]) -> List[str]:
    # For plain text paragraph extraction, sometimes the text is merged accidentally, so we have a mega chunk
    # This is usually for pre-2000 SEC filings, where headers are all caps, etc
    """
     There may be certain rules to look out for as candidates for splitting:
     1. If the candidate paragraph is too large (> 1600 chars)
     
    """
    output = []
    def split_paragraph(p: str) -> List[str]:
        # Split the current text chunk based on some rules
        output = split_paragraph_simple(p)
        output = remove_caps(output)
        output = cleanup_loose_fragments(output)
        return output
    def remove_caps(paragraphs: List[str]) -> List[str]:
        # Strip out ALL CAPS artifact headers (Good for 90% of cases, no need for perfection)
        # 1. if it is a single word, it must be at least 5 chars long so that CFTC, SFAS doesn't count
        # 2. Any other cases, we delete consecutive occureances of all caps, such as TEXT CORP. (MORE TEXT AS A HEADER); 
        # Bulleted patterns such as 1)/1. CAP HEADERS
        
        cleaned_paragraphs = []
        for p in paragraphs:
            # Remove page artifacts
            p = PAGE_ARTIFACT_REGEX.sub(' ', p)
            
            words = p.split()
            if not words:
                continue
                
            new_words = []
            caps_run = []
            
            def process_run(run):
                if not run: return []
                # Check if run should be removed
                if len(run) >= 2:
                    return [] # Remove
                elif len(run) == 1:
                    # Check length constraint
                    w = run[0]
                    if len(w) >= 5:
                        return [] # Remove
                    else:
                        return run
                return run

            for w in words:
                # Check if word is ALL CAPS (no lowercase)
                if w.isupper():
                    caps_run.append(w)
                else:
                    # End of run
                    if caps_run:
                        new_words.extend(process_run(caps_run))
                        caps_run = []
                    new_words.append(w)
            
            # Process final run
            if caps_run:
                new_words.extend(process_run(caps_run))
            
            # Reconstruct paragraph
            cleaned_p = " ".join(new_words)
            if cleaned_p.strip():
                cleaned_paragraphs.append(cleaned_p)
                
        return cleaned_paragraphs

    def cleanup_loose_fragments(paragraphs: List[str]) -> List[str]:
        # Clean up simple patterns, no need for massive rules here
        # Remove stray bullet double dash patterns --: ex: 1. --; 2. --
        output = []
        for p in paragraphs:
            p = re.sub(r"[0-9]\.\s+--", "", p)
            output.append(p)
        return output
        
    def split_paragraph_simple(p: str) -> List[str]:
        # Split the current text chunk based on some rules
        # 1. end of sentence. ALL CAPS Capitalized Word ->   support companies. PRINCIPLES OF CONSOLIDATION The accompanying
        
        # Insert a unique separator (e.g., \n\n) before the header
        p_new = MEGA_SPLIT_REGEX.sub(r"\1\n\n\2", p)
        
        
        return p_new.split("\n\n")

    for paragraph in paragraphs:
        # Split by tables first to protect them
        parts = TABLE_PROTECT_REGEX.split(paragraph)
        for part in parts:
            if not part.strip():
                continue
            
            # If it is a table, preserve it as is
            if "<TABLE>" in part.upper():
                output.append(part)
                continue

            if len(part) > 1600:
                output.extend(split_paragraph(part))
            else:
                output.append(part)
    return output

def process_item(item: Tuple) -> Optional[Tuple]:
    """
    Process a single document item through the filtering pipeline.

    Returns: (url, json_paragraphs, cik, year, discards) or None on error
    """
    try:
        url, matches_json, cik, year = item
    except (ValueError, TypeError) as e:
        print(f"❌ Error unpacking item: {e}")
        return None

    try:
        paragraphs = json.loads(matches_json)
    except (json.JSONDecodeError, TypeError) as e:
        print(f"❌ Error parsing JSON for {url}: {e}")
        return None

    # Helper function to append to both buffers atomically
    def append_to_buffer(buffer_type: str, idx: int, text_orig: str, text_masked: str):
        """Append (index, text) tuples to both original and masked buffers."""
        if buffer_type == "clean":
            clean_buffer_orig.append((idx, text_orig))
            clean_buffer_masked.append((idx, text_masked))
        elif buffer_type == "sophisticated":
            sophisticated_buffer_orig.append((idx, text_orig))
            sophisticated_buffer_masked.append((idx, text_masked))

    # Parallel buffer structure
    clean_buffer_orig = []
    clean_buffer_masked = []
    sophisticated_buffer_orig = []
    sophisticated_buffer_masked = []
    local_discards = []
    all_text_parts = []  # Track all text for metadata counting (even if discarded)
    explicit_non_derivative = False
    paragraphs = split_mega_paragraph(paragraphs)
    for idx, p in enumerate(paragraphs):
        try:
            # Track all text for metadata (before any filtering)
            # Skip metadata paragraphs from previous stages
            if not p.startswith('{"type": "metadata"'):
                all_text_parts.append(p)

            p_masked = ENTITY_EXCLUSION_REGEX.sub(ENTITY_TOKEN, p)

            # === TABLE HANDLING ===
            if "<TABLE>" in p.upper():
                process_table(p, url, idx, append_to_buffer, local_discards)
                continue
            # === ACCOUNTING STANDARDS ===
            if EXCLUDE_REGEX_ACCOUNTING_STD.search(p):
                kept, acc_std_discards = process_accounting_standards_paragraph(p, url)
                local_discards.extend(acc_std_discards)

                if kept:
                    salvaged_p = " ".join(kept)
                    salvaged_p_masked = ENTITY_EXCLUSION_REGEX.sub(
                        ENTITY_TOKEN, salvaged_p
                    )
                    buffer_type = (
                        "sophisticated"
                        if is_sophisticated_content(salvaged_p_masked)
                        else "clean"
                    )

                    append_to_buffer(buffer_type, idx, salvaged_p, salvaged_p_masked)
                continue
            # === EXCLUSIONS ===
            exclusion_reason = check_hard_exclusions(p)
            if exclusion_reason == NoiseReason.NON_DERIV.value:
                if is_sophisticated_content(p_masked):
                    explicit_non_derivative = True

            # --- HYPOTHETICAL SALVAGE LOGIC ---
            # Reasons we want to drop, UNLESS they contain specific definitions
            SALVAGEABLE_REASONS = {
                NoiseReason.HYP_SCORE.value,
                NoiseReason.CONTRACT.value,
                NoiseReason.REG.value,
                NoiseReason.BANK.value,
                NoiseReason.NC.value
            }

            if exclusion_reason in SALVAGEABLE_REASONS:
                # CHECK: Does this "Noise" actually name an instrument?
                # We use STRICT (e.g. "Interest Rate Swap") or SOFT + CONTEXT (e.g. "Hedging Contracts")
                has_instrument = STRICT_REGEX.search(p_masked) or (
                    SOFT_REGEX.search(p_masked)
                    and HEDGING_CONTEXT_REGEX.search(p_masked)
                )

                if has_instrument:
                    # SALVAGED: Keep it for context, but tag it as Deadweight.
                    # This ensures Step 2 (Non-Use Filter) ignores it for "Active" counting,
                    # but the Global Tracker (Step 4) can still read the definition.

                    # (Ensure get_tag helper is available or format string manually)
                    tag_str = get_tag(DEADWEIGHT_TOKEN, exclusion_reason)
                    p_deadweight = f"{tag_str} {Stage.PF_DB} {p}"

                    # Save to 'clean' buffer (it's legally 'clean' text, just contextually dead)
                    append_to_buffer("clean", idx, p_deadweight, p_masked)
                    continue
            elif exclusion_reason:
                local_discards.append((url, p, exclusion_reason))
                continue

            # === SALVAGE: EQUITY COMP ===
            if EXCLUDE_REGEX_EQUITY_COMP.search(p_masked):
                try:
                    sentences = SENTENCE_SPLIT_PATTERN.split(p)
                    sentences_masked = SENTENCE_SPLIT_PATTERN.split(p_masked)

                    if len(sentences) != len(sentences_masked):
                        local_discards.append(
                            (url, p, NoiseReason.EQ_COMP.value)
                        )
                        continue

                    kept_indices = []
                    for sent_idx, (sent_masked,) in enumerate(zip(sentences_masked)):
                        if (
                            STRICT_REGEX.search(sent_masked)
                            or GEN_STRICT_CONTEXT_REGEX.search(sent_masked)
                        ):
                            kept_indices.append(sent_idx)
                        elif SOFT_REGEX.search(sent_masked):
                            if (
                                HEDGING_CONTEXT_REGEX.search(sent_masked)
                                or is_sophisticated_content(sent_masked)

                            ):
                                kept_indices.append(sent_idx)

                    if kept_indices:
                        if len(kept_indices) == len(sentences):
                            # No discards, use original directly
                            append_to_buffer("clean", idx, p, p_masked)
                        else:
                            # Reconstruct from kept indices
                            salvaged_p = " ".join(sentences[i] for i in kept_indices)
                            salvaged_p_masked = " ".join(
                                sentences_masked[i] for i in kept_indices
                            )
                            buffer_type = (
                                "sophisticated" if is_sophisticated_content(salvaged_p_masked) else "clean"
                            )
                            append_to_buffer(
                                buffer_type, idx, salvaged_p, salvaged_p_masked
                            )

                            # Log discarded sentences
                            discarded_indices = set(range(len(sentences))) - set(kept_indices)
                            discarded_text = " ".join(
                                sentences[i] for i in sorted(discarded_indices)
                            )
                            local_discards.append((url, discarded_text, NoiseReason.EQ_COMP.value))
                except Exception as e:
                    local_discards.append((url, p[:100], NoiseReason.EQ_COMP.value))
                continue

            # === DISTRIBUTION ===
            is_soph_target = is_sophisticated_target(p_masked)
            is_soph_context = SOPHISTICATED_CONTEXT_REGEX.search(p_masked)
            if is_soph_target:
                append_to_buffer("sophisticated", idx, p, p_masked)
            elif is_soph_context:
                append_to_buffer("sophisticated", idx, p, p_masked)
                append_to_buffer("clean", idx, p, p_masked)
            else:
                append_to_buffer("clean", idx, p, p_masked)

        except Exception as e:
            print(f"❌ Unexpected error processing paragraph {idx} in {url}: {e}")
            local_discards.append(
                (url, str(p)[:100], f"processing_error_{type(e).__name__}")
            )
            continue

    # === FINAL GATEKEEPERS ===
    final_results = []
    is_nst = False
    try:
        # A. Validate Standard Buffer
        std_masked_texts = [text for _, text in clean_buffer_masked]
        if any(find_hedging_context(p) for p in std_masked_texts):
            final_results.extend(clean_buffer_orig)
        elif clean_buffer_orig:
            discarded = "\n\n".join([text for _, text in clean_buffer_orig])
            local_discards.append((url, discarded, NoiseReason.HEDGE_FAIL.value))
    except Exception as e:
        print(f"⚠️ Error validating standard buffer for {url}: {e}")

    try:
        # B. Validate Sophisticated Buffer
        soph_masked_texts = [text for _, text in sophisticated_buffer_masked]
        std_masked_texts = [text for _, text in clean_buffer_masked]

        if not explicit_non_derivative and validate_sophisticated_buffer(soph_masked_texts, std_masked_texts):
            final_results.extend(sophisticated_buffer_orig)
        else: 
            is_nst = True
            if sophisticated_buffer_orig:
                discarded = "\n\n".join([text for _, text in sophisticated_buffer_orig])
                local_discards.append((url, discarded, NoiseReason.NO_SOPH.value))
    except Exception as e:
        print(f"⚠️ Error validating sophisticated buffer for {url}: {e}")

    # === RECONSTRUCT & SORT ===
    try:
        # Always prepare metadata, even if final_results is empty
        # Use final_results text if available, otherwise use all collected text
        if final_results:
            text_for_counting = final_results
            is_empty = False
        elif all_text_parts:
            text_for_counting = [(0, text) for text in all_text_parts]
            is_empty = True  # Content exists but all filtered out
        else:
            # Document had no derivative content at all
            text_for_counting = []
            is_empty = True

        combined_text = " ".join([text for _, text in text_for_counting]) if text_for_counting else ""
        currency_commodity_counts = count_currencies_and_commodities(combined_text)

        # Prepend the Metadata Paragraph
        metadata = {
            "type": "metadata",
            "cik": cik,
            "year": year,
            "url": url,
            "NST": is_nst,
            "is_empty": is_empty,
            "currencies": currency_commodity_counts["currencies"],
            "commodities": currency_commodity_counts["commodities"],
            "currency_total": currency_commodity_counts["currency_total"],
            "commodity_total": currency_commodity_counts["commodity_total"]
        }

        if final_results:
            final_results.sort(key=lambda x: x[0])
            seen = set()
            unique_paragraphs = []
            unique_paragraphs.append(json.dumps(metadata))
            for _, text in final_results:
                if text not in seen:
                    unique_paragraphs.append(text)
                    seen.add(text)
            return (
                url,
                json.dumps(unique_paragraphs),
                cik,
                year,
                aggregate_discards(local_discards),
            )
        else:
            # No results, but still include metadata
            unique_paragraphs = [json.dumps(metadata)]
            return (
                url,
                json.dumps(unique_paragraphs),
                cik,
                year,
                aggregate_discards(local_discards),
            )
    except Exception as e:
        print(f"❌ Error reconstructing final results for {url}: {e}")

    # Fallback: still include metadata if there's an error
    try:
        if all_text_parts:
            combined_text = " ".join(all_text_parts)
        else:
            combined_text = ""
        currency_commodity_counts = count_currencies_and_commodities(combined_text)
        metadata = {
            "type": "metadata",
            "NST": is_nst,
            "is_empty": True,  # Fallback means filtering failed or no results
            "currencies": currency_commodity_counts["currencies"],
            "commodities": currency_commodity_counts["commodities"],
            "currency_total": currency_commodity_counts["currency_total"],
            "commodity_total": currency_commodity_counts["commodity_total"]
        }
        return (url, json.dumps([json.dumps(metadata)]), cik, year, aggregate_discards(local_discards))
    except:
        return (url, "[]", cik, year, aggregate_discards(local_discards))


# =============================================================================
# QUEUE PROCESSES
# =============================================================================
def setup_target_db(path):
    if Path(path).exists():
        # Optional: Delete if you want a fresh start, or keep to append
        # Path(path).unlink()
        pass

    conn = sqlite3.connect(path)
    c = conn.cursor()
    c.execute(
        "CREATE TABLE IF NOT EXISTS webpage_result (url TEXT PRIMARY KEY, matches TEXT NOT NULL)"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS report_data (url TEXT PRIMARY KEY, cik INTEGER, year INTEGER, FOREIGN KEY (url) REFERENCES webpage_result(url))"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS discarded_sentences (id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT, sentence TEXT, discard_reason TEXT)"
    )
    c.execute("CREATE INDEX IF NOT EXISTS url_idx ON webpage_result (url)")
    conn.commit()
    conn.close()


def get_processed_urls(path):
    if not Path(path).exists():
        return set()
    conn = sqlite3.connect(path)
    c = conn.cursor()
    try:
        c.execute("SELECT url FROM webpage_result")
        return {row[0] for row in c.fetchall()}
    except:
        return set()


def data_generator(source_db, processed_urls, batch_size=BATCH_SIZE):
    """
    Yields rows one by one. This prevents loading 250k rows into RAM.
    """
    conn = sqlite3.connect(source_db)
    c = conn.cursor()
    c.execute(
        "SELECT w.url, w.matches, r.cik, r.year FROM webpage_result w LEFT JOIN report_data r ON w.url = r.url WHERE w.matches IS NOT NULL"
    )

    while True:
        rows = c.fetchmany(batch_size)
        if not rows:
            break

        for row in rows:
            url = row[0]
            if url in processed_urls:
                continue

            # OPTIONAL: Handle empty matches early to save worker overhead
            if row[1] == "[]":
                # Yield a special flag or just process it normally (it's fast)
                yield row
            else:
                yield row

    conn.close()


def flush_buffers(conn, buffer, discards):
    if not buffer and not discards:
        return

    c = conn.cursor()
    try:
        c.execute("BEGIN TRANSACTION")
        if buffer:
            # Buffer is list of (url, matches, cik, year)
            # url = 0, matches = 1, cik = 2, year = 3
            c.executemany(
                "INSERT OR IGNORE INTO webpage_result (url, matches) VALUES (?, ?)",
                [(r[0], r[1]) for r in buffer],
            )
            c.executemany(
                "INSERT OR IGNORE INTO report_data (url, cik, year) VALUES (?, ?, ?)",
                [(r[0], r[2], r[3]) for r in buffer],
            )
        if discards:
            c.executemany(
                "INSERT INTO discarded_sentences (url, sentence, discard_reason) VALUES (?, ?, ?)",
                discards,
            )
        conn.commit()
    except Exception as e:
        print(f"❌ Write Error: {e}")
        conn.rollback()


# =============================================================================
# MAIN LOGIC
# =============================================================================

from concurrent.futures import ProcessPoolExecutor
from tqdm import tqdm

if __name__ == "__main__":
    print(f"🚀 Starting Executor-Based Prefilter ({NUM_WORKERS} workers)")

    # 1. Setup
    setup_target_db(TARGET_DB_PATH)
    processed_urls = get_processed_urls(TARGET_DB_PATH)
    print(f"📋 Found {len(processed_urls)} processed URLs.")

    # 2. Connect Writer DB (Main Thread Only)
    target_conn = sqlite3.connect(TARGET_DB_PATH, timeout=60)
    target_conn.execute("PRAGMA journal_mode=WAL")
    target_conn.execute("PRAGMA synchronous=NORMAL")

    # 3. Processing Loop
    buffer = []
    discards_buffer = []
    count = 0

    with ProcessPoolExecutor(max_workers=NUM_WORKERS) as executor:
        # Create iterator (does not load all to RAM)
        source_iter = list(data_generator(SOURCE_DB_PATH, processed_urls))
        total_items = len(source_iter)

        # executor.map yields results in order
        results_iter = executor.map(process_item, source_iter, chunksize=CHUNK_SIZE)

        # Wrap in tqdm with total
        for result in tqdm(results_iter, desc="Processing", total=total_items):
            if not result:
                continue

            url, matches, cik, year, discards = result
            buffer.append((url, matches, cik, year))
            if discards:
                discards_buffer.extend(discards)

            if len(buffer) >= BATCH_SIZE:
                flush_buffers(target_conn, buffer, discards_buffer)
                buffer = []
                discards_buffer = []

            count += 1

    # 4. Final Flush
    if buffer or discards_buffer:
        flush_buffers(target_conn, buffer, discards_buffer)

    target_conn.close()
    print(f"✅ Complete. Processed {count} documents.")
