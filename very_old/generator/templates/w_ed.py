warrant_issuance_templates = [
    'In connection with the {event}, {company} issued warrants to purchase up to {shares} shares of common stock at an exercise price of {currency_code}{price} per share, in accordance with the guidance contained in FASB ASC 815 "Derivatives and Hedging" whereby under that provision the warrants do not meet the criteria for equity treatment and must be recorded as a liability',
    "During {month} {year}, {company} issued {shares} warrants exercisable at {currency_code}{price} per share in conjunction with {event} and is classified as a liability",
    "As part of {event}, {company} granted liability-classified warrants for {shares} shares with a strike price of {currency_code}{price}, expiring in {expiry_year}",
    "{company} issued {shares} warrants at an exercise price of {currency_code}{price} per share, are classified as liabilities the guidence of ASC 815, as consideration for {event}",
    "In {month} {year}, warrants to acquire {shares} shares at {currency_code}{price} per share were issued in connection with {event}, and are derivative liabilities",
    "Under the guidance in ASC 815-40, certain warrants issued at {year} do not meet the criteria for equity treatment",
]

# Warrant events/reasons
warrant_events = [
    "a debt financing transaction",
    "the series B preferred stock offering",
    "a credit facility agreement",
    "initial public offering",
    "a strategic partnership agreement",
    "the convertible note issuance",
    "a private placement",
    "the acquisition financing",
    "vendor financing arrangements",
]

# Warrant fair value measurement templates
warrant_fv_templates = [
    "The fair value of the warrants classifed as liabilities was determined to be {currency_code}{amount} {money_unit} using the  as of {month} {end_day}, {year}",
    "At issuance, the warrant liabilities were valued at {currency_code}{amount} {money_unit} using a {model}",
    "{company} estimated the fair value of the warrants at {currency_code}{amount} {money_unit} as of {month} {end_day}, {year} using the {model} methodology",
    "Using a {model}, the warrant liabilities were fair valued at {currency_code}{amount} {money_unit} as of {month} {end_day}, {year}",
    "The fair value of outstanding liability-classified warrants totaled {currency_code}{amount} {money_unit} at year-end {year}, {verb} using {model}",
    "The fair value of outstanding warrant liabilities totaled {currency_code}{amount} {money_unit} at year-end {year}, {verb} using {model}",
    "The fair value of the warrants classified as liabilities is estimated using the {model}, with the following inputs as of {month} {year}",
    "The fair value of the warrant liabilities presented below were {verb} using {model}",
]


# Warrant liability classification templates
warrant_liability_templates = [
    "The warrants are classified as liabilities and marked to market each reporting period with changes in fair value recorded in {location}",
    "These warrants are recorded as liabilities at fair value, with subsequent changes recognized in {location}",
    "{company} accounts for the warrants as liabilities rather than equity measured at fair value through {location}",
    "After all relevant assessments, {company} determined that the warrants issued under the {event} require classification as a liability pursuant to ASC 840",
    "Warrant liabilities are remeasured to fair value at each balance sheet date with gains and losses recorded in {location}",
    "As the warrants contain certain provisions, they are classified as liabilities and adjusted to fair value quarterly through {location}",
    "Warrants accounted for as liabilities have the potential to be settled in cash or are not indexed to {company}'s own stock",
    "This warrant liability will be re-measured at each balance sheet date until the warrants are exercised or expire, and any change in fair value will be recognized in {company}'s {location}",
    "Any decrease or increase in the estimated fair value of the warrant liability since the most recent balance sheet date is recorded in {company}'s {location} as changes in fair value of derivative liabilities",
    "The amount of warrant liability was determined and recognized on {location} for the applicable reporting period based on the number of warrants that would have been issued",
]

