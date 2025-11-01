from typing import Callable, Dict, Generic, List, Literal, Optional, Set, Tuple, TypeVar
from dataclasses import dataclass, field

from defs.instrument_definitions import HedgedItem, NotionalInstrument
@dataclass
class EquityHedgedItem(HedgedItem):
    """Represents an equity instrument being hedged (for EQ derivatives).

    Args:
        equity_type: Literal["market_index", "own_stock", "third_party_stock"] - The type of equity.
        number_of_shares: Optional[int] - The number of shares being hedged.
        share_price: Optional[float] - The share price at a point in time.
        stock_symbol: Optional[str] - The stock ticker symbol.
    """

    equity_type: Literal["market_index", "own_stock", "third_party_stock"]
    number_of_shares: Optional[int] = None
    share_price: Optional[float] = None
    stock_symbol: Optional[str] = None


class EQInstrument(NotionalInstrument[EquityHedgedItem]):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, category="EQ", **kwargs)
