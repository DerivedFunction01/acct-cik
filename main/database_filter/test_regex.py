import re
import sys
from typing import Dict, List, Tuple, Set

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
# 1. DYNAMIC INSTRUMENT GENERATORS
# =============================================================================


class InstrumentGenerator:
    """Dynamically generates realistic derivative instrument phrases."""

    IR_BASES = ["swap", "forward", "cap", "floor", "collar", "swaption", "lock"]
    IR_RATES = [
        "interest rate",
        "fixed rate",
        "floating rate",
        "SOFR",
        "LIBOR",
        "treasury",
    ]
    IR_BENCHMARKS = ["SOFR", "SONIA", "LIBOR", "EURIBOR", "ESTR"]

    FX_CURRENCIES = ["USD", "EUR", "JPY", "GBP", "AUD", "CAD", "CHF"]
    FX_BASES = ["forward", "swap", "option"]
    FX_DESCRIPTORS = ["cross-currency", "foreign currency", "non-deliverable"]

    CP_COMMODITIES = [
        "crude oil",
        "natural gas",
        "copper",
        "gold",
        "wheat",
        "electricity",
    ]
    CP_BASES = ["swap", "futures", "forward", "option"]
    CP_DESCRIPTORS = ["price", "spread", "index"]

    EQ_INDICES = ["S&P 500", "Nasdaq", "Dow Jones", "Russell 2000", "FTSE 100"]
    EQ_BASES = ["swap", "option", "forward", "warrant"]
    EQ_DESCRIPTORS = ["equity", "stock price", "market index"]

    SUFFIXES = ["agreement", "contract", "arrangement", "instrument"]

    @staticmethod
    def generate_ir_instruments() -> List[str]:
        """Generate diverse IR instruments."""
        instruments = [
            # Simple base instruments
            "interest rate swap",
            "interest rate cap",
            "interest rate floor",
            "SOFR swap",
            "LIBOR forward",
            "treasury lock",
            # With suffixes
            "interest rate swap agreement",
            "fixed rate swap contract",
            "floating rate cap agreement",
            "SOFR-based cap contract",
            "treasury lock agreement",
            # Complex descriptive
            "pay fixed, receive floating swap",
            "pay fixed, receive floating interest rate swap agreement",
            "pay variable, receive fixed swap contract",
            # Specific types
            "zero coupon swap",
            "credit default swap",
            "overnight index swap",
            "FRA",
        ]
        return list(set(instruments))  # Dedupe

    @staticmethod
    def generate_fx_instruments() -> List[str]:
        """Generate diverse FX instruments."""
        instruments = [
            # Simple base instruments
            "foreign currency forward",
            "FX forward",
            "currency swap",
            "currency option",
            "non-deliverable forward",
            # With suffixes
            "foreign currency forward contract",
            "FX forward agreement",
            "cross-currency swap agreement",
            "currency option contract",
            "non-deliverable forward arrangement",
            # Code-specific
            "USD swap",  # Testing the new safe currency match
            "EUR forward contract",  # Testing currency code + suffix
            # Complex descriptive
            "cross-currency swap",
            "cross-currency basis swap",
            "multi-currency forward",
            "hedge of net investment",
        ]
        return list(set(instruments))

    @staticmethod
    def generate_cp_instruments() -> List[str]:
        """Generate diverse Commodity instruments."""
        instruments = [
            # Simple base instruments
            "commodity swap",
            "commodity futures",
            "commodity forward",
            "commodity option",
            # With suffixes
            "commodity swap agreement",
            "commodity futures contract",
            "commodity forward arrangement",
            "commodity call option",
            # Specific commodities
            "crude oil swap",
            "natural gas forward",
            "copper futures contract",
            "gold swap agreement",
            # With price descriptors
            "crude oil price swap",
            "natural gas price forward",
            "copper price option",
            # Spreads
            "crack spread swap",
            "spark spread derivative",
            "dark spread contract",
            # Complex
            "power purchase agreement",
            "virtual power purchase agreement",
            "weather derivative",
        ]
        return list(set(instruments))

    @staticmethod
    def generate_eq_instruments() -> List[str]:
        """Generate diverse Equity instruments."""
        instruments = [
            # Simple base instruments
            "equity swap",
            "equity option",
            "equity forward",
            # With suffixes
            "equity swap agreement",
            "equity option contract",
            "equity forward arrangement",
            # Index-specific
            "S&P 500 swap",
            "Nasdaq forward",
            "Dow Jones option",
            "S&P 500 total return swap",
            # Complex structural
            "embedded conversion option",
            "conversion option liability",
            "warrant liability",
            "bifurcated conversion option",
            "derivative warrant",
            "warrant classified as derivative liability",
        ]
        return list(set(instruments))

    @staticmethod
    def generate_gen_instruments() -> List[str]:
        """Generate generic/unspecialized instruments."""
        instruments = [
            "derivative",
            "derivative contract",
            "derivative instrument",
            "hedging instrument",
            "cash flow hedge",
            "fair value hedge",
            "over-the-counter derivative",
            "derivative financial instrument",
            "call option",
            "put option",
            "swaption",
        ]
        return list(set(instruments))

    @staticmethod
    def generate_fp_instruments() -> List[str]:
        """Generate non-derivative terms that could be false positives."""
        return [
            # General Legal/Corporate FPs
            "Employment agreement",
            "Services contract",
            "License agreement",
            # Currency FPs (simple trade/loan)
            "Intercompany currency arrangement",
            "Foreign exchange service agreement",
            "Trade contract",
            "Currency purchase agreement",
            # Equity FPs (non-derivative)
            "Stock option plan",  # Not a derivative liability
            "Subscription agreement",
            "Share purchase contract",
            "Equity financing agreement",
            # Commodity FPs (physical delivery)
            "Crude oil purchase contract",
            "Natural gas sales agreement",
            "Power supply agreement",
            "Electricity contract",
            # Rate FPs (simple loans/debt)
            "Fixed rate loan agreement",
            "Floating rate note",
            "Interest payment arrangement",
        ]


