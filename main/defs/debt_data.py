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


# Define debt categories and their specific types
DEBT_CATEGORIES = [
    DebtCategory(
        name="Corporate & Bank Debt",
        debt_types=[
            DebtType(name="term loan", benchmarks=["SOFR", "LIBOR", "prime rate"]),
            DebtType(name="revolving credit facility", benchmarks=["SOFR", "LIBOR", "prime rate"]),
            DebtType(name="bridge loan", benchmarks=["prime rate"]),
            DebtType(name="syndicated loan", benchmarks=["SOFR", "LIBOR"]),
            DebtType(name="bilateral loan", benchmarks=["SOFR", "prime rate"]),
            DebtType(name="asset-based lending (ABL)", benchmarks=["prime rate"]),
            DebtType(name="equipment financing", benchmarks=["fixed rate"]),
            DebtType(name="working capital loan", benchmarks=["prime rate"]),
            DebtType(name="project finance loan", benchmarks=["LIBOR", "SOFR"]),
            DebtType(name="acquisition financing", benchmarks=["SOFR", "LIBOR"]),
            DebtType(name="mezzanine debt", benchmarks=["fixed rate"]),
            DebtType(name="venture debt", benchmarks=["prime rate"]),
            DebtType(name="subordinated debt", benchmarks=["fixed rate"]),
            DebtType(name="senior secured debt", benchmarks=["SOFR", "LIBOR"]),
            DebtType(name="senior unsecured debt", benchmarks=["fixed rate"]),
            DebtType(name="convertible debt", benchmarks=["fixed rate"]),
            DebtType(name="private placement note", benchmarks=["fixed rate"]),
        ]
    ),
    DebtCategory(
        name="Marketable Securities (Bonds & Notes)",
        debt_types=[
            DebtType(name="corporate bond", benchmarks=["fixed rate"]),
            DebtType(name="government bond", benchmarks=["treasury rate"]),
            DebtType(name="municipal bond", benchmarks=["SIFMA"]),
            DebtType(name="agency bond", benchmarks=["treasury rate"]),
            DebtType(name="zero-coupon bond", benchmarks=[]),
            DebtType(name="perpetual bond", benchmarks=["fixed rate"]),
            DebtType(name="callable bond", benchmarks=["fixed rate"]),
            DebtType(name="puttable bond", benchmarks=["fixed rate"]),
            DebtType(name="fixed-rate bond", benchmarks=["fixed rate"]),
            DebtType(name="floating-rate note", benchmarks=["SOFR", "LIBOR", "treasury rate"]),
            DebtType(name="inflation-indexed bond", benchmarks=[]),
            DebtType(name="convertible bond", benchmarks=["fixed rate"]),
            DebtType(name="secured bond", benchmarks=["fixed rate"]),
            DebtType(name="unsecured bond", benchmarks=["fixed rate"]),
            DebtType(name="debenture", benchmarks=["fixed rate"]),
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
            DebtType(name="certificate of deposit (CD)", benchmarks=[]),
            DebtType(name="banker's acceptance", benchmarks=[]),
            DebtType(name="repurchase agreement (repo)", benchmarks=["SOFR"]),
            DebtType(name="federal funds", benchmarks=[]),
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
            DebtType(name="commercial mortgage", benchmarks=["SOFR", "treasury rate"]),
            DebtType(name="home equity line of credit (HELOC)", benchmarks=["prime rate"]),
            DebtType(name="real estate loan", benchmarks=["SOFR"]),
            DebtType(name="construction loan", benchmarks=["prime rate"]),
        ]
    ),
    DebtCategory(
        name="Other / Hybrid",
        debt_types=[
            DebtType(name="lease obligation", benchmarks=[]),
            DebtType(name="capital lease liability", benchmarks=[]),
            DebtType(name="convertible preferred share", benchmarks=[]),
            DebtType(name="credit agreement", benchmarks=["SOFR", "LIBOR", "prime rate"]),
        ]
    ),
]

# Flatten the list for random selection of any debt type
all_debt_types: List[DebtType] = [debt for category in DEBT_CATEGORIES for debt in category.debt_types]