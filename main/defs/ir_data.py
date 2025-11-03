import random
from dataclasses import dataclass, field
from typing import List, Optional, Union

from defs.instrument_definitions import HedgedItem, NotionalInstrument

# --- NEW: Import common verb lists for reuse --- (This was already here, but I'm confirming its good use)
from defs.common_data import individual_use_verbs, aggregate_use_verbs, termination_verbs_past
from defs.function_definitions import _format_single_notional, _get_company_reference
from defs.table_definitions import GenericTable


@dataclass
class DebtHedgedItem(HedgedItem):
    """Represents a debt instrument being hedged (for IR derivatives).

    Args:
        debt_type: str - The type of debt instrument being hedged.
        issuance_month: Optional[str] - The issuance month of the debt.
        issuance_year: int - The issuance year of the debt.
        maturity_month: Optional[str] - The maturity month of the debt.
        maturity_year: int - The maturity year of the debt.
        principal_amount: int - The principal amount of the debt.
        benchmark_rate: Optional[str] - Any type of rate.
        spread_bps: Optional[int] - The spread in basis points over the benchmark.
        fixed_rate_pct: Optional[float] - The fixed interest rate percentage.
        change_rate_pct: Optional[float] - The new interest rate percentage after a change.
        payment_amount: Optional[int] - The payment amount.
        payment_frequency: Optional[str] - The payment frequency (e.g., "quarterly").
    """

    debt_type: str
    issuance_month: Optional[str]
    issuance_year: int
    maturity_month: Optional[str]
    maturity_year: int
    principal_amount: int
    currency: str = "USD"
    benchmark_rate: Optional[str] = None
    spread_bps: Optional[int] = None
    fixed_rate_pct: Optional[float] = None
    change_rate_pct: Optional[float] = None
    payment_amount: Optional[int] = None
    payment_frequency: Optional[str] = None


# Specific instrument types can now be defined cleanly.
# We can add more specific fields to each type later if needed.
class IRInstrument(NotionalInstrument[DebtHedgedItem]):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, category="IR", **kwargs)


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
        "In connection with the {capex_purpose}, {company} {action_verb} {amount_str} of {debt_types} to partially fund the transaction",
        "The proceeds from the {debt_type} issuance were primarily allocated to capital expenditures, including {capex_purpose}.",
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
    "acquisition": [
        "acquisition of a competitor",
        "purchase of a new subsidiary",
        "strategic acquisition to expand market share",
        "acquisition of a complementary business",
        "purchase of key technology assets",
        "acquisition to enter a new geographic market",
        "merger with a strategic partner",
        "buyout of a minority shareholder",
        "acquisition of a product line",
        "takeover of a publicly-traded company",
    ],
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


