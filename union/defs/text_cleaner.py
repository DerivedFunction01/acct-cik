import re
import difflib
import csv
from pathlib import Path
from typing import Any, Optional, List, Tuple, Dict
from dataclasses import dataclass
from enum import Enum
from defs.regex_lib import (
    SENTENCE_SPLIT_PATTERN,
    build_alternation,
    build_compound,
    build_regex,
    YEAR_REGEX,
)
from defs.union_regex import CHANGE_TERMS, NOUNS, PERSONNEL_EVENT_TERMS, WORKER_TERMS, DIVERSITY_TERMS, SUFFIX_AGREEMENTS, SUFFIX_ORGS
from defs.region_regex import MAJOR_CURRENCIES

COMPANY_TOKEN = "the Company"

SPACE_PATTERN = re.compile(r"\s+")
PUNCT_SPACE_PATTERN = re.compile(r"\s+([,\.;\:\!\?])")
DOUBLE_PUNCT_PATTERN = re.compile(r"([,\.;\:\!\?])\1+")
MISSING_SPACE_PATTERN = re.compile(r"(?:(?<!\b[A-Z])\.|[,;\:\!\?])(?=[a-zA-Z])")
HANGING_APOSTROPHE_PATTERN = re.compile(r"\s+'(s|re|ve|t|m|ll|d)\b", re.IGNORECASE)


def clean_spaces_and_punctuation(text: str) -> str:
    """
    Normalizes whitespace and cleans up punctuation.
    """
    if not text:
        return ""
    text = SPACE_PATTERN.sub(" ", text).strip()
    text = PUNCT_SPACE_PATTERN.sub(r"\1", text)
    text = DOUBLE_PUNCT_PATTERN.sub(r"\1", text)
    text = MISSING_SPACE_PATTERN.sub(r"\g<0> ", text)
    text = HANGING_APOSTROPHE_PATTERN.sub(r"'\1", text)
    return text


def normalize_unicode(text: str) -> str:
    """
    Normalize common Unicode single and double quotation marks to ASCII
    straight quotes. Handles curly quotes and prime characters often
    introduced by smart-quoting in word processors.
    """
    if not text:
        return ""

    # Common Unicode quote characters -> ASCII equivalents
    replacements = {
        "\u2018": "'",  # LEFT SINGLE QUOTATION MARK
        "\u2019": "'",  # RIGHT SINGLE QUOTATION MARK (also used as apostrophe)
        "\u201A": "'",  # SINGLE LOW-9 QUOTATION MARK
        "\u201B": "'",  # SINGLE HIGH-REVERSED-9 QUOTATION MARK
        "\u2032": "'",  # PRIME
        "\u201C": '"',  # LEFT DOUBLE QUOTATION MARK
        "\u201D": '"',  # RIGHT DOUBLE QUOTATION MARK
        "\u201E": '"',  # DOUBLE LOW-9 QUOTATION MARK
        "\u201F": '"',  # DOUBLE HIGH-REVERSED-9 QUOTATION MARK
        "\u2033": '"',  # DOUBLE PRIME
    }

    for src, dst in replacements.items():
        text = text.replace(src, dst)

    return text


class WebTextCleaner:
    false_positives = [
        (re.compile(r"\bcredit\s+unions?\b", re.IGNORECASE), "Bank"),
        (re.compile(r"\beuropean\s+union\b", re.IGNORECASE), "The EU"),
        (re.compile(r"\bsoviet\s+union\b", re.IGNORECASE), "USSR"),
        (re.compile(r"\bafrican\s+union\b", re.IGNORECASE), "Africa"),
        (re.compile(r"\bthe\s+Union\s+of\s+south\s+africa\b", re.IGNORECASE), "South Africa"), # South africa
        (re.compile(r"\bUnion\s+of\s+south\s+american?\b", re.IGNORECASE), "South America"), # South africa
        (re.compile(r"\bstate\s+of\s+the\s+union\b", re.IGNORECASE), "Speech"),
        (re.compile(r"\bstudent\s+unions?\b", re.IGNORECASE), "Student Body"),
        (re.compile(r"\b(?:(?:(?:non|delayed)[- ]?)?union\s+fractures?|bony[- ]unions?)\b", re.IGNORECASE), "fracture"),
        (re.compile(r"\bmonetary\s+unions?\b", re.IGNORECASE), "currency agreement"),
        (re.compile(r"\b(?:kosher|orthodox|kashrut)\s+unions?\b", re.IGNORECASE), "certification"),
        (re.compile(r"\bUnion\s+of\s+Orthodox\s+(?:Jewish\s+)?(?:Congregations)?\b", re.IGNORECASE), "certification"),
        (
            build_regex(
                [
                    build_compound(
                        [r"union", r"pacific", r"western", r"first", r"trans"],
                        [
                            r"union",
                            r"fire",
                            r"pacific",
                            r"carbide",
                            r"banks?",
                            r"mines?",
                            r"company",
                            r"corporation",
                            r"oil",
                            r"holdings?",
                            r"gas"
                            r"trust",
                            r"station",
                            r"electric",
                            r"college",
                            r"university",
                        ],
                    ),
                ]
            ),
            "Company",
        ),
    ]

    def clean(self, text: str) -> str:
        if not text:
            return ""
        for regex, replacement in self.false_positives:
            text = regex.sub(replacement, text)
        return text


