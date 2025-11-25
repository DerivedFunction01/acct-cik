"""
Modular Regex Tester for Financial Derivatives
Centralized instrument lists + templated test phrases = easy maintenance
"""

import re
import sys
from pathlib import Path

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
# CENTRALIZED INSTRUMENT DEFINITIONS (Easy to extend!)
# =============================================================================

INSTRUMENTS = {
    "ir": [
        "interest rate swaps?",
        "irs",
        "zero[- ]?coupon swap",
        "interest rate caps?",
        "cap options?",
        "interest rate (?:call|put) options?",
        "treasury locks?",
        "treasury rate locks?",
        "libor[- ]?based swaps?",
        "sofr swaps?",
        "cross[- ]?currency interest rate swaps?",
        "basis swaps?",
        "overnight index swaps?",
        "ois",
        "forward rate agreements?",
        "fra",
    ],
    "fx": [
        "foreign exchange (?:derivative )?contracts?",
        "fx forwards?",
        "forward exchange contracts?",
        "cross[- ]?currency swaps?",
        "currency swaps?",
        "ndfs?",
        "non[- ]?deliverable forwards?",
        "currency options?",
        "fx options?",
        "deliverable forwards?",
    ],
    "cp": [
        "commodity swaps?",
        "commodity futures",
        "power purchase agreements?",
        "ppas?",
        "weather derivatives?",
        "crude oil (?:options|swaps|futures)",
        "natural gas hedges?",
        "energy derivatives?",
        "metal price swaps?",
    ],
    "eq": [
        "embedded conversion options?",
        "convertible notes? conversion features?",
        "warrants?",
        "warrant liabilities",
        "equity swaps?",
        "bifurcated (?:embedded )?derivatives?",
        "conversion options? derivatives?",
        "prepaid forward contracts?",
    ],
}

# Generic hedging/context phrases (not tied to specific instruments)
HEDGING_TEMPLATES = [
    "We use {instr} to hedge our exposure.",
    "The company entered into {instr} agreements?.",
    "We hold {instr} on our floating rate debt.",
    "We designated {instr} as cash flow hedges.",
    "We execute {instr} for hedging purposes.",
    "Outstanding {instr} are marked to fair value.",
]

GENERIC_PHRASES = [
    "The company uses derivatives for hedging.",
    "We designated hedging instruments as cash flow hedges.",
    "Derivative contracts are recorded at fair value.",
    "Notional amounts for cap contracts do not represent actual risk exposure.",
]


# =============================================================================
# AUTO-GENERATED TEST PHRASES USING TEMPLATES
# =============================================================================


def generate_test_phrases():
    """Generate rich test phrases dynamically from instruments + templates"""
    phrases = {"gen": GENERIC_PHRASES.copy()}

    for category, instruments in INSTRUMENTS.items():
        cat_phrases = []
        for instr in instruments:
            for template in HEDGING_TEMPLATES:
                # Replace placeholder or insert naturally
                if "{instr}" in template:
                    phrase = template.format(instr=instr)
                else:
                    # Fallback: insert instrument in common positions
                    phrase = template.replace("hedging instruments", instr, 1)
                    if phrase == template:
                        phrase = f"We use {instr} to manage interest rate risk."
                cat_phrases.append(phrase)

            # Add some non-templated realistic variants
            cat_phrases.extend(
                [
                    f"We have {instr} outstanding with notional of $500 million.",
                    f"The fair value of our {instr} increased this quarter.",
                    f"{instr.title()} are used to mitigate currency translation risk.",
                ]
            )

        # Dedupe while preserving order
        seen = set()
        deduped = []
        for p in cat_phrases:
            if p not in seen:
                seen.add(p)
                deduped.append(p)
        phrases[category] = deduped[:12]  # Limit per category for clarity

    return phrases


TEST_PHRASES = generate_test_phrases()


# =============================================================================
# REGEX MAPPING
# =============================================================================

REGEXES = {
    "ir": IR_REGEX,
    "fx": FX_REGEX,
    "cp": CP_REGEX,
    "eq": EQ_REGEX,
    "gen": GEN_REGEX,
    "hedging": HEDGING_CONTEXT_REGEX,
}

# Auto-validate that all categories have regexes
for cat in TEST_PHRASES.keys():
    if cat not in REGEXES:
        print(f"Warning: No regex defined for category '{cat}'")


# =============================================================================
# TEST FUNCTIONS (unchanged logic, now cleaner data)
# =============================================================================


def test_single_phrase(phrase: str, category: str = None) -> None:
    print("\n" + "=" * 80)
    print(f"Testing: '{phrase}'")
    print("=" * 80)

    categories = [category] if category else REGEXES.keys()
    found_any = False

    for cat in categories:
        if cat not in REGEXES:
            print(f"\n✗ {cat.upper()}: No regex defined")
            continue

        regex = REGEXES[cat]
        matches = list(regex.finditer(phrase))

        if matches:
            found_any = True
            print(f"\n{categories} {cat.upper()}: MATCHED")
            for m in matches:
                print(f"  → '{m.group(0)}' @ {m.span()}")
        else:
            print(f"\n✗ {cat.upper()}: No match")

    if not found_any and not category:
        print("\nNo regex matched this phrase.")


