from dataclasses import dataclass, field
from typing import Callable, Dict, Generic, List, Literal, Optional, Set, Tuple, TypeVar
import random

# Imports moved here for the NotionalSentence.build() method
from defs.common_data import  *
from defs.template_definitions import *

def _get_company_reference(company_name: str, chance: float = 0.6) -> str:
    """Randomly returns either the full company name or a generic placeholder."""
    return company_name if random.random() < chance else "The Company"


# =============================================================================
# SCENARIO DEFINITION - CLASSES
# This file contains the core data structures (dataclasses) that define the
# state of a financial narrative for generation.
# =============================================================================