class MinimalTextCleaner:
    # Suffixes to strip from the passed company name
    name_suffixes = [
        r"inc\.?",
        r"corp\.?",
        r"corporation",
        r"l\.?l\.?c\.?",
        r"co\.?",
        r"company",
        r"ltd\.?",
        r"limited",
        r"p\.?l\.?c\.?",
        r"s\.?a\.?",
        r"group",
        r"holdings?",
        r"trust",
        r"assoc\.?",
        r"association",
    ]

    # Suffixes to remove from the text generally (safer subset)
    text_suffixes = [
        r"inc\.?",
        r"corp\.?",
        r"corporation",
        r"l\.?l\.?c\.?",
        r"ltd\.?",
        r"p\.?l\.?c\.?",
        r"s\.?a\.?",
    ]

    # Regex to strip suffixes from the end of the company name
    name_suffix_pattern = re.compile(
        r"\s+" + build_alternation(name_suffixes) + r"\.?$", re.IGNORECASE
    )

    # Regex to remove safe suffixes from text
    text_suffix_pattern = re.compile(
        r"\b" + build_alternation(text_suffixes) + r"(?:\b\.?|(?<=\.))", re.IGNORECASE
    )

    # False Positives for Union/Labor context
    false_positives = [
        (re.compile(r"all[- ]in[- ]all", re.IGNORECASE), "in conclusion"),
        (re.compile(r"not\s+all", re.IGNORECASE), "Some"),
    ] + WebTextCleaner.false_positives


    ip_terms_pattern = build_alternation(
        [
            r"patents?",
            r"trademarks?",
            r"licenses?",
            r"franchises?",
            r"concessions?",
            r"royalty\s+agreements?",
        ]
    )
    ip_context_regex = re.compile(rf"\b(?:{ip_terms_pattern})\b", re.IGNORECASE)
    labor_contract_regex = re.compile(r"\blabor\s+contracts?\b", re.IGNORECASE)

    # Bullet and Dashed Patterns
    bullet_pattern = re.compile(
        r"(?:(?<=^)|(?<=\n))"  # Start of paragraph or line
        r"(?:"
        r"\(\d{1,2}\)|"
        r"-\d{3}-|"
        r"\d{1}-|"
        r"\d{4}-\d{1}|"
        r"\d{4}-[A-Z0-9]*[A-Z][A-Z0-9]*|"
        # 2. Capture numbers with period/colon ONLY if NOT a year: 1., 1: -> STRIP
        r"\d{1,2}(?:\.|\)|\:)|"
        # 3. Roman numerals and letters -> STRIP
        r"\([ivxlcdm]+\)|[ivxlcdm]+\.|"
        r"\([a-z]\)|(?<!\.[a-z])[a-z]\.|"
        r"\([A-Z]\)|(?<!\.[A-Z])[A-Z]\."
        r")"
        r"(?=[\s\(])",  # Followed by whitespace
        re.IGNORECASE,
    )
    sentence_bullet_pattern = re.compile(
        r"(?<=[.!?])\s+"
        r"(?:"
        r"\(\d{1,2}\)|"
        r"\d{1,2}(?:\.|\)|\:)|"
        r"\([ivxlcdm]+\)|[ivxlcdm]+\.|"
        r"\([a-z]\)|(?<!\.[a-z])[a-z]\.|"
        r"\([A-Z]\)|(?<!\.[A-Z])[A-Z]\."
        r")"
        r"(?=\s)",
        re.IGNORECASE,
    )

    # Page number artifacts (e.g. -10-, 4-, -4-, 10-)
    page_number_pattern = re.compile(
        r"(?:(?<=^)|(?<=\s))"
        r"(?:"
        r"-\d{1,3}-|"
        r"\d{1,3}-"
        r")"
        r"(?=\s|$)",
        re.IGNORECASE,
    )

    # Date and Year Patterns
    months = [
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Sept",
        "Oct",
        "Nov",
        "Dec",
    ]
    months_pattern_str = build_alternation(months) + r"[a-z]*\.?"

    date_md_pattern = re.compile(
        rf"\b(?:{months_pattern_str})\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,)?(?!\d)",
        re.IGNORECASE,
    )

    date_dm_pattern = re.compile(
        rf"(?<!\d)(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?(?:{months_pattern_str})\b",
        re.IGNORECASE,
    )

    month_only_pattern = re.compile(rf"\b(?:{months_pattern_str})\b")

    year_pattern = YEAR_REGEX
    slash_date_pattern = re.compile(r"\b(?:\d{1,2}/)+\d{2,4}\b")
    year_range_short_pattern = re.compile(r"\b((?:19|20)\d{2})-(\d{2})\b")

    # Word to number mappings
    num_words = {
        "zero": 0,
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10,
        "eleven": 11,
        "twelve": 12,
        "thirteen": 13,
        "fourteen": 14,
        "fifteen": 15,
        "sixteen": 16,
        "seventeen": 17,
        "eighteen": 18,
        "nineteen": 19,
        "twenty": 20,
        "thirty": 30,
        "forty": 40,
        "fifty": 50,
        "sixty": 60,
        "seventy": 70,
        "eighty": 80,
        "ninety": 90,
    }
    multipliers = {
        "dozen": 12,
        "hundred": 100,
        "thousand": 1_000,
        "million": 1_000_000,
        "billion": 1_000_000_000,
        "trillion": 1_000_000_000_000,
    }
    fractions = {
        "half": 0.5,
        "halves": 0.5,
        "quarter": 0.25,
        "quarters": 0.25,
        "third": 1 / 3,
        "thirds": 1 / 3,
        "fourth": 0.25,
        "fourths": 0.25,
        "fifth": 0.2,
        "fifths": 0.2,
        "sixth": 1 / 6,
        "sixths": 1 / 6,
        "seventh": 1 / 7,
        "sevenths": 1 / 7,
        "eighth": 1 / 8,
        "eighths": 1 / 8,
        "ninth": 1 / 9,
        "ninths": 1 / 9,
        "tenth": 0.1,
        "tenths": 0.1,
    }

    # Build regex for number phrases
    _all_words = (
        list(num_words.keys()) + list(multipliers.keys()) + list(fractions.keys())
    )
    _word_pattern = build_alternation([re.escape(w) for w in _all_words])
    number_phrase_pattern = re.compile(
        rf"\b{_word_pattern}(?:[\s-]+{_word_pattern})*\b", re.IGNORECASE
    )

    # Qualitative financial terms to numeric conversion map
    # No point doing all
    # _hundred = [
    #     r"(?<!not\s)all(?=\s+(?:of|are|were))",  # all in all is rare to see in a financial filing
    #     # 33% are completely covered. =/= 33% are 100% covered -> wrong. We need it as a noun/adj, not adverb
    #     r"(?:complete|full|whole|entire) portions?",
    # ]
    # _hundred_alternation = build_alternation(_hundred)

    # Format: (Regex Pattern, Replacement String)
    qualitative_patterns = [
        # "none of" -> "0%"
        (
            build_regex(
                [
                    r"none(?=\s+(?:of|are|is|were|was))",
                    r"(?<=(?:\sare|were|\swas)\s)none",
                    r"(?<=is\s)none",
                ]
            ),
            "0%",
        ),
        # "a couple (of)" -> "2"
        (re.compile(r"\ba\s+couple\s+(?:of\s+)?", re.IGNORECASE), "two "),
        # "a few" before multipliers -> "three" (approximation for calculation)
        (
            re.compile(
                rf"\ba\s+few\s+(?={build_alternation(list(multipliers.keys()))})",
                re.IGNORECASE,
            ),
            "three ",
        ),
        (
            re.compile(
                rf"\bhalf\s+(?:of\s+)?(?:a\s+)?(?={build_alternation(list(multipliers.keys()))})",
                re.IGNORECASE,
            ),
            "0.5 ",
        ),
        (
            re.compile(
                rf"\ba\+quarter\s+(?:of\s+)?(?:a\s+)?(?={build_alternation(list(multipliers.keys()))})",
                re.IGNORECASE,
            ),
            "0.25 ",
        ),
        (
            re.compile(
                rf"\bthree\+quarters\s+(?:of\s+)?(?:a\s+)?(?={build_alternation(list(multipliers.keys()))})",
                re.IGNORECASE,
            ),
            "0.75 ",
        ),
        (
            re.compile(
                rf"\ba\s+(?={build_alternation(list(multipliers.keys()))}|(?:quarter|third|fifth|sixth)\s+of)",
                re.IGNORECASE,
            ),
            "one ",
        ),
        # "all of/entire" -> "100%"
        # (build_regex([_hundred_alternation]), "100%"),
        # # entirety -> 95%
        # (build_regex([r"entirety(?=\s+(?:of|are|were))"]), "95%"),
    ]

    # Handle "no [worker]", "none whom" -> "0 [worker]"
    _worker_pattern = build_alternation(WORKER_TERMS + NOUNS)
    no_worker_pattern = re.compile(
        rf"\bno(?:ne)?\s+((?:[\w-]+\s+){{0,2}}{_worker_pattern})\b", re.IGNORECASE
    )

    # Handle "all [worker]" -> "100% of [worker]"
    # Ensure not preceded by "not"
    # all_worker_pattern = re.compile(
    #     rf"(?<!\bnot\s)\ball\s+((?:[\w-]+\s+){{0,3}}{_worker_pattern})\b", re.IGNORECASE
    # )

    # # Handle "[worker] ... were/are all" -> "[worker] ... were/are 100%"
    # worker_all_pattern = re.compile(
    #     rf"\b({_worker_pattern}(?:\s+[\w-]+){{0,3}}\s+(?:were|are)?)\s+all\b",
    #     re.IGNORECASE,
    # )

    # Fix capitalization of "the" at start of sentences
    fix_the_capitalization_pattern = re.compile(r"(^|[.!?]\s+)the\b")

    # Pronouns to Company Token
    # Note: 'us' is strictly not allcaps to avoid matching 'US' (United States)
    pronoun_pattern = re.compile(r"\b[Uu]s\b")

    percent_pattern = re.compile(r"\bper[- ]?cent\b", re.IGNORECASE)
    percent_space_pattern = re.compile(r"(\d)\s+%", re.IGNORECASE)
    percent_range_pattern = re.compile(
        r"\b(\d+(?:\.\d+)?)\s*%?\s*(?:-|–|—|to)\s*(\d+(?:\.\d+)?)\s*%", re.IGNORECASE
    )

    # Numbers
    comma_pattern = re.compile(r"(?<=\d),(?=\d{3})")
    parenthetical_duplicate_number_pattern = re.compile(
        r"\b(?P<left>\d+(?:\.\d+)?)\s*\(\s*(?P<right>\d+(?:\.\d+)?)\s*\)"
    )
    scale_map = {
        "dozen": 12,
        "hundred": 100,
        "thousand": 1_000,
        "million": 1_000_000,
        "billion": 1_000_000_000,
        "trillion": 1_000_000_000_000,
    }
    scale_pattern = re.compile(
        rf"\b(\d+(?:\.\d+)?)\s+({'|'.join(scale_map.keys())})\b", re.IGNORECASE
    )

    # Pattern to handle hyphenated fractions like "three-fourths", "one-half"
    # This must be processed BEFORE number_phrase_pattern
    _fraction_words = "|".join(
        list(fractions.keys())
        + [
            w[:-3] for w in fractions.keys() if w.endswith("ths")
        ]  # base forms like "fourth" from "fourths"
    )
    _num_words_str = "|".join(num_words.keys())
    hyphenated_fraction_pattern = re.compile(
        rf"\b({_num_words_str})-({_fraction_words}s?)\b", re.IGNORECASE
    )
    fraction_qualifiers = {
        "approx",
        "approx.",
        "approximately",
        "roughly",
        "nearly",
        "about",
        "around",
        "almost",
    }

    # False Fraction Protection
    # Terms that are fractions but often used in dates/periods: quarter, half, third, fourth...
    # We want to protect them when they are used as time periods or ordinals.
    _ordinals_and_time = [
        "fiscal",
        "first",
        "second",
        "third",
        "fourth",
        "fifth",
        "sixth",
        "next",
        "last",
        "previous",
        "current",
        "past",
        r"th(?:is|ese)",
        "following",
        r"report(?:ing|ed)?",
        "subsequent",
        "the",
        "remaining",
        r"\d+(?:st|nd|rd|th)",
        "interim",
        "annual",
        "daily",
        "monthly",
        "weekly",
        "prior",
        "ealier",
        "upcoming",
        "ensuing",
        "preceding",
        "ending",
        "ended",
        "comparative",
        "consecutive",
        "cumulative",
        "rolling",
        "trailing",
    ]
    _ordinals_pattern = build_alternation(_ordinals_and_time)

    _fraction_terms = list(fractions.keys())
    _fraction_terms_pattern = build_alternation(_fraction_terms)

    # Terms that indicate a time period following a fraction
    _time = build_alternation(
        [
            r"years?",
            r"quarters?",
            r"months?",
            r"weeks?",
            r"days?",
            r"hours?",
            r"minutes?",
            r"seconds?",
            r"periods?",
            r"half",
        ]
    )
    _period_terms = [
        rf"(?:full\s+|fiscal\s+|report(?:ing|ed)\s+)?{_time}",
        r"centur(?:y|ies)",
    ]
    _period_pattern = build_alternation(_period_terms)

    # Flexible gap (e.g. "quarter of the fiscal year")
    # Allow up to 3 words between fraction and period
    _gap_pattern = r"(?:\s+\w+){0,3}"

    # Financial period patterns (YTD, YoY, etc.)
    _x_to_date = rf"{_time}(?:\s*[-–]\s*|\s+to\s+)date"
    _x_end = rf"{_time}(?:\s*[-–]\s*|\s+)end"
    _x_over_x = rf"{_time}(?:\s*[-–]\s*|\s+over\s+){_time}"

    false_fraction_pattern = build_regex(
        [
            rf"(?:{_ordinals_pattern})\s+(?:of\s+(?:the\s+)?)?{_fraction_terms_pattern}",
            rf"{_fraction_terms_pattern}\s+(?:ended|ending)",
            r"in\s+(?:the\s+)?(?:first|second|1st|2nd)\s+hal(?:f|ves)",
            rf"{_fraction_terms_pattern}{_gap_pattern}\s+{_period_pattern}",
            _x_to_date,
            _x_end,
            _x_over_x,
        ]
    )

    EXHIBIT_NOUNS = [
        "exhibits?",
        "references?",
        "note",
        "appendix",
        "schedules?",
        "articles?",
        "sections?",
        "subsections?",
        "statements?",
        "table",
        "No.",
        "pages?",
        "pp.",
        "p.",
        "figures?",
        "charts?",
        "summary",
        "items?",
        "chapters?",
        "numbers?",
        "trust",
    ]

    EXHIBIT_FRAGMENT = build_alternation(EXHIBIT_NOUNS)
    exhibit_pattern = re.compile(
        rf"\b{EXHIBIT_FRAGMENT}\b"
        r"(?:\s*No\.?)?"
        r"\s*\d(?:[\d\.\-]*\d)?"
        r"(?:\s*(?:,?\s*(?:and|or|&)|,|to|through|-)\s*\d(?:[\d\.\-]*\d)?)*"
        r"\b",
        re.IGNORECASE,
    )

    # Page artifact pattern (e.g. "2 <PAGE> 7")
    # Limit to 1-3 digits to avoid matching years (e.g. 2000 <PAGE>)
    page_pattern = re.compile(
        r"(?:\b\d{1,3}\s*)?<PAGE>(?:\s*\d{1,3}\b)?", re.IGNORECASE
    )

    # Regex for acronyms with dots (2-5 letters) e.g. U.S., U.S.A.
    acronym_pattern = re.compile(r"\b(?:[A-Z]\.){2,5}")

    # Covid normalization
    covid_pattern = re.compile(
        r"\b(?:(?:covid|coronavirus)(?:[\s-]*(?:19|2019))?|SARS-CoV-2)\b", re.IGNORECASE
    )

    # Float pattern: Matches 1.5, 10.00, but NOT 1.5% (lookahead protects %)
    float_pattern = re.compile(r"\b\d+\.\d+\b(?!%)")

    zip_code_pattern = re.compile(r"\b\d{5}(?:[- ]\d{4})?\b")

    phone_number_pattern = re.compile(r"(?:\b\+?\d{1,3}[-.\s]*)?(?:\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}\b")

    # Law/Act Year Pattern
    law_terms = [
        r"Acts?",
        r"Codes?",
        r"Laws?",
        r"Regulations?",
        r"Rules?",
        r"Statutes?",
        r"Ord(?:inance|er)s?",
        r"Treat(?:y|ies)",
    ]
    law_pattern_str = build_alternation(law_terms)
    
    law_year_regex = re.compile(
        rf"\b((?:{law_pattern_str})\s+(?:of\s+)?)(?:19|20)\d{{2}}\b|"
        rf"\b(?:19|20)\d{{2}}(\s+(?:[\w-]+\s+){{0,2}}{law_pattern_str})\b",
        re.IGNORECASE
    )

    def __init__(self):
        pass

    def normalize_company_name(self, name: str) -> str:
        if not name:
            return ""
        name = name.strip()
        prev_name = None
        while name != prev_name:
            prev_name = name
            candidate = self.name_suffix_pattern.sub("", name).strip()

            # If stripping results in a single number, return the last known name
            tokens = candidate.split()
            if len(tokens) == 1:
                token = tokens[0].lower()
                if token.isdigit() or token in self.num_words:
                    return name

            name = candidate
        return name

    def _convert_slash_date(self, match):
        text = match.group(0)
        parts = text.split('/')
        last = parts[-1]

        # Determine if we should treat the last part as a year
        is_year = False

        if len(parts) >= 3:
            is_year = True
        elif len(parts) == 2:
            first = parts[0]
            # If first part is a month, check if second part is ambiguous (<= 31)
            if first.isdigit() and 1 <= int(first) <= 12:
                if len(last) == 4:
                    is_year = True
                elif len(last) == 2 and last.isdigit() and int(last) > 31:
                    is_year = True

        if not is_year:
            return " "

        year = None
        if len(last) == 4 and last.isdigit():
            year = int(last)
        elif len(last) == 2 and last.isdigit():
            val = int(last)
            year = (2000 + val) if 0 <= val <= 35 else (1900 + val)

        if year and 1900 <= year <= 2100:
            return f" {year} "
        return " "

    def _convert_hyphenated_fraction(self, match):
        """
        Convert hyphenated fractions like "three-fourths" to "75%"
        Examples:
          "one-half" → "50%"
          "three-fourths" → "75%"
          "two-thirds" → "66.67%"
        """
        num_word = match.group(1).lower()
        frac_word = match.group(2).lower()

        # Get the number
        if num_word not in self.num_words:
            return match.group(0)  # Shouldn't happen, but be safe

        numerator = self.num_words[num_word]

        # Get the fraction - handle both "half" and "halves", "fourth" and "fourths", etc.
        if frac_word not in self.fractions:
            # Try removing 's' if present
            frac_base = frac_word.rstrip("s")
            if frac_base not in self.fractions:
                return match.group(0)  # Not a recognized fraction
            denominator = self.fractions[frac_base]
        else:
            denominator = self.fractions[frac_word]

        result = numerator * denominator
        return f"{result * 100:g}%"

    def _scale_replacer(self, match):
        try:
            number = float(match.group(1))
            multiplier = self.scale_map.get(match.group(2).lower(), 1)
            value = number * multiplier
            if value.is_integer():
                return f"{int(value)}"
            return f"{value}"
        except ValueError:
            return match.group(0)

    def _parse_number_phrase(self, match):
        text = match.group(0)
        clean_text = text.lower().replace("-", " ")
        words = clean_text.split()

        # If phrase is only multipliers (e.g. "million"), leave it for scale_pattern
        if all(w in self.multipliers for w in words):
            return text

        # IMPORTANT RULE: Fractions are ONLY converted when:
        # 1. Preceded by a number (e.g., "one half", "three-fourths", "two thirds")
        # 2. Preceded by a qualifier (e.g., "approx half", "roughly third")
        #
        # Standalone fractions like "first quarter", "second half" are preserved
        # because they're not actually fractions - they're business/time period terminology

        # List of qualifiers that can precede a fraction

        # Check what we have
        has_number = any(w in self.num_words for w in words)
        has_qualifier = any(w in self.fraction_qualifiers for w in words)
        has_fraction = any(w in self.fractions for w in words)
        # if not has_fraction:
        #     return text
        # If it's ONLY a fraction word (standalone), preserve it
        # Examples: "half", "third" (when standing alone)
        if has_fraction and not has_number and not has_qualifier:
            # Allow some to convert, but keep others (ordinals)
            is_safe = True
            for w in words:
                if w not in ["half"]:
                    is_safe = False
                    break
            if not is_safe:
                return text  # Preserve standalone fractions like "third"

        # Special case: Check for "number fraction_word" patterns like "three fourths"
        # where "fourths" ends with "ths" but the base "fourth" is a fraction
        # This handles cases where the regex splits hyphenated fractions
        if len(words) >= 2:
            for i in range(len(words) - 1):
                word = words[i]
                next_word = words[i + 1]

                # Check if we have a number followed by something like "fourths"
                if word in self.num_words:
                    # Check if next word ends with "ths" (like "fourths", "thirds", "halves")
                    if next_word.endswith("ths"):
                        base = next_word[:-3]  # Remove 'ths' suffix
                        if base in self.fractions:
                            # Convert "three fourths" to "75%"
                            num = self.num_words[word]
                            frac = self.fractions[base]
                            result = num * frac
                            return f"{result * 100:g}%"
                    # Also check for "halves" -> "half"
                    elif next_word == "halves":
                        num = self.num_words[word]
                        result = num * 0.5
                        return f"{result * 100:g}%"

        total_value = 0
        current_chunk = 0
        is_fraction = False
        fraction_value = 0.0

        for word in words:
            if word in self.num_words:
                current_chunk += self.num_words[word]
            elif word in self.multipliers:
                mult = self.multipliers[word]
                if mult < 1000:
                    current_chunk = (current_chunk if current_chunk else 1) * mult
                else:
                    total_value += (current_chunk if current_chunk else 1) * mult
                    current_chunk = 0
            elif word in self.fractions:
                # Convert to fraction if:
                # 1. We have accumulated a number before it (e.g., "one" before "half")
                # 2. We have a qualifier before it (e.g., "approx" before "half")
                if current_chunk > 0:
                    # We have a number like "one", "two", "three"
                    fraction_value += current_chunk * self.fractions[word]
                    current_chunk = 0
                    is_fraction = True
                elif word in ["half"]:  # has_qualifier
                    # Allow qualifiers like "approx half", "roughly third"
                    fraction_value += self.fractions[word]
                    is_fraction = True
                # Otherwise skip this fraction word (standalone case)

        if is_fraction:
            final_val = total_value + fraction_value
            if final_val == 0:
                return text
            return f"{final_val * 100:g}%"

        total_value += current_chunk
        if total_value == 0 and "zero" not in clean_text:
            return text
        return str(total_value)

    def _collapse_parenthetical_duplicate_numbers(self, text: str) -> str:
        """
        Collapse duplicate numeric parentheticals after normalization:
        e.g. "15 (15)" -> "15", "15.0 (15)" -> "15.0".
        """

        def repl(match: re.Match) -> str:
            left = match.group("left")
            right = match.group("right")
            try:
                if float(left) == float(right):
                    return left
            except ValueError:
                return match.group(0)
            return match.group(0)

        return self.parenthetical_duplicate_number_pattern.sub(repl, text)

    def normalize_acronyms(self, text: str) -> str:
        """
        Normalizes acronyms (e.g. U.S. -> US) by removing dots,
        unless the dot acts as a sentence terminator (followed by uppercase).
        """

        def replace_func(match):
            original = match.group(0)
            normalized = original.replace(".", "")

            end_idx = match.end()
            full_text = match.string

            # Scan forward past whitespace
            i = end_idx
            while i < len(full_text) and full_text[i].isspace():
                i += 1

            # If we hit end of string or found an uppercase letter, treat as sentence end
            if i >= len(full_text) or full_text[i].isupper():
                return f"{normalized}."

            return normalized

        return self.acronym_pattern.sub(replace_func, text)

    def clean(
        self,
        text: str,
        company_name: Optional[str] = None,
        reporting_year: Optional[int] = None,
        min_length: Optional[int] = None,
    ) -> str:
        if not text:
            return ""

        paragraphs = text.split("\n\n")
        paragraphs = [p.strip() for p in paragraphs]
        texts = []
        for paragraph in paragraphs:
            # Normalize Unicode quotes to ASCII straight quotes
            paragraph = normalize_unicode(paragraph)

            # 2. Normalize Acronyms (Early)
            paragraph = self.normalize_acronyms(paragraph)

            # 2. False Positives
            for pat, repl in self.false_positives:
                paragraph = pat.sub(repl.capitalize(), paragraph)

            # Drop "labor contract(s)" only when sentence context is IP/legal boilerplate.
            sentences = []
            for sent in SENTENCE_SPLIT_PATTERN.split(paragraph):
                if self.ip_context_regex.search(sent):
                    sent = self.labor_contract_regex.sub(" ", sent)
                sentences.append(sent)
            paragraph = " ".join(sentences)

            # Normalize Covid
            paragraph = self.covid_pattern.sub("covid", paragraph)

            # 3. Company Name
            if company_name:
                core_name = self.normalize_company_name(company_name)
                if len(core_name) > 2:
                    escaped_name = re.escape(core_name)
                    suffix_regex = (
                        r"(?:\s+(?:" + "|".join(self.name_suffixes) + r")\.?)*"
                    )
                    company_regex = re.compile(
                        rf"\b{escaped_name}{suffix_regex}(?:\b|(?<=\.))", re.IGNORECASE
                    )
                    paragraph = company_regex.sub(COMPANY_TOKEN, paragraph)

            # 3b. Pronoun Replacement
            paragraph = self.pronoun_pattern.sub(COMPANY_TOKEN, paragraph)

            # Fix capitalization of "the" (e.g. "the Company" at start of sentence)
            paragraph = self.fix_the_capitalization_pattern.sub(
                lambda m: m.group(1) + "The", paragraph
            )

            # 4. General Suffix Removal
            paragraph = self.text_suffix_pattern.sub("", paragraph)

            # NEW: Remove bullets and Cleanup references (before whitespace collapse)
            paragraph = self.exhibit_pattern.sub(" ", paragraph)
            paragraph = self.page_pattern.sub(" ", paragraph)
            paragraph = self.bullet_pattern.sub(" ", paragraph)
            paragraph = self.sentence_bullet_pattern.sub(" ", paragraph)
            paragraph = self.page_number_pattern.sub(" ", paragraph)

            # 1. Whitespace
            paragraph = clean_spaces_and_punctuation(paragraph)

            # Remove years from laws
            paragraph = self.law_year_regex.sub(lambda m: m.group(1) or m.group(2), paragraph)

            # 4b. Date and Year Removal
            paragraph = self.slash_date_pattern.sub(self._convert_slash_date, paragraph)
            paragraph = self.year_range_short_pattern.sub(r" <\1> ", paragraph)
            paragraph = self.date_md_pattern.sub(" ", paragraph)
            paragraph = self.date_dm_pattern.sub(" ", paragraph)
            paragraph = self.month_only_pattern.sub(" ", paragraph)
            paragraph = self.year_pattern.sub(r" <\1> ", paragraph)
            paragraph = self.zip_code_pattern.sub("zip code", paragraph)
            paragraph = self.phone_number_pattern.sub("phone", paragraph)

            # NEW: Protect False Fractions
            protected_map = {}

            def protect_match(m):
                key = f"__FF_PROTECT_{len(protected_map)}__"
                protected_map[key] = m.group(0)
                return key

            paragraph = self.false_fraction_pattern.sub(protect_match, paragraph)

            # 5. Numbers
            # First handle hyphenated fractions like "three-fourths" before they get split
            paragraph = self.hyphenated_fraction_pattern.sub(
                self._convert_hyphenated_fraction, paragraph
            )

            for pattern, replacement in self.qualitative_patterns:
                paragraph = pattern.sub(replacement, paragraph)
            # paragraph = self.all_worker_pattern.sub(r"100% of \1", paragraph)
            # paragraph = self.worker_all_pattern.sub(r"\1 100%", paragraph)
            paragraph = self.no_worker_pattern.sub(r"0 \1", paragraph)
            paragraph = self.number_phrase_pattern.sub(
                self._parse_number_phrase, paragraph
            )
            paragraph = self.comma_pattern.sub("", paragraph)
            paragraph = self.scale_pattern.sub(self._scale_replacer, paragraph)
            paragraph = self._collapse_parenthetical_duplicate_numbers(paragraph)

            # Restore False Fractions
            for key, val in protected_map.items():
                paragraph = paragraph.replace(key, val)

            # Percent normalization
            paragraph = self.percent_pattern.sub("%", paragraph)
            paragraph = self.percent_range_pattern.sub(r"\1% to \2%", paragraph)
            paragraph = self.percent_space_pattern.sub(r"\1%", paragraph)

            # Punctuation cleanup
            paragraph = clean_spaces_and_punctuation(paragraph)

            # Long enough to be considered one, even if it is a single sentence
            if paragraph and (min_length is None or len(paragraph) >= min_length):
                texts.append(paragraph)

        text = "\n\n".join(texts)
        return text


