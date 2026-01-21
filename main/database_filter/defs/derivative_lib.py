import re
from defs.ir_regex import IR_CONTEXT_REGEX, IR_REGEX, IR_SOFT_REGEX, IR_STRICT_CONTEXT_REGEX, IR_LOOSE_REGEX, IR_RISK_REGEX
from defs.cp_regex import COMMODITY_REGEX, CP_CONTEXT_REGEX, CP_REGEX, CP_SOFT_REGEX, CP_STRICT_CONTEXT_REGEX, CP_LOOSE_REGEX, CP_RISK_REGEX
from defs.cr_regex import CR_CONTEXT_REGEX, CR_REGEX, CR_SOFT_REGEX, CR_STRICT_CONTEXT_REGEX, CR_LOOSE_REGEX, CR_RISK_REGEX
from defs.eq_regex import EQ_CONTEXT_REGEX, EQ_REGEX, EQ_SOFT_REGEX, EQ_STRICT_CONTEXT_REGEX, EQ_LOOSE_REGEX, EQ_RISK_REGEX
from defs.fx_regex import FX_CONTEXT_REGEX, FX_REGEX, FX_SOFT_REGEX, FX_STRICT_CONTEXT_REGEX, FX_LOOSE_REGEX, FX_RISK_REGEX
from defs.gen_regex import GEN_REGEX, NOTIONAL_REGEX, HEDGING_CONTEXT_REGEX, GEN_STRICT_CONTEXT_REGEX
from defs.regex_lib import SENTENCE_SPLIT_PATTERN, build_alternation, build_regex
from defs.derivatives_core import DOUBLE_BASE_REGEX, LOOSE_GEN_REGEX, PRECISE_LOOSE_GEN_REGEX


STRICT_REGEX = re.compile(
    r"|".join(
        [
            IR_REGEX.pattern,
            FX_REGEX.pattern,
            CP_REGEX.pattern,
            EQ_REGEX.pattern,
            CR_REGEX.pattern,
            GEN_REGEX.pattern
        ]
    ),
    re.IGNORECASE,
)
SOFT_REGEX = re.compile(
    r"|".join(
        [
            IR_SOFT_REGEX.pattern,
            FX_SOFT_REGEX.pattern,
            CP_SOFT_REGEX.pattern,
            EQ_SOFT_REGEX.pattern,
            CR_SOFT_REGEX.pattern,
            GEN_REGEX.pattern,
        ]
    ),
    re.IGNORECASE,
)
SOFT_CATEGORY_REGEX = re.compile(
    r"|".join(
        [
            IR_SOFT_REGEX.pattern,
            FX_SOFT_REGEX.pattern,
            CP_SOFT_REGEX.pattern,
            EQ_SOFT_REGEX.pattern,
            CR_SOFT_REGEX.pattern,
        ]
    ),
    re.IGNORECASE,
)
ALL_REGEX = re.compile(
    r"|".join(
        [
            FX_SOFT_REGEX.pattern,
            CP_SOFT_REGEX.pattern,
            EQ_SOFT_REGEX.pattern,
            IR_SOFT_REGEX.pattern,
            CR_SOFT_REGEX.pattern,
            GEN_REGEX.pattern,
            GEN_STRICT_CONTEXT_REGEX.pattern,
            NOTIONAL_REGEX.pattern,
        ]
    ),
    re.IGNORECASE,
)

CATEGORY_MAP = {
    "ir": (IR_REGEX, IR_SOFT_REGEX, IR_STRICT_CONTEXT_REGEX, IR_CONTEXT_REGEX, IR_LOOSE_REGEX, IR_RISK_REGEX),
    "fx": (FX_REGEX, FX_SOFT_REGEX, FX_STRICT_CONTEXT_REGEX, FX_CONTEXT_REGEX, FX_LOOSE_REGEX, FX_RISK_REGEX),
    "cp": (CP_REGEX, CP_SOFT_REGEX, CP_STRICT_CONTEXT_REGEX, CP_CONTEXT_REGEX, CP_LOOSE_REGEX, CP_RISK_REGEX),
    "eq": (EQ_REGEX, EQ_SOFT_REGEX, EQ_STRICT_CONTEXT_REGEX, EQ_CONTEXT_REGEX, EQ_LOOSE_REGEX, EQ_RISK_REGEX),
    "cr": (CR_REGEX, CR_SOFT_REGEX, CR_STRICT_CONTEXT_REGEX, CR_CONTEXT_REGEX, CR_LOOSE_REGEX, CR_RISK_REGEX),
 
}


def find_hedging_context(paragraph: str) -> bool:
    """Standard Gatekeeper for regular derivatives."""
    if "<TABLE>" in paragraph.upper():  # Tables should have been parsed
        return False
    elif STRICT_REGEX.search(paragraph) or GEN_STRICT_CONTEXT_REGEX.search(paragraph):
        return True
    elif SOFT_REGEX.search(paragraph) and HEDGING_CONTEXT_REGEX.search(paragraph):
        return True
    else:  # perform hard sentence by sentence verification
        for sent in SENTENCE_SPLIT_PATTERN.split(paragraph):
            if DOUBLE_BASE_REGEX.search(sent): # "swaps, locks", "cap and floor"
                return True
            if PRECISE_LOOSE_GEN_REGEX.search(sent):
                if HEDGING_CONTEXT_REGEX.search(sent):
                    return True
    return False


GLUE_MAP = {
    "ir": build_regex([
        r"(?:interest|fixed|variable|floating)[- ]rates?",
        r"interest\s+exchange",
    ]),
    "fx": build_regex([
        r"(?:foreign|forward)[- ](?:forward|foreign)",
        r"(?:foreign|forward|cross|multi)[- ](?:currency|exchange rate|exchange)",
        r"(?<!single[- ])currency",
        r"fx",
        r"forex",
        r"exchange\s+rate",
    ]),
    "cp": COMMODITY_REGEX,
    "eq": build_regex([
        r"equit(?:y|ies)",
        r"stocks?",
        r"shares?",
    ]),
    "cr": build_regex([
        r"credits?",
        r"defaults?",
    ]),
}
def create_target() -> str:
    _ABSENCE_NOUNS = [
        r"positions?",
        r"obligations?",
        r"activit(?:ies|y)",  # "no derivative activity"
        r"involvements?",  # "no involvement with derivatives"
        r"holdings?",  # "no holdings"
    ]
    _DENIAL_TARGET = rf"(?:{STRICT_REGEX.pattern}|{PRECISE_LOOSE_GEN_REGEX.pattern}|{build_alternation(_ABSENCE_NOUNS)})"
    return _DENIAL_TARGET


def run_tests():
    from defs.ir_regex import run_tests as ir_run
    from defs.fx_regex import run_tests as fx_run
    from defs.cp_regex import run_tests as cp_run
    from defs.eq_regex import run_tests as eq_run
    from defs.cr_regex import run_tests as cr_run
    
    ir_run()
    fx_run()
    cp_run()
    eq_run()
    cr_run()