# Derivative liability general templates
deriv_liability_general_templates = [
    "Derivative liabilities consist primarily of warrant liabilities and are measured at fair value on a recurring basis using Level 3 inputs",
    "{company}'s derivative liabilities primarily relate to freestanding warrants and embedded conversion features that require bifurcation",
    "As of {month} {end_day}, {year}, derivative liabilities totaled {currency_code}{amount} {money_unit} compared to {currency_code}{prev_amount} {money_unit} in the prior year",
    "Changes in the fair value of derivative liabilities during {year} resulted in a {gain_loss} of {currency_code}{amount} {money_unit}",
    "{company} recognized derivative liabilities of {currency_code}{amount} {money_unit} related to warrants issued in connection with financing transactions during {year}",
    "{company} ’s warrant liability is based on  utilizing management judgment and pricing inputs from observable and unobservable markets with less volume and transaction frequency than active markets",
    "The following table presents information about {company}'s warrant liabilities that are measured at fair value on a recurring basis at {month} {end_day}, {year} and indicates the fair value hierarchy of the valuation inputs",
]

# Down round feature templates
down_round_templates = [
    "The warrants contain down round provisions that adjust the exercise price if {company} issues equity securities at prices below the then-current exercise price",
    "Due to down round features that could result in a variable number of shares upon exercise, the warrants are classified as liabilities rather than equity",
    "The warrants include anti-dilution protection in the form of down round provisions, requiring liability classification under ASC 815-40",
    "Down round features embedded in the warrants preclude equity classification and require remeasurement at fair value each period",
]

# Earnout liability templates
earnout_templates = [
    "In connection with the acquisition of {target}, {company} recorded an earnout liability of {currency_code}{amount} {money_unit}, which will be settled in cash or shares based on achievement of revenue milestones through {year}",
    "{company} assumed earnout obligations valued at {currency_code}{amount} {money_unit} as part of the {target} acquisition, payable upon achievement of specified operational targets",
    "Contingent consideration arrangements from business combinations resulted in derivative liabilities of {currency_code}{amount} {money_unit} as of {month} {end_day}, {year}",
    "The earnout liability related to the {target} acquisition was remeasured to {currency_code}{amount} {money_unit} during {year}, with the change recorded in other income (expense)",
]

# Embedded derivative identification templates
embedded_identification_templates = [
    "{company} has identified embedded derivatives within certain {host_contract} that require bifurcation and separate accounting under ASC 815",
    "Certain {host_contract} contain embedded features that meet the definition of derivatives and are not clearly and closely related to the host contract",
    "{company}'s {host_contract} include embedded derivative features that have been bifurcated and recorded separately at fair value",
    "Embedded derivatives have been identified within {host_contract} and are accounted for separately from the host instrument",
    "{company} {verb} {host_contract} and determined that certain embedded features require bifurcation under derivative accounting guidance",
    '{company} adopted SFAS 155, "Accounting for Certain Hybrid Instruments" to identify all embedded derivative features',
    "{company} measures a hybrid financial instrument in its entirety at fair value after having identified all embedded derivative features",
    "{company} identified and documented the embedded derivative features, and the irrevocably elected to measure and carry the {host_contract} at fair value",
    "This standard requires the conversion feature of {host_contract} be separated from the host contract and presented as a derivative instrument if certain conditions are met",
]

host_contracts = [
    "convertible debt instruments",
    "OTC convertible notes hedge",
    "convertible hedge",
    "hybrid financial instruments",
    "convertible preferred stock",
    "redeemable preferred stock",
    "convertible notes payable",
    "customer contracts",
    "supplier agreements",
    "lease agreements with variable payments",
    "warrants",
]

# Specific embedded derivative types
embedded_types_templates = [
    "The embedded derivatives consist primarily of {embedded_type} that are measured at fair value through earnings",
    "{company} has bifurcated {embedded_type} from the host {host_contract}",
    "Embedded {embedded_type} within {host_contract} are carried at fair value with changes recorded in {location}",
    "The {embedded_type} embedded in the {host_contract} requires separate recognition as a derivative liability",
]