class CurrencyRemover:
    """
    Removes currency amounts from text.
    Designed to run AFTER MinimalTextCleaner has normalized numbers (removed commas).
    """

    def __init__(self):
        symbols = set()
        suffixes = set(["cent", "cents"])

        for code, props in MAJOR_CURRENCIES.items():
            for s in props.get("symbols", []):
                symbols.add(re.escape(s))
            for n in props.get("names", []):
                suffixes.add(re.escape(n))
            suffixes.add(re.escape(code))

        symbol_pattern = build_alternation(list(symbols))
        suffix_pattern = build_alternation(list(suffixes))

        self.currency_pattern = re.compile(
            rf"(?:(?:{symbol_pattern})\s*\(?\s*\d+(?:\.\d+)?\s*\)?)|"
            rf"(?:\b\d+(?:\.\d+)?\s+(?:{suffix_pattern})\b)",
            re.IGNORECASE,
        )

    def clean(self, text: str) -> str:
        # split by double new lines
        paragraphs = text.split("\n\n")
        paragraphs = [p.strip() for p in paragraphs]
        texts = []
        for paragraph in paragraphs:
            paragraph = self.currency_pattern.sub(" ", paragraph)
            paragraph = clean_spaces_and_punctuation(paragraph)
            if paragraph:
                texts.append(paragraph)
        text = "\n\n".join(texts)
        return text


