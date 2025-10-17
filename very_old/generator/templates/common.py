money_unit_list = ["thousand", "million", "billion"]
months = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
]

quarters = ["first", "second", "third", "fourth", "last", "1st", "2nd", "3rd", "4th"]
# Currency codes for international flavor
currency_codes = [
    "$",
    "USD ",
    "€",
    "EUR ",
    "£",
    "GBP ",
    "¥",
    "JPY ",
    "CHF ",  # Swiss Franc
    "CNY ",  # Chinese Yuan
    "HKD ",  # Hong Kong Dollar
    "SGD ",  # Singapore Dollar
    "CAD ",  # Canadian Dollar
    "AUD ",  # Australian Dollar
    "NZD ",  # New Zealand Dollar
    "SEK ",  # Swedish Krona
    "NOK ",  # Norwegian Krone
    "DKK ",  # Danish Krone
    "ZAR ",  # South African Rand
    "BRL ",  # Brazilian Real
    "MXN ",  # Mexican Peso
    "INR ",  # Indian Rupee
    "KRW ",  # South Korean Won
    "TRY ",  # Turkish Lira
]
currency_pairs = [
    # Major USD crosses
    "EUR/USD",
    "GBP/USD",
    "USD/JPY",
    "USD/CHF",
    "USD/CAD",
    "AUD/USD",
    "NZD/USD",
    "USD/CNY",
    "USD/HKD",
    "USD/SGD",
    "USD/INR",
    "USD/KRW",
    "USD/MXN",
    "USD/BRL",
    "USD/TRY",
    "USD/ZAR",
    # Euro crosses
    "EUR/GBP",
    "EUR/JPY",
    "EUR/CHF",
    "EUR/CAD",
    "EUR/AUD",
    "EUR/NZD",
    "EUR/SEK",
    "EUR/NOK",
    "EUR/DKK",
    "EUR/PLN",
    "EUR/HUF",
    "EUR/CZK",
    # Asia-Pacific crosses
    "AUD/JPY",
    "AUD/NZD",
    "AUD/CAD",
    "NZD/JPY",
    "SGD/JPY",
    "CNY/JPY",
    # Pound crosses
    "GBP/JPY",
    "GBP/CHF",
    "GBP/CAD",
    "GBP/AUD",
    "GBP/NZD",
]


major_currencies = [
    "the Euro",
    "the British pound",
    "the Swiss franc",
    "the Japanese yen",
    "the Canadian dollar",
    "the Australian dollar",
    "the Chinese yuan",
    "the U.S. Dollar",
]

european_currencies = [
    "the Euro",
    "the British pound",
    "the Swiss franc",
    "the Norwegian krone",
    "the Swedish krona",
    "the Polish zloty",
    "the Czech koruna",
    "the Hungarian forint",
]

asian_currencies = [
    "the Japanese yen",
    "the Chinese yuan",
    "the Indian rupee",
    "the South Korean won",
    "the Singapore dollar",
    "the Thai baht",
    "the Malaysian ringgit",
]

americas_currencies = [
    "the Canadian dollar",
    "the Mexican peso",
    "the Brazilian real",
    "the Argentine peso",
    "the Chilean peso",
    "the Colombian peso",
]
all_currencies = (
    set(major_currencies)
    | set(european_currencies)
    | set(asian_currencies)
    | set(americas_currencies)
)
all_currencies = list(all_currencies)
frequencies = [
    "quarterly",
    "on a regular basis",
    "at least quarterly",
    "monthly",
    "periodically",
]
volume_units = [
    "barrels",
    "MMBtu",
    "MWh",
    "metric tons",
    "bushels",
    "gallons",
    "ton",
    "pound",
    "bushel",
    "board foot",
]
assessment_verbs = [
    "assessed",
    "evaluated",
    "tested",
    "measured",
    "analyzed",
    "conducted",
    "performed",
]
balance_sheet_locations = [
    "other income (expense), net",
    "change in fair value of derivative liabilities",
    "other comprehensive income",
    "earnings",
    "the consolidated statements of operations",
    "statement of operations",
]


# ========== SHARED / GENERIC ==========
shared_issuers = [
    "FASB",
    "Financial Accounting Standards Board",
    "SEC",
    "IASB",
    "International Accounting Standards Board",
    "PCAOB",
    "FASB's Emerging Issues Task Force",
]

shared_topics = [
    "revenue recognition",
    "lease accounting",
    "credit losses",
    "financial instruments",
    "business combinations",
    "stock compensation",
    "fair value measurements",
    "income taxes",
    "segment reporting",
    "consolidation",
    "intangible assets",
    "debt modifications",
    "defined benefit plans",
    "collaborative arrangements",
    "insurance contracts",
]

other_standard_names = [
    "ASU 2016-02",  # Leases (ASC 842)
    "ASU 2014-09",  # Revenue Recognition (ASC 606)
    "ASU 2016-13",  # Credit Losses (ASC 326)
    "ASC 842",  # Leases
    "ASC 606",  # Revenue
    "ASC 326",  # Credit Losses
    "ASC 718",  # Stock Compensationg
    "ASC 805",  # Business Combinations
    "ASC 740",  # Income Taxes
    "ASC 820",  # Fair Value Measurement
    "Topic 842",  # Leases
    "Topic 606",  # Revenue Recognition
]