embedded_types = [
    "conversion features",
    "redemption features",
    "reset provisions",
    "make-whole provisions",
    "contingent interest features",
    "price adjustment mechanisms",
    "indexed payment terms",
    "foreign currency-linked provisions",
    "commodity price escalation clauses",
    # Common embedded derivative features to add:
    "put options",  # investor put right in debt
    "call options",  # issuer call right
    "prepayment options",  # common in loans/leases
    "step-up interest features",  # coupon steps up/down
    "participating payment features",  # extra payments linked to equity/earnings
    "profit participation features",  # linked to issuer performance
    "contingent conversion features",  # conversion only if trigger met
    "down-round protection",  # equity-linked anti-dilution
    "ratchet provisions",  # similar to down-round resets
    "dual currency provisions",  # payment in one of two currencies
    "interest rate reset features",  # coupon reset tied to benchmark
    "equity-linked provisions",  # payment terms tied to stock price
    "inflation indexation clauses",  # payments indexed to CPI/RPI
    "performance-based conversion",  # convertibility linked to financial targets
]


# Convertible debt embedded derivative templates
convertible_debt_templates = [
    "{company} issued {currency_code}{principal} {money_unit} in convertible senior notes in {month} {year}. The conversion feature was determined to be an embedded derivative requiring bifurcation, with an initial fair value of {currency_code}{embedded_fv} {money_unit}",
    "In {month} {year}, {company} completed an offering of {currency_code}{principal} {money_unit} aggregate principal amount of convertible notes. The embedded conversion option was bifurcated and valued at {currency_code}{embedded_fv} {money_unit}",
    "The convertible notes include conversion features that are not clearly and closely related to the debt host. The embedded derivative was recorded at a fair value of {currency_code}{embedded_fv} {money_unit} at issuance",
    "Upon issuance of the {currency_code}{principal} {money_unit} convertible debt in {year}, {company} allocated {currency_code}{embedded_fv} {money_unit} to the embedded conversion derivative",
]

# Fair value measurement of embedded derivatives
embedded_fv_templates = [
    "The fair value of the embedded derivative was {currency_code}{amount} {money_unit} as of {month} {end_day}, {year}, compared to {currency_code}{prev_amount} {money_unit} at {month} {end_day}, {prev_year}",
    "Embedded derivative liabilities totaled {currency_code}{amount} {money_unit} at year-end {year}, representing a {change_direction} from {currency_code}{prev_amount} {money_unit} in the prior year",
    "As of {month} {end_day}, {year}, {company} recorded embedded derivative liabilities of {currency_code}{amount} {money_unit} measured using Level 3 inputs",
    "The embedded derivatives had a fair value of {currency_code}{amount} {money_unit} at {month} {end_day}, {year}, with changes in value recorded in other expense",
]

# Valuation methodology templates
embedded_valuation_templates = [
    "The fair value of embedded derivatives is determined using a {model}, incorporating assumptions for {assumptions}",
    "{company} values embedded derivatives using {model} with key inputs including {assumptions}",
    "Fair value is estimated using {model}, which considers {assumptions}",
    "Embedded derivatives are valued using {model}, with significant unobservable inputs related to {assumptions}",
]

valuation_models = [
    "Monte Carlo simulation model",
    "binomial lattice model",
    "Black-Scholes option pricing model",
    "BSM model",
]

valuation_assumptions = [
    "stock price volatility, risk-free interest rates, and expected term",
    "credit spreads, conversion probability, and stock price volatility",
    "volatility, dividend yield, and time to maturity",
    "probability of conversion, discount rates, and market price of common stock",
    "expected volatility, probability of redemption, and time to maturity",
]

# Fair value change recognition templates
embedded_fv_change_templates = [
    "During {year}, {company} recognized a {gain_loss} of {currency_code}{amount} {money_unit} related to changes in the fair value of embedded derivatives",
    "Changes in fair value of embedded derivatives resulted in a {gain_loss} of {currency_code}{amount} {money_unit} for the year ended {month} {end_day}, {year}",
    "{company} recorded {gain_loss}s of {currency_code}{amount} {money_unit} from the remeasurement of embedded derivative liabilities during {year}",
    "Fair value adjustments on embedded derivatives contributed a {gain_loss} of {currency_code}{amount} {money_unit} to {location} in {year}",
]

