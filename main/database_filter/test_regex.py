"""
Regex Tester Script
Import regexes from derivative_regex.py and test them interactively.
"""

import re
import sys
from pathlib import Path

# Adjust path if needed
try:
    from derivative_regex import (
        IR_REGEX,
        FX_REGEX,
        CP_REGEX,
        EQ_REGEX,
        GEN_REGEX,
        HEDGING_CONTEXT_REGEX,
    )
except ImportError:
    print("Error: Could not import from derivative_regex.py")
    print("Make sure derivative_regex.py is in the same directory or PYTHONPATH")
    sys.exit(1)


# =============================================================================
# TEST DATA
# =============================================================================

TEST_PHRASES = {
    "ir": [
        "We use interest rate swaps to hedge our exposure.",
        "The company entered into a zero coupon swap agreement.",
        "We hold interest rate caps on our floating rate debt.",
        "We use interest rate call options to manage risk.",
        "Treasury locks are used for hedging purposes.",
        "We designated LIBOR-based swaps as cash flow hedges.",
    ],
    "fx": [
        "We enter into foreign exchange derivative contracts to mitigate risk.",
        "The company uses FX forwards to hedge currency exposure.",
        "We have cross currency swaps outstanding.",
        "Currency exchange rate fluctuations affect our earnings.",
        "We execute NDF contracts for non-deliverable currencies.",
    ],
    "cp": [
        "We use commodity swaps to hedge oil price risk.",
        "The company has commodity futures contracts.",
        "We entered into power purchase agreements.",
        "Weather derivatives protect against seasonal variation.",
        "Crude oil price exposure is managed through options.",
    ],
    "eq": [
        "We have embedded conversion options in convertible notes.",
        "Warrant liabilities are marked to fair value monthly.",
        "Equity swaps are used for hedging purposes.",
        "The bifurcated conversion option is a derivative liability.",
    ],
    "gen": [
        "The company uses derivatives for hedging.",
        "We designated hedging instruments as cash flow hedges.",
        "The derivative contracts are marked to fair value.",
        "Hedge accounting treatment applies to our positions.",
    ],
}

REGEXES = {
    "ir": IR_REGEX,
    "fx": FX_REGEX,
    "cp": CP_REGEX,
    "eq": EQ_REGEX,
    "gen": GEN_REGEX,
    "hedging": HEDGING_CONTEXT_REGEX,
}


# =============================================================================
# TEST FUNCTIONS
# =============================================================================


def test_single_phrase(phrase: str, category: str = None) -> None:
    """Test a single phrase against all (or specific) regexes."""
    print("\n" + "=" * 70)
    print(f"Testing: '{phrase}'")
    print("=" * 70)

    if category:
        categories = [category]
    else:
        categories = list(REGEXES.keys())

    found_any = False

    for cat in categories:
        regex = REGEXES[cat]
        matches = regex.findall(phrase)

        if matches:
            found_any = True
            print(f"\n✓ {cat.upper()}: Matched")
            print(f"  Matches: {matches}")

            # Show span
            for match in regex.finditer(phrase):
                start, end = match.span()
                print(f"    Position {start}-{end}: '{phrase[start:end]}'")
        else:
            print(f"\n✗ {cat.upper()}: No match")

    if not found_any:
        print("\n⚠ No matches found in any category")


def test_category_phrases(category: str) -> None:
    """Test all predefined phrases for a category."""
    if category not in TEST_PHRASES:
        print(f"Error: Unknown category '{category}'")
        print(f"Available: {list(TEST_PHRASES.keys())}")
        return

    phrases = TEST_PHRASES[category]
    regex = REGEXES[category]

    print("\n" + "=" * 70)
    print(f"Testing {category.upper()} Phrases")
    print("=" * 70)

    for phrase in phrases:
        matches = regex.findall(phrase)
        status = "✓" if matches else "✗"
        print(f"\n{status} '{phrase}'")
        if matches:
            print(f"   Matched: {matches}")


