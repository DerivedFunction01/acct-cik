from derivative_regex import LOOSE_GEN_REGEX, TERMINATION_ALL_REGEX, YEAR_REGEX
from prefiltered_lib import MinimalTextCleaner

_cleaner = MinimalTextCleaner()

def check_future_maturity(
    text: str, reporting_year: int
) -> bool:
    """
    Determines if text represents Strong Evidence of Future Maturity (MAT_FUT).

    Logic:
    1. Must mention a Termination Keyword (Verb or Noun).
    2. Must mention a Future Year (> reporting_year).
    """
    if not reporting_year:
        return False

    # 1. Check Topic (Fastest Fail)
    if not TERMINATION_ALL_REGEX.search(text):
        return False
    
    text = _cleaner.clean_numerics(text, remove_years=False)
    if not LOOSE_GEN_REGEX.search(text): # No mention of swap, contract, etc
        return False
    # 2. Check Time
    # Extract years and check if ANY is in the future
    # Note: We use clean_numerics logic implicitly or caller handles cleaning
    years = [int(y) for y in YEAR_REGEX.findall(text)]

    if not years:
        return False

    has_future_year = any(y > reporting_year for y in years)

    return has_future_year