# Closely and clearly related analysis templates
ccr_analysis_templates = [
    # Assessment leading to bifurcation
    "{company} {verb} an assessment of whether the embedded features were clearly and closely related to the economic characteristics of the host contract and concluded bifurcation was required",
    "The embedded features are not clearly and closely related to the debt host instrument, as the conversion feature is indexed to {company}'s own stock and includes down round protection",
    "Management {verb} the economic characteristics and risks of the embedded features and determined they are not clearly and closely related to the host, requiring separate accounting",
    "The embedded derivative fails the clearly and closely related test due to its equity-linked characteristics and variable settlement provisions",
    # Assessment leading to no bifurcation
    "{company} {verb} the terms of the embedded provisions and concluded they are clearly and closely related to the host contract, and therefore do not require bifurcation",
    "The embedded features are considered clearly and closely related to the debt host instrument, and accordingly no separate derivative recognition is necessary",
    "Based on its analysis, management determined that the embedded option is clearly and closely related to the host contract and remains accounted for within the host instrument",
    # Neutral/assessment-only language
    "Management {verb} whether the embedded features were clearly and closely related to the host instrument as required under ASC 815",
    "{company} {verb} the economic characteristics of the embedded provisions in accordance with the clearly and closely related guidance",
    "An evaluation of the embedded derivative features was performed to {verb} whether they are clearly and closely related to the host contract",
    # Variations in contract types
    "{company} {verb} its lease agreements containing variable payments and determined the features are not clearly and closely related to the lease host",
    "{company} {verb} customer contracts containing indexed payment terms and concluded bifurcation was required",
    "Management reviewed supplier agreements with commodity-linked pricing terms and determined the features were not clearly and closely related to the host contract",
]

# Conversion/settlement templates
embedded_settlement_templates = [
    "Upon conversion or redemption of the host instrument, the embedded derivative is remeasured to fair value with any gain or loss recognized in earnings, and the liability is extinguished",
    "In {month} {year}, {currency_code}{principal} {money_unit} of convertible notes were converted, resulting in settlement of the associated embedded derivative liability and recognition of a {gain_loss} of {currency_code}{amount} {money_unit}",
    "{company} settled embedded derivative liabilities totaling {currency_code}{amount} {money_unit} during {year} in connection with debt extinguishment transactions",
    "During the {quarter} quarter of {year}, the conversion of notes resulted in derecognition of {currency_code}{amount} {money_unit} in embedded derivative liabilities",
]

# Embedded FX derivatives templates
embedded_fx_templates = [
    # General identification
    "Certain {host_contract} contain payments indexed to foreign currency exchange rates that represent embedded foreign currency derivatives",
    "{company} has identified embedded foreign currency derivatives in {host_contract} where payments are denominated in a currency other than the functional currency of either party",
    "Embedded foreign exchange derivatives arise from {host_contract} with payment terms linked to movements in the {currency_pair} exchange rate",
    "{company}'s {host_contract} include embedded FX derivatives requiring bifurcation due to currency mismatches between contract terms and functional currencies",
    # Outcome: bifurcation required
    "The embedded foreign currency feature is not clearly and closely related to the host contract and was bifurcated as a separate derivative instrument",
    "Management concluded that the currency-indexed provisions of the {host_contract} are not clearly and closely related and therefore require separate accounting",
    "{company} determined that the foreign currency-linked payments within {host_contract} fail the closely related test and must be accounted for as derivatives",
    # Outcome: bifurcation not required
    "The foreign currency denominated payments within the {host_contract} are considered clearly and closely related to the host and do not require bifurcation",
    "Management assessed the FX-linked terms of the {host_contract} and concluded they are clearly and closely related to the economic characteristics of the host instrument",
    "The embedded foreign exchange feature is deemed to be clearly and closely related to the host contract and remains within the host’s accounting treatment",
    # Contract variations
    "{company}'s long-term debt agreements denominated in {currency_pair} contain embedded FX derivatives requiring analysis under ASC 815",
    "Lease agreements with rental payments linked to {currency_pair} expose {company} to embedded foreign exchange derivative features",
    "Supplier agreements denominated in {currency_pair} include embedded currency features subject to bifurcation assessment",
    "Customer contracts requiring settlement in {currency_pair} create embedded FX derivatives under the host revenue arrangement",
    "Royalty agreements denominated in foreign currency contain embedded foreign exchange features subject to ASC 815 analysis",
    # Neutral disclosure language
    "Management evaluated embedded foreign exchange features in {host_contract} to determine whether they are clearly and closely related to the host instrument",
    "An assessment was performed of foreign currency-linked provisions in {host_contract} under the embedded derivative guidance",
]