# =============================================================================
# 2. ENHANCED TEST DATA GENERATION (FIXED FOR REDUNDANCY)
# =============================================================================


def generate_verification_data() -> Dict[str, List[Tuple[str, str]]]:
    """Generate structured test phrases with dynamic instruments."""
    TEST_DATA: Dict[str, List[Tuple[str, str]]] = {}

    # Template 1: Bare instrument (ideal for strict Max Munch test)
    SIMPLE_TEMPLATE: str = "{instr}"
    # Template 2: Instrument in simple context (used for cross-validation)
    SIMPLE_CONTEXT_TEMPLATE: str = "We use {instr} to hedge our exposure."
    # Template 3: Simple context for False Positives
    FP_CONTEXT_TEMPLATE: str = "The document includes a {instr}."

    # Generate instruments for each category
    category_instruments = {
        "ir": InstrumentGenerator.generate_ir_instruments(),
        "fx": InstrumentGenerator.generate_fx_instruments(),
        "cp": InstrumentGenerator.generate_cp_instruments(),
        "eq": InstrumentGenerator.generate_eq_instruments(),
        "gen": InstrumentGenerator.generate_gen_instruments(),
        "fp": InstrumentGenerator.generate_fp_instruments(),  # NEW FP CATEGORY
    }

    # Generate test cases
    for category, instruments in category_instruments.items():
        cat_tests = []
        tested_instruments: Set[str] = set()

        # Determine which templates to use
        templates_to_use = [SIMPLE_TEMPLATE, SIMPLE_CONTEXT_TEMPLATE]
        if category == "fp":
            # For FPs, we must test them in context to ensure they don't match
            templates_to_use = [FP_CONTEXT_TEMPLATE]

        for instr in instruments:
            # Add bare instrument test for TRUE POSITIVES (Max Munch)
            if category != "fp" and instr not in tested_instruments:
                phrase = SIMPLE_TEMPLATE.format(instr=instr)
                cat_tests.append((phrase, instr))
                tested_instruments.add(instr)

            # Add contextual tests (for cross-validation and FP checks)
            for template in templates_to_use:
                phrase = template.format(instr=instr)
                # For FPs, the expected match is an empty string
                expected = "" if category == "fp" else instr
                cat_tests.append((phrase, expected))

        # Final dedupe and limit
        seen_phrases = set()
        deduped = []
        for p, m in cat_tests:
            if p not in seen_phrases:
                seen_phrases.add(p)
                deduped.append((p, m))

        TEST_DATA[category] = deduped[:50]

    return TEST_DATA


