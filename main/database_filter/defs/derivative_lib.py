import re
from defs.ir_regex import IR_CONTEXT_REGEX, IR_REGEX, IR_SOFT_REGEX, IR_STRICT_CONTEXT_REGEX
from defs.cp_regex import CP_CONTEXT_REGEX, CP_REGEX, CP_SOFT_REGEX, CP_STRICT_CONTEXT_REGEX
from defs.cr_regex import CR_CONTEXT_REGEX, CR_REGEX, CR_SOFT_REGEX, CR_STRICT_CONTEXT_REGEX
from defs.eq_regex import EQ_CONTEXT_REGEX, EQ_REGEX, EQ_SOFT_REGEX, EQ_STRICT_CONTEXT_REGEX
from defs.fx_regex import FX_CONTEXT_REGEX, FX_REGEX, FX_SOFT_REGEX, FX_STRICT_CONTEXT_REGEX
from defs.ir_regex import IR_CONTEXT_REGEX, IR_REGEX, IR_SOFT_REGEX, IR_STRICT_CONTEXT_REGEX, IR_LOOSE_REGEX
from defs.cp_regex import CP_CONTEXT_REGEX, CP_REGEX, CP_SOFT_REGEX, CP_STRICT_CONTEXT_REGEX, CP_LOOSE_REGEX
from defs.cr_regex import CR_CONTEXT_REGEX, CR_REGEX, CR_SOFT_REGEX, CR_STRICT_CONTEXT_REGEX, CR_LOOSE_REGEX
from defs.eq_regex import EQ_CONTEXT_REGEX, EQ_REGEX, EQ_SOFT_REGEX, EQ_STRICT_CONTEXT_REGEX, EQ_LOOSE_REGEX
from defs.fx_regex import FX_CONTEXT_REGEX, FX_REGEX, FX_SOFT_REGEX, FX_STRICT_CONTEXT_REGEX, FX_LOOSE_REGEX
from defs.gen_regex import GEN_REGEX, DER_STD_REGEX, NOTIONAL_REGEX, HEDGING_CONTEXT_REGEX, GEN_STRICT_CONTEXT_REGEX, PRECISE_LOOSE_GEN_REGEX
from defs.regex_lib import SENTENCE_SPLIT_PATTERN


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
    "ir": (IR_REGEX, IR_SOFT_REGEX, IR_STRICT_CONTEXT_REGEX, IR_CONTEXT_REGEX, IR_LOOSE_REGEX),
    "fx": (FX_REGEX, FX_SOFT_REGEX, FX_STRICT_CONTEXT_REGEX, FX_CONTEXT_REGEX, FX_LOOSE_REGEX),
    "cp": (CP_REGEX, CP_SOFT_REGEX, CP_STRICT_CONTEXT_REGEX, CP_CONTEXT_REGEX, CP_LOOSE_REGEX),
    "eq": (EQ_REGEX, EQ_SOFT_REGEX, EQ_STRICT_CONTEXT_REGEX, EQ_CONTEXT_REGEX, EQ_LOOSE_REGEX),
    "cr": (CR_REGEX, CR_SOFT_REGEX, CR_STRICT_CONTEXT_REGEX, CR_CONTEXT_REGEX, CR_LOOSE_REGEX),
 
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
            if PRECISE_LOOSE_GEN_REGEX.search(sent):
                if HEDGING_CONTEXT_REGEX.search(sent):
                    return True
    return False