shared_purposes = [
    "improve financial reporting and provide additional disclosures",
    "align accounting practices with economic substance",
    "enhance transparency and comparability",
    "simplify the accounting model",
    "provide clarification on implementation issues",
    "expand presentation and disclosure requirements",
    "address practice diversity and implementation questions",
    "converge U.S. GAAP with international standards",
    "expand the related presentation and disclosure requirements",
    "change how companies assess effectiveness",
    "eliminate the separate measurement and reporting of hedge ineffectiveness",
]

shared_additional_features_templates = [
    "The guidance also {additional_feature}",
    "Additionally, the standard {additional_feature}",
    "The new guidance {additional_feature}",
    "The update also {additional_feature}",
]

shared_effective_date_templates = [
    "The guidance is effective in fiscal year {year}, with early adoption permitted",
    "The standard is effective for fiscal years beginning after {month} {day}, {year}",
    "This guidance becomes effective for annual periods beginning after {month} {end_day}, {year}, with early application permitted",
    "The amendments are effective for fiscal years, and interim periods within those years, beginning after {month} {end_day}, {year}",
    "Effective date is for annual reporting periods beginning after {month} {end_day}, {year}",
    "{company} must adopt this guidance no later than fiscal year {year}",
]

shared_adoption_status_templates = [
    "{company} adopted this guidance on {month} {day}, {year} using the {method}",
    "{company} adopted {standard} effective {month} {day}, {year}",
    "{company} early adopted the standard in {year}",
    "{company} will adopt the guidance in fiscal year {year}",
    "{company} is currently evaluating the impact of adopting this guidance",
    "{company} does not expect the adoption of this standard to have a material impact on its consolidated financial statements",
    "{company} adopted the new guidance prospectively",
    "The standard was adopted retrospectively with a cumulative-effect adjustment to retained earnings",
]

shared_adoption_methods = [
    "modified retrospective approach",
    "full retrospective method",
    "prospective method",
    "cumulative-effect adjustment",
    "practical expedient package",
    "modified retrospective transition method",
]

shared_adoption_impact_templates = [
    "The adoption resulted in {impact}",
    "Upon adoption, {company} recognized {impact}",
    "The cumulative effect of adoption was {impact}",
    "Implementation of the standard resulted in {impact}",
    "As a result of adoption, {impact}",
]

shared_evaluation_templates = [
    "{company} is currently evaluating the potential impact of this guidance on its consolidated financial statements and related disclosures",
    "{company} has not yet completed its assessment of the impact of adopting this standard",
    "{company} is analyzing the effects of the new guidance on its accounting policies and internal controls",
    "Management is in the process of evaluating the provisions of the standard to determine its impact",
    "{company} has established an implementation team to assess the requirements and impacts of the new guidance",
    "{company} does not expect this guidance to have a material effect on its financial position or results of operations",
]

shared_transition_templates = [
    "{company} will apply the {method} upon adoption",
    "{company} elected to apply the practical expedients available under the transition guidance",
    "{company} intends to adopt the standard using the {method} with {feature}",
    "{company} selected the {method} for transition purposes",
]

shared_transition_features = [
    "the option to not restate comparative periods",
    "application of hindsight",
    "certain relief provisions",
    "portfolio-level application where appropriate",
    "use of transition practical expedients",
]

shared_disclosure_change_templates = [
    "The new standard requires additional disclosures regarding {disclosure_topic}",
    "Enhanced disclosures are required for {disclosure_topic}",
    "The guidance eliminates disclosure of {disclosure_topic} while adding requirements for {disclosure_topic2}",
    "New qualitative and quantitative disclosure requirements focus on {disclosure_topic}",
    "{company} will provide expanded disclosures about {disclosure_topic} beginning in fiscal year {year}",
]

shared_practical_expedient_templates = [
    "{company} elected to apply the practical expedient to {expedient_description}",
    "{company} utilized practical expedients available under the transition guidance, including {expedient_description}",
    "{company} did not elect the practical expedient related to {expedient_description}",
    "Available practical expedients include the option to {expedient_description}",
]

shared_recent_pronouncement_templates = [
    "Recently issued accounting pronouncements not yet adopted include {standard}, which addresses {topic}",
    "In {month} {year}, the {issuer} issued {standard} related to {topic}, which {company} will adopt in {adoption_year}",
    "Management continues to monitor new accounting pronouncements issued by the {issuer} for potential impact",
    "Other new accounting guidance issued but not yet effective is not expected to have a material impact on the consolidated financial statements",
    "{company} reviews all recently issued accounting standards to determine their applicability and impact",
]