def test_category_phrases(category: str) -> None:
    if category not in TEST_PHRASES:
        print(f"Unknown category: {category}")
        return

    print(f"\n{'='*80}")
    print(
        f"Testing {category.upper()} Category Phrases ({len(TEST_PHRASES[category])} phrases)"
    )
    print("=" * 80)

    regex = REGEXES.get(category)
    if not regex:
        print(f"No regex defined for '{category}'")
        return

    for phrase in TEST_PHRASES[category]:
        match = bool(regex.search(phrase))
        status = "PASS" if match else "FAIL"
        print(f"{status} {phrase}")
        if match:
            for m in regex.finditer(phrase):
                print(f"     → '{m.group(0)}'")


def test_deletion(phrase: str, category: str) -> None:
    if category not in REGEXES:
        print(f"Unknown category: {category}")
        return

    regex = REGEXES[category]
    print(f"\n{'='*80}")
    print(f"Deletion Test: {category.upper()}")
    print(f"Regex: {regex.pattern[:100]}{'...' if len(regex.pattern) > 100 else ''}")
    print("=" * 80)
    print(f"Original:  {phrase}")

    if regex.search(phrase):
        cleaned = regex.sub(" [DELETED] ", phrase)
        print(f"After:     {cleaned}")
        print(f"Matches: {[m.group(0) for m in regex.finditer(phrase)]}")
    else:
        print("No match → nothing deleted")


# =============================================================================
# QUICK & INTERACTIVE MODES
# =============================================================================


def run_quick_test():
    print("Running Quick Test on All Categories...\n")
    for cat in TEST_PHRASES.keys():
        if cat in REGEXES:
            test_category_phrases(cat)


def interactive_mode():
    print("\n" + "=" * 80)
    print("Derivative Regex Tester – Modular Edition")
    print("=" * 80)
    print("Commands:")
    print("  test <phrase> [category]     – Test one phrase")
    print("  cat <category>               – Test all phrases in category")
    print("  delete <phrase> <cat>        – Show what gets removed")
    print("  quick                        – Run all tests")
    print("  list [category]              – Show test phrases")
    print("  instruments <cat>            – Show instrument keywords")
    print("  quit                         – Exit")
    print()

    while True:
        try:
            cmd = input("\n> ").strip()
            if not cmd:
                continue

            parts = cmd.split(maxsplit=2)
            action = parts[0].lower()

            if action in ("quit", "exit", "q"):
                print("Goodbye!")
                break

            elif action == "quick":
                run_quick_test()

            elif action in ("test", "t"):
                if len(parts) < 2:
                    print("Usage: test <phrase> [category]")
                else:
                    phrase = parts[1] if len(parts) == 2 else parts[1]
                    category = parts[2] if len(parts) == 3 else None
                    test_single_phrase(phrase, category)

            elif action in ("cat", "category"):
                if len(parts) < 2:
                    print(f"Available: {', '.join(TEST_PHRASES.keys())}")
                else:
                    test_category_phrases(parts[1].lower())

            elif action == "delete":
                if len(parts) < 3:
                    print("Usage: delete <phrase> <category>")
                else:
                    test_deletion(parts[1], parts[2].lower())

            elif action == "list":
                if len(parts) == 1:
                    for c, ps in TEST_PHRASES.items():
                        print(f"\n--- {c.upper()} ({len(ps)} phrases) ---")
                        for i, p in enumerate(ps[:8], 1):
                            print(f"{i:2}. {p}")
                        if len(ps) > 8:
                            print(f"   ... and {len(ps)-8} more")
                else:
                    cat = parts[1].lower()
                    if cat in TEST_PHRASES:
                        for i, p in enumerate(TEST_PHRASES[cat], 1):
                            print(f"{i:2}. {p}")
                    else:
                        print("Category not found")

            elif action == "instruments":
                cat = parts[1].lower() if len(parts) > 1 else None
                if not cat:
                    print("Categories:", ", ".join(INSTRUMENTS.keys()))
                elif cat in INSTRUMENTS:
                    print(f"\n{cat.upper()} instrument keywords:")
                    for i, kw in enumerate(INSTRUMENTS[cat], 1):
                        print(f"  {i:2}. {kw}")
                else:
                    print("Unknown category")

            else:
                print("Unknown command")

        except KeyboardInterrupt:
            print("\nBye!")
            break
        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()
        if arg == "quick":
            run_quick_test()
        elif arg in ("i", "interactive"):
            interactive_mode()
        else:
            print("Usage: python regex_test.py [quick | interactive]")
    else:
        interactive_mode()