class ContextualNumberCleaner:
    """Remove non-employee numbers from Item 1 union/labor paragraphs.
    For example: We have 100 manufacturing facilities. There is 10% increase/decrease/growth. Decrease of 10%.
    """

    def __init__(self):

        # 1. Physical Assets / Facilities
        asset_terms = [
            r"facilit(?:y|ies)",
            r"plants?",
            r"offices?",
            r"cit(?:y|ies)",
            r"states?",
            r"locations?",
            r"stores?",
            r"branch(?:es)?",
            r"warehouses?",
            r"restuarants?",
            r"vehicles?",
            r"trucks?",
            r"auto(?:mobiles|s)?",
            r"distributions?",
            r"laborator(?:y|ies)",
            r"labs?",
            r"centers?",
            r"mines?",  # coal mines
            r"air(?:line|craft|port|plane)?s?",
        ]

        asset_pattern = build_alternation(asset_terms)
        worker_pattern = build_alternation(WORKER_TERMS + [r"members?"])

        # Define number and range patterns
        num = r"\d+(?:\.\d+)?"
        sep = r"\s*(?:-|to|–|—|of)\s*"

        # Captures: 10, 10-20, 10 to 20
        number_range = rf"{num}(?:{sep}{num})?"

        # Captures: 10%, 10-20%, 10 to 20%, 10%-20%
        percent_range = rf"{num}(?:\s*%?{sep}{num})?\s*%"

        # Matches: "100 [manufacturing] facilities"
        # Define an asset component as up to 2 intervening words + an asset term.
        # Allow the asset component to appear up to twice, joined by common
        # connectors (comma, and, &, /, or, -). This tightly constrains
        # what can be considered an asset phrase and avoids matching when
        # unrelated filler words appear.
        asset_comp = rf"(?:[\'\w-]+\s+){{0,2}}(?:{asset_pattern})"
        connectors = r"(?:\s*(?:,|and|&|/|or|-)\s*)"
        asset_chain = rf"{asset_comp}(?:{connectors}{asset_comp})?"

        # Do not strip the numeric if the asset_chain is immediately followed by
        # a worker term (e.g. "workers"). Also block if a worker term appears
        # AFTER a connector + a second asset component (e.g. "warehouse and
        # fulfillment center workers"). This restricts the negative lookahead to
        # only the directly relevant patterns instead of an arbitrary word window.
        next_worker_simple = rf"\s+(?:{worker_pattern})\b"
        next_worker_after_second = (
            rf"\s*(?:,|and|&|/|or|-)\s*(?:[\'\w-]+\s+){{0,2}}(?:{worker_pattern})\b"
        )
        combined_negative = rf"(?!{next_worker_simple}|{next_worker_after_second})"

        self.asset_regex = re.compile(
            rf"\b(?:{number_range}|{percent_range})\s+({asset_chain})\b{combined_negative}",
            re.IGNORECASE,
        )

        # 2. Union Patterns (CONSOLIDATED)
        # Handles:
        # - "5 unions" or "5 union" with optional labor/trade prefix
        # - Blocks patterns like "5 union members" or "5 union-represented"
        # - Matches at word boundaries or before punctuation
        union_prefixes = r"(?:(?:labor|trade)\s+)?"
        union_adj_blockers = build_alternation(
            WORKER_TERMS
            + [r"members?", r"represented", r"covered", r"based", r"affiliated"]
        )
        self.union_regex = re.compile(
            rf"\b{number_range}\s+((?:[\'\w-]+\s+){{0,1}}{union_prefixes}unions?)"
            rf"(?!(?:[\s-]+)(?:{union_adj_blockers}))"
            rf"(?=[,\.;\:\!\?]|\s|$)",
            re.IGNORECASE,
        )

        # Matches: "12 [separate] bargaining units", "12 [employee] bargaining units"
        # self.bargaining_unit_regex = re.compile(
        #     rf"\b{number_range}\s+((?:[\'\w-]+\s+){{0,5}}bargaining\s+units?)\b",
        #     re.IGNORECASE,
        # )

        change_pattern = build_alternation(CHANGE_TERMS)

        # Matches: "10% of the increase"
        self.change_pre_regex = re.compile(
            rf"\b{percent_range}((?:\s+[\'\w-]+){{0,2}}\s+{change_pattern})\b",
            re.IGNORECASE,
        )

        # Matches: "increase of approx 10%" or "increase by 10% to 30%"
        self.change_post_regex = re.compile(
            rf"\b({change_pattern})"
            rf"(?:\s+[\'<>\w-]+){{0,5}}\s+"  # allow N filler words
            rf"((?:{percent_range}|{number_range}\b)\s+"
            rf"(?:[\'<>\w-]+\s+){{0,4}})?"
            rf"(?:{percent_range}|{number_range}\b)",
            re.IGNORECASE,
        )

        personnel_event_pattern = build_alternation(
            PERSONNEL_EVENT_TERMS + [r"former", r"previous", r"past"]
        )

        # Matches: "furloughed [approx] 20000"
        self.personnel_event_regex = re.compile(
            rf"\b({personnel_event_pattern})"
            rf"(?:\s+[\'<>\w-]+){{0,8}}\s+"  # up to N filler words
            rf"(?:{number_range}|{percent_range})\b",
            re.IGNORECASE,
        )

        # 100 layoffs, etc
        self.personnel_event_reverse_regex = re.compile(
            rf"\b(?:{number_range}|{percent_range})"
            rf"(?:\s+[\'\w-]+){{0,8}}\s+"  # up to N filler words
            rf"({personnel_event_pattern})\b",
            re.IGNORECASE,
        )

        # 4. Time/Duration Patterns
        time_units = [
            r"years?",
            r"months?",
            r"weeks?",
            r"days?",
            r"quarters?",
            r"hrs?",
            r"hours?",
            r"annum",
            r"annual",
            r"periods?",
        ]
        time_unit_pattern = build_alternation(time_units)

        duration_context = [
            r"extensions?",
            r"contracts?",
            r"agreements?",
            r"periods?",
            r"terms?",
            r"durations?",
            r"renewals?",
            r"plans?",
            r"increas(?:e|es)?",
            r"decreas(?:e|es)?",
            r"pay",
            r"wages?",
            r"salary",
            r"rates?",
            r"formula",
            r"basis",
        ]
        duration_context_pattern = build_alternation(duration_context)

        # Matches: "3 year [contract]", "3-year [extension]", "0.25 per [hour]"
        self.duration_regex = re.compile(
            rf"\b(?:{number_range}|{percent_range})\s*(?:[-]|per)?\s*{time_unit_pattern}(?:\s+({duration_context_pattern}))?\b",
            re.IGNORECASE,
        )

        # 5. Subset Event Pattern (e.g. "of which 257 ... were on layoff")
        # Preserves the context ("of which", gap text, event) while removing the number.
        self.subset_event_regex = re.compile(
            rf"\b(of\s+(?:which|whom|those)|includ(?:ing|es?)|compris(?:ing|es?))\s+"
            rf"(?:{number_range}|{percent_range})"
            rf"([,\s]+(?:[\'\w-]+\s+){{0,15}})"
            rf"({personnel_event_pattern})\b",
            re.IGNORECASE,
        )

        # 6. Union Identifiers (e.g. "Local 140", "District 65")
        union_identifiers = [
            r"locals?",
            r"districts?",
            r"regions?",
            r"lodges?",
            r"councils?",
            r"chapters?",
            r"branches?",
            r"propositions?",  # California proposition
        ]
        union_id_pattern = build_alternation(union_identifiers)
        self.union_id_regex = re.compile(
            rf"\b({union_id_pattern})\s+(?:Union\s*)?(?:(?:No\.|#)\s*)?{number_range}\b",
            re.IGNORECASE,
        )

        # 7. Birth Year Patterns for Diversity Stats
        year_token = r"<\d{4}>"
        year_range = rf"{year_token}(?:\s*(?:-|–|—|to|and)\s*{year_token})?"
        born_context = r"\b(born|b\.)\b"
        born_qualifier = r"(?:before|after|between|from|at|since)?"

        # Captures "born", "born before", "born between" to preserve it
        born_prefix = rf"({born_context}(?:\s+{born_qualifier})?)"

        # Matches: "born <1965> - <1980>", "born before <1946>", "born between <1981> and <1996>"
        self.birth_year_regex = re.compile(
            rf"{born_prefix}\s+{year_range}", re.IGNORECASE
        )

        # 8. Diversity Percentages
        diversity_pattern = build_alternation(DIVERSITY_TERMS)

        # stripping union stats that happen to be near diversity terms.
        div_gap = r"(?:(?!(?:and|&)\b)[\'\w-]+\s+){0,10}"

        # Matches: "20% [of workforce are] women"
        self.diversity_pre_regex = re.compile(
            rf"\b{percent_range}\s+({div_gap}{diversity_pattern})\b", re.IGNORECASE
        )

        # Matches: "women [comprise] 20%"
        self.diversity_post_regex = re.compile(
            rf"\b({diversity_pattern}\s+{div_gap}){percent_range}", re.IGNORECASE
        )

        # 9. Remaining/Other Stripper
        # Matches: "1000 [remaining] employees" -> "1000 employees"
        self.remaining_cleaner_regex = re.compile(
            rf"\b({number_range})\s+(?:remaining|other)\b", re.IGNORECASE
        )

        # 10. Small Contract Counts (1-20) to prevent accidental ratio/count confusion
        contract_context = (
            r"(?:(?:labor|trade)\s+)?(?:(?:union|collective\s+bargaining)\s+)?"
        )
        contract_nouns = build_alternation(SUFFIX_AGREEMENTS + SUFFIX_ORGS + [r"cbas?"])

        self.small_contract_regex = re.compile(
            rf"\b(?:{number_range}|{percent_range})\s+((?:{contract_context})?{contract_nouns})\b",
            re.IGNORECASE,
        )

        # 11. Small digits followed by char (e.g. "4-S", "4 S")
        self.small_digit_pattern = re.compile(r"\b\d[\s-](?=[A-Za-z]\b)")

        # NEW: Expansion for St. -> Street to disambiguate from Saint
        # Look for TitleCase or Alphanumeric word before St.
        # Exclude common prepositions to avoid "In St. Louis" -> "In Street Louis"
        self.st_expansion_regex = re.compile(
            r"\b(?!(?:In|At|On|To|From|Of|With|By|For|The)\b)([A-Z0-9][\w]*)\s+St\.?\b",
        )

        street_terms = [
            r"ave(?:nue)?\.?",
            r"street",
            r"blvd\.?",
            r"boulevard",
            r"cir(?:cle)?\.?",
            r"court",
            r"ct\.?",
        ]

        other_terms_gap = [
            r"frameworks?",
            r"customers",
            r"suppliers?",
            r"products",
            r"disputes?",
            r"acres?",
            r"leases?",
            r"patents?",
            r"trademarks?",
            r"propert(?:y|ies)",
            r"squared?",
            r"sq\.?",
            r"km",
            r"meters",
            r"yards",
            r"miles?",
            r"kilometers?",
            r"feet",
            r"loans",
            r"debt",
        ] + street_terms

        other_terms_strict = [
            r"countr(?:y|ies)",
            r"regions?",
            r"cities",
            r"states",
            r"areas",
            r"units?",
            r"companies"
        ]

        # Boundary strategy:
        # - Terms without periods are wrapped in word boundaries.
        # - Terms with periods use a non-word/end lookahead instead of trailing \b.
        #   This avoids misses for tokens like "st." where \b after "." can fail.
        gap_terms_with_period = [t for t in other_terms_gap if r"\." in t]
        gap_terms_without_period = [t for t in other_terms_gap if r"\." not in t]

        gap_term_parts = []
        if gap_terms_without_period:
            gap_term_parts.append(rf"\b{build_alternation(gap_terms_without_period)}\b")
        if gap_terms_with_period:
            gap_term_parts.append(
                rf"(?:{build_alternation(gap_terms_with_period)})(?=\W|$)"
            )
        gap_term_pattern = build_alternation(gap_term_parts)

        strict_term_pattern = rf"\b{build_alternation(other_terms_strict)}\b"

        self.other_terms_regex = re.compile(
            rf"\b({number_range}|{percent_range})\s+((?:(?:[\'\w-]+\s+){{0,2}}(?:{gap_term_pattern}))|(?:{strict_term_pattern}))",
            re.IGNORECASE,
        )
        
        self.union_street_regex = build_regex(
            [
                build_compound(r"union", street_terms)
            ]
        )

        location_unit_terms = [
            r"floors?",
            r"apts?",
            r"apartments?",
            r"suites?",
            r"units?",
            r"rooms?",
            r"buildings?",
            r"bldgs?",
            r"box",
            r"routes?",
            r"highways?",
            r"interstate",
            r"p\.?o\.?\s*box",
            r"rooms?",
        ]
        self.location_unit_regex = re.compile(
            rf"\b({build_alternation(location_unit_terms)})\s+(?:#\.?\s*|no\.?\s*)?{number_range}\b",
            re.IGNORECASE,
        )

        # 12. Employee Groups (ERGs) - usually noise (e.g. "5 employee resource groups")
        erg_terms = [
            r"groups?",
            r"councils?",
        ]
        
        self.erg_regex = re.compile(
            rf"\b{number_range}\s+((?:[\'\w-]+\s+){{0,3}}{build_alternation(erg_terms)})\b",
            re.IGNORECASE,
        )

    def clean(self, text: str, home_country: Optional[str] = None) -> str:
        if not text:
            return ""

        def union_id_replacer(m):
            ident = m.group(1)
            # Default to US unless explicitly Canada
            suffix = "Canada" if home_country == "CA" else "US"
            return f" {ident} {suffix} "

        paragraphs = text.split("\n\n")
        paragraphs = [p.strip() for p in paragraphs]
        texts = []
        for paragraph in paragraphs:
            paragraph = self.asset_regex.sub(r" \1 ", paragraph)
            paragraph = self.subset_event_regex.sub(r" \1\2\3 ", paragraph)
            paragraph = self.change_pre_regex.sub(r" \1 ", paragraph)
            paragraph = self.change_post_regex.sub(r" \1 ", paragraph)
            paragraph = self.personnel_event_regex.sub(r" \1 ", paragraph)
            paragraph = self.personnel_event_reverse_regex.sub(r" \1 ", paragraph)
            paragraph = self.duration_regex.sub(r" \1 ", paragraph)
            paragraph = self.union_id_regex.sub(union_id_replacer, paragraph)
            paragraph = self.birth_year_regex.sub(r" \1 ", paragraph)
            paragraph = self.diversity_pre_regex.sub(r" \1 ", paragraph)
            paragraph = self.diversity_post_regex.sub(r" \1 ", paragraph)
            # paragraph = self.bargaining_unit_regex.sub(r" \1 ", paragraph)
            paragraph = self.union_regex.sub(
                r" \1 ", paragraph
            )  # CONSOLIDATED union pattern
            paragraph = self.remaining_cleaner_regex.sub(r" \1 ", paragraph)
            paragraph = self.small_contract_regex.sub(r" \1 ", paragraph)
            paragraph = self.small_digit_pattern.sub(" ", paragraph)
            paragraph = self.st_expansion_regex.sub(r"\1 Street", paragraph)
            paragraph = self.other_terms_regex.sub(r" \2 ", paragraph)
            paragraph = self.union_street_regex.sub(r" ", paragraph)
            paragraph = self.location_unit_regex.sub(r" \1 ", paragraph)
            paragraph = self.erg_regex.sub(r" \1 ", paragraph)
            paragraph = clean_spaces_and_punctuation(paragraph)
            if paragraph:
                texts.append(paragraph)

        return "\n\n".join(texts)