def test_deletion(phrase: str, category: str) -> None:
    """Test what would be deleted from a phrase."""
    if category not in REGEXES:
        print(f"Error: Unknown category '{category}'")
        return

    regex = REGEXES[category]

    print("\n" + "=" * 70)
    print(f"Testing Deletion for {category.upper()}")
    print("=" * 70)

    print(f"\nOriginal:\n  '{phrase}'")

    match = regex.search(phrase)
    if match:
        print(f"\nMatched: '{match.group(0)}'")
        deleted = regex.sub(" ", phrase)
        print(f"\nAfter deletion:\n  '{deleted}'")
    else:
        print(f"\nNo match found - nothing would be deleted")


def interactive_mode() -> None:
    """Interactive testing mode."""
    print("\n" + "=" * 70)
    print("Interactive Regex Tester")
    print("=" * 70)
    print("\nCommands:")
    print("  test <phrase>              - Test phrase against all regexes")
    print("  test <phrase> <category>   - Test phrase against specific category")
    print("  test <category>            - Test all predefined phrases for category")
    print("  delete <phrase> <category> - Show what gets deleted")
    print("  list                       - List all test phrases")
    print("  categories                 - Show available categories")
    print("  quit                       - Exit")
    print()

    while True:
        try:
            user_input = input("\n> ").strip()

            if not user_input:
                continue

            parts = user_input.split(" ", 2)
            command = parts[0].lower()

            if command == "quit":
                break

            elif command == "test":
                if len(parts) == 1:
                    print("Usage: test <phrase> [category]")
                elif len(parts) == 2:
                    # test <phrase> - test all categories
                    test_single_phrase(parts[1])
                elif len(parts) == 3:
                    phrase = parts[1]
                    category = parts[2].lower()
                    # Could be "test <category>" or "test <phrase> <category>"
                    if category in TEST_PHRASES:
                        # It's a category
                        test_category_phrases(category)
                    elif category in REGEXES:
                        # It's a category
                        test_category_phrases(category)
                    else:
                        # It's a phrase with category
                        test_single_phrase(phrase, category)

            elif command == "delete":
                if len(parts) < 3:
                    print("Usage: delete <phrase> <category>")
                else:
                    phrase = parts[1]
                    category = parts[2].lower()
                    test_deletion(phrase, category)

            elif command == "list":
                print("\nPredefined test phrases:")
                for cat, phrases in TEST_PHRASES.items():
                    print(f"\n{cat.upper()}:")
                    for i, phrase in enumerate(phrases, 1):
                        print(f"  {i}. {phrase}")

            elif command == "categories":
                print("\nAvailable categories:")
                for cat in REGEXES.keys():
                    print(f"  - {cat}")

            else:
                print(f"Unknown command: {command}")
                print("Type 'quit' to exit or see commands above")

        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print(f"Error: {e}")


# =============================================================================
# QUICK TEST MODE (Run without user input)
# =============================================================================


def run_quick_test() -> None:
    """Run all predefined tests."""
    print("\n" + "=" * 70)
    print("Quick Test: All Predefined Phrases")
    print("=" * 70)

    for category, phrases in TEST_PHRASES.items():
        test_category_phrases(category)


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()

        if command == "quick":
            run_quick_test()

        elif command == "test":
            if len(sys.argv) < 3:
                print("Usage: python regex_test.py test '<phrase>' [category]")
            else:
                phrase = sys.argv[2]
                category = sys.argv[3].lower() if len(sys.argv) > 3 else None
                test_single_phrase(phrase, category)

        elif command == "delete":
            if len(sys.argv) < 4:
                print("Usage: python regex_test.py delete '<phrase>' <category>")
            else:
                phrase = sys.argv[2]
                category = sys.argv[3].lower()
                test_deletion(phrase, category)

        elif command == "interactive" or command == "i":
            interactive_mode()

        else:
            print(f"Unknown command: {command}")
            print("\nUsage:")
            print(
                "  python regex_test.py quick                 - Run all predefined tests"
            )
            print("  python regex_test.py test '<phrase>'       - Test a phrase")
            print(
                "  python regex_test.py test '<phrase>' <cat> - Test phrase on category"
            )
            print("  python regex_test.py delete '<phrase>' <cat> - Show deletion")
            print("  python regex_test.py interactive           - Interactive mode")

    else:
        # Default: interactive mode
        interactive_mode()