shared_standards_templates = [
    "In {month} {year}, the {issuer} issued guidance on {topic} to {purpose}",
    "The {issuer} issued {standard} in {year}, which {description}",
    "New accounting guidance issued by the {issuer} in {month} {year} addresses {topic}",
    "{standard} was issued in {year} to {purpose}",
    "During {year}, the {issuer} released updated guidance on {topic}",
]

# ========== HEDGING / DERIVATIVE POLICY ==========
hedging_descriptions = [
    "expand presentation and disclosure requirements, change how companies assess hedge effectiveness, and eliminate separate measurement of hedge ineffectiveness",
    "improves alignment of hedge accounting with risk management strategies",
    "modifies the treatment of fair value and cash flow hedges to reflect underlying economics",
]

hedging_additional_features = [
    "enables more financial and nonfinancial hedging strategies to become eligible for hedge accounting",
    "aligns accounting treatment with risk management activities",
    "simplifies the application of hedge accounting",
    "allows designation of component risks in nonfinancial hedges",
    "permits hedging of contractually specified components in cash flow exposures",
]

hedge_change_policy_templates = [
    "In {month} {year}, the {issuer} issued {standard} related to hedging activities. The guidance {description}. Additionally, it {additional_feature}",
    "The {issuer} issued {standard} to address {topic}. This update {description}. The new guidance {additional_feature}",
    "Hedging Activities: In {month} {year}, {issuer} released guidance on {topic}. It {description} and {additional_feature}",
    "The amendment to Topic 815 {description} and {additional_feature}. Effective for fiscal years beginning after {month} {eff_day}, {year}",
]

# ========== GENERAL ACCOUNTING POLICY ==========
general_descriptions = [
    "requires recognition of lease assets and liabilities for operating leases",
    "changes the impairment model for financial instruments to an expected credit loss model",
    "establishes a revenue recognition framework based on transfer of control",
    "updates classification and measurement guidance for financial instruments",
    "updates accounting for share-based payments",
    "clarifies business combination definition and asset vs business acquisition criteria",
    "simplifies goodwill impairment testing",
    "updates income tax recognition for intra-entity asset transfers",
]

general_additional_features = [
    "simplifies certain aspects of accounting application",
    "provides transition relief and expedients",
    "permits practical expedients for implementation",
    "reduces disclosure complexity while maintaining transparency",
    "allows entities to apply hindsight in transition",
]

general_policy_templates = [
    "In {month} {year}, the {issuer} issued {standard} addressing {topic}. The standard {description}. Additionally, it {additional_feature}",
    "The {issuer} issued {standard} to {purpose}. The guidance {description} and {additional_feature}",
    "Accounting Update: In {month} {year}, {issuer} released {standard} covering {topic}. It {description}. The update {additional_feature}",
    "During {year}, the {issuer} issued guidance under {standard} to {purpose}. {description}. Additionally, it {additional_feature}",
]

# ==============================
# Counterparty / Credit Risk Templates
# ==============================
risk_templates = [
    "Based upon certain factors, including a review of the {item} for {company}'s counterparties, {company} determined its counterparty credit risk to be {materiality}",
    "After assessing {item} and other indicators for {company}'s derivative counterparties, management concluded that counterparty exposure is {materiality}",
    "{company} periodically reviews {item} and other market data to evaluate counterparty credit risk, which was determined to be {materiality}",
    "Based on a review of {item} and internal assessments, {company} concluded that exposure to counterparty credit risk is {materiality}",
    "{company} monitors {item} as part of its evaluation of counterparty credit exposure associated with derivative contracts",
    "Considering {item}, credit ratings, and exposure limits, {company} determined that counterparty risk is {materiality}",
    "{company} evaluates {item} to assess potential credit exposure under its derivative contracts and considers such exposure to be {materiality}",
    "Taking into account {item} and the financial strength of counterparties, {company} considers the overall counterparty credit risk to be {materiality}",
]

# ==============================
# Risk Items
# ==============================

# Derivative / Hedging-Related Risk Items
risk_items_derivative = [
    "credit default swap spreads",
    "credit default swap rates",
    "counterparty credit spreads",
    "market-implied default probabilities",
    "collateral coverage ratios under derivative agreements",
    "credit exposure under derivative master netting arrangements",
    "net derivative positions by counterparty",
    "credit valuation adjustments (CVA)",
    "potential future exposure on derivative contracts",
    "credit risk metrics for derivative counterparties",
    "mark-to-market exposure on outstanding swaps",
    "counterparty exposure by derivative type",
]

# General / Non-Derivative (“Other”) Risk Items
risk_items_other = [
    "customer credit ratings",
    "trade receivable aging reports",
    "exposure by customer group",
    "accounts receivable turnover ratios",
    "supplier credit evaluations",
    "internal credit risk assessments unrelated to derivatives",
    "counterparty concentration in commercial transactions",
    "loan portfolio credit quality indicators",
    "credit loss reserves and allowances",
    "overall counterparty creditworthiness in non-derivative activities",
    "exposure to sovereign or institutional counterparties",
]

# Optional
materiality = [
    "immaterial",
    "not significant",
    "limited",
    "material",
    "significant",
    "not material",
]