class ConcisenessCleaner:
    """
    Removes unnecessary words (articles, estimations) and simplifies verbose phrasing.
    Runs after other cleaners to prepare text for extraction.
    """

    def __init__(self):
        self.removal_regex = build_regex(
            [
                # r"herein",
                # r"thereof",
                # r"therein",
                # r"hereby",
                # r"whereby",
                # r"(?:dai|week|year)ly",
                # r"productions?",
                # r"facilit(?:y|ies)",
                # r"distributions?",
                # r"subsidiar(?:y|ies)",
                # r"fulfillments?",
                # r"propert(?:y|ies)",
                # r"stores?",
                # r"branch(?:es)?",

                # r"centers?",
                # r"addition(?:ally)?",
                # r"furthermore",
                # r"moreover",
                # r"particular(?:ly)?",
                # r"general(?:ly)?",
                # r"principally",
            ]
        )

        # Replacements (Long -> Short)
        self.replacements = [
            (re.compile(r"\bUS\s+GAAP\b", re.IGNORECASE), "GAAP"),
            (re.compile(r"\bUS\s+Dollars?\b", re.IGNORECASE), "USD"),
            (re.compile(r"\bUS\s+Treasur(?:y|ies)\b", re.IGNORECASE), "Treasury"),
            (re.compile(r"\bUS\s+Gov(?:ernment)?\b", re.IGNORECASE), "Government"),
            (re.compile(r"\bUS\s+SEC\b", re.IGNORECASE), "SEC"),
            (re.compile(r"\bUS\s+Code\b", re.IGNORECASE), "USC"),
            (
                re.compile(r"\bnon[- ]?domestic(?:ally)?\b", re.IGNORECASE),
                "international",
            ),
            (
                re.compile(
                    r"\b(non[- ](?:[\'\w-]+\s+){0,1})domestic\b", re.IGNORECASE
                ),
                r"\1",
            ),
        ]

        # Strip "international/national" from "labor unions" if union is lowercase
        # e.g. "international and national labor unions" -> "labor unions"
        modifiers = r"(?:(?:[Ii]nter)?[Nn]ational|(?:[Ii]n)?[Dd]ependent)"
        conjunctions = r"(?:\s*(?:and|or|&|,)\s*)"
        modifier_phrase = rf"{modifiers}(?:{conjunctions}{modifiers})*"

        self.replacements.append(
            (
                re.compile(rf"\b{modifier_phrase}\s+((?:[Ll]abor\s+)?unions?)\b"),
                r"\1",
            )
        )

        self.recap_pattern = re.compile(r"([.!?]\s+)([a-z])")
        self.leading_symbols = re.compile(r"^[\s\-\*•·>_,;!.\?]+", re.UNICODE)

    def clean(self, text: str) -> str:
        if not text:
            return ""
        paragraphs = text.split("\n\n")
        processed = []
        for p in paragraphs:
            p = p.strip()
            if not p:
                continue
            sentences = []
            for sent in SENTENCE_SPLIT_PATTERN.split(p):

                # Apply removals
                # sent = self.removal_regex.sub(" ", sent)

                # Apply replacements
                for pattern, replacement in self.replacements:
                    sent = pattern.sub(replacement, sent)
                sent = clean_spaces_and_punctuation(sent)
                sent = self.leading_symbols.sub("", sent).strip()
                if not sent:
                    continue
                sent = sent[0].upper() + sent[1:]
                sentences.append(sent.strip())

            processed.append(" ".join(sentences))

        return "\n\n".join(processed)

