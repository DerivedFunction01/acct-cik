# --- HYPOTHETICAL SCORING COMPONENTS ---

# TIER 1: STRICT ARTIFACTS (The "Fake" Instruments)
# These do not exist in the real world. Finding one is almost certainly methodology.
# Weight: High (Immediate Kill or near-kill)
from defs.regex_lib import build_regex


HYPOTHETICAL_STRICT = [
    r"hypothetical\s+derivatives?",
    r"hypothetical\s+positions?",
    r"hypothetical\s+trades?",
    r"hypothetical\s+instruments?",
    r"hypothetical\s+hedges?",
]

# TIER 2: METHODOLOGY PHRASES (The "Stats Class" Lingo)
# Strong indicators of modeling context.
# Weight: Medium (2 hits = Discard)
HYPOTHETICAL_PHRASES = [
    r"sensitivity\s+analysis",
    r"value[- ]at[- ]risk",
    r"confidence\s+(?:level|interval)",
    r"statistical\s+(?:measure|model|analysis)",
    r"parallel\s+shift",
    r"stress\s+testing",
    r"simulation\s+model",
    r"market\s+risk\s+measurement",
    # Matches "hypothetical" + (0-5 words) + "increase/decrease/change/shift"
    r"hypothetical(?:\s+\S+){0,5}\s+(?:increase|decrease|change|shift|loss|impact|effect)",
    r"rate\s+shocks?",
    r"yield\s+curve\s+shifts?",
    r"immediate\s+(?:and\s+sustained\s+)?shift",
    r"instantaneous\s+(?:parallel\s+)?shift",
    r"weakening\s+or\s+strengthening",
    r"regression\s+analysis",
    r"unobservable\s+inputs?",
    r"internally\s+developed\s+models?",
    r"prospective(?:ly)?\s+(?:basis|test|assessment)",
    r"retrospective(?:ly)?\s+(?:basis|test|assessment)",
    # Safe Basis Point Check
    r"\d+\s+basis\s+point\s+(?:increase|decrease|shift|shock|change)",
]

# TIER 3: LOOSE INDICATORS (The Context Fillers)
# Common words in sensitivity sections, but safe on their own.
# Accumulation (density) creates the signal.
# Weight: Low (Need 3-4 hits to Discard)
HYPOTHETICAL_SINGLES = [
    r"hypothetical",  # Standalone word
    r"simulation",
    r"statistical",
    r"probabilit(?:y|ies|istic)",
    r"assumption",
    r"parameter",
    r"holding\s+constant",
    r"baseline",
    r"variance",
    r"unobservable",
    r"estimate",
]

HYP_STRICT_REGEX = build_regex(HYPOTHETICAL_STRICT)
HYP_PHRASE_REGEX = build_regex(HYPOTHETICAL_PHRASES)
HYP_SINGLE_REGEX = build_regex(HYPOTHETICAL_SINGLES)
def is_hypothetical_noise(text: str, threshold: int = 8) -> bool:
    # 1. Weights
    W_STRICT = 10  # KILL SHOT: "Hypothetical derivatives" (Instant >= 8)
    W_PHRASE = 2  # "Sensitivity analysis", "Value at Risk"
    W_SINGLE = 1  # "Statistical", "Probability"

    # 2. Count
    strict_hits = len(HYP_STRICT_REGEX.findall(text))
    phrase_hits = len(HYP_PHRASE_REGEX.findall(text))
    single_hits = len(HYP_SINGLE_REGEX.findall(text))

    # 3. Score
    score = (
        (strict_hits * W_STRICT) + (phrase_hits * W_PHRASE) + (single_hits * W_SINGLE)
    )

    return score >= threshold