# Generate test data
TEST_DATA = generate_verification_data()

# Regexes map (FP category is tested against ALL regexes)
REGEXES = {
    "ir": IR_REGEX,
    "fx": FX_REGEX,
    "cp": CP_REGEX,
    "eq": EQ_REGEX,
    "gen": GEN_REGEX,
}

# =============================================================================
# 3. VERIFICATION FUNCTIONS
# =============================================================================


def test_auto_verification(
    category: str, phrase: str, expected_match: str
) -> Tuple[bool, str]:
    """Tests a single phrase and verifies the longest match."""
    regex = REGEXES.get(category)
    if not regex:
        # Special handling for FP category: test against all, expect no match
        if category == "fp":
            all_regexes = list(REGEXES.values())
            for reg in all_regexes:
                match = reg.search(phrase)
                if match:
                    matched_text = match.group(0).strip().lower()
                    return (
                        False,
                        f"FP Matched by {reg.pattern[:20]}...: '{matched_text}'",
                    )
            return True, "Correctly found NO match (False Positive Passed)"

        return False, f"Category '{category.upper()}' has no defined regex."

    # Standard true positive check
    match = regex.search(phrase)
    expected_clean = expected_match.strip().lower()

    if expected_clean == "":
        # Should not happen for standard categories, but defensive
        return False, "Error: Standard category must have an expected match."

    if not match:
        return False, f"No match found. Expected: '{expected_clean}'"

    matched_text = match.group(0).strip().lower()

    if matched_text == expected_clean:
        return True, f"Matched: '{matched_text}'"
    else:
        return False, f"Mismatched. Expected: '{expected_clean}', Got: '{matched_text}'"


def test_cross_validation(
    phrase: str, expected_category: str
) -> Tuple[bool, Dict[str, str], List[Tuple[str, str]]]:
    """
    Cross-validation: ensures ONLY the expected regex matches among *specialized*
    categories. GEN_REGEX is allowed to match anything.
    """
    results = {}
    unwanted_matches = []

    for category, regex in REGEXES.items():
        match = regex.search(phrase)
        if match:
            matched_text = match.group(0).strip().lower()
            results[category] = matched_text

            # Unwanted match if:
            # 1. It's not the expected category, AND
            # 2. It's not the generic category ("gen").
            # 3. It's not an FP test (where all matches are wrong)
            if category != expected_category and category != "gen":
                unwanted_matches.append((category, matched_text))
        else:
            results[category] = "(no match)"

    # Passed if: expected category matched AND no unwanted specialized categories matched
    expected_matched = (
        expected_category in results and results[expected_category] != "(no match)"
    )
    passed = expected_matched and len(unwanted_matches) == 0

    return passed, results, unwanted_matches