class CompanyCleaner:
    def __init__(self):
        self.cleaner = MinimalTextCleaner()
        # Regex to find potential company name occurrences in text (Title Case phrases)
        self.candidate_pattern = re.compile(
            r"\b[A-Z1-9][\w\-\']*(?:\s+(?:&|and|of|the|[A-Z][\w\-\']+))*\b"
        )
        self.numeric_firms_regex = None
        self.union_firms_regex = None
        self._numeric_firm_list = []  # Store list for fuzzy matching
        self._union_firm_list = []
        self._load_numeric_firms()

    def _load_numeric_firms(self):
        """Load numeric and union firms from CSV file."""
        candidates = [
            Path("numeric_firm_names.csv"),
            Path("union/numeric_firm_names.csv"),
            Path(__file__).parent.parent / "numeric_firm_names.csv"
        ]

        file_path = None
        for p in candidates:
            if p.exists():
                file_path = p
                break

        if not file_path:
            return

        numeric_names = set()
        union_names = set()
        numeric_list = []
        union_list = []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    name = row.get("core_name")
                    if name:
                        name = name.strip()
                        if len(name) < 3:
                            continue

                        # Remove punctuation to count words correctly
                        clean_name = re.sub(r'[^\w\s]', '', name)
                        tokens = clean_name.split()

                        is_union = any(t.lower() in ('union', 'unions') for t in tokens)

                        # Generate prefixes for partial matching
                        prefixes = {name}
                        if len(tokens) > 2:
                            parts = name.split()
                            for i in range(2, len(parts)):
                                prefix = " ".join(parts[:i])
                                prefix_lower = prefix.lower()
                                if prefix_lower in ["credit union", "labor union", "trade union", "european union", "soviet union"]:
                                    continue
                                if prefix_lower.endswith((" of", " and", " &", " for")):
                                    continue
                                prefixes.add(prefix)

                        if is_union:
                            if len(tokens) < 2:
                                continue

                            # Generate sliding windows for unions
                            # E.g., "Tri Union Development Corp" -> ["Tri Union Development Corp", "Tri Union Development", "Union Development Corp", "Union Development"]
                            union_windows = set(prefixes)

                            if len(tokens) >= 2:
                                parts = name.split()
                                # Generate all 2+ token windows
                                for start in range(len(parts)):
                                    for end in range(start + 2, len(parts) + 1):
                                        window = " ".join(parts[start:end])
                                        window_lower = window.lower()

                                        # Filter out generic/bad windows
                                        if window_lower in ["credit union", "labor union", "trade union", "european union", "soviet union"]:
                                            continue
                                        if window_lower.endswith((" of", " and", " &", " for")):
                                            continue

                                        union_windows.add(window)

                            for p in union_windows:
                                union_names.add(p)
                                union_list.append(p)
                        else:
                            # Numeric firms still use prefix matching
                            for p in prefixes:
                                numeric_names.add(p)
                                numeric_list.append(p)

        except Exception:
            pass

        # Store lists for fuzzy matching
        self._numeric_firm_list = numeric_list
        self._union_firm_list = union_list

        # Build regex patterns from flexible patterns
        if numeric_names:
            sorted_names = sorted(list(numeric_names), key=len, reverse=True)
            self.numeric_firms_regex = re.compile(
                r"\b(?:" + "|".join(sorted_names) + r")\b", re.IGNORECASE
            )

        if union_names:
            sorted_unions = sorted(list(union_names), key=len, reverse=True)
            self.union_firms_regex = re.compile(
                r"\b(?:" + "|".join(sorted_unions) + r")\b", re.IGNORECASE
            )

    def clean_numeric_names(self, text: str) -> str:
        """
        Clean numeric firm names (e.g., "Seven Eleven", "Six Flags").
        Uses both regex patterns and fuzzy matching to catch aliases/shortforms.
        Replaces with COMPANY_TOKEN, NOT with converted numbers.
        """
        # First pass: Exact pattern matching
        if self.numeric_firms_regex:
            def repl(m):
                val = m.group(0)
                # Enforce Title Case or All Caps or Digits to avoid lowercase false positives (e.g. "zero")
                if val[0].isupper() or val[0].isdigit():
                    return COMPANY_TOKEN
                return val
            text = self.numeric_firms_regex.sub(repl, text)

        # Second pass: Fuzzy match remaining Title Case phrases against numeric firm list
        # This catches aliases and shortforms not in the regex
        if self._numeric_firm_list:
            matches = list(self.candidate_pattern.finditer(text))
            replacements = []

            for m in matches:
                candidate = m.group(0)
                if len(candidate) < 2:
                    continue

                cand_lower = candidate.lower()

                # Check each numeric firm in the list for fuzzy match
                for firm_name in self._numeric_firm_list:
                    firm_lower = firm_name.lower()
                    ratio = difflib.SequenceMatcher(None, cand_lower, firm_lower).ratio()

                    # 0.85+ threshold for fuzzy match
                    if ratio >= 0.85:
                        replacements.append(m.span())
                        break

            # Apply replacements in reverse order to maintain indices
            for start, end in sorted(replacements, reverse=True):
                text = text[:start] + COMPANY_TOKEN + text[end:]

        return text

    def clean_union_firms(self, text: str) -> str:
        """
        Clean union firms with strict matching:
        - Exact regex pattern match (from CSV)
        - Searches for 2+ token windows that match union patterns
        - Title Case or All Caps enforcement
        - Does NOT use fuzzy matching for unions
        
        Example matches:
        - "Union Texas" → matches "Union Texas"
        - "Tri Union Development" → matches "Union Development"
        - "Shearson Union Square" → matches "Union Square"
        
        Non-matches:
        - "union employees" (lowercase)
        - "Union of X" (filtered out in _load_numeric_firms)
        """
        if not self.union_firms_regex:
            return text

        def repl(m):
            val = m.group(0)
            # Enforce Title Case or All Caps for Union matches
            # This prevents "union employees" (lowercase) from being replaced
            # while allowing "Union Texas" or "UNION TEXAS"
            if val[0].isupper():
                return COMPANY_TOKEN
            return val

        return self.union_firms_regex.sub(repl, text)

    def clean(self, text: str, company_name: Optional[str] = None) -> str:
        if not text:
            return text

        # 1. Clean standard numeric firms (Case Insensitive, with fuzzy matching)
        text = self.clean_numeric_names(text)

        # 2. Clean Union firms (Case Sensitive / Title Case enforced)
        text = self.clean_union_firms(text)

        if not company_name:
            return text

        # Normalize the company name (strip suffixes like Inc., Corp.)
        normalized_name = self.cleaner.normalize_company_name(company_name)
        if len(normalized_name) < 3:
            return text

        target_lower = normalized_name.lower()

        matches = list(self.candidate_pattern.finditer(text))
        replacements = []

        for m in matches:
            candidate = m.group(0)
            if len(candidate) < 2:
                continue

            cand_lower = candidate.lower()
            is_match = False

            # 1. Exact Match
            if cand_lower == target_lower:
                is_match = True
            # 2. Fuzzy Match
            elif difflib.SequenceMatcher(None, cand_lower, target_lower).ratio() >= 0.85:
                is_match = True
            # 3. Prefix Match (Shortened names)
            elif len(target_lower) > 4 and len(cand_lower) > 4:
                if target_lower.startswith(cand_lower) or cand_lower.startswith(target_lower):
                    is_match = True

            if is_match:
                replacements.append(m.span())

        # Apply replacements in reverse order to maintain indices
        out_text = text
        for start, end in reversed(replacements):
            out_text = out_text[:start] + COMPANY_TOKEN + out_text[end:]

        return out_text


# ============================================================================
# AUTOMATED TEST FRAMEWORK
# ============================================================================


class TestType(Enum):
    """Types of validation tests."""

    CONTAINS = "contains"  # Result must contain string
    NOT_CONTAINS = "not_contains"  # Result must not contain string
    EXACT = "exact"  # Result must be exact match
    REGEX = "regex"  # Result must match regex
    LENGTH_LESS = "length_less"  # Result length < expected
    LENGTH_GREATER = "length_greater"  # Result length > expected
    COUNT = "count"  # Count of pattern occurrences
    PROPERTY = "property"  # Custom property validation


@dataclass
class TestCase:
    """Represents a single test case."""

    name: str
    input_text: str
    company_name: Optional[str] = None
    reporting_year: Optional[int] = None
    validations: Optional[List[Tuple[TestType, str, any]]] = None  # type: ignore

    def __post_init__(self):
        if self.validations is None:
            self.validations = []