# Historical warrant templates (for label 5)
warrant_past_templates = [
    "During {year}, {company} had outstanding warrant liabilities to purchase {shares} shares at {currency_code}{price} per share, which expired unexercised in {month} {year}",
    "In {year}, all outstanding warrants were exercised or expired, and {company} has no derivative liabilities as of {month} {end_day}, {current_year}",
    "{company} previously issued warrants in connection with {event} during {year}. These derivative liabilities were fully exercised by {month} {expiry_year}",
    "Warrants issued in {year} with an exercise price of {currency_code}{price} per share were settled during {settlement_year}, eliminating all derivative warrant liabilities",
    "As of {month} {end_day}, {current_year}, {company} no longer has any outstanding derivative liabilities. All liability-classified warrants issued in {year} were exercised or expired by {expiry_year}",
]

warrant_liability_extinguishment_templates = [
    "The warrant liabilities of {currency_code}{amount} {money_unit} recorded in {year} were extinguished upon exercise and expiration during {settlement_year}",
    "All warrant liabilities were eliminated in {settlement_year} following the exercise of outstanding warrants by holders",
    "During {settlement_year}, {company} settled all outstanding warrant liabilities, recognizing a final fair value adjustment of {currency_code}{amount} {money_unit}",
    "The warrant liability balance of {currency_code}{amount} {money_unit} at {month} {end_day}, {year} was reduced to zero during {settlement_year} upon warrant exercises",
]

earnout_past_templates = [
    "The earnout liability related to the {target} acquisition, recorded in {year}, was settled in {settlement_year} upon achievement of the specified milestones",
    "Contingent consideration from the {year} acquisition of {target} was paid out in {settlement_year}, extinguishing the {currency_code}{amount} {money_unit} earnout liability",
    "{company}'s earnout obligations from prior acquisitions were fully satisfied by {settlement_year}, with no remaining contingent consideration liabilities",
    "During {settlement_year}, {company} paid {currency_code}{amount} {money_unit} to settle earnout liabilities related to business combinations completed in {year}",
]


# ========== SNIPPET 3: Add past-tense embedded derivative templates ==========
# Insert after embedded_fx_templates (around line 280)

# Historical embedded derivative templates (for label 7)
embedded_past_templates = [
    # Convertible debt / notes
    "{company} previously {verb} embedded derivatives within {host_contract} issued in {year}. These instruments were fully converted or redeemed by {settlement_year}",
    "Embedded derivative liabilities related to convertible notes issued in {year} were extinguished upon conversion during {settlement_year}",
    "The embedded derivatives bifurcated from {host_contract} in {year} were eliminated following the redemption of the host instruments in {settlement_year}",
    "All embedded features associated with convertible debt issued in {year} expired unexercised by {settlement_year}",
    # General elimination / maturity
    "As of {month} {end_day}, {current_year}, {company} has no embedded derivative liabilities. All instruments containing embedded features were settled in {settlement_year}",
    "{company} redeemed all outstanding {host_contract} containing embedded derivatives during {settlement_year}, resulting in elimination of bifurcated liabilities",
    "Embedded derivative instruments recognized in prior periods were derecognized following the settlement of the underlying {host_contract}",
    "The embedded features within {host_contract} issued in {year} matured in accordance with their contractual terms during {settlement_year}",
    # Other host contract variations
    "Embedded derivatives associated with redeemable preferred stock issued in {year} were extinguished upon repurchase in {settlement_year}",
    "The embedded foreign currency features within supplier agreements entered in {year} no longer exist following contract termination in {settlement_year}",
    "Royalty agreements containing commodity-linked embedded derivatives expired by {settlement_year}, and no related liabilities remain",
    "Lease agreements with variable FX-linked payments identified as embedded derivatives were terminated during {settlement_year}",
    # Explicit none outstanding / balance sheet focus
    "No embedded derivative liabilities were outstanding as of {month} {end_day}, {current_year}, as all bifurcated instruments had been settled or converted",
    "All previously bifurcated embedded derivatives were derecognized, and no amounts remain recorded on the consolidated balance sheet",
    "Management notes that as of {month} {end_day}, {current_year}, {company} no longer maintains any embedded derivative positions",
]