def run_primary_test_suite() -> Tuple[int, int]:
    """Runs primary verification tests (longest match check, including FPs)."""
    total_tests = 0
    total_passed = 0

    print("\n" + "=" * 100)
    print("🚀 PRIMARY TEST SUITE: Verification and False Positive Check (Max Munch/FP)")
    print("=" * 100)

    for category, tests in TEST_DATA.items():
        print(f"\n--- {category.upper()} ({len(tests)} cases) ---")
        category_passed = 0

        for i, (phrase, expected_match) in enumerate(tests, 1):
            total_tests += 1
            passed, result_message = test_auto_verification(
                category, phrase, expected_match
            )

            if passed:
                total_passed += 1
                category_passed += 1
                status = "✓"
            else:
                status = "✗"

            # Only print failures to save space
            if not passed:
                print(f"[{status}] Case {i}: {phrase}")
                print(f"       Expected: '{expected_match}'")
                print(f"        {result_message}")

        print(f"     → {category_passed}/{len(tests)} passed")

    return total_tests, total_passed


def run_cross_validation_suite() -> Tuple[int, int]:
    """Runs cross-validation (ensures no regex bleeds into other categories)."""
    # Cross-validation does NOT apply to FP or GEN categories, so we filter them out
    categories_for_cross_check = {
        k: v for k, v in TEST_DATA.items() if k not in ["fp", "gen"]
    }

    total_tests = 0
    total_passed = 0

    print("\n" + "=" * 100)
    print("🔍 CROSS-VALIDATION TEST SUITE: Category Isolation Check")
    print("=" * 100)

    for category, tests in categories_for_cross_check.items():
        # Sample 5 tests per category for cross-validation (to save runtime)
        sample_tests = tests[:5]
        print(
            f"\n--- {category.upper()} Category Isolation ({len(sample_tests)} spot checks) ---"
        )
        category_passed = 0

        for phrase, expected_match in sample_tests:
            total_tests += 1
            passed, results, unwanted = test_cross_validation(phrase, category)

            if passed:
                total_passed += 1
                category_passed += 1
                status = "✓"
                print(f"[{status}] '{phrase[:60]}...'")
            else:
                status = "✗"
                print(f"[{status}] '{phrase[:60]}...'")
                print(f"        Expected only {category.upper()}, but got:")
                for wrong_cat, match in unwanted:
                    print(f"          - {wrong_cat.upper()}: '{match}'")

        print(f"     → {category_passed}/{len(sample_tests)} isolated correctly")

    return total_tests, total_passed


def run_test_suite() -> None:
    """Runs all test suites and prints summary."""

    # Run primary tests
    total_primary, passed_primary = run_primary_test_suite()

    # Run cross-validation tests
    total_cross, passed_cross = run_cross_validation_suite()

    # Summary
    print("\n" + "=" * 100)
    print("📊 FINAL TEST SUMMARY")
    print("=" * 100)
    print(f"\nPrimary Tests (Max Munch & FP):")
    print(
        f"     Total: {total_primary} | Passed: {passed_primary} | Failed: {total_primary - passed_primary}"
    )
    print(f"     Success Rate: {100 * passed_primary / total_primary:.1f}%")

    print(f"\nCross-Validation Tests (Isolation):")
    print(
        f"     Total: {total_cross} | Passed: {passed_cross} | Failed: {total_cross - passed_cross}"
    )
    print(f"     Success Rate: {100 * passed_cross / total_cross:.1f}%")

    total_all = total_primary + total_cross
    passed_all = passed_primary + passed_cross
    print(f"\nOverall:")
    print(
        f"     Total: {total_all} | Passed: {passed_all} | Failed: {total_all - passed_all}"
    )
    print(f"     Success Rate: {100 * passed_all / total_all:.1f}%")

    print("\n" + "=" * 100)
    if passed_all == total_all:
        print(
            "🎉 ALL TESTS PASSED! Maximum Munch preserved, categories isolated, and FPs rejected."
        )
    else:
        print("⚠️  FAILURES DETECTED. Review output above for details.")
    print("=" * 100)


# =============================================================================
# MAIN EXECUTION
# =============================================================================

if __name__ == "__main__":
    run_test_suite()