class TestValidator:
    """Validates cleaned text against expected transformations."""

    def __init__(self):
        self.cleaner = MinimalTextCleaner()
        self.results = []
        self.passed = 0
        self.failed = 0

    def add_validation(
        self,
        test_case: TestCase,
        test_type: TestType,
        pattern: str,
        expected_value: Optional[Any] = None,
    ) -> TestCase:  # type: ignore
        """Fluent API to add validation to a test case."""
        if test_case.validations is None:
            test_case.validations = []
        test_case.validations.append((test_type, pattern, expected_value))
        return test_case

    def run_test(self, test_case: TestCase) -> Dict:
        """Run a single test case and return results."""
        result = {
            "name": test_case.name,
            "input": test_case.input_text,
            "company_name": test_case.company_name,
            "output": None,
            "passed": True,
            "validations": [],
        }

        # Clean the text
        output = self.cleaner.clean(
            test_case.input_text, test_case.company_name, test_case.reporting_year
        )
        result["output"] = output

        assert test_case.validations is not None
        # Run all validations
        for test_type, pattern, expected_value in test_case.validations:
            validation_result = self._validate(
                output, test_type, pattern, expected_value
            )
            result["validations"].append(validation_result)

            if not validation_result["passed"]:
                result["passed"] = False

        return result

    def _validate(
        self, text: str, test_type: TestType, pattern: str, expected_value: Any
    ) -> Dict:  # type: ignore
        """Execute a single validation."""
        validation = {
            "type": test_type.value,
            "pattern": pattern,
            "passed": False,
            "message": "",
        }

        try:
            if test_type == TestType.CONTAINS:
                passed = pattern in text
                validation["passed"] = passed
                validation["message"] = f"{'✓' if passed else '✗'} Contains '{pattern}'"

            elif test_type == TestType.NOT_CONTAINS:
                passed = pattern not in text
                validation["passed"] = passed
                validation["message"] = (
                    f"{'✓' if passed else '✗'} Does not contain '{pattern}'"
                )

            elif test_type == TestType.EXACT:
                passed = text == pattern
                validation["passed"] = passed
                validation["message"] = f"{'✓' if passed else '✗'} Exact match"
                if not passed:
                    validation["message"] += f"\nExpected: {pattern}\nGot: {text}"

            elif test_type == TestType.REGEX:
                passed = bool(re.search(pattern, text))
                validation["passed"] = passed
                validation["message"] = (
                    f"{'✓' if passed else '✗'} Matches regex '{pattern}'"
                )

            elif test_type == TestType.LENGTH_LESS:
                passed = len(text) < expected_value
                validation["passed"] = passed
                validation["message"] = (
                    f"{'✓' if passed else '✗'} Length {len(text)} < {expected_value}"
                )

            elif test_type == TestType.LENGTH_GREATER:
                passed = len(text) > expected_value
                validation["passed"] = passed
                validation["message"] = (
                    f"{'✓' if passed else '✗'} Length {len(text)} > {expected_value}"
                )

            elif test_type == TestType.COUNT:
                count = len(re.findall(pattern, text, re.IGNORECASE))
                passed = count == expected_value
                validation["passed"] = passed
                validation["message"] = (
                    f"{'✓' if passed else '✗'} Pattern count: {count} (expected {expected_value})"
                )

        except Exception as e:
            validation["passed"] = False
            validation["message"] = f"✗ Error: {str(e)}"

        return validation

    def run_all_tests(self, test_cases: List[TestCase], debug: bool = False) -> bool:
        """Run all test cases and print results."""
        self.results = []
        self.passed = 0
        self.failed = 0

        print("\n" + "=" * 80)
        print("AUTOMATED TEXT CLEANER TEST SUITE")
        print("=" * 80 + "\n")

        for test_case in test_cases:
            result = self.run_test(test_case)
            self.results.append(result)

            # Count pass/fail
            if result["passed"]:
                self.passed += 1
                status = "✓ PASSED"
            else:
                self.failed += 1
                status = "✗ FAILED"

            # Print input/output
            if not result["passed"] or debug:
                # Print test header
                print(f"{status} | {result['name']}")
                print("-" * 80)
                print(
                    f"Input: {result['input'][:100]}..."
                    if len(result["input"]) > 100
                    else f"Input: {result['input']}"
                )
                print(
                    f"Output: {result['output'][:100]}..."
                    if len(result["output"]) > 100
                    else f"Output: {result['output']}"
                )

                # Print validation details
                if result["validations"]:
                    print("\nValidations:")
                    for v in result["validations"]:
                        print(f"  {v['message']}")

                print()

        # Summary
        print("=" * 80)
        print(
            f"SUMMARY: {self.passed} passed, {self.failed} failed out of {len(test_cases)} tests"
        )
        print("=" * 80 + "\n")

        return self.failed == 0


# ============================================================================
# TEST CASES
# ============================================================================


