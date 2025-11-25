import re
import sys
from typing import Dict, List, Tuple

# Assume derivative_regex.py is correctly imported and available
try:
    from derivative_regex import (
        IR_REGEX,
        FX_REGEX,
        CP_REGEX,
        EQ_REGEX,
        GEN_REGEX,
    )
except ImportError:
    print("Error: Could not import from derivative_regex.py")
    print("Ensure derivative_regex.py is in the execution path.")
    sys.exit(1)

# =============================================================================
# 1. INSTRUMENT & TEMPLATE DEFINITIONS
# =============================================================================

# Pool of instruments from simple to complex for each category.
# The string itself is the expected longest match for the regex.
INSTRUMENTS: Dict[str, List[str]] = {
    "ir": [
        "interest rate swap",
        "fixed-rate swap agreement",
        "SOFR-based cap",
        "treasury lock contract",
        "pay fixed, receive floating swap agreement",  # Critical complex descriptive structure
        "zero coupon swap",
        "credit default swap",
        "FRA",
    ],
    "fx": [
        "foreign currency forward",
        "FX forward contract",
        "cross currency swap agreement",
        "USD/EUR forward",
        "non-deliverable forward",
        "currency option",
    ],
    "cp": [
        "commodity swap",
        "crude oil futures contract",
        "natural gas swap agreement",
        "power purchase agreement",
        "weather derivative",
        "commodity call option",
    ],
    "eq": [
        "equity swap",
        "stock option contract",
        "warrant liability",
        "embedded conversion option",
        "equity forward agreement",
    ],
}

# Generic hedging/context phrases (placeholder {instr} is replaced)
HEDGING_TEMPLATES: List[str] = [
    "We use {instr} to hedge our exposure.",
    "The company entered into {instr}.",
    "We hold {instr} on our floating rate debt.",
    "We designated {instr} as cash flow hedges.",
    "We execute {instr} for hedging purposes.",
    "Outstanding {instr} are marked to fair value.",
]

# Specific generic phrases where the expected match needs careful definition
GENERIC_PHRASES: List[Tuple[str, str]] = [
    ("The company uses derivatives for hedging.", "derivatives"),
    ("We designated hedging instruments as cash flow hedges.", "cash flow hedges"),
    ("Derivative contracts are recorded at fair value.", "Derivative contracts"),
    (
        "Notional amounts for cap contracts do not represent actual risk exposure.",
        "cap contracts",
    ),
]

# =============================================================================
# 2. DATA GENERATION LOGIC
# =============================================================================


def generate_verification_data() -> Dict[str, List[Tuple[str, str]]]:
    """Generate structured test phrases with their expected MAX MUNCH match."""
    TEST_DATA: Dict[str, List[Tuple[str, str]]] = {}

    # 1. Start with Generic Phrases
    TEST_DATA["gen"] = GENERIC_PHRASES.copy()

    # 2. Generate Category-Specific Phrases
    for category, instruments in INSTRUMENTS.items():
        cat_tests = []
        for instr in instruments:
            expected_match = (
                instr  # The instrument itself is the expected longest match
            )

            for template in HEDGING_TEMPLATES:
                # Replace placeholder
                phrase = template.format(instr=instr)
                cat_tests.append((phrase, expected_match))

            # Add non-templated realistic variants
            cat_tests.extend(
                [
                    (
                        f"We have {instr} outstanding with notional of $500 million.",
                        expected_match,
                    ),
                    (
                        f"The fair value of our {instr} increased this quarter.",
                        expected_match,
                    ),
                    (
                        f"{instr.title()} are used to mitigate currency translation risk.",
                        expected_match,
                    ),
                ]
            )

        # Dedupe and limit per category
        seen = set()
        deduped = []
        for p, m in cat_tests:
            if p not in seen:
                seen.add(p)
                deduped.append((p, m))

        # Limit to 20 tests per category for manageable output
        TEST_DATA[category] = deduped[:20]

    return TEST_DATA


# Generate the final test data map
TEST_DATA = generate_verification_data()

# Regexes map for test function access
REGEXES = {
    "ir": IR_REGEX,
    "fx": FX_REGEX,
    "cp": CP_REGEX,
    "eq": EQ_REGEX,
    "gen": GEN_REGEX,
}

# =============================================================================
# 3. AUTOMATIC VERIFICATION FUNCTION
# =============================================================================


def test_auto_verification(
    category: str, phrase: str, expected_match: str
) -> Tuple[bool, str]:
    """
    Tests a single phrase against its corresponding regex and verifies the longest match.
    """
    regex = REGEXES.get(category)
    if not regex:
        return False, f"Category '{category.upper()}' has no defined regex."

    # Use search() to find the single, longest match (Maximum Munch)
    match = regex.search(phrase)

    expected_clean = expected_match.strip().lower()

    if not match:
        return False, f"No match found. Expected: '{expected_clean}'"

    # Clean the matched text for comparison
    matched_text = match.group(0).strip().lower()

    # Assert that the matched text equals the expected match
    if matched_text == expected_clean:
        return True, f"Matched: '{matched_text}'"
    else:
        # Show what was matched if it was wrong
        return False, f"Mismatched. Expected: '{expected_clean}', Got: '{matched_text}'"


def run_test_suite() -> None:
    """Runs all automatic verification tests and prints a summary."""
    total_tests = 0
    total_passed = 0

    print("\n" + "=" * 80)
    print("🚀 AUTOMATIC REGEX VERIFICATION TEST SUITE (Max Munch Check)")
    print("=" * 80)

    for category, tests in TEST_DATA.items():
        print(f"\n--- {category.upper()} ({len(tests)} cases) ---")

        for i, (phrase, expected_match) in enumerate(tests, 1):
            total_tests += 1
            passed, result_message = test_auto_verification(
                category, phrase, expected_match
            )

            if passed:
                total_passed += 1
                status = "✓ PASS"
            else:
                status = "✗ FAIL"

            print(f"[{status}] Case {i}: {phrase}")
            print(f"         {result_message}")

    print("\n" + "=" * 80)
    print("📊 TEST SUMMARY")
    print(f"   Total Tests Run: {total_tests}")
    print(f"   Tests Passed:  {total_passed}")
    print(f"   Tests Failed:  {total_tests - total_passed}")
    print("=" * 80)

    if total_tests == total_passed:
        print("🎉 ALL TESTS PASSED SUCCESSFULLY! The Maximum Munch is preserved.")
    else:
        print("⚠️ FAILURE DETECTED. Review FAIL cases to fix regex ordering or design.")


# =============================================================================
# MAIN EXECUTION
# =============================================================================

if __name__ == "__main__":
    run_test_suite()
