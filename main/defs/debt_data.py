from dataclasses import dataclass, field
from typing import List

# --- NEW: Import common verb lists for reuse --- (This was already here, but I'm confirming its good use)
from .common_data import individual_use_verbs, aggregate_use_verbs, termination_verbs_past

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


# ============ DEBT AND CREDIT FACILITIES ============

debt_templates = {
    # --- NEW: Resable components for debt sentences ---
    "balance": [
        "{time_prefix}, {company} {verb} total {debt_type} of {amount_str}, {composition_clause}",
        "{time_prefix}, total {debt_type} was {amount_str}, {composition_clause}",
        "{company}'s {state_descriptor} borrowings under its {debt_type} totaled {amount_str} {time_suffix}",
        "{time_prefix}, there was {amount_str} {state_descriptor} on the {debt_type} and {amount_str2} {state_descriptor} on the {debt_type2}",
        "{debt_type}, {interest_rate_clause}, totaled {amount_str} {time_suffix}, {composition_clause}",
    ],
    "issuance": [
        "{time_prefix}, {company} {action_verb} {amount_str} in {debt_types} {maturity_clause} {interest_rate_clause}",
        "{time_prefix}, {company} completed a private placement of {amount_str} of {debt_types}, {interest_rate_clause}",
        "Proceeds from the {debt_type} issuance were used for {purpose_clause}",
    ],
    "repayment": [
        "{time_prefix}, {company} {action_verb} {amount_str} of its {state_descriptor} {debt_type} prior to {termination_noun}",
        "{company} {action_verb} {amount_str} of {state_descriptor} {debt_type} {time_suffix} using cash from operations",
        "In {year}, {company} retired {amount_str} of {debt_type} upon {termination_noun}",
        "At {month} {year}, {company} {action_verb} {amount_str} of the {amount_str2} borrowed",
    ],
    "refinancing": [
        "{time_prefix}, {company} {action_verb} {amount_str} of existing {debt_type}, {interest_rate_clause}, {maturity_clause}",
    ],
    "details": [
        "The {debt_type} has a principal amount of {amount_str} and {maturity_clause}",
        "The weighted average {ir_term} on {company}'s {debt_type} was approximately {pct}% {time_suffix}",
        "{time_suffix}, {company}'s {debt_type} had a weighted average maturity of {small_int} years",
        "{time_suffix}, {company}'s variable-rate borrowings bore interest at an average rate of {pct}%",
        "Interest expense related to {debt_type} for {year} was approximately {amount_str}",
        "The agreement effectively sets a cap and floor {ir_term} of {pct}% and {pct2}%, respectively, on most of the {debt_type}",
        "The notional amount on the {debt_type} reduces {frequency} from approximately {amount_str} {time_suffix} to {amount_str2} prior to {termination_noun}",
        "{time_suffix}, unamortized debt issuance costs related to {debt_type} totaled {amount_str}",
        "The fair value of {company}'s {debt_type} was estimated at {amount_str} {time_suffix}",
    ],
    "unhedged": [
        "{company}'s {debt_type} which is subject to a floating rate of interest and is not hedged by {swap_type} is valued at {amount_str} {time_suffix}",
    ],
    "debt_covenant": [
        "The credit agreement contains customary affirmative and negative covenants, including financial covenants related to leverage ratios and interest coverage",
        "As of {month} {end_day}, {year}, {company} was in compliance with all debt covenants",
        "The revolving credit facility requires maintenance of a maximum leverage ratio of {small_int}:1 and minimum interest coverage ratio of {small_int2}:1",
        "Debt agreements contain restrictions on dividends, additional indebtedness, and asset sales, subject to certain exceptions",
        # Covenant and credit facility context
        "The revolving credit facility contains customary financial covenants, including maintaining a maximum leverage ratio and minimum interest coverage ratio",
        "{company} was in compliance with all debt covenants as of {month} {end_day}, {year}",
        "{company}'s credit agreements require maintenance of specified leverage and coverage ratios, which {company} met as of {month} {end_day}, {year}",
    ],
}
# --- NEW: Reusable clause components ---
debt_composition_clauses = [
    "consisting primarily of {debt_types}",
    "including {debt_types}",
    "comprised of {debt_types}",
]

debt_interest_rate_clauses = [
    "with an average {ir_term} of {pct}%",
    "with {ir_term}s ranging from {pct}% to {pct2}%",
    "bearing interest at {pct}% per annum",
    "at an {ir_term} of {pct}%",
    "with a weighted average {ir_term} of {pct}%",
]

debt_maturity_clauses = [
    "with a maturity date of {maturity_year}",
    "expiring in {maturity_year}",
    "extending the {termination_noun} to {maturity_year}",
    "that {termination_verb} in {maturity_year}",
]
CAPEX_PURPOSES = {
    "energy": [
        "exploration and development of new energy sources",
        "renewable energy and sustainability projects",
        "investment in energy-efficient technologies",
        "upgrades to power generation and transmission infrastructure",
    ],
    "metals_minerals": [
        "acquisition of specialized machinery and equipment",
        "expansion of mining operations and extraction facilities",
        "development of new mineral processing plants",
    ],
    "agriculture": [
        "strategic land acquisitions and site development",
        "investment in modern farming equipment and irrigation systems",
        "construction of grain storage and processing facilities",
    ],
    "lumber_wood": [
        "upgrading of transportation and logistics assets",
        "modernization of sawmills and wood processing lines",
        "investment in sustainable forest management technologies",
    ],
    "chemicals_plastics": [
        "investment in sustainable manufacturing processes",
        "construction of new chemical production units",
        "upgrades to existing production lines for new polymer formulations",
    ],
    "textiles": [
        "upgrades to existing production lines",
        "acquisition of advanced weaving and knitting machinery",
        "implementation of water-saving dyeing and finishing technologies",
    ],
    "generic": [
        # General Corporate & Operations
        "manufacturing capacity expansion",
        "information technology infrastructure",
        "facility improvements and equipment upgrades",
        "expansion of global office facilities",
        "enhancement of customer service centers",
        "construction of new administrative offices",
        "renovation of retail stores and showrooms",
        "safety and regulatory compliance upgrades",
        "environmental compliance and remediation",
        "security enhancements and infrastructure protection",
        "employee training and development facilities",
        # Technology & R&D
        "research and development laboratories",
        "product development and testing facilities",
        "research and development of new products",
        "digital transformation and software development",
        "data center construction and modernization",
        "expansion of data storage and cloud capabilities",
        "modernization of telecommunications networks",
        "enhancement of cybersecurity measures",
        # Supply Chain & Logistics
        "distribution center automation",
        "supply chain and logistics optimization",
        "fleet modernization and vehicle replacement",
        "development of new distribution centers",
        "upgrading of transportation and logistics assets",
        # Manufacturing & Automation
        "implementation of advanced robotics and automation",
        "acquisition of specialized machinery and equipment",
        "upgrades to existing production lines",
    ],
}

# --- NEW: Verbs for different actions ---
debt_action_verbs = {
    "issuance": list(set(["issued", "entered into", "secured"] + individual_use_verbs)),
    "repayment": list(set(["repaid", "paid down", "settled"] + termination_verbs_past)),
    "refinancing": ["refinanced", "restructured"],
    "balance": list(set(["had", "held", "maintained"] + aggregate_use_verbs)),
}
