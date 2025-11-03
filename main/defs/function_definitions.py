import random
import re
from typing import Literal

# A set of common currency symbols to differentiate them from units
KNOWN_CURRENCY_SYMBOLS = {
    "$",
    "€",
    "£",
    "¥",
    "CHF",
    "kr",
    "zł",
    "Ft",
    "Kč",
    "₺",
    "₽",
    "лв",
    "lei",
    "₩",
    "฿",
    "RM",
    "R$",
    "د.إ",
    "ر.س",
    "₹",
}

KNOWN_CURRENCY_SYMBOLS = {"$", "€", "£", "¥"}  # Example set


from typing import Literal

KNOWN_CURRENCY_SYMBOLS = {"$", "€", "£", "¥"}  # example set


def _format_single_notional(
    amount: int | float,
    symbol: str,  # The currency symbol or unit, e.g., '$' or 'barrels'
    prefer_abbreviated: bool,
    no_unit_word: bool = False,  # Suppresses "million/billion/etc."
    zero_format: Literal["nil", "zero", "amount"] = "amount",
    negative_format: Literal[-1, 0, 1] = 1,  # default = 1 → (num) unit
) -> str:
    """
    Formats a single notional amount into a readable string like '$250.0 million'
    or '250.0 thousand barrels'.

    - If no_unit_word=True, abbreviates numerically but omits the unit word
      (e.g., '$250.0' instead of '$250.0 million').
    - If prefer_abbreviated=False, shows full number with commas.
    - negative_format:
        -1 → accounting style, e.g. '($250.0 million)' or '(2.5 million barrels)'
         0 → minus sign, e.g. '-$250.0 million' or '-2.5 million barrels'
         1 → parentheses only around the number, e.g. '$(2.5) million' or '(2.5) million barrels'
    """
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
    if symbol in KNOWN_CURRENCY_SYMBOLS:
        base = f"{symbol}{formatted_number}{unit_word}"
    else:
        base = f"{formatted_number}{unit_word} {symbol}".strip()

    # Apply negative formatting
    if is_negative:
        if negative_format == -1:
            return f"({base})"
        elif negative_format == 0:
            return f"-{base}"
        elif negative_format == 1:
            if symbol in KNOWN_CURRENCY_SYMBOLS:
                return f"{symbol}({formatted_number}){unit_word}"
            else:
                return f"({formatted_number}){unit_word} {symbol}".strip()
        else:
            raise ValueError("negative_format must be -1, 0, or 1")

    return base

def _get_correct_rounding(amount: int | float, multiplier: int):
    return round(amount / multiplier) * multiplier

import re


def _cleanup_sentence(sentence: str) -> str:
    """Clean up sentence by removing placeholders, fixing spacing, and capitalizing properly."""

    # Add a space before a clause if the preceding character is not a space, comma, or newline
    sentence = re.sub(
        r"([a-zA-Z0-9,])(\{[^}]+\})",
        r"\1 \2",
        sentence,
    )

    # Remove ALL placeholders of the form {something}
    sentence = re.sub(r"\{[^}]*\}", "", sentence)

    # Clean up multiple spaces
    sentence = re.sub(r"\s{2,}", " ", sentence)

    # Remove leading commas/spaces
    sentence = re.sub(r"^\s*,\s*", "", sentence)

    # Fix common punctuation issues
    sentence = sentence.replace(" ,", ",")
    sentence = sentence.replace(",,", ",")
    sentence = sentence.replace(" .", ".")
    sentence = sentence.replace(", .", ".")

    # Correct pluralization (company -> companies, but not always/employs)
    sentence = re.sub(r"([^aeiou])ys\b", r"\1ies", sentence, flags=re.IGNORECASE)

    # Capitalize first letter of the sentence and after periods
    def capitalize_after_period(match):
        return match.group(1) + match.group(2).upper()

    sentence = sentence.strip()
    if sentence:
        # Capitalize first character
        sentence = sentence[0].upper() + sentence[1:]
        # Capitalize after ". " or "? " or "! "
        sentence = re.sub(r"([.!?]\s+)([a-z])", capitalize_after_period, sentence)

    return sentence.strip()

def _get_company_reference(company_name: str, chance: float = 0.25) -> str:
    """Randomly returns either the full company name or a generic placeholder."""
    return company_name if random.random() < chance else "The Company"
