import random
import re
from typing import Literal, Optional

# --- NEW: Global cache for currencies to avoid circular import overhead ---
_ALL_CURRENCIES = None


def _format_single_notional(
    amount: int | float,
    symbol: str,  # The currency symbol or unit, e.g., '$' or 'barrels'
    prefer_abbreviated: bool,
    no_unit_word: bool = False,  # Suppresses "million/billion/etc."
    zero_format: Literal["nil", "zero", "amount"] = "amount",
    negative_format: int = 1,  # default = 1 → (num) unit [-1, 0, 1, 2]
    notional_multiplier: Optional[int] = None, # NEW: Explicit multiplier
) -> str:
    """
    Formats a single notional amount into a readable string like '$250.0 million' or '250.0 thousand barrels'.

    - If no_unit_word=True, abbreviates numerically but omits the unit word (e.g., '$250.0' instead of '$250.0 million').
    - If notional_multiplier is provided, it will be used for scaling the amount, 
      otherwise the function determines the best unit (million, billion) automatically.
    - If prefer_abbreviated=False, shows full number with commas.
    - negative_format:
        -1 → accounting style, e.g. '($250.0 million)' or '(2.5 million barrels)'
         0 → minus sign, e.g. '-$250.0 million' or '-2.5 million barrels'
         1 → parentheses only around the number, e.g. '$(2.5) million' or '(2.5) million barrels'
         2 → minus sign after currency symbol, e.g. '$-250.0 million' (currency only)
    """
    # --- NEW: Lazy load currencies to prevent circular import issues ---
    global _ALL_CURRENCIES
    if _ALL_CURRENCIES is None:
        from defs.fx_data import all_currencies
        _ALL_CURRENCIES = all_currencies

    # Find the currency object to determine its formatting rules
    currency_obj = next((c for c in _ALL_CURRENCIES if c.symbol == symbol or c.code == symbol), None)
    is_currency = currency_obj is not None
    symbol_first = currency_obj.symbol_first if currency_obj else True
    if amount == 0:
        if zero_format in ["nil", "zero"]:
            return zero_format

    is_negative = amount < 0
    abs_amount = abs(amount)

    amount_to_string = {
        "trillion": 1_000_000_000_000,
        "billion": 1_000_000_000,
        "million": 1_000_000,
        "thousand": 1_000,
    }

    formatted_number = None
    unit_word = ""

    if prefer_abbreviated:
        # --- NEW: Use explicit multiplier if provided ---
        if notional_multiplier and notional_multiplier > 1:
            formatted_number = f"{abs_amount / notional_multiplier:.1f}"
            if not no_unit_word:
                # Find the word for the given multiplier
                for word, val in amount_to_string.items():
                    if val == notional_multiplier:
                        unit_word = f" {word}"
                        break
        else: # Original auto-detection logic
            for word, divisor in sorted(
                amount_to_string.items(), key=lambda x: x[1], reverse=True
            ):
                if abs_amount >= divisor:
                    formatted_number = f"{abs_amount / divisor:.1f}"
                    if not no_unit_word:
                        unit_word = f" {word}"
                    break

    if formatted_number is None:
        formatted_number = f"{abs_amount:,.0f}"

    # Build base string
    # --- NEW: Check if the symbol is an ISO code (e.g., USD) to add a space ---
    is_iso_code = is_currency and len(symbol) == 3 and symbol.isupper()

    if is_currency and symbol_first:
        space = " " if is_iso_code else ""
        base = f"{symbol}{space}{formatted_number}{unit_word}"
    else:
        base = f"{formatted_number}{unit_word} {symbol}".strip()

    # Apply negative formatting
    if is_negative:
        if negative_format == -1:
            return f"({base})"
        elif negative_format == 0:
            return f"-{base}"
        elif negative_format == 1:
            if is_currency and symbol_first:
                space = " " if is_iso_code else ""
                return f"{symbol}{space}({formatted_number}){unit_word}"
            else:
                return f"({formatted_number}){unit_word} {symbol}".strip()
        elif negative_format == 2:
            if is_currency and symbol_first:
                space = " " if is_iso_code else ""
                return f"{symbol}-{space}{formatted_number}{unit_word}"
            else:
                return f"-{base}"  # Fallback to format 0 for non-currencies
        else:
            raise ValueError("negative_format must be -1, 0, 1, or 2")

    return base