def create_test_cases() -> List[TestCase]:
    """Create comprehensive test cases."""
    return [
        # Test 1: Company Name Replacement
        TestCase(
            name="Company Name Replacement",
            input_text="Johnson & Johnson Corporation is a leading company. Johnson & Johnson was founded long ago.",
            company_name="Johnson & Johnson Corporation",
            validations=[
                (TestType.CONTAINS, "The Company", None),
                (TestType.COUNT, r"the Company", 2),
                (TestType.NOT_CONTAINS, "Johnson & Johnson Corporation", None),
            ],
        ),
        # Test 2: Date Removal (Month Day format)
        TestCase(
            name="Date Removal - Month Day Format",
            input_text="As of December 31, 2023, we had significant growth.",
            validations=[
                (TestType.NOT_CONTAINS, "December 31", None),
                (TestType.CONTAINS, "we had significant growth", None),
            ],
        ),
        # Test 3: Date Removal (Day Month format)
        TestCase(
            name="Date Removal - Day Month Format",
            input_text="On the 15th of July, we announced new products.",
            validations=[
                (TestType.NOT_CONTAINS, "15th of July", None),
                (TestType.CONTAINS, "we announced new products", None),
            ],
        ),
        # Test 4: Year Wrapping
        TestCase(
            name="Year Wrapping",
            input_text="In 2023 and 1999, we made significant investments.",
            validations=[
                (TestType.CONTAINS, "<2023>", None),
                (TestType.CONTAINS, "<1999>", None),
            ],
        ),
        # Test 5: Word Numbers to Digits
        TestCase(
            name="Word Numbers to Digits",
            input_text="We have 5 million dollars and two employees.",
            validations=[
                (TestType.CONTAINS, "5000000", None),
                (TestType.NOT_CONTAINS, "5 million", None),
                (TestType.CONTAINS, "2", None),
            ],
        ),
        # Test 6: Fraction to Percentage
        TestCase(
            name="Fraction to Percentage",
            input_text="Approximately three-fourths of our staff are satisfied.",
            validations=[
                (TestType.CONTAINS, "75%", None),
                (TestType.NOT_CONTAINS, "three-fourths", None),
            ],
        ),
        # Test 7: Scale Numbers (numbers with scale words)
        TestCase(
            name="Scale Numbers",
            input_text="We invested 2 million dollars and earned 500 thousand dollars.",
            validations=[
                (TestType.CONTAINS, "2000000", None),
                (TestType.CONTAINS, "500000", None),
            ],
        ),
        # Test 8: Comma Removal in Numbers
        TestCase(
            name="Comma Removal",
            input_text="The company has 138,100 employees worldwide.",
            validations=[
                (TestType.CONTAINS, "138100", None),
                (TestType.NOT_CONTAINS, "138,100", None),
            ],
        ),
        # Test 9: Suffix Removal
        TestCase(
            name="Suffix Removal",
            input_text="Our subsidiaries include ABC Inc., XYZ Corp., and 123 Ltd.",
            validations=[
                (TestType.NOT_CONTAINS, "Inc.", None),
                (TestType.NOT_CONTAINS, "Corp.", None),
                (TestType.NOT_CONTAINS, "Ltd.", None),
            ],
        ),
        # Test 10: False Positive Prevention (Credit Union)
        TestCase(
            name="False Positive - Credit Union",
            input_text="We have partnerships with credit unions and banks.",
            validations=[
                (TestType.CONTAINS, "bank", None),
                (TestType.NOT_CONTAINS, "union", None),
            ],
        ),
        # Test 11: False Positive Prevention (European Union)
        TestCase(
            name="False Positive - European Union",
            input_text="The European Union has strict regulations.",
            validations=[
                (TestType.CONTAINS, "EU", None),
                (TestType.NOT_CONTAINS, "European Union", None),
            ],
        ),
        # Test 12: Percent Normalization
        TestCase(
            name="Percent Normalization",
            input_text="Sales increased by 25 % and costs rose 10 per cent.",
            validations=[
                (TestType.NOT_CONTAINS, "25 %", None),
                (TestType.CONTAINS, "25%", None),
                (TestType.NOT_CONTAINS, "per cent", None),
                (TestType.CONTAINS, "10%", None),
            ],
        ),
        # Test 13: Whitespace Normalization
        TestCase(
            name="Whitespace Normalization",
            input_text="The   company   has   multiple    spaces   between    words.",
            validations=[
                (TestType.NOT_CONTAINS, "   ", None),
                (
                    TestType.CONTAINS,
                    "The company has multiple spaces between words",
                    None,
                ),
            ],
        ),
        # Test 14: Month-only Removal
        TestCase(
            name="Month Only Removal",
            input_text="In January we launched products, and in February we expanded.",
            validations=[
                (TestType.NOT_CONTAINS, "January", None),
                (TestType.NOT_CONTAINS, "February", None),
                (TestType.CONTAINS, "we launched products", None),
            ],
        ),
        # Test 15: Complex Text (Integration)
        TestCase(
            name="Complex Integration Test",
            input_text="Apple Inc. reported 138,100 employees on December 31, 2023. Approximately one half of staff work in the European Union earning 5 million dollars per year at 25 percent bonus.",
            company_name="Apple Inc.",
            validations=[
                (TestType.CONTAINS, "The Company", None),
                (TestType.NOT_CONTAINS, "The Company.", None),
                (TestType.NOT_CONTAINS, "The Company .", None),
                (TestType.CONTAINS, "138100", None),
                (TestType.CONTAINS, "<2023>", None),
                (TestType.NOT_CONTAINS, "December 31", None),
                (TestType.CONTAINS, "50%", None),
                (TestType.CONTAINS, "Europe", None),
                (TestType.CONTAINS, "5000000", None),
                (TestType.CONTAINS, "25%", None),
            ],
        ),
        TestCase(
            name="First Quarter (Business Period)",
            input_text="In the first quarter of 2023, we grew rapidly.",
            validations=[
                (TestType.CONTAINS, "first quarter", None),  # Should NOT be converted
                (TestType.NOT_CONTAINS, "25%", None),  # Should not convert to percent
            ],
        ),
        TestCase(
            name="Reference removal",
            input_text="Exhibit 5, Statement No. 10, Figure 2, Item 1. 55 employees",
            validations=[
                (TestType.NOT_CONTAINS, "Exhibit 5", None),
                (TestType.NOT_CONTAINS, "Statement No. 10", None),
                (TestType.NOT_CONTAINS, "Figure 2", None),
                (TestType.NOT_CONTAINS, "Item 1", None),
                (TestType.CONTAINS, "55", None),
            ],
        ),
        TestCase(
            name="Fourth Quarter (Business Period)",
            input_text="Fourth quarter earnings were strong.",
            validations=[
                (TestType.CONTAINS, "Fourth quarter", None),  # Should NOT be converted
                (TestType.NOT_CONTAINS, "25%", None),
            ],
        ),
        TestCase(
            name="Q2/Q3 Format",
            input_text="We saw growth in the second quarter and third quarter.",
            validations=[
                (TestType.CONTAINS, "second quarter", None),  # Should NOT be converted
                (TestType.CONTAINS, "third quarter", None),  # Should NOT be converted
                (TestType.NOT_CONTAINS, "50%", None),
                (TestType.NOT_CONTAINS, "75%", None),
            ],
        ),
        # Test 16: Edge case - Empty string
        TestCase(
            name="Edge Case - Empty String",
            input_text="",
            validations=[
                (TestType.EXACT, "", None),
            ],
        ),
        # Ordinal numbers (should NOT convert)
        TestCase(
            name="Ordinals - First, Second, Third",
            input_text="First, second, and third place finishers.",
            validations=[
                (TestType.CONTAINS, "First", None),
                (TestType.CONTAINS, "second", None),
                (TestType.CONTAINS, "third", None),
            ],
        ),
        # Business quarters (should NOT convert)
        TestCase(
            name="Business Quarters Q1-Q4",
            input_text="Q1 results, Q2 earnings, third quarter report, fourth quarter.",
            validations=[
                (TestType.CONTAINS, "quarter", None),
                (TestType.NOT_CONTAINS, "25%", None),
                (TestType.NOT_CONTAINS, "75%", None),
            ],
        ),
        # Time periods (should NOT convert)
        TestCase(
            name="Time Periods - Half Year",
            input_text="first half and second half of year.",
            validations=[
                (TestType.CONTAINS, "first half", None),
                (TestType.CONTAINS, "second half", None),
            ],
        ),
        # Clear fractions (SHOULD convert)
        TestCase(
            name="Clear Fractions",
            input_text="One half, one third, one fourth, three-fourths.",
            validations=[
                (TestType.NOT_CONTAINS, "one half", None),  # Converted
                (TestType.NOT_CONTAINS, "one third", None),  # Converted
                (TestType.NOT_CONTAINS, "one fourth", None),  # Converted
                (TestType.NOT_CONTAINS, "three-fourths", None),  # Converted
            ],
        ),
        # Test 17: Edge case - No changes needed
        TestCase(
            name="Edge Case - No Changes",
            input_text="The business operates in multiple countries.",
            validations=[
                (TestType.CONTAINS, "The business operates", None),
            ],
        ),
        # Test 18: Standalone Fractions (Half Only)
        TestCase(
            name="Standalone Fractions",
            input_text="Half of our employees and a quarter of the staff.",
            validations=[
                (TestType.CONTAINS, "50%", None),
                (TestType.CONTAINS, "25%", None),
            ],
        ),
        # Test 19: Protected Time Periods
        TestCase(
            name="Protected Time Periods",
            input_text="In the first half of the year, fiscal quarter results were good. Third year of operation.",
            validations=[
                (TestType.CONTAINS, "first half", None),
                (TestType.NOT_CONTAINS, "50%", None),
                (TestType.CONTAINS, "fiscal quarter", None),
                (TestType.NOT_CONTAINS, "25%", None),
                (TestType.CONTAINS, "Third year", None),
                (TestType.NOT_CONTAINS, "33.33%", None),
            ],
        ),
        # Test 20: Extended False Fractions
        TestCase(
            name="Extended False Fractions",
            input_text="Results for the quarter of the reporting period were solid. Also for the half of the fiscal year.",
            validations=[
                (TestType.CONTAINS, "quarter of the reporting period", None),
                (TestType.NOT_CONTAINS, "25%", None),
                (TestType.CONTAINS, "half of the fiscal year", None),
                (TestType.NOT_CONTAINS, "50%", None),
            ],
        ),
        # Test 21: Financial Periods (YTD, YoY)
        TestCase(
            name="Financial Periods",
            input_text="quarter-to-date, year-to-date, quarter-over-quarter, quarter-end.",
            validations=[
                (TestType.CONTAINS, "quarter-to-date", None),
                (TestType.NOT_CONTAINS, "25%", None),
                (TestType.CONTAINS, "year-to-date", None),
                (TestType.CONTAINS, "quarter-over-quarter", None),
                (TestType.CONTAINS, "quarter-end", None),
            ],
        ),
        # Test 22: "A" Fraction with "of"
        TestCase(
            name="'A' Fraction with 'of'",
            input_text="We have a quarter of the market, a third of the votes, and a fifth of the revenue. I found a quarter on the ground.",
            validations=[
                (TestType.CONTAINS, "25%", None),
                (TestType.CONTAINS, "33.33", None),
                (TestType.CONTAINS, "20%", None),
                (TestType.CONTAINS, "a quarter on the ground", None),
            ],
        ),
        # Test 23: Bullets and Exhibits (even if the numbers are converted, exhibit pattern to clean up)
        TestCase(
            name="Bullets and Exhibits",
            input_text="(b)(1) 1. Item 1-2. (2) Item 39.52. a. Item a. (b) Item b. i. Item i. 10-20 range. (2023) Year 512.",
            validations=[
                (TestType.NOT_CONTAINS, "1.", None),
                (TestType.NOT_CONTAINS, "1-2", None),
                (TestType.NOT_CONTAINS, "39.52", None),
                (TestType.NOT_CONTAINS, "(2)", None),
                (TestType.NOT_CONTAINS, "a.", None),
                (TestType.NOT_CONTAINS, "(b)", None),
                (TestType.NOT_CONTAINS, "i.", None),
                (TestType.CONTAINS, "<2023>", None),
                (TestType.NOT_CONTAINS, "Item one", None),
                (TestType.CONTAINS, "range", None),
                (TestType.CONTAINS, "Year", None),
                (TestType.CONTAINS, "512", None),
            ],
        ),
        # Test 24: Protected Years and Acronyms
        TestCase(
            name="Protected Years and Acronyms",
            input_text="2023. Year. 2023-2024 Range. U.S. Policy. i.e. example.",
            validations=[
                (TestType.CONTAINS, "<2023>", None),
                (TestType.CONTAINS, "<2024>", None),
                (TestType.CONTAINS, "US", None),
                (TestType.CONTAINS, "i.e.", None),
            ],
        ),
        # Test 24b: Year Range Short (2023-24)
        TestCase(
            name="Year Range Short",
            input_text="During the 2023-24 fiscal year.",
            validations=[
                (TestType.CONTAINS, "<2023>", None),
                (TestType.NOT_CONTAINS, "-24", None),
            ],
        ),
        # Test 25: None of -> 0% of, All are -> 100%
        TestCase(
            name="None of -> 0% of",
            input_text="None of our employees are unionized. Second to none. All are unionized. Not all of them. All office workers.",
            validations=[
                (TestType.CONTAINS, "0% of our employees", None),
                (TestType.CONTAINS, "Second to none", None),
                (TestType.CONTAINS, "Some", None),
            ],
        ),
        # Test 26: Pronoun Replacement
        TestCase(
            name="Pronoun Replacement",
            input_text="We believe our employees are vital. Contact us.",
            validations=[
                (TestType.CONTAINS, "We believe", None),
                (TestType.CONTAINS, "Contact the Company", None),
            ],
        ),
        # Test 27: No Workers -> 0 Workers
        TestCase(
            name="No Workers -> 0 Workers",
            input_text="We have no employees and no unionized workers. no full-time staff.",
            validations=[
                (TestType.CONTAINS, "0 employees", None),
                (TestType.CONTAINS, "0 unionized workers", None),
                (TestType.CONTAINS, "0 full-time staff", None),
            ],
        ),
        # Test 28: Capitalize "the" at start of sentence
        TestCase(
            name="Capitalize 'the' at start",
            input_text="the Company is here. apple inc. reported results.",
            company_name="Apple Inc.",
            validations=[
                (
                    TestType.CONTAINS,
                    "The Company is here. The Company reported results.",
                    None,
                ),
            ],
        ),
        # Test 29: Punctuation Cleanup
        TestCase(
            name="Punctuation Cleanup",
            input_text="Word . Word , word .. word ,, word . . word",
            validations=[
                (TestType.EXACT, "Word. Word, word. word, word. word", None),
            ],
        ),
        # Test 30: Page Artifact Removal
        TestCase(
            name="Page Artifact Removal",
            input_text="End of page. 2 <PAGE> 7 Start of next page.",
            validations=[
                (TestType.NOT_CONTAINS, "<PAGE>", None),
                (TestType.NOT_CONTAINS, "2", None),
                (TestType.NOT_CONTAINS, "7", None),
            ],
        ),
        # Test 31: Covid Normalization
        TestCase(
            name="Covid Normalization",
            input_text="Due to Covid-19, COVID 19, and Coronavirus impacts.",
            validations=[
                (TestType.CONTAINS, "Due to covid, covid, and covid impacts.", None),
            ],
        ),
        # Test 32: Page Number Removal
        TestCase(
            name="Page Number Removal",
            input_text="Text 4- text -4- text 10- text -100- text 10-20 text 10-year.",
            validations=[
                (TestType.NOT_CONTAINS, "4-", None),
                (TestType.NOT_CONTAINS, "-4-", None),
                (TestType.NOT_CONTAINS, "10- ", None),
                (TestType.NOT_CONTAINS, "-100-", None),
                (TestType.CONTAINS, "10-20", None),
                (TestType.CONTAINS, "10-year", None),
            ],
        ),
        # Test 33: Float Removal
        TestCase(
            name="Float Removal",
            input_text="We have 1.5 issues and 10.00 problems but 25.5% growth and 100 employees.",
            validations=[
                (TestType.NOT_CONTAINS, "1.5", None),
                (TestType.NOT_CONTAINS, "10.00", None),
                (TestType.CONTAINS, "25.5%", None),
                (TestType.CONTAINS, "100", None),
            ],
        ),
        # Test 34: Numeric Company Name Protection
        TestCase(
            name="Numeric Company Name Protection",
            input_text="Ten Corp announced results. Ten employees were hired.",
            company_name="Ten Corp",
            validations=[
                (TestType.CONTAINS, "The Company announced", None),
                (TestType.CONTAINS, "Ten employees", None),
            ],
        ),
        # Test 35: Non-Domestic Mapping
        TestCase(
            name="Non-Domestic Mapping",
            input_text="We have non-domestic operations and non-US domestic sales.",
            validations=[
                (TestType.CONTAINS, "international operations", None),
                (TestType.CONTAINS, "non-US sales", None),
                (TestType.NOT_CONTAINS, "domestic sales", None),
            ],
        ),
    ]


def run_tests():
    """Run the test suite."""
    test_cases = create_test_cases()
    validator = TestValidator()
    all_passed = validator.run_all_tests(test_cases, debug=False)

    return 0 if all_passed else 1
