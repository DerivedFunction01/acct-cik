from dataclasses import dataclass, field
from typing import List

@dataclass
class DebtType:
    """Represents a specific type of debt with its associated benchmark rates."""
    name: str
    benchmarks: List[str] = field(default_factory=list)

@dataclass
class DebtCategory:
    """Groups related debt types together."""
    name: str
    debt_types: List[DebtType]

# Define benchmark rates
benchmark_rates = [
    "SOFR", "LIBOR", "EURIBOR", "SONIA", "Fed Funds Rate", "Prime Rate"
]

# Define debt categories and their specific types
DEBT_CATEGORIES = [
    DebtCategory(
        name="Corporate & Bank Debt",
        debt_types=[
            DebtType(name="term loan", benchmarks=["SOFR", "LIBOR", "Prime Rate"]),
            DebtType(name="revolving credit facility", benchmarks=["SOFR", "LIBOR", "Prime Rate"]),
            DebtType(name="bridge loan", benchmarks=["Prime Rate"]),
            DebtType(name="syndicated loan", benchmarks=["SOFR", "LIBOR"]),
            DebtType(name="bilateral loan", benchmarks=["SOFR", "Prime Rate"]),
            DebtType(name="asset-based lending (ABL)", benchmarks=["Prime Rate"]),
            DebtType(name="equipment financing", benchmarks=["Fixed Rate"]),
            DebtType(name="working capital loan", benchmarks=["Prime Rate"]),
            DebtType(name="project finance loan", benchmarks=["LIBOR", "SOFR"]),
            DebtType(name="acquisition financing", benchmarks=["SOFR", "LIBOR"]),
            DebtType(name="mezzanine debt", benchmarks=["Fixed Rate"]),
            DebtType(name="venture debt", benchmarks=["Prime Rate"]),
            DebtType(name="subordinated debt", benchmarks=["Fixed Rate"]),
            DebtType(name="senior secured debt", benchmarks=["SOFR", "LIBOR"]),
            DebtType(name="senior unsecured debt", benchmarks=["Fixed Rate"]),
            DebtType(name="convertible debt", benchmarks=["Fixed Rate"]),
            DebtType(name="private placement note", benchmarks=["Fixed Rate"]),
        ]
    ),
    DebtCategory(
        name="Marketable Securities (Bonds & Notes)",
        debt_types=[
            DebtType(name="corporate bond", benchmarks=["Fixed Rate"]),
            DebtType(name="government bond", benchmarks=["Treasury Rate"]),
            DebtType(name="municipal bond", benchmarks=["SIFMA"]),
            DebtType(name="agency bond", benchmarks=["Treasury Rate"]),
            DebtType(name="zero-coupon bond", benchmarks=[]),
            DebtType(name="perpetual bond", benchmarks=["Fixed Rate"]),
            DebtType(name="callable bond", benchmarks=["Fixed Rate"]),
            DebtType(name="puttable bond", benchmarks=["Fixed Rate"]),
            DebtType(name="fixed-rate bond", benchmarks=["Fixed Rate"]),
            DebtType(name="floating-rate note", benchmarks=["SOFR", "LIBOR", "Treasury Rate"]),
            DebtType(name="inflation-indexed bond", benchmarks=["CPI"]),
            DebtType(name="convertible bond", benchmarks=["Fixed Rate"]),
            DebtType(name="secured bond", benchmarks=["Fixed Rate"]),
            DebtType(name="unsecured bond", benchmarks=["Fixed Rate"]),
            DebtType(name="debenture", benchmarks=["Fixed Rate"]),
        ]
    ),
    DebtCategory(
        name="International Bonds",
        debt_types=[
            DebtType(name="eurobond", benchmarks=["EURIBOR", "LIBOR"]),
        ]
    ),
    DebtCategory(
        name="Short-Term & Money Market",
        debt_types=[
            DebtType(name="commercial paper", benchmarks=[]),
            DebtType(name="certificate of deposit (CD)", benchmarks=["Fed Funds Rate"]),
            DebtType(name="banker's acceptance", benchmarks=[]),
            DebtType(name="repurchase agreement (repo)", benchmarks=["SOFR"]),
            DebtType(name="federal funds", benchmarks=["Fed Funds Rate"]),
            DebtType(name="money market instrument", benchmarks=[]),
            DebtType(name="eurodollar borrowing", benchmarks=["LIBOR"]),
        ]
    ),
    DebtCategory(
        name="Asset-Backed & Structured Finance",
        debt_types=[
            DebtType(name="asset-backed security (ABS)", benchmarks=["SOFR"]),
            DebtType(name="mortgage-backed security (MBS)", benchmarks=["SOFR"]),
            DebtType(name="collateralized loan obligation (CLO)", benchmarks=["SOFR", "LIBOR"]),
            DebtType(name="factoring", benchmarks=[]),
            DebtType(name="supply chain finance", benchmarks=[]),
        ]
    ),
    DebtCategory(
        name="Financing & Consumer Loans",
        debt_types=[
            DebtType(name="residential mortgage", benchmarks=["SOFR"]),
            DebtType(name="commercial mortgage", benchmarks=["SOFR", "Treasury Rate"]),
            DebtType(name="home equity line of credit (HELOC)", benchmarks=["Prime Rate"]),
            DebtType(name="real estate loan", benchmarks=["SOFR"]),
            DebtType(name="construction loan", benchmarks=["Prime Rate"]),
        ]
    ),
    DebtCategory(
        name="Other / Hybrid",
        debt_types=[
            DebtType(name="lease obligation", benchmarks=[]),
            DebtType(name="capital lease liability", benchmarks=[]),
            DebtType(name="convertible preferred share", benchmarks=[]),
            DebtType(name="credit agreement", benchmarks=["SOFR", "LIBOR", "Prime Rate"]),
        ]
    ),
]

# Flatten the list for random selection of any debt type
all_debt_types: List[DebtType] = [debt for category in DEBT_CATEGORIES for debt in category.debt_types]