def _get_correct_rounding(amount: Optional[int | float], multiplier: int) -> Optional[int]:
    """
    Rounds an amount to the nearest significant figure based on the multiplier,
    matching the .1f formatting used for abbreviated numbers.
    For example, with a multiplier of 1,000,000, 1,234,567 becomes 1,200,000.
    """
    if not amount:
        return None
    if multiplier <= 1:
        return round(amount)

    # Round to one decimal place relative to the multiplier's scale.
    return int(round(amount / multiplier, 1) * multiplier)


# --- Precompiled regex patterns ---
CLAUSE_SPACE_PATTERN = re.compile(r"([a-zA-Z0-9,])(\{[^}]+\})")
PLACEHOLDER_PATTERN = re.compile(r"\{[^}]*\}")
MULTISPACE_PATTERN = re.compile(r"\s{2,}")
LEADING_COMMA_PATTERN = re.compile(r"^\s*,\s*")
PLURALIZE_PATTERN = re.compile(r"([^aeiou])ys\b", flags=re.IGNORECASE)
CAPITALIZE_PATTERN = re.compile(r"(\w*)([.!?]\s+)([a-z])")
ARTICLE_PATTERN = re.compile(r"(__article__|a|an)\s+(\w+)", re.IGNORECASE)

# Abbreviations for capitalization logic
ABBREVIATIONS = [
    "Inc",
    "Corp",
    "Ltd",
    "Co",
    "LLC",
    "et al",
    "e.g",
    "i.e",
    "etc",
    "vs",
    "Mr",
    "Mrs",
    "Ms",
    "Dr",
    "Sr",
    "Jr",
    "No",
]
ABBREVIATIONS_PATTERN = r"\b(" + "|".join(re.escape(ab) for ab in ABBREVIATIONS) + r")"


def _cleanup_sentence(sentence: str) -> str:
    """Clean up sentence by removing placeholders, fixing spacing, and capitalizing properly."""

    # Add a space before a clause if the preceding character is not a space, comma, or newline
    sentence = CLAUSE_SPACE_PATTERN.sub(r"\1 \2", sentence)

    # Remove ALL placeholders of the form {something}
    sentence = PLACEHOLDER_PATTERN.sub("", sentence)

    # Clean up multiple spaces
    sentence = MULTISPACE_PATTERN.sub(" ", sentence)

    # Remove leading commas/spaces
    sentence = LEADING_COMMA_PATTERN.sub("", sentence)

    # Fix common punctuation issues
    sentence = sentence.replace(" ,", ",").replace(",,", ",")
    sentence = sentence.replace(" .", ".").replace(", .", ".")

    # Correct pluralization (company -> companies, but not always/employs)
    sentence = PLURALIZE_PATTERN.sub(r"\1ies", sentence)

    if sentence:

        def capitalize_after_period(match):
            word_before_period = match.group(1)
            if word_before_period and re.fullmatch(
                ABBREVIATIONS_PATTERN, word_before_period, re.IGNORECASE
            ):
                return match.group(0)  # abbreviation, leave as-is
            return match.group(1) + match.group(2) + match.group(3).upper()

        # Capitalize the very first letter
        sentence = sentence[0].upper() + sentence[1:]
        # Capitalize after sentence-ending punctuation
        sentence = CAPITALIZE_PATTERN.sub(capitalize_after_period, sentence)

    # Replace __article__ with 'a' or 'an' based on the following word, but not if __article__ an/a
    def replace_article(match):
        article_placeholder, next_word = match.groups()
        if article_placeholder == "__article__":
            if next_word.lower() in ("a", "an", "another"):
                return next_word
            if next_word.lower().startswith(("a", "e", "i", "o", "u")):
                return "an " + next_word
            else:
                return "a " + next_word
        else:
            return article_placeholder + " " + next_word

    sentence = ARTICLE_PATTERN.sub(replace_article, sentence)

    return sentence

def _get_company_reference(company_name: str, chance: float = 0.25) -> str:
    """Randomly returns either the full company name or a generic placeholder."""
    return company_name if random.random() < chance else "The Company"