convertible_debt_redemption_templates = [
    # Full conversion / redemption
    "The {currency_code}{principal} {money_unit} convertible notes issued in {year} were fully converted to common stock during {settlement_year}, resulting in derecognition of the {currency_code}{embedded_fv} {money_unit} embedded derivative liability",
    "In {month} {settlement_year}, {company} redeemed all outstanding convertible debt originally issued in {year}, eliminating embedded derivative liabilities of {currency_code}{amount} {money_unit}",
    "The convertible debt instruments with embedded derivatives issued in {year} matured in {settlement_year}, with all notes converted to equity prior to maturity",
    "During {settlement_year}, {company} completed the conversion of all {currency_code}{principal} {money_unit} in convertible notes, extinguishing the related embedded derivative liability",
    # Partial / repurchase
    "{company} repurchased a portion of its convertible notes issued in {year}, reducing embedded derivative liabilities by {currency_code}{amount} {money_unit} during {settlement_year}",
    "Only part of the {currency_code}{principal} {money_unit} convertible notes were converted during {settlement_year}, with the remainder redeemed in cash, eliminating the associated embedded derivatives",
    # Early / induced conversion
    "In {settlement_year}, {company} induced early conversion of {currency_code}{principal} {money_unit} convertible notes originally due {maturity_year}, eliminating related embedded derivative liabilities",
    "Convertible notes issued in {year} were settled earlier than contractual maturity in {settlement_year}, derecognizing bifurcated embedded derivative liabilities",
    # Settlement method variations
    "Embedded derivative liabilities of {currency_code}{embedded_fv} {money_unit} were extinguished when convertible notes were settled in cash rather than shares during {settlement_year}",
    "Upon conversion in {settlement_year}, holders elected mixed settlement (part cash, part equity), resulting in derecognition of the embedded derivative component",
    # Gain/loss on extinguishment
    "The redemption of convertible debt in {settlement_year} resulted in a {gain_loss} of {currency_code}{amount} {money_unit} recognized on extinguishment of the embedded derivative liability",
    "Conversion of convertible notes during {settlement_year} eliminated embedded derivative liabilities and generated a {gain_loss} recorded in other income (expense)",
    # Zero balance confirmation
    "As of {month} {end_day}, {settlement_year}, no embedded derivative liabilities remain from convertible notes, as all such instruments were either converted or redeemed",
]


embedded_no_longer_outstanding_templates = [
    # General eliminations
    "{company} no longer has any embedded derivative liabilities as all instruments containing bifurcated features were settled, converted, or matured by {settlement_year}",
    "As of {month} {end_day}, {current_year}, there are no outstanding embedded derivatives. All such liabilities were extinguished in {settlement_year}",
    "The embedded derivative liabilities of {currency_code}{amount} {money_unit} recorded in prior years were fully eliminated by {settlement_year}",
    "No embedded derivatives remain outstanding as of year-end {current_year}. The last remaining instruments were settled in {settlement_year}",
    # Balance sheet focused
    "No amounts related to embedded derivatives are recorded on the consolidated balance sheet as of {month} {end_day}, {current_year}",
    "All previously bifurcated embedded derivatives have been derecognized, and no liability remains as of {month} {end_day}, {current_year}",
    "{company} has eliminated all embedded derivative liabilities from its financial statements as of {current_year}",
    # Explicit extinguishment / derecognition
    "The final embedded derivative liability was derecognized in {settlement_year}, and no further instruments contain bifurcated features",
    "Embedded derivatives identified in earlier periods have all been extinguished, with none remaining outstanding at the end of {current_year}",
    # Catch-all confirmation
    "Management has determined that as of {month} {end_day}, {current_year}, {company} does not have any contracts requiring bifurcation of embedded derivatives",
    "No embedded derivative features exist within any outstanding financial instruments as of the reporting date",
]