@dataclass
class DebtContextSentence: # Simplified to handle one item at a time
    """
    Builds a multi-sentence paragraph providing context about a single debt instrument.
    This class is defined here to live alongside its debt-specific templates.
    """
    # --- NEW: Allow a list of items for table generation ---
    company_name: str
    reporting_year: int
    reporting_month: str
    reporting_day: int
    # Can be a single item for a sentence or a list for a table
    hedged_item: Union["DebtHedgedItem", List["DebtHedgedItem"]]
    prefer_abbreviated: bool
    currency_symbol: str = "$"
    instrument: Optional["IRInstrument"] = None # Pass instrument to know if it's hedged
    more_detail: bool = False

    def build(self) -> str:
        """Builds a paragraph about the company's debt exposures."""
        # --- NEW: Add table generation logic ---
        # If a list of items is provided and with a 40% chance, build a table.
        if isinstance(self.hedged_item, list) and random.random() < 0.4:
            return self._build_debt_table()

        # Fallback to existing sentence generation for a single item.
        if isinstance(self.hedged_item, list):
            # If it's a list but we're not building a table, just describe the first item.
            if not self.hedged_item:
                return ""
            item_to_describe = self.hedged_item[0]
        else:
            item_to_describe = self.hedged_item

        return self._build_debt_sentence(item_to_describe)

    def _build_debt_table(self) -> str:
        """Builds a text-based table summarizing the debt portfolio."""
        if not isinstance(self.hedged_item, list) or not self.hedged_item:
            return ""

        # --- NEW: Randomly choose one of several table formats ---
        table_type = random.choice(["summary", "maturity_schedule", "rate_profile"])

        # --- 1. Debt Portfolio Summary (existing logic) ---
        if table_type == "summary":
            title = f"Summary of Outstanding Debt as of {self.reporting_month} {self.reporting_day}, {self.reporting_year}"
            headers = ["Debt Instrument", "Principal Amount", "Interest Rate (%)", "Maturity"]
            widths = [35, 20, 18, 12]
            alignments = ['l', 'r', 'r', 'c']
            data_rows = []
            for item in self.hedged_item:
                principal_str = _format_single_notional(item.principal_amount, self.currency_symbol, self.prefer_abbreviated, True)
                rate = (item.spread_bps / 100 if item.spread_bps else random.uniform(2.5, 8.5))
                rate_str = f"{rate:.2f}"
                maturity_str = str(item.maturity_year)
                data_rows.append([item.debt_type, principal_str, rate_str, maturity_str])

        # --- 2. Debt Maturity Schedule ---
        elif table_type == "maturity_schedule":
            title = f"Debt Maturities as of {self.reporting_month} {self.reporting_day}, {self.reporting_year}"
            headers = ["Maturity Period", "Principal Amount Due"]
            widths = [30, 25]
            alignments = ['l', 'r']
            maturity_groups = {"Less than 1 year": 0, "1-3 years": 0, "3-5 years": 0, "More than 5 years": 0}
            for item in self.hedged_item:
                years_to_maturity = item.maturity_year - self.reporting_year
                if years_to_maturity <= 1:
                    maturity_groups["Less than 1 year"] += item.principal_amount
                elif 1 < years_to_maturity <= 3:
                    maturity_groups["1-3 years"] += item.principal_amount
                elif 3 < years_to_maturity <= 5:
                    maturity_groups["3-5 years"] += item.principal_amount
                else:
                    maturity_groups["More than 5 years"] += item.principal_amount
            data_rows = []
            for group, total in maturity_groups.items():
                if total > 0:
                    amount_str = _format_single_notional(total, self.currency_symbol, self.prefer_abbreviated, True)
                    data_rows.append([group, amount_str])

        # --- 3. Interest Rate Profile ---
        else: # rate_profile
            title = f"Interest Rate Profile of Debt Portfolio as of {self.reporting_month} {self.reporting_day}, {self.reporting_year}"
            headers = ["Debt Instrument", "Principal Amount", "Benchmark", "Spread (bps)", "Effective Rate (%)"]
            widths = [30, 20, 15, 15, 20]
            alignments = ['l', 'r', 'l', 'r', 'r']
            data_rows = []
            for item in self.hedged_item:
                if not item.benchmark_rate or not item.spread_bps: continue # Skip items without detailed rate info
                principal_str = _format_single_notional(item.principal_amount, self.currency_symbol, self.prefer_abbreviated, True)
                benchmark_rate_val = random.uniform(1.5, 4.5) # Simulate a base rate
                effective_rate = benchmark_rate_val + (item.spread_bps / 100)
                data_rows.append([
                    item.debt_type,
                    principal_str,
                    item.benchmark_rate,
                    str(item.spread_bps),
                    f"{effective_rate:.2f}"
                ])

        data_rows = []
        for item in self.hedged_item:
            principal_str = _format_single_notional(
                item.principal_amount, self.currency_symbol, self.prefer_abbreviated, True
            )
            rate = (item.spread_bps / 100 if item.spread_bps else random.uniform(2.5, 8.5))
            rate_str = f"{rate:.2f}"
            maturity_str = str(item.maturity_year)
            data_rows.append([item.debt_type, principal_str, rate_str, maturity_str])

        if not data_rows:
            return ""

        table_builder = GenericTable(headers=headers, data_rows=data_rows, widths=widths, alignments=alignments, title=title)
        return table_builder.build()

    def _build_debt_sentence(self, item_to_describe: "DebtHedgedItem") -> str:
        """Generates the narrative sentence(s) for a single debt item."""
        # Lazy import to prevent circular dependency
        from .function_definitions import _cleanup_sentence, _format_single_notional
        from .template_definitions import point_in_time_prefixes, period_of_time_prefixes
        from .common_data import (  # fmt: skip
            months,
            termination_noun,
            termination_verbs_past,
            interest_rate_terms,
            frequencies,
            state_descriptors,
            quarters
        )

        sentences = []

        # --- 1. Generate the main sentence about the specific debt item ---
        debt_amount_str = _format_single_notional(
            item_to_describe.principal_amount, self.currency_symbol,  self.prefer_abbreviated
        )

        # Populate clauses using the single hedged_item
        ir_clause = random.choice(debt_interest_rate_clauses).format(
            ir_term=item_to_describe.benchmark_rate or random.choice(interest_rate_terms),
            pct=f"{(item_to_describe.spread_bps / 100 if item_to_describe.spread_bps else random.uniform(2.5, 6.5)):.2f}",
            pct2=f"{(item_to_describe.spread_bps / 100 + random.uniform(1,2) if item_to_describe.spread_bps else random.uniform(6.5, 8.5)):.2f}"
        )
        maturity_clause = random.choice(debt_maturity_clauses).format(
            maturity_year=item_to_describe.maturity_year,
            termination_noun=random.choice(termination_noun),
            termination_verb=random.choice(termination_verbs_past)
        )

        # Choose a template that describes the details of a single instrument
        template = random.choice(debt_templates["details"])

        # --- NEW: Use dynamic time prefixes ---
        time_prefix_template = random.choice(point_in_time_prefixes)
        time_prefix = time_prefix_template.format(
            month=self.reporting_month, end_day=self.reporting_day, year=self.reporting_year, quarter=random.choice(quarters)
        )
        time_suffix_template = random.choice(point_in_time_prefixes)
        time_suffix = time_suffix_template.format(
            month=self.reporting_month, end_day=self.reporting_day, year=self.reporting_year, quarter=random.choice(quarters)
        )

        # Format the main sentence
        main_sentence = template.format(
            company=_get_company_reference(self.company_name),
            debt_type=item_to_describe.debt_type,
            amount_str=debt_amount_str,
            maturity_clause=maturity_clause,
            interest_rate_clause=ir_clause,
            ir_term=item_to_describe.benchmark_rate
            or random.choice(interest_rate_terms),
            pct=f"{(item_to_describe.spread_bps / 100 if item_to_describe.spread_bps else random.uniform(2.5, 6.5)):.2f}",
            pct2=f"{(item_to_describe.spread_bps / 100 + random.uniform(1,2) if item_to_describe.spread_bps else random.uniform(6.5, 8.5)):.2f}",
            small_int=item_to_describe.maturity_year - self.reporting_year,
            year=self.reporting_year,
            time_prefix=time_prefix,
            time_suffix=time_suffix,
            state_descriptor=random.choice(state_descriptors),
            frequency=item_to_describe.payment_frequency or random.choice(frequencies),
            amount_str2=_format_single_notional(
                item_to_describe.principal_amount * random.uniform(0.1, 0.5),
                self.currency_symbol,
                
                self.prefer_abbreviated,
            ),
            termination_noun=random.choice(termination_noun),
            **{
                key: ""
                for key in ["composition_clause", "debt_type2", "swap_type", "end_day"]
            },  # Fill unused placeholders
        )
        sentences.append(_cleanup_sentence(main_sentence))

        # --- 2. Optionally, add a second sentence about a specific event ---
        if random.random() < 0.4: # 40% chance to add a second sentence
            event_type = random.choice(["issuance", "repayment", "refinancing"])
            template = random.choice(debt_templates[event_type])

            # --- NEW: Use dynamic time prefixes for events ---
            event_time_prefix_template = random.choice(period_of_time_prefixes)
            event_time_prefix = event_time_prefix_template.format(
                month=item_to_describe.issuance_month or random.choice(months), year=self.reporting_year, quarter=random.choice(quarters)
            )

            capex_purpose = random.choice(CAPEX_PURPOSES["generic"])
            event_sentence = template.format(
                company=self.company_name,
                action_verb=random.choice(debt_action_verbs.get(event_type, [""])),
                debt_type=item_to_describe.debt_type,
                debt_types=item_to_describe.debt_type, # debt_types is often plural, but using singular is fine here
                amount_str=debt_amount_str,
                amount_str2=_format_single_notional(item_to_describe.principal_amount * random.uniform(0.8, 1.2), self.currency_symbol,  self.prefer_abbreviated),
                interest_rate_clause=ir_clause,
                maturity_clause=maturity_clause,
                purpose_clause=f"general corporate purposes, including {capex_purpose}",
                capex_purpose=capex_purpose,
                time_prefix=event_time_prefix,
                time_suffix=time_suffix,
                year=self.reporting_year,
                month=item_to_describe.issuance_month or random.choice(months),
                termination_noun=random.choice(termination_noun),
                state_descriptor=random.choice(state_descriptors),
                **{key: "" for key in ["pct", "pct2", "small_int", "frequency", "swap_type", "end_day"]} # Add other placeholders as needed
            )
            sentences.append(_cleanup_sentence(event_sentence))
        if self.more_detail:
            # --- NEW: Add 2-3 more sentences for extra detail ---
            
            # Define a dictionary of all possible placeholders to format any template
            all_placeholders = {
                "company": _get_company_reference(self.company_name),
                "debt_type": item_to_describe.debt_type,
                "amount_str": debt_amount_str,
                "amount_str2": _format_single_notional(
                    item_to_describe.principal_amount * random.uniform(0.8, 1.2),
                    self.currency_symbol,  self.prefer_abbreviated
                ),
                "month": self.reporting_month,
                "end_day": self.reporting_day,
                "year": self.reporting_year,
                "time_suffix": time_suffix,
                "small_int": random.randint(2, 5),
                "small_int2": random.randint(2, 4),
                "pct": f"{random.uniform(2.5, 6.5):.2f}",
                "pct2": f"{random.uniform(6.5, 8.5):.2f}",
                "swap_type": self.instrument.instrument_alias if self.instrument else "",
                "ir_term": item_to_describe.benchmark_rate or random.choice(interest_rate_terms),
                "maturity_clause": maturity_clause,
                "frequency": item_to_describe.payment_frequency or random.choice(frequencies),
                "termination_noun": random.choice(termination_noun),
            }

            # Define which template categories are suitable for "more detail"
            # 'details' is included to add more specific financial metrics.
            detail_categories = ["debt_covenant", "details"]
            # --- NEW: Only add "unhedged" if there is no associated instrument ---
            if self.instrument is None:
                detail_categories.append("unhedged")

            # Randomly select 2 or 3 categories to add sentences from
            num_details = random.randint(2, 3)
            # Use random.sample to ensure we don't pick the same category twice
            categories_to_add = random.sample(detail_categories, k=min(num_details, len(detail_categories)))

            for category in categories_to_add:
                template = random.choice(debt_templates[category])
                # Use a copy and update with any missing keys to prevent format errors
                sentence = template.format_map({**all_placeholders, **{k: "" for k in ["action_verb", "debt_types", "purpose_clause", "capex_purpose", "time_prefix", "state_descriptor", "composition_clause", "debt_type2", "interest_rate_clause"]}})
                sentences.append(_cleanup_sentence(sentence))

        return ". ".join(sentences) + "."
