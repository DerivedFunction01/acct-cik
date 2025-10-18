import itertools
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

# Base variables
hedge_types = ["cash flow", "fair value", "net investment"]
hedge_metrics = ["changes in cash flows", "changes in fair value", "variability", "exposure"]


hedge_mitigation_verbs = ["attempt","seek","pursue","undertake"]
hedge_may_mitigation_verbs = ["may attempt","may seek","may pursue","may undertake"]

hedge_use_verbs = ["entered into", "executed", "utilized", "employed", "used", "had", "reported", "maintained", "committed", "implemented", 
                   "applied", "engaged in", "pursued", "utilizes", "employs", "uses", "maintains", "has", "have", "applies", "reports"]
hedge_may_use_verbs = [ "may engage in", "may commit in", "may implement", "may enter into", "may utilize", "may employ", "may use", "may apply", "may have", "may pursue" ]

hedge_change_verbs = ["increase", "decrease", "affect", "impact"]

hedge_methods = [
    "regression analysis and dollar-offset methods",
    "quantitative analysis",
    "statistical methods",
    "the dollar-offset method",
    "prospective and retrospective testing",
]

hedge_standards = [
    "ASC 815",
    "applicable accounting guidance",
    "U.S. GAAP",
    "accounting standards",
    "ASU 2017-12",  # Targeted Improvements to Hedge Accounting
    "ASC 815",  # Derivatives and Hedging
    "Topic 815",  # Derivatives and Hedging
]
hedge_topics = [
    "derivatives and hedging",
    "hedging activities",
    "cash flow hedges",
    "fair value hedges",
]
commodities = [
    "agricultural products", "aluminum", "asphalt", "base metals", "biodiesel", "biomass",
    "bitumen", "cement", "chemicals", "coal", "cocoa", "coffee", "commodity", "concrete", "copper", "corn",
    "cotton", "crude oil", "dairy", "diesel fuel", "electricity", "energy", "ethanol", "feedstock", "fertilizer", "fuel", "gas",
    "gasoline", "grain", "gravel", "hardwood lumber", "iron ore", "limestone", "livestock", "logs", "lumber", "metals", "minerals",
    "natural gas", "nitrogen", "paper", "petrochemicals", "petroleum", "phosphate", "plastics", "plywood", "polymers",
    "potash", "precious metals", "pulp", "raw materials", "resin", "rubber", "salt",
    "sand", "soda ash", "softwood lumber", "soybeans", "steel",
    "sugar", "sulfur", "textiles", "timber", "titanium", "uranium",
    "wood", "wood chips", "wood pellets", "wool",
]
cost_types = [
    "input costs", "energy costs", "fuel costs", "raw material costs", "manufacturing costs", "mining costs",
    "extraction costs", "transportation costs", "storage costs", "commodity costs", "production costs", "lumber costs",
]

# Base sentence structures
base_structures = [
    "{prefix}, {company} {verb} {amount_swap_order} {hedge_designation}",
    "{prefix}, {amount_swap_order} {hedge_designation}",
    "{company} {verb} {amount_swap_order} {time_phrase} {hedge_designation}",
    "{company}'s {portfolio_term} {time_phrase} {portfolio_verb} {amount_swap_order}",
]

# Time prefix variations (single year)
one_year_prefixes = [
    "As of {month} {end_day}, {year}",
    "At year-end {year}",
    "As of {month} {year}",
    "At the end of {year}",
    "At the close of {year}",
    "During {month} {year}",
    "In {month} {year}",
    "In the {quarter} quarter of {year}",
    "During the {quarter} quarter of {year}",
]

one_year_table_prefixes =[
    "{year}", # table-like format
    "{month} {year}", # table-like format
]

# Two-year time prefixes
two_year_prefixes = [
    "At {month} {end_day}, {year} and {prev_year}",
    "As of {month} {end_day}, {year} and {prev_year}",
]

two_year_table_prefixes = [
    "{year} and {prev_year}" # table-like format
    "{year} {prev_year}" # table-like format
    "{month} {year} {prev_year}" # table-like format
]

# Three-year time prefixes
three_year_prefixes = [
    "At {month} {end_day}, {year}, {prev_year}, and {prev2_year}",
    "As of {month} {end_day}, {year}, {prev_year}, and {prev2_year}",
]

three_year_table_prefixes = [
    "{year}, {prev_year}, and {prev2_year}" # table-like format
    "{year} {prev_year} {prev2_year}" # table-like format
    "{month} {year} {prev_year} {prev2_year}" # table-like format
]

# Amount connectors (words that connect amounts to swap types)
amount_connectors = [
    "with notional amounts totaling",
    "with notional amounts of",
    "with aggregate notional values of",
    "with a notional amount of",
    "totaling",
    "with notional values of",
    "with a value of",
    "with amounts totaling",
    "with a total of",
    "with fair value of",
    "with fair values totaling",
]

# Amount patterns (order of amount vs swap)
one_year_amount_patterns = [
    "{swap_type} {connector} {currency_code}{notional} {money_unit}",
    "{connector} {currency_code}{notional} {money_unit} in {swap_type}",   
]

# One-year amount patterns
one_year_table_patterns = [
    "{swap_type} {currency_code}{notional} {money_unit}",
    "{swap_type}: {currency_code}{notional}", # Table-like format
]

# Two-year amount patterns
two_year_amount_patterns = [
    "{swap_type} {connector} {currency_code}{notional} {money_unit} and {currency_code}{prev_notional} {money_unit}, respectively",
    "{connector} {currency_code}{notional} {money_unit} and {currency_code}{prev_notional} {money_unit}, respectively, in {swap_type}",
]

two_year_table_patterns = [
    "{swap_type} {currency_code}{notional} {currency_code}{prev_notional}", # Table-like format
    "{swap_type} {currency_code}{notional}, {currency_code}{prev_notional}", # Table-like format
    "{swap_type}: {currency_code}{notional} {currency_code}{prev_notional}", # Table-like format
    "{swap_type}: {currency_code}{notional}, {currency_code}{prev_notional}", # Table-like format
]

# Three-year amount patterns
three_year_amount_patterns = [
    "{swap_type} {connector} {currency_code}{notional} {money_unit}, {currency_code}{prev_notional} {money_unit}, and {currency_code}{prev2_notional} {money_unit}, respectively",
    "{connector} {currency_code}{notional} {money_unit}, {currency_code}{prev_notional} {money_unit}, and {currency_code}{prev2_notional} {money_unit}, respectively, in {swap_type}",
]

three_year_table_patterns = [
    "{swap_type} {currency_code}{notional} {currency_code}{prev_notional} {currency_code}{prev2_notional}", # Table-like format
    "{swap_type} {currency_code}{notional}, {currency_code}{prev_notional}, {currency_code}{prev2_notional}", # Table-like format
    "{swap_type}: {currency_code}{notional} {currency_code}{prev_notional} {currency_code}{prev2_notional}", # Table-like format
    "{swap_type}: {currency_code}{notional}, {currency_code}{prev_notional}, {currency_code}{prev2_notional}", # Table-like format
]

# Hedge designation phrases (optional endings)
hedge_designations = [
    "",
    "designated as hedges",
    "designated as hedging instruments",
    "designated as {hedge_type} hedges",
    "used for hedging purposes",
    "remaining designated as hedges",
    "as part of its hedging strategy",
    "as part of its risk management strategy",
    "within its hedging program",
]

# Portfolio terms
portfolio_terms = [
    "derivative portfolio",
    "derivative instruments",
    "{swap_type} portfolio",
    "portfolio",
]

# Portfolio state verbs
portfolio_verbs = [
    "consists of",
    "includes",
    "included",
]

# Outstanding/active state descriptors
state_descriptors = [
    "outstanding",
    "active",
    "remaining",
    "",
]

# Special templates for historical/maturity disclosures
historical_templates = [
    "{company}'s {swap_type} contracted in {old_year} remain {state} as of {year}, with a notional balance of {currency_code}{old_notional} {money_unit}, scheduled to mature in {future_year}",
    "{company}'s notional balance of {currency_code}{old_notional} {money_unit} in {swap_type} contracted in {old_year} remains {state} as of {year}, scheduled to mature in {future_year}",
    "To manage exposure, {company} {verb} {swap_type} in {old_year}, with an inception notional of {currency_code}{old_notional} {money_unit} and a stated maturity in {future_year}",
    "To manage exposure, {company} {verb} notional amounts of {currency_code}{old_notional} {money_unit} in {swap_type} during {old_year}, with a stated maturity in {future_year}",
    "In {month} {old_year}, {company} {verb} {swap_type} with fair values of {currency_code}{old_notional} {money_unit}, which are set to expire in {month} {future_year}",
    "In {month} {old_year}, {company} {verb} notional amounts of {currency_code}{old_notional} {money_unit} in {swap_type}, which are set to expire in {month} {future_year}",
    "As of {month} {year}, {company} {verb} {swap_type} {verb} in {old_year}, with total notional of {currency_code}{old_notional} {money_unit}, expiring in {future_year}",
    "As of {month} {year}, {company} {verb} fair values of {currency_code}{old_notional} {money_unit} in {swap_type} initiated in {old_year}, expiring in {future_year}",
    "{company} {verb} {swap_type} which expires in {month} {future_year}",
    "{company} {verb} {swap_type} which matures in {month} {future_year}",
    "{company} {verb} {swap_type} which expires in {future_year}",
    "{company} {verb} {swap_type} which matures in {future_year}",
    "{company}'s {swap_type} terminates in {month} {future_year}",
    "{company}'s {swap_type} terminates in {future_year}",
    "{company}'s {swap_type} matures in {month} {future_year}",
    "{company}'s {swap_type} matures in {future_year}",
    "{company} {verb} {swap_type} with a value of {currency_code}{notional} {money_unit} that expires in {future_year}",
    "{company} {verb} {swap_type} with a fair value of {currency_code}{notional} {money_unit} that matures in {future_year}",
    "{company} {verb} {swap_type} with a value of {currency_code}{notional} {money_unit} that expires in {month} {future_year}",
    "{company} {verb} {swap_type} with a fair value of {currency_code}{notional} {money_unit} that matures in {month} {future_year}",
    "{company} {verb} {swap_type} with a value of {currency_code}{notional} {money_unit} which expires in {future_year}",
    "{company} {verb} {swap_type} with a value of {currency_code}{notional} {money_unit} which matures in {future_year}",
    "{company} {verb} {swap_type} with a notional value of {currency_code}{notional} {money_unit} which expires in {month} {future_year}",
    "{company} {verb} {swap_type} with a value of {currency_code}{notional} {money_unit} which matures in {month} {future_year}",
]

gen_specific_mitigation = [
    "to protect against unfavorable changes in market conditions",
    "to offset risks associated with forecasted transactions",
    "to reduce overall earnings volatility",
    "to enhance stability of financial performance",
    "to manage risk exposure across multiple markets",
    "to manage overall exposure to changes in market variables",
    "to manage the company's aggregate risk profile",
    "to align with the company's overall risk management objectives",
    "to reduce variability in cash flows and earnings",
    "to hedge exposures arising from normal business operations",
    "to manage exposure to price, rate, or market changes",
    "to provide more predictable financial outcomes",
    "to stabilize cash flows from core operations",
    "to limit adverse effects of market volatility",
    "to hedge forecasted or anticipated transactions",
    "to support financial risk management strategies",
    "to manage exposures in accordance with the company's hedging policy",
    "to mitigate exposure to broad market risks",
    "to minimize the impact of market fluctuations on reported results",
    "to reduce the impact of changing economic conditions",
    "to maintain a balanced risk position",
    "to manage enterprise-wide risk exposures",
    "to reduce volatility in consolidated financial results",
]

# Generic accounting reasons (shared across all hedge types)
gen_specific_results = [
    "resulting in {currency_code}{notional} {money_unit} of unrealized losses recorded in accumulated OCI",
    "resulting in fair value losses recorded in equity",
    "resulting in {currency_code}{notional} {money_unit} of unrealized gains recorded in accumulated OCI",
    "resulting in fair value gains recorded in equity",
    "with net unrealized losses of {currency_code}{notional} {money_unit} reflected in accumulated other comprehensive income",
    "with net unrealized gains of {currency_code}{notional} {money_unit} reflected in accumulated other comprehensive income",
    "leading to mark-to-market adjustments recorded in other comprehensive income",
    "with changes in fair value recognized in equity",
    "with changes in fair value recognized in earnings",
]

# Interest Rate (IR) — general/policy intent phrases ("to ...")
ir_specific_mitigation = [
    "to modify the interest rate characteristics of outstanding senior notes",
    "to hedge interest rate exposure on a portion of its debt portfolio",
    "to convert fixed-rate senior notes to variable rates",
    "to manage interest rate risk on long-term debt",
    "to adjust the interest rate profile of its debt",
    "to hedge changes in the fair value of fixed-rate liabilities",
    "to manage exposure to interest rate fluctuations",
    "to modify the interest rate structure of its senior notes",
    "to hedge the fair value of outstanding debt",
    "to manage interest rate exposure on bonds",
    "to adjust the interest rate characteristics of long-term liabilities",
    "to mitigate interest rate risk on debt issuances",
    "to manage debt-related interest rate risk",
    "to hedge fixed-rate debt obligations",
    "to optimize the interest rate profile of its debt portfolio, converting portions of fixed-rate debt to floating-rate instruments",
    "to adjust the effective interest rate composition of outstanding debt",
    "to reduce interest rate volatility on its debt obligations",
    "to transform fixed-rate debt into variable-rate debt where appropriate",
    "to hedge against rising interest rates, modifying the interest rate characteristics of its borrowings",
    "to manage the interest rate exposure of its long-term debt portfolio",
    "to convert portions of debt into instruments with more favorable interest rate terms",
    "to balance fixed and floating rate obligations",
    "to adjust the effective interest profile",
    "to limit the negative impact of interest rates",
    "to hedge against fluctuations in interest rates",
    "to manage exposure to changes in benchmark interest rates",
    "to stabilize the cost of borrowing",
    "to protect against unfavorable changes in long-term debt obligations",
    "to hedge interest rate risk on forecasted debt issuances",
    "to hedge against changes in interest rates that could impact expected future issuances of debt",
    "to lock in favorable interest rates prior to anticipated debt issuances",
    "to hedge interest rate exposure on forecasted debt offerings",
    "to mitigate the risk of rising interest rates on planned fixed-rate debt issuances",
    "to secure interest rates for future debt issuances",
    "to manage interest rate risk",
    "to protect against interest rate volatility for planned fixed-rate debt issuances",
    "to lock in rates for anticipated debt financings",
    "to stabilize future interest costs",
    "to mitigate interest rate fluctuations on planned debt offerings",
    "to secure rates for future fixed-rate debt",
    "to manage interest rate exposure for anticipated debt issuances",
    "to lock in rates prior to debt financings",
    "to hedge against rising interest rates for planned debt issuances",
    "to stabilize interest rates for forecasted bond issuances",
    "to manage risk on future debt offerings",
    "to secure favorable rates for anticipated fixed-rate debt",
    "to mitigate interest rate risk on planned financings",
    "to limit the impact of interest rate changes on earnings and cash flows, and to lower overall borrowing costs",
    "to limit its exposure to interest rate fluctuations",
    "to manage variable interest rate exposure over a medium- to long-term period",
    "to manage variable interest rate exposure",
    "to manage interest costs by using a mix of fixed- and floating-rate debt",
]

# Interest Rate (IR) — factual/realized results ("effectively...", "converting...", "hedging...")
ir_specific_results = [
    "effectively converting fixed-rate debt to floating-rate debt",
    "effectively converting floating-rate debt to fixed-rate debt",
    "effectively converting portions of fixed-rate debt to floating rates",
    "effectively convert the hedged portion of debt to floating rates",
    "converting floating rate exposure to fixed rates, with quarterly exchange of payment differentials based on notional values",
    "with quarterly settlements based on the differential between fixed and floating rates on notional amounts",
    "with quarterly net settlements calculated on agreed notional principal amounts",
    "scheduled to expire in {month} {future_year}",
    "to hedge debt obligations, with an initial notional of {currency_code}{old_notional} {money_unit}, maturing in {future_year}",
    "which carry notional amounts of {currency_code}{old_notional} {money_unit} and terminate in {future_year}",
    "with a starting notional value of {currency_code}{old_notional} {money_unit}, declining annually until expiration in {month} {future_year}",    
    "with a starting notional value of {currency_code}{old_notional} {money_unit}, declining annually until expiration in {future_year}",
    "resulting in a decrease in interest expense of {currency_code}{notional} {money_unit}",
    "resulting in an increase in interest expense of {currency_code}{notional} {money_unit}",
    "recognizing the gains and losses on derivative instruments as an adjustment to interest expense in the period the hedged interest payment affects earnings",
]

# Foreign Exchange (FX) specific accounting reasons
# FX — general or policy intent ("to ...")
fx_specific_mitigation = [
    "to manage translation exposure",
    "to hedge foreign borrowings",
    "to hedge exposure to foreign currency fluctuations on cross-border transactions",
    "to hedge forecasted foreign currency revenues",
    "to manage translation risk of foreign subsidiaries",
    "to hedge anticipated foreign currency purchases",
    "to protect against volatility in foreign currency receivables",
    "to hedge forecasted foreign currency cash flows",
    "to manage currency risk",
    "to hedge forecasted foreign currency expenditures",
    "to hedge currency-denominated obligations",
    "to hedge foreign currency exposures",
    "to hedge forecasted foreign currency transactions",
    "to hedge foreign exchange exposures",
    "to hedge intercompany transactions",
    "to hedge intercompany exposures",
    "to manage currency-denominated cash flows",
]

# FX — realized / factual results ("hedging ...", "mitigating ...", "offsetting ...", "protecting ...", etc.)
fx_specific_results = [
    "offsetting foreign currency translation adjustments",
    "mitigating exchange rate fluctuations on foreign currency denominated transactions",
    "with translation gains of {currency_code}{notional} {money_unit} recognized in other comprehensive income",
    "with translation losses of {currency_code}{notional} {money_unit} recognized in other comprehensive income",
    "hedging net investment in foreign operations",
    "due to changes in foreign exchange rates and are recorded at fair value",
    "mitigating exposure to foreign currency fluctuations",
    "hedging foreign-denominated cash flows",
    "mitigating foreign exchange risk",
    "protecting against currency fluctuations",
    "protecting against exchange rate movements",
]

# Equity — general or policy intent ("to ...", "for ...", "intended ...", "as ...")
eq_specific_mitigation = [
    "to manage exposure to changes in the market price of its common stock and related equity-based compensation costs",
    "to hedge variability in compensation expense associated with changes in share price",
    "to mitigate exposure to equity price movements",
    "to manage market risks associated with fluctuations in stock price",
    "to offset potential volatility from changes in share price",
    "to reduce variability in reported expenses arising from equity-linked compensation",
    "as economic hedges of share price exposure",
    "to hedge the market price risk associated with stock-based compensation plans",
    "to mitigate equity-related market risk",
    "to manage risks related to equity-linked compensation obligations",
    "to manage share price exposure",
    "to offset volatility in stock-based compensation expense",
    "to hedge changes in equity valuation",
    "to hedge exposure to its common stock value",
    "to manage equity-linked exposures",
    "to mitigate volatility in stock-based compensation costs",
    "to manage changes in the value of its shares",
    "as part of its equity risk management strategy",
    "to hedge share price fluctuations",
    "to manage exposure to its common stock price volatility",
    "to hedge variability in equity-based compensation expenses",
    "to mitigate equity price risk",
    "to manage stock price fluctuations",
    "to hedge equity-related exposures",
    "to offset share price volatility",
    "to reduce variability in equity-linked compensation costs",
    "to manage market risks tied to stock-based compensation",
    "to hedge equity market risk",
    "to manage equity price movements",
    "to hedge equity-based compensation obligations",
    "to hedge equity price changes",
    "to mitigate volatility in equity-based compensation",
    "to manage equity valuation risks",
    "to manage equity price volatility",
    "to hedge stock-based compensation costs",
    "to mitigate volatility in equity compensation expenses",
    "to manage share price fluctuations",
    "to hedge equity market risks",
    "to hedge equity price exposure",
    "to manage stock price volatility",
    "to hedge equity-based compensation costs",
    "to manage share price risk",
    "to mitigate equity price volatility",
    "to hedge stock-based compensation risks",
    "to manage equity market risk",
    "to manage stock-based compensation costs",
    "to hedge equity-linked risks",
]

# Equity — realized/factual results ("hedging ...", "offsetting ...", "mitigating ...", etc.)
eq_specific_results = [
    "offsetting market value changes in the underlying equity positions",
    "mitigating exposure to equity market volatility",
    "offsetting losses on equity investments",
    "offsetting gains on equity investments",
    "hedging exposures tied to equity-based programs",
    "linked to the value of its common stock or market indices",
]
# Commodity — general or policy intent ("to ...", "for ...", "intended ...")
cp_specific_mitigation = [
    "to hedge {commodity} price risk",
    "to manage {commodity} exposures",
    "to hedge forecasted {commodity} purchases or sales",
    "to manage fluctuations in {commodity} prices",
    "for {commodity} risk management",
    "to hedge volatility in {commodity} costs",
    "to mitigate {commodity} price exposure",
    "to hedge {commodity} procurement",
    "to stabilize {commodity} costs",
    "to manage {commodity} price volatility",
    "to hedge {commodity} exposures",
    "to mitigate risks from {commodity} price swings",
    "to protect against {commodity} market fluctuations",
    "to manage {commodity} exposure",
    "to lock in pricing",
    "to manage {commodity} cost volatility",
    "to hedge forecasted {commodity} purchases",
    "to stabilize input costs",
    "to hedge {commodity} procurement risks",
    "to hedge {commodity} procurement risk",
    "to limit its exposure to {commodity} price increases",
]

# Commodity — realized/factual results ("hedging ...", "mitigating ...", "offsetting ...", "protecting ...", etc.)
cp_specific_results = [
    "offsetting {commodity} price fluctuations",
    "mitigating exposure to volatile {commodity} prices",
    "stabilizing cost of goods sold despite {commodity} price movements",
    "hedging against increases in {commodity} costs",
    "hedging against decreases in {commodity} sale prices",
    "effectively hedged volatility in {commodity} costs",
    "mitigating exposure to {commodity} price fluctuations",
    "protecting against changes in {commodity} prices",
    "protecting against {commodity} market volatility",    
    "protecting against {commodity} price volatility",
    "hedging against {commodity} price increases",
    "hedging against {commodity} price decreases",
    "mitigating {commodity} price risk",
    "stabilizing {commodity} costs",
    "offsetting {commodity} cost fluctuations",
    "protecting against {commodity} price changes",
    "hedging against {commodity} market volatility",
    "mitigating exposure to {commodity} market fluctuations",
    "stabilizing input costs despite {commodity} price movements",
]

# Special templates for accounting impact
hedge_impact_templates = [
    "As of {month} {end_day}, {year}, {swap_type} were designated as {hedge_type} hedges, {impact_result}",
    "At {end_day} {month}, {year}, {company} {verb} {swap_type} with a total notional amount of {currency_code}{notional} {money_unit}, {impact_result}",
    "The net unrealized loss on the {swap_type} was {currency_code}{notional} {money_unit} at {month} {end_day}, {year} and is reflected in accumulated other comprehensive income",
    "The net unrealized gain on the {swap_type} was {currency_code}{notional} {money_unit} at {month} {end_day}, {year} and is reflected in accumulated other comprehensive income",
    "The gains and losses on derivative instruments such as {swap_type} for the years ended {month} {end_day} were as follows: {year}, {prev_year}, and {prev2_year} (In {money_unit}), {notional}, {prev_notional} and {prev2_notional}, respectively",
    "At {month} {year}, {company} {verb} {swap_type}, {swap_type} designated as {hedge_type} hedges: Amount of {gain_loss} recognized in accumulated other comprehensive loss (effective portion), net of tax {currency_code}{notional}, {impact_result}",
    "At {month} {end_day}, {year}, {company} {verb} {swap_type}, {swap_type} designated as {hedge_type} hedges: Amount of {gain_loss} reclassified from accumulated other comprehensive loss into {location} (effective portion), net of tax {currency_code}{notional}",
    "At {month} {year}, {company} {verb} {swap_type} designated as {hedge_type} hedges: Amount of {gain_loss} recognized in {location} (ineffective portion), before tax {currency_code}{notional}",
    "{swap_type} not designated as hedging instruments at {year}: Amount of {gain_loss} recognized in {location}, before tax {currency_code}{notional}, {impact_result}",
    "As of {month} {end_day}, {year}, {company} {verb} {swap_type}: Net {gain_loss}s of approximately {currency_code}{notional} ({money_unit}) (after tax)",
]

hedge_context_template = [
    "{context}, {company} {verb} {swap_type}",
    "{company} {verb} {swap_type}, {context}"
]

# No-prior-year patterns (two-year)
two_year_no_prior_patterns = [
    "no such instruments were outstanding at {prev_year}",
    "while no comparable {swap_type} existed during {prev_year}",
    "There were no {swap_type} outstanding at the close of {prev_year}",
    "there were no such {swap_type} reported in {prev_year}",
    "with no comparable {swap_type} outstanding in {prev_year}",
    "with no {swap_type} outstanding during {prev_year}",
    "no {swap_type} remained outstanding at the end of {prev_year}",
    "There were no outstanding {swap_type} balances at {prev_year}",
]

# No-prior-year patterns (three-year)
three_year_no_prior_patterns = [
    "no such instruments were outstanding at {prev_year} or {prev2_year}",
    "while no comparable {swap_type} existed during {prev_year} or {prev2_year}",
    "There were no {swap_type} outstanding at the close of {prev_year} or {prev2_year}",
    "there were no such {swap_type} reported in {prev_year} or {prev2_year}",
    "with no comparable {swap_type} outstanding in {prev_year} or {prev2_year}",
    "with no {swap_type} outstanding during {prev_year} or {prev2_year}",
    "no {swap_type} remained outstanding at the end of {prev_year} or {prev2_year}",
    "There were no outstanding {swap_type} balances at {prev_year} or {prev2_year}",
]

# Special templates for no-prior-year disclosures (two-year)
two_year_no_prior_templates = [
    "At {month} {end_day}, {year}, {company} {verb} {swap_type} totaling {currency_code}{notional} {money_unit}; {no_prior_pattern}",
    "As of {month} {end_day}, {year}, {company} {verb} active {swap_type} with a notional value of {currency_code}{notional} {money_unit}, {no_prior_pattern}",
    "At year-end {year}, {company}'s {swap_type} totaled {currency_code}{notional} {money_unit}. {no_prior_pattern}",
    "As of {month} {year}, {company} {verb} {swap_type} with notional amounts of {currency_code}{notional} {money_unit}; {no_prior_pattern}",
    "During {year}, {company} {verb} {swap_type} positions totaling {currency_code}{notional} {money_unit}, {no_prior_pattern}",
    "During {year}, {company} initiated {swap_type} positions totaling {currency_code}{notional} {money_unit}, {no_prior_pattern}",
    "At {month} {end_day}, {year}, {company} {verb} {swap_type} serving as fair value hedges, {no_prior_pattern}",
    "As of {month} {end_day}, {year}, {company} {verb} {swap_type} notional of {currency_code}{notional} {money_unit}; {no_prior_pattern}",
]

# Special templates for no-prior-year disclosures (three-year)
three_year_no_prior_templates = [
    "At {month} {end_day}, {year}, {company} {verb} {swap_type} totaling {currency_code}{notional} {money_unit}; {no_prior_pattern}",
    "As of {month} {end_day}, {year}, {company} had active {swap_type} with a notional value of {currency_code}{notional} {money_unit}, {no_prior_pattern}",
    "At year-end {year}, {company}'s {swap_type} totaled {currency_code}{notional} {money_unit}. {no_prior_pattern}",
    "As of {month} {year}, {company} {verb} {swap_type} with notional amounts of {currency_code}{notional} {money_unit}; {no_prior_pattern}",
    "During {year}, {company} initiated {swap_type} positions totaling {currency_code}{notional} {money_unit}, {no_prior_pattern}",
    "At {month} {end_day}, {year}, {company} {verb} {swap_type} serving as fair value hedges, {no_prior_pattern}",
    "As of {month} {end_day}, {year}, {company} {verb} {swap_type} notional of {currency_code}{notional} {money_unit}; {no_prior_pattern}",
    "At {month} {end_day}, {year}, {company} {verb} {swap_type} totaling {currency_code}{notional} {money_unit}. {no_prior_pattern}",
]

# ==============================================================================
# HEDGE TRANSACTION TEMPLATE SYSTEM
# ==============================================================================

# ------------------------------------------------------------------------------
# OPTIONAL/COMPARATIVE TEMPLATES (Two-Year Comparisons)
# ------------------------------------------------------------------------------

# Comparison verbs/phrases
comparison_phrases = [
    "compared to",
    "versus",
    "down from",
    "reduced from",
]

# Trend descriptors
trend_descriptors = [
    "with notional amounts decreasing from",
    "with notional amounts increasing from",
    "with notional values of",
    "had a notional value of",
    "with fair value decreasing from",
    "with fair value increasing from",
    "with fair values of",
    "had a fair value of",
    "with amounts decreasing from",
    "with amounts increasing from",
    "with values of",
    "had a value of",
]

# Optional hedge purposes
optional_purposes = [
    "to hedge forecasted revenue which were not part of a collar strategy",
    "to hedge forecasted transactions",
    "to hedge revenue streams",
    "for hedging forecasted revenue",
    "for transaction hedging",
    "for revenue hedging",
    "for hedging",
]

# Base optional template patterns
optional_template_patterns = [
    "{company} also have {verb} {swap_type} {purpose}. Such {swap_type} had a fair value of {currency_code}{notional1} {money_unit} and {currency_code}{notional2} {money_unit} as of {month} {end_day}, {year} and {month} {end_day}, {prev_year}, respectively",
    "{company} {verb} {swap_type} with notional values of {currency_code}{notional1} {money_unit} as of {month} {end_day}, {year} {comparison} {currency_code}{notional2} {money_unit} as of {month} {end_day}, {prev_year}",
    "As of {month} {end_day}, {year}, {company} {verb} {swap_type} with a fair value of {currency_code}{notional1} {money_unit}, {comparison} {currency_code}{notional2} {money_unit} in the prior year",
    "{company} {verb} {swap_type} {purpose}, {trend} {currency_code}{notional2} {money_unit} as of {month} {end_day}, {prev_year} to {currency_code}{notional1} {money_unit} as of {month} {end_day}, {year}",
    "As of {month} {end_day}, {year}, {swap_type} with a fair value of {currency_code}{notional1} {money_unit} were in place, {comparison} {currency_code}{notional2} {money_unit} as of {month} {end_day}, {prev_year}",
    "In {year}, {swap_type} with a notional value of {currency_code}{notional1} {money_unit} were active, {comparison} {currency_code}{notional2} {money_unit} in {prev_year}",
    "As of {month} {end_day}, {year}, {company}'s {swap_type} portfolio had a fair value of {currency_code}{notional1} {money_unit}, {comparison} {currency_code}{notional2} {money_unit} in {prev_year}",
    "At year-end {year}, {swap_type} with a fair value of {currency_code}{notional1} {money_unit} were {verb} {purpose}, {comparison} {currency_code}{notional2} {money_unit} in {prev_year}",
]

# ------------------------------------------------------------------------------
# SHARED TIMING COMPONENTS (Used across all events: termination, expiration, dedesignation, settlement)
# ------------------------------------------------------------------------------

# Time periods
time_periods = [
    "In the {quarter} quarter of {year}",
    "During the {quarter} quarter of {year}",
    "In {month} {year}",
    "During {month} {year}",
    "In {year}",
    "During {year}",
    "prior to {month} {end_day}, {year}",
    "prior to year-end {year}",
    "As of {month} {end_day}, {year}",
]

# Action verbs (shared across all events)
termination_verbs = [
    "terminated",
    "settled",
    "closed out",
    "ended",
    "unwound",
    "expired",
    "matured",
    "reached maturity",
    "reached their expiration date",
    "liquidated",
]

# Settlement frequencies
settlement_frequencies = [
    "quarterly",
    "annually",
    "monthly",
    "semi-annually",
]
# Payment phrases
payment_phrases = [
    # Settlement patterns (merged)
    "Under each {swap_type}, settlements occur {frequency} for {currency_code}{notional} {money_unit}, {pay_result}",
    "Each {swap_type} settles {frequency} for {currency_code}{notional} {money_unit}, {pay_result}",
    "{frequency} payments of {currency_code}{notional} {money_unit} are required under each {swap_type}, {pay_result}",
    "For every {swap_type}, {frequency} payments of {currency_code}{notional} {money_unit} are made, {pay_result}",
    "Each {swap_type} involves {frequency} settlements of {currency_code}{notional} {money_unit}, {pay_result}",
    "{frequency} settlements under each {swap_type} for {currency_code}{notional} {money_unit} {pay_result}",
    "Each {swap_type} calls for {frequency} payments of {currency_code}{notional} {money_unit}, {pay_result}",
    "Each {swap_type} entails {frequency} settlement of {currency_code}{notional} {money_unit}, {pay_result}",
]
# Settlement result phrases
payment_results = [
    "with all gains and losses recognized upon payment",
    "with the resulting gains and losses fully recorded",
    "and all gains and losses are realized as they occur",
    "with all resulting gains and losses reflected in earnings",
    "ensuring that all gains and losses are recognized at the time of settlement",
    "result in full recognition of realized gains and losses",
    "and all associated gains and losses are recorded when realized",
    "with realized gains and losses recorded accordingly",
]

# Result phrases - no outstanding positions (shared)
no_position_results = [
    "{company} {verb} no outstanding derivative positions as of year-end {year}",
    "resulting in no outstanding hedge positions as of {month} {end_day}, {year}",
    "with no derivative instruments remaining at period end",
    "leaving no active derivative positions at year-end",
    "resulting in no active hedges as of {month} {end_day}, {year}",
    "leaving no derivative instruments outstanding",
    "with no remaining hedge positions at year-end {year}",
    "resulting in no active derivative contracts at period end",
    "leaving no outstanding hedges as of {month} {end_day}, {year}",
    "with no derivative positions remaining at year-end",
    "resulting in no active hedges at period end",
    "with no hedges remaining at year-end",
    "resulting in no outstanding derivative instruments",
    "leaving no active derivative positions",
    "with no hedges in place at {month} {end_day}, {year}",
    "with no derivatives outstanding at year-end",
    "resulting in no active hedge positions",
    "leaving no derivative contracts at period end",
    "with no outstanding hedges as of {month} {end_day}, {year}",
    "there were no such {swap_type} outstanding",
]

# No-replacement phrases (for expirations specifically)
no_replacement_phrases = [
    "with no new positions {verb} during the year",
    "with no replacement hedges executed during the remainder of the fiscal year",
    "and {company} elected not to enter into new derivative contracts during the period",
    "and no new hedging instruments were established for the fiscal year",
    "with no new derivative positions initiated",
    "with no new hedges entered during the year",
    "and {company} did not execute new derivative contracts",
    "with no replacement hedges established",
    "and no new derivative instruments were {verb} during the fiscal year",
    "with no new positions taken",
    "and {company} chose not to initiate new hedges",
    "with no new derivative contracts executed",
    "leaving no active hedges for the remainder of the year",
    "with no new hedges established",
    "with no new positions entered",
    "and {company} did not replace them with new hedges",
    "with no new derivative contracts initiated",
    "and no further hedging instruments were established",
    "with no new hedges entered into",
    "with no new contracts {verb}",
]

# De-designation specific actions
dedesignation_actions = [
    "de-designated",
    "discontinued hedge accounting for",
    "removed hedge designation from",
    "ceased hedge accounting for",
    "ended hedge accounting for",
    "removed hedge accounting from",
    "ceased applying hedge accounting to",
]

# De-designation results (in addition to shared no_position_results)
dedesignation_specific_results = [
    "removing hedge accounting treatment for these instruments",
    "discontinuing hedge accounting",
    "with no hedge accounting applied at year-end",
    "removing their hedge accounting status",
    "ending their hedge accounting status",
]

# All event results (combined settlement_results, no_position_results, dedesignation_specific_results)
termination_event_results =  no_position_results + dedesignation_specific_results

# Templates for zero notional in current year vs. non-zero in prior years
zero_current_vs_prior_notional_templates = [
    "As of {end_of_year}, {company} had no outstanding {swap_type}, compared to notional amounts of {currency_code}{prev_notional} {money_unit} in {prev_year}",
    "At {end_of_year}, there were no such {swap_type} outstanding, whereas in {prev_year} and {prev2_year}, notional amounts were {currency_code}{prev_notional} {money_unit} and {currency_code}{prev2_notional} {money_unit}, respectively",
    "{company} held no {swap_type} at the end of {year}, in contrast to {currency_code}{prev_notional} {money_unit} at the end of {prev_year}",
    "The notional amount of {swap_type} was zero as of {end_of_year}; however, the company {verb} {currency_code}{prev_notional} {money_unit} of such instruments in {prev_year}",
    "While {company} {verb} {swap_type} with notional amounts of {currency_code}{prev_notional} {money_unit} in {prev_year}, there were no such derivatives outstanding as of {end_of_year}",    
    "As of {end_of_year}, {company} had no outstanding {swap_type}, compared to notional amounts of {currency_code}{prev_notional} {money_unit} in {prev_year} and {currency_code}{prev2_notional} {money_unit} in {prev2_year}",
    "At {end_of_year}, there were no {swap_type} outstanding, whereas in {prev_year} and {prev2_year}, notional amounts were {currency_code}{prev_notional} {money_unit} and {currency_code}{prev2_notional} {money_unit}, respectively",
    "{company} held no {swap_type} at the end of {year}, in contrast to {currency_code}{prev_notional} {money_unit} at the end of {prev_year} and {currency_code}{prev2_notional} {money_unit} at the end of {prev2_year}",
    "The notional amount of {swap_type} was zero as of {end_of_year}; however, {company} {verb} {currency_code}{prev_notional} {money_unit} of such instruments in {prev_year} and {currency_code}{prev2_notional} {money_unit} in {prev2_year}",
    "While {company} {verb} {swap_type} with notional amounts of {currency_code}{prev_notional} {money_unit} in {prev_year} and {currency_code}{prev2_notional} {money_unit} in {prev2_year}, there were no such derivatives outstanding as of {end_of_year}",
    
]

# Merged event template patterns (termination, expiration, dedesignation, settlement)
merged_event_patterns = [
    # Termination patterns
    "{time_period}, {company} {termination_verb} all remaining {swap_type} agreements. {term_result}",
    "{time_period}, all previously designated {swap_type} were {termination_verb}, {term_result}",
    "{company} {termination_verb} all {swap_type} positions {time_period}, {term_result}",
    "All outstanding {swap_type} matured or were {termination_verb} {time_period}, {term_result}",
    "{time_period}, {company} {termination_verb} all {swap_type} agreements, {term_result}",
    "{time_period}, {company} {termination_verb} {swap_type} positions, {term_result}",
    "{time_period}, all {swap_type} were {termination_verb}, {term_result}",
    "{company} {termination_verb} all outstanding {swap_type} {time_period}, {term_result}",
    "{time_period}, {company} {termination_verb} its {swap_type} portfolio, {term_result}",
    "{time_period}, all {swap_type} agreements were {termination_verb}, {term_result}",
    "As of {month} {end_day}, {year}, there were no such {swap_type} outstanding",
    # Expiration patterns
    "All previously outstanding derivatives {termination_verb} {time_period}, {no_replacement}",
    "{company}'s derivative portfolio was fully {termination_verb} {time_period} {no_replacement}",
    "Outstanding hedge positions {termination_verb} throughout {year}, {no_replacement}",
    "{time_period}, all existing {swap_type} {termination_verb}, {no_replacement}",
    "{time_period}, all {swap_type} contracts {termination_verb}, {no_replacement}",
    "{company}'s {swap_type} portfolio fully {termination_verb} {time_period}, {no_replacement}",
    "{time_period}, all outstanding {swap_type} {termination_verb}, {no_replacement}",
    "{time_period}, {company}'s {swap_type} positions {termination_verb}, {no_replacement}",
    "All {swap_type} {termination_verb} {time_period}, {no_replacement}",
    "{time_period}, {company}'s derivative portfolio of {swap_type} was fully settled, {no_replacement}",
    # De-designation patterns
    "{company} {dedesignation_action} all of our {swap_type} {time_period}",
    "{company} {dedesignation_action} {swap_type} {time_period}, {term_result}",
    "All {swap_type} were {dedesignation_action} as hedging instruments {time_period}",
    "{time_period}, {company} {dedesignation_action} all outstanding {swap_type}",
    "{time_period}, all {swap_type} were {dedesignation_action}, {term_result}",
    "All {swap_type} were {dedesignation_action} {time_period}, {term_result}",
    "{time_period}, all {swap_type} lost their hedge designation status",
    # Quarterly termination with settlement patterns
    "{time_period}, {company} {termination_verb} {swap_type} with {frequency} settlements, {term_result}",
    "{time_period}, all {swap_type} were {termination_verb} {frequency}, {term_result}",
    "{company} conducted {frequency} {termination_verb} of {swap_type} {time_period}, {term_result}",
]


# Other templates
fx_currency_templates = [
    "The currency hedged items are usually denominated in the following main currencies: {currencies}",
    "{company}'s primary currency exposures include {currencies}",
    "Foreign currency risk primarily relates to exposures in {currencies}",
    "Our most significant currency exposures are to {currencies}",
    "{company} faces foreign exchange risk primarily from {currencies}",
    "In order to reduce foreign currency translation exposure from {currencies}, {company} seeks to denominate borrowings in the currencies of our principal assets and cash flows. These are primarily denominated in {currencies}",
    "To minimize translation exposure, {company} aligns the currency composition of its debt with the currencies of its operating assets, primarily {currencies}",
    "{company} reduces foreign currency translation risk by borrowing in the same currencies as its principal assets and cash flows, which are mainly {currencies}",
    "{company} matches debt currency denomination to the currencies of its key operating assets to mitigate translation exposure, focusing on {currencies}",
]

# ==============================================================================
# HEDGE POLICY
# ==============================================================================
hedge_policy_templates = [
    "Changes in the fair value of {swap_type} are recorded each period in current earnings or other comprehensive income (loss), depending on whether a derivative instrument is designated as part of a hedging transaction and, if it is, the type of hedging transaction",
    "{swap_type} are measured at fair value with gains and losses recorded in earnings or accumulated other comprehensive income based on hedge designation",
    "{company} accounts for {swap_type} at fair value, with changes in fair value recognized in either net income or other comprehensive income depending on the nature of the hedging relationship",
    "Fair value changes in {swap_type} are reflected in the financial statements through either the income statement or other comprehensive income, based on whether hedge accounting is applied",
    "{company} records {swap_type} at fair value, with changes recognized in earnings or OCI depending on hedge designation",
    "Changes in derivative fair values are recorded in net income or accumulated OCI, based on the type of hedge and its designation",
    "{swap_type} are accounted for at fair value, with gains or losses recorded in earnings or other comprehensive income per hedge accounting rules",
    "{company} recognizes fair value changes of {swap_type} in either current earnings or OCI, depending on the hedging relationship",
    "{swap_type} are measured at fair value, with changes reflected in net income or accumulated OCI based on hedge designation",
    "Fair value adjustments for derivatives are recorded in earnings or OCI, depending on whether the instrument qualifies for hedge accounting",
    "{company} accounts for {swap_type} at fair value, recognizing changes in either the income statement or other comprehensive income",
    "Changes in the fair value of {swap_type} are recorded in earnings or OCI, based on the nature of the hedging relationship",
    "{swap_type} are valued at fair value, with gains and losses recognized in net income or OCI depending on hedge accounting treatment",
    "{company} records fair value changes in {swap_type} in either earnings or accumulated OCI, based on hedge designation",
    "Derivative fair value changes are recognized in the income statement or OCI, depending on the type of hedging relationship",
    "{company} accounts for {swap_type} at fair value, with changes recorded in earnings or OCI per applicable accounting standards",
    "Fair value changes in {swap_type} are reflected in net income or OCI, based on their hedge designation",
    "{swap_type} are measured at fair value, with changes recorded in earnings or other comprehensive income depending on hedge accounting",
    "{company} recognizes derivative fair value changes in either net income or OCI, based on the hedging relationship",
    "Changes in derivative fair values are recorded in current earnings or OCI, depending on the hedge type and accounting treatment",
    "All {swap_type}, other than those that satisfy specific exceptions, are recorded at fair value. {company} record changes in the fair value of our derivative positions based on the value for which the derivative instrument could be exchanged between willing parties",
    "If market quotes are not available to estimate fair value, management’s best estimate of fair value is based on the quoted market price of {swap_type} with similar characteristics or determined through industry-standard valuation techniques",
    "{company} value our {swap_type} using observable inputs including interest rate curves, risk adjusted discount rates, credit spreads and other relevant data",
    "Gains and losses on {swap_type} are recognized currently in earnings",
    "The ultimate fair value of our {swap_type} is uncertain, and {company} believe that it is reasonably possible that a change in the estimated fair value could occur in the near future",
    "The accounting for the changes in the fair value of the {swap_type} depends on the intended use of the {swap_type} and the resulting designation",
    "For a {swap_type} that does not qualify as a {hedge_type} hedge, the change in {hedge_type} is recognized currently in net income",
    "The derivatives that {company} uses to hedge these risks are governed by our risk management policies include {swap_type}",
    "The goal of the hedging program such as using {swap_type} is to mitigate financial risks",
    "If the derivative such as {swap_type} is a hedge, changes in the fair value of derivatives may be recognized in other comprehensive income until the hedged item is recognized in earnings",
]

hedge_documentation_templates = [
    "For a {swap_type} to qualify as a hedge at inception and throughout the hedged period, {company} formally document the nature and relationships between the hedging instruments and hedged item",
    "For a {swap_type} designated as a {hedge_type} hedge, the gain or loss is recognized in earnings in the period of change together with the offsetting loss or gain on the risk being hedged",
    "{company} maintains formal documentation of all hedging relationships, including the risk management objective and strategy for undertaking the hedge",
    "Hedge accounting requires formal documentation at inception describing the hedging relationship and {company}'s risk management objectives",
    "{company} document our hedging relationships and risk management strategies at inception in accordance with applicable accounting standards",
    "{company} prepares formal documentation for all hedges, detailing the hedging {swap_type}, hedged item, and risk management strategy",
    "At hedge inception, {company} document the relationship between the {swap_type} and the hedged item, including the risk management objective",
    "{company} maintains detailed documentation of hedging relationships to comply with hedge accounting requirements",
    "{company} formally document all hedging relationships at inception, including the strategy and objectives for risk management",
    "Hedge documentation includes the risk management objective, hedging {swap_type}, and hedged item, prepared at inception",
    "{company} records formal documentation for hedges, outlining the relationship and risk management strategy",
    "{company} document the hedging relationship and risk management objectives at the start of each hedge in line with accounting standards",
    "{company} maintains documentation for all derivative hedges, including the hedged item and risk management strategy",
    "Formal documentation of hedging relationships is prepared at inception to support hedge accounting treatment",
    "{company} document the nature of hedging relationships and risk management objectives at the outset of each hedge",
    "{company} ensures formal documentation of all hedges, including the hedged item and risk management strategy",
    "Hedge accounting documentation includes the hedging {swap_type}, hedged item, and risk management objectives at inception",
    "{company} prepare formal documentation for all hedging relationships to meet accounting standard requirements",
    "{company} documents the risk management strategy and hedging relationships at the start of each hedge",
    "Formal hedge documentation is maintained, detailing the hedged item, hedging {swap_type}, and risk management objectives",
    "{company} document all hedging relationships at inception, including the risk management strategy and hedge objectives",
]

hedge_effectiveness_policy_templates = [
    "{company} {verb}, both at inception and on an on-going basis, whether the {swap_type} that are utilized in {hedge_type} hedging transactions are highly effective in offsetting the {metric} of hedged items",
    "{company} {verb} hedge effectiveness {frequency} to ensure derivatives continue to meet the criteria for hedge accounting",
    "Hedge effectiveness is {verb} {frequency} using {method} in accordance with {standard}",
    "{company} {verb} {frequency} assessments of hedge effectiveness to determine whether hedging relationships remain highly effective",
    "{company} {verb} hedge effectiveness {frequency} in accordance with {standard}",
    "{company} {verb} hedge effectiveness {frequency} using {method} to ensure compliance with {standard}",
    "{company} {verb} {frequency} tests of hedge effectiveness for {swap_type} to offset changes in {metric}",
    "Hedge effectiveness is {verb} {frequency} to verify that derivatives qualify for hedge accounting under {standard}",
    "{company} evaluate {swap_type} effectiveness {frequency} to ensure they offset {metric} as intended",
    "{company} {verb} effectiveness of {swap_type} {frequency} using {method} per {standard}",
    "{company} {verb} {frequency} hedge effectiveness tests using {method} to comply with {standard}",
    "Hedge effectiveness is {verb} {frequency} for {swap_type} to meet {standard} requirements",
    "{company} {verb} the effectiveness of {swap_type} {frequency} to offset changes in {metric} per {standard}",
    "{company} {verb} {frequency} assessments of {swap_type} effectiveness using {method}",
    "{company} {verb} hedge effectiveness {frequency} for {swap_type} in accordance with {standard}",
    "{company} {verb} {swap_type} effectiveness {frequency} to confirm compliance with {standard}",
    "{company}'s hedge positions in {swap_type} are continually assessed to determine whether new or offsetting transactions are required",
]

hedge_effectiveness_actual_templates = [
    "The {swap_type} was determined to be highly effective in offsetting the {metric} of the hedged item",
    "As of {month} {end_day}, {year}, the {swap_type} was considered a highly effective {hedge_type} hedge against {metric}",
    "All designated {swap_type} were deemed highly effective as of the latest assessment date",
    "Management concluded that the {swap_type} is a highly effective {hedge_type} hedge against {metric}",
    "Each {swap_type} guarantees a return equal to the actual return, and as such, effectively acts as a {hedge_type} hedge",
    "The {swap_type} designated as a {hedge_type} hedge was determined to be highly effective in offsetting {metric}",
    "Based on {frequency} assessments using {method}, the {swap_type} has been, and is expected to continue to be, highly effective",
    "The hedging relationship for the {swap_type} was highly effective throughout the period in accordance with {standard}",
    "{company} concluded that its {swap_type} were highly effective as {hedge_type} hedges of {metric} during the year",
    "For the year ended {month} {end_day}, {year}, all designated {swap_type} hedges were highly effective",
    "The effectiveness of the {swap_type} was confirmed using {method}, and the hedge was deemed highly effective",
    "Quantitative testing using {method} confirmed the {swap_type} was highly effective in mitigating {metric} under {standard}",
]

hedge_ineffectiveness_policy_templates = [
    "{company} assess hedge ineffectiveness {frequency} and record the gain or loss related to the ineffective portion of derivative instruments, if any, to current earnings",
    "Any hedge ineffectiveness is recognized immediately in earnings in the period identified",
    "Ineffectiveness, if present, is measured {frequency} and recorded in the consolidated statements of operations",
    "{company} recognizes any ineffective portion of hedging instruments in current period earnings",
    "Gains or losses from the ineffective portion of derivative instruments are recognized in earnings {frequency}",
    "{company} evaluates hedge ineffectiveness and records any such amounts in the statement of operations for the relevant period",
    "Ineffective amounts arising from hedging relationships are reported in earnings as part of the assessment {frequency}",
    "{company} monitors hedge effectiveness and immediately recognizes any ineffectiveness in income",
    "Hedge ineffectiveness, when identified, is reflected in earnings for the reporting period in which it occurs",
    "The ineffective portion of designated hedges is calculated and recognized in current earnings {frequency}",
]

hedge_ineffectiveness_actual_templates = [
    "During {year}, the company recorded {currency_code}{amount} {money_unit} of ineffectiveness related to its {swap_type} hedges",
    "Hedge ineffectiveness of {currency_code}{amount} {money_unit} was recognized in earnings for the year ended {month} {end_day}, {year}",
    "The ineffective portion of the {hedge_type} hedge resulted in a {gain_loss} of {currency_code}{amount} {money_unit} recorded in the consolidated statements of operations",
    "For the {quarter} quarter of {year}, ineffectiveness on certain {swap_type} hedges amounted to {currency_code}{amount} {money_unit}",
    "An insignificant amount of hedge ineffectiveness was recorded in earnings during {year}",
    "The amount of hedge ineffectiveness recognized in earnings for {year} and {prev_year} was not material",
]

hedge_discontinuation_templates = [
    "If {company} determine that a forecasted transaction is no longer probable of occurring, {company} discontinue hedge accounting and any related unrealized gain or loss on the derivative instrument is recognized in current earnings",
    "Hedge accounting is discontinued if the hedged forecasted transaction is no longer expected to occur, with accumulated gains or losses reclassified to earnings",
    "When a hedged forecasted transaction becomes improbable, {company} dedesignates the hedging relationship and recognizes deferred gains or losses immediately",
    "If a forecasted transaction fails to occur, amounts previously deferred in other comprehensive income are reclassified to current period earnings",
    "{company} ceases hedge accounting for derivatives when the hedged item is no longer expected to occur, with any accumulated gains or losses recorded in earnings",
    "Deferred gains or losses on discontinued hedges are recognized immediately in the consolidated statements of operations",
    "Upon dedesignation of a hedge, the ineffective and deferred portions of derivative instruments are recorded in current period earnings",
    "Hedge discontinuation is applied when the underlying forecasted transaction is no longer probable, reclassifying previously deferred amounts to income",
    "If the hedged item does not materialize, accumulated OCI amounts for the hedge are transferred to current earnings",
    "{company} derecognizes hedge accounting when criteria are no longer met, and any associated gains or losses are recognized in the period of discontinuation",
    "{swap_type} being accounted for as a {hedge_type} hedge does not qualify for hedge accounting because it is no longer highly effective in offsetting {metric} of a hedged item",
    "If the {swap_type} expires or is sold, terminated or exercised, or if management determines that designation of the {swap_type} as a hedge instrument is no longer appropriate, hedge accounting would be discontinued",
    "In {year}, {company} discontinued hedge accounting for certain {swap_type} as part of a strategic change in its risk management approach",
    "Upon discontinuation of the {hedge_type} hedge, a net {gain_loss} of {currency_code}{amount} {money_unit} was reclassified from accumulated other comprehensive income into {location}",
    "Hedge accounting was discontinued for the {swap_type} in {month} {year} following the early repayment of the hedged debt instrument",
    "When a hedge is discontinued because it is no longer effective, the derivative is no longer designated as a hedge, and subsequent changes in fair value are recognized in earnings",
    "For discontinued {hedge_type} hedges, any gains or losses previously deferred in other comprehensive income are recognized in earnings when the hedged transaction affects earnings",
    "{company} may terminate or de-designate a {swap_type} at any time, at which point hedge accounting is discontinued prospectively",
]

hedge_no_trading_templates = [
    "{company} does not enter into derivative transactions for trading purposes",
    "{company}'s policy prohibits the use of derivatives for speculative or trading purposes",
    "Derivatives are {verb} solely for hedging and risk management, not for speculative trading",
    "{company} does not engage in derivative transactions for speculative purposes",
    "All derivative transactions are {verb} for hedging purposes and not for trading or speculation",   
    "The use of derivatives is strictly limited to hedging activities, not for speculative trading",
    "{company} does not utilize derivative instruments for speculative purposes",
    "Derivatives are {verb} exclusively for hedging identified risks, not for trading gains",
    "{company} maintains a strict policy against using derivatives for speculative trading",
    "No derivative transactions are {verb} for trading or speculative activities",
    "Derivatives are {verb} solely to manage exposures, not for proprietary trading",
    "{company} prohibits speculative derivative activities",
    "The company's derivative strategy is focused on risk mitigation, not trading",
    "Derivatives are {verb} for hedging purposes only, not for speculation",
    "{company} does not engage in speculative derivative transactions",
    "All derivative activities are non-trading in nature",
    "Derivatives are {verb} to hedge specific risks, not for market speculation",
    "{company} has a policy against using derivatives for trading profits",
    "The use of derivatives is restricted to hedging, excluding speculative positions",
    "No derivatives are {verb} for trading accounts",
    "{company} does not conduct proprietary trading in derivatives",
    "Derivatives are {verb} exclusively for risk management, not for trading income",
    "The company's derivative policy forbids speculative trading",
    "All derivative transactions are {verb} for hedging, not for trading purposes",
    "{company} does not use derivatives for speculative investments",
    
]

hedge_counterparty_templates = [
 "Most of the counterparties to the derivatives are major banks and {company} is monitoring the associated inherent credit risks",
    "{company} enters into derivative contracts with major financial institutions and monitors counterparty credit risk on an ongoing basis",
    "Derivative counterparties are limited to major banking institutions with strong credit ratings to minimize counterparty risk",
    "Credit risk from derivatives is mitigated by transacting only with highly-rated financial institution counterparties",
    "{company} manages counterparty credit exposure by diversifying its derivative contracts among multiple major banks",    
    "The majority of derivative counterparties are major banks, and {company} actively monitors inherent credit risks",
    "{company} mitigates counterparty credit risk by engaging with major financial institutions and continuously monitoring their creditworthiness",
    "To minimize counterparty risk, {company} restricts derivative transactions to major banks with high credit ratings",
    "Counterparty credit risk is managed by diversifying derivative agreements across several major banking institutions",
    "{company} primarily transacts with major banks for its derivatives, and associated credit risks are under continuous review",
    "Derivative counterparties are selected from major financial institutions, and {company} maintains vigilance over inherent credit risks",
    "Credit risk from derivative instruments is managed by limiting transactions to major banks with robust credit profiles",
    "{company} ensures counterparty credit risk is minimized by diversifying derivative contracts among multiple highly-rated financial institutions",
    "The majority of {company}'s derivative counterparties are major banks, and credit risk is actively monitored",
    "{company} engages with major financial institutions for derivatives and continuously assesses counterparty credit risk", 
    "Based upon certain factors, including a review of the {swap_type} for {company}'s counterparties, {company} determined its counterparty credit risk to be immaterial",
    "Based upon certain factors, including a review of the {swap_type} for {company}'s counterparties, {company} determined its counterparty credit risk to be material",
]

# --- Generic context
begin_gen_context_templates = [
    "{company} is exposed to various market risks, including changes in interest rates, foreign exchange rates, and commodity prices",
    "As part of its overall risk management strategy, {company} monitors and manages exposure to fluctuations in market conditions",
    "{company}'s operations and financial results are affected by changes in market factors such as interest rates, exchange rates, and commodity prices",
    "Our global activities expose us to market risks that arise from changes in economic and financial conditions worldwide",
    "As a diversified enterprise, {company} is subject to risks associated with fluctuations in market prices and rates",
    "{company}'s risk management program addresses exposure to market risk, including movements in interest rates, currencies, and commodities",
    "Due to the nature of its operations, {company} faces exposure to various financial market risks",
    "Market risk represents the potential for losses arising from movements in market variables affecting {company}'s earnings or cash flows",
    "{company}'s financial performance is influenced by volatility in interest rates, currency exchange rates, and other market prices",
    "Operating in global markets, {company} is exposed to risks from changes in financial market conditions, which it manages through derivative and non-derivative instruments",
]

# --- Combined FX + IR context ---
begin_fx_ir_context_templates = [
    "{company}'s global operations expose it to various market risks, including fluctuations in foreign currency exchange rates and interest rates",
    "Our business operations in multiple countries result in exposure to foreign currency exchange rate movements and interest rate volatility",
    "{company} operates in numerous international markets, which subjects us to risks from changes in currency exchange rates and interest rates",
    "{company}'s multinational operations are impacted by foreign currency movements and interest rate changes in various markets",
    "As a global entity, {company} faces exposure to exchange rate volatility and interest rate risks in its operations",
    "Operating in various jurisdictions, {company} is exposed to fluctuations in foreign currencies and interest rate movements",
    "Our global business model results in exposure to foreign exchange rate changes and interest rate fluctuations",
    "As a multinational company, {company} is subject to risks from currency movements and interest rate volatility across regions",
    "Our global operations are impacted by changes in foreign exchange rates and varying interest rate environments",
    "{company} faces currency exchange and interest rate risks due to its operations in multiple international markets",
]

# --- FX-specific context ---
begin_fx_context_templates = [
    "{company}'s international operations expose it to risks arising from fluctuations in foreign currency exchange rates",
    "Due to its global footprint, {company} is exposed to currency translation and transaction risks",
    "Our cross-border operations result in exposure to changes in exchange rates between functional and reporting currencies",
    "{company} operates subsidiaries in various countries, creating exposure to foreign currency movements",
    "As a global enterprise, {company} faces risks related to fluctuations in exchange rates across its international markets",
    "Our revenues, expenses, and cash flows are subject to variability due to foreign currency exchange rate changes",
    "Operating in multiple currencies, {company} is exposed to volatility in exchange rates that can affect its financial results",
    "As part of its global operations, {company} is subject to risks arising from changes in currency values",
    "Foreign currency movements impact {company}'s consolidated financial position and cash flows",
    "{company} faces currency-related risks due to its extensive international operations",
]

# --- IR-specific context ---
begin_ir_context_templates = [
    "{company} is exposed to market risks arising from changes in interest rates on its debt and investment portfolios",
    "Our financing activities expose us to fluctuations in interest rates that impact borrowing costs and returns on investments",
    "{company} faces exposure to changes in market interest rates affecting both variable-rate debt and interest-bearing assets",
    "As part of its funding strategy, {company} manages risks associated with interest rate movements",
    "Our exposure to interest rate volatility arises primarily from debt obligations and cash management activities",
    "{company}'s borrowing costs and investment income are influenced by changes in prevailing interest rate environments",
    "Operating in multiple financial markets, {company} is subject to risks from changes in benchmark interest rates",
    "{company} actively monitors and manages its exposure to interest rate fluctuations through derivative and non-derivative instruments",
    "Interest rate volatility can materially affect {company}'s financing costs and overall liquidity position",
    "Changes in interest rate conditions across markets affect {company}'s funding and hedging strategies",
]

begin_eq_context_templates = [
    "{company} is exposed to market risks related to fluctuations in the price of its common stock and other equity instruments",
    "Volatility in equity markets affects {company}'s exposure to equity-linked compensation and investment values",
    "{company}'s share-based compensation costs are influenced by changes in its stock price and market conditions",
    "As part of its equity risk management, {company} monitors exposure to stock market fluctuations",
    "{company}'s financial results are impacted by changes in equity market valuations",
    "Movements in equity indices can affect {company}'s exposure to equity-linked obligations",
    "As a publicly traded entity, {company} is exposed to risks associated with market price movements of its shares",
    "{company} faces risks arising from fluctuations in the value of equity-based instruments",
    "Equity market volatility may influence {company}'s compensation expenses and investment performance",
    "{company}'s exposure to equity price movements arises primarily from its stock-based compensation and equity investments",
]

begin_cp_context_templates = [
    "{company} is exposed to market risks arising from changes in {commodity} prices that affect its production costs and revenues",
    "Fluctuations in {commodity} prices can impact {company}'s profitability and cost structure",
    "As part of its operations, {company} is exposed to volatility in {commodity} prices",
    "Changes in {commodity} prices can influence {company}'s margins and overall financial performance",
    "{company}'s cost of goods sold is affected by variability in {commodity} market prices",
    "Our operations are subject to risks associated with changes in the prices of key commodities such as {commodity}",
    "{company} faces exposure to {commodity} market volatility, which can impact both input costs and sales prices",
    "The profitability of {company}'s operations depends in part on the stability of {commodity} prices",
    "As part of its risk management strategy, {company} monitors and manages exposure to {commodity} price fluctuations",
    "{company} faces risks related to volatility in {commodity} markets that affect its operating results",
]

# --- Shared placeholders for extension ---
begin_context_placeholders = [
    "particularly through its international subsidiaries and cross-border transactions",
    "arising from sales, purchases, and borrowings denominated in foreign currencies",
    "through operations spanning North America, Europe, and Asia",
    "as a result of foreign investments and intercompany funding activities",
    "driven by the mix of currencies in which it conducts business",
    "from exposure to both local and international interest rate environments",
    "primarily related to its global financing and treasury activities",
    "due to variability in exchange and interest rates across markets where it operates",
    "from transactions conducted in currencies other than its functional currency",
    "through its diverse portfolio of foreign operations and financing arrangements",
]


# ==============================================================================
# TEMPLATE GENERATION FUNCTIONS
# ==============================================================================

def to_sentence_case(text):
    """Convert text to sentence case."""
    if not text.strip():
        return text
    result = []
    prev_non_space = None
    for char in text:
        if char.isspace():
            result.append(char)
            continue
        if char.isalpha():
            if prev_non_space == "." or prev_non_space is None:
                result.append(char.upper())
            else:
                result.append(char.lower())
        else:
            result.append(char)
        prev_non_space = char
    return "".join(result)


def _expand_pattern(pattern):
    """Expand placeholders in a pattern using all combinations of replacement lists."""
    placeholder_map = {
        "{term_result}": termination_event_results,
        "{frequency}": settlement_frequencies,
        "{termination_verb}": termination_verbs,
        "{comparison}": comparison_phrases,
        "{trend}": trend_descriptors,
        "{purpose}": optional_purposes,
        "{time_period}": time_periods,
        "{no_replacement}": no_replacement_phrases,
        "{dedesignation_action}": dedesignation_actions,
        "{state}": state_descriptors,
        "{pay_result}": payment_results,
    }

    # Identify placeholders present in the pattern
    active_placeholders = [k for k in placeholder_map if k in pattern]
    if not active_placeholders:
        return [pattern]

    # Create all possible combinations of replacements
    replacement_lists = [placeholder_map[k] for k in active_placeholders]
    expanded = []
    for combo in itertools.product(*replacement_lists):
        new_pattern = pattern
        for key, val in zip(active_placeholders, combo):
            new_pattern = new_pattern.replace(key, val)
        expanded.append(new_pattern)
    return expanded


def generate_optional_templates():
    """Generate all optional/comparative templates."""
    templates = []
    for pattern in optional_template_patterns:
        expanded = _expand_pattern(pattern)
        templates.extend([to_sentence_case(t) for t in expanded])
    return templates


def generate_termination_templates():
    """Generate all merged event templates (termination, expiration, dedesignation)."""
    templates = []
    for pattern in merged_event_patterns:
        expanded = _expand_pattern(pattern)
        templates.extend([to_sentence_case(t) for t in expanded])
    return templates


def generate_payment_templates():
    """Generate payment-related templates."""
    templates = []
    for pattern in payment_phrases:
        expanded = _expand_pattern(pattern)
        templates.extend([to_sentence_case(t) for t in expanded])
    return templates


def generate_hedge_position_templates(hedge_type="gen"):
    """
    Generate all template combinations for a specific hedge type.
    Args:
        hedge_type: One of "ir", "fx", "eq", "cp", "gen"
    Returns:
        List of all generated templates
    """
    accounting_results_map = {
        "ir": gen_specific_results + ir_specific_results,
        "fx": gen_specific_results + fx_specific_results,
        "eq": gen_specific_results + eq_specific_results,
        "cp": gen_specific_results + cp_specific_results,
        "gen": gen_specific_results,
    }
    accounting_results = accounting_results_map.get(
        hedge_type.lower(), gen_specific_results
    )

    templates = []

    # Single-year amount_swap_orders
    amount_swap_orders = [
        to_sentence_case(pattern.replace("{connector}", connector))
        for pattern in one_year_amount_patterns
        for connector in amount_connectors
    ]

    # Two-year and three-year versions
    two_year_amounts = [
        to_sentence_case(pattern.replace("{connector}", connector))
        for pattern in two_year_amount_patterns
        for connector in amount_connectors
    ]
    three_year_amounts = [
        to_sentence_case(pattern.replace("{connector}", connector))
        for pattern in three_year_amount_patterns
        for connector in amount_connectors
    ]

    # Single-year templates
    for prefix in one_year_prefixes:
        for amount_order in amount_swap_orders:
            for designation in hedge_designations:
                full = (
                    f"{prefix}, {{company}} {{verb}} {amount_order} {designation}"
                    if designation
                    else f"{prefix}, {{company}} {{verb}} {amount_order}"
                )
                templates.append(to_sentence_case(full))

    # Two-year templates
    for prefix in two_year_prefixes:
        for amount_order in two_year_amounts:
            for designation in hedge_designations:
                full = (
                    f"{prefix}, {{company}} {{verb}} {amount_order} {designation}"
                    if designation
                    else f"{prefix}, {{company}} {{verb}} {amount_order}"
                )
                templates.append(to_sentence_case(full))

    # Three-year templates
    for prefix in three_year_prefixes:
        for amount_order in three_year_amounts:
            for designation in hedge_designations:
                full = (
                    f"{prefix}, {{company}} {{verb}} {amount_order} {designation}"
                    if designation
                    else f"{prefix}, {{company}} {{verb}} {amount_order}"
                )
                templates.append(to_sentence_case(full))

    # Single-year table-like patterns
    for template in one_year_table_prefixes:
        for order in one_year_table_patterns:
            full = (
                f"{template} {order}"
            )
            templates.append(to_sentence_case(full))

    # Two-year table-like patterns
    for template in two_year_table_prefixes:
        for order in two_year_table_patterns:
            full = (
                f"{template} {order}"
            )
            templates.append(to_sentence_case(full))
    # Three-year table-like patterns
    for template in three_year_table_prefixes:
        for order in three_year_table_patterns:
            full = (f"{template} {order}")
            templates.append(to_sentence_case(full))

    # Historical templates
    for template in historical_templates:
        expanded = _expand_pattern(template)
        templates.extend([to_sentence_case(t) for t in expanded])

    # Accounting impact templates
    for template in hedge_impact_templates:
        if "{impact_result}" in template:
            for reason in accounting_results:
                full = template.replace("{impact_result}", reason)
                templates.append(to_sentence_case(full))
        else:
            templates.append(to_sentence_case(template))

    # Two-year / Three-year "no prior year" templates
    for template in two_year_no_prior_templates:
        for pattern in two_year_no_prior_patterns:
            templates.append(
                to_sentence_case(template.replace("{no_prior_pattern}", pattern))
            )
    for template in three_year_no_prior_templates:
        for pattern in three_year_no_prior_patterns:
            templates.append(
                to_sentence_case(template.replace("{no_prior_pattern}", pattern))
            )

    return templates

def generate_hedge_mitigation_templates(hedge_type="gen"):
    hedge_context_map = {
        "ir": ir_specific_mitigation,
        "fx": fx_specific_mitigation,
        "eq": eq_specific_mitigation,
        "cp": cp_specific_mitigation,
        "gen": gen_specific_mitigation,
    }
    specific_mitigation = hedge_context_map.get(hedge_type.lower(), gen_specific_mitigation)

    templates = []
    for template in hedge_context_template: # Contains {context} to map
        for context in specific_mitigation:
            full = template.replace("{context}", context)
            templates.append(to_sentence_case(full))
    return templates


def generate_hedge_begin_context_templates(hedge_type="gen"):
    hedge_context_map = {
        "ir": begin_ir_context_templates + begin_fx_ir_context_templates,
        "fx": begin_fx_context_templates + begin_fx_ir_context_templates,
        "cp": begin_cp_context_templates,
        "eq": begin_eq_context_templates,
        "gen": begin_gen_context_templates,
    }

    # Select the correct context set; fallback to generic if unknown
    specific_mitigation = hedge_context_map.get(
        hedge_type.lower(), begin_gen_context_templates
    )

    templates = []

    # Combine context with placeholder endings
    for context in specific_mitigation:
        for placeholder in begin_context_placeholders:
            templates.append(f"{context}, {placeholder}")
    return templates


import random

# =============================================================================
# DERIVATIVES
# =============================================================================

GLOBAL_PREFIXES = [""]

SWAP_PREFIXES = [
    "pay-fixed, receive-floating",
    "pay-floating, receive-fixed",
    "pay variable, receive fixed",
    "pay fixed, receive variable",
]

PAY_PREFIX_RATIO = 0.15  # ~15% of total swap-like combinations


# =============================================================================
# BASE TYPES
# =============================================================================

STANDALONE_TYPES = ["swap"]
DEPENDENT_TYPES = [
    "cap",
    "floor",
    "collar",
    "swaption",
    "lock",
    "forward",
    "option",
    "future",
    "derivative",
    "hedge",
]

BASE_TYPES = STANDALONE_TYPES + DEPENDENT_TYPES

DEFAULT_SUFFIXES = ["", "agreement", "contract", "arrangement", "instrument", "transaction"]

SPECIAL_EXPANSIONS = {
    "option": [
        "call option",
        "put option",
        "call contract",
        "put contract",
        "option contract",
    ],
}

CATEGORY_EXTRAS = {
    "ir": [],
    "fx": ["NDF"],
    "cp": [],
    "eq": [],
    "gen": ["over-the-counter contract", "collar strategies", "total return swap"],
}

PLACEHOLDERS = {
    "ir": [
        "interest-rate",
        "single-currency",
        "Eurodollar",
        "SOFR",
        "SONIA",
        "LIBOR",
        "LIBOR-based",
        "EURIBOR",
        "treasury-rate",
        "forward-rate",
        "fixed-rate",
        "floating-rate",
        "variable-rate",
        "benchmark-rate",
    ],
    "fx": [
        "foreign exchange",
        "foreign currency",
        "currency",
        "cross-currency",
        "cross currency interest rate",
        "forward currency",
        "foreign currency forward",
        "FX",
        "dollar call",
    ],
    "cp": ["commodity price", "commodity-related", "fixed commodity"],
    "eq": ["equity", "equity-related"],
    "gen": [""],
}


# =============================================================================
# EXPANSION FUNCTIONS
# =============================================================================


def expand_types(base_types, suffixes, special):
    """Expand base types with suffixes and special overrides."""
    results = []
    for base in base_types:
        results.extend(f"{base} {s}".strip() for s in suffixes)
        if base in special:
            results.extend(special[base])
    return sorted(set(results))


def expand_derivative_terms(placeholders, types, extras):
    """Combine all logical dimensions into descriptive derivative terms."""
    results = []

    for ph in placeholders if placeholders else [""]:
        for t in types:
            # Skip dependent types without a placeholder
            if len(ph) == 0 and t in DEPENDENT_TYPES:
                continue
            # Determine valid prefixes
            prefixes = GLOBAL_PREFIXES.copy()
            if any(x in t for x in ["swap", "swaption", "rate lock"]):
                # Apply stochastic sampling to swap-style prefixes
                sampled = [
                    p for p in SWAP_PREFIXES if random.random() < PAY_PREFIX_RATIO
                ]
                prefixes += sampled

            for pre in prefixes:
                # If a placeholder exists (e.g., "interest-rate") and the type is a bare dependent type (e.g., "cap" with no suffix),
                # skip it to avoid creating incomplete terms like "interest-rate cap".
                # It will be correctly handled when the type is "cap agreement".
                if ph and t in DEPENDENT_TYPES:
                    continue
                term = " ".join(x for x in [pre, ph, t] if x).strip()
                results.append(term)

    results.extend(extras)
    return sorted(set(results))

# =============================================================================
# BUILD FINAL DICTIONARY
# =============================================================================

SHARED_TYPES = expand_types(BASE_TYPES, DEFAULT_SUFFIXES, SPECIAL_EXPANSIONS)

derivative_keywords = {
    cat: expand_derivative_terms(
        PLACEHOLDERS[cat],
        SHARED_TYPES,
        CATEGORY_EXTRAS[cat],
    )
    for cat in PLACEHOLDERS
}


tasks = {
    "hedge_payment_templates": (generate_payment_templates, []),
    "hedge_termination_templates": (generate_termination_templates, []),
}
swap_t = ["ir", "fx", "cp", "eq", "gen"]
for ht in swap_t:
    tasks[f"hedge_position_templates_{ht}"] = (generate_hedge_position_templates, [ht])
    tasks[f"hedge_mitigation_templates_{ht}"] = (generate_hedge_mitigation_templates, [ht])
    tasks[f"hedge_begin_context_templates_{ht}"] = (generate_hedge_begin_context_templates, [ht])

results = {}
with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
    future_to_key = {executor.submit(func, *args): key for key, (func, args) in tasks.items()}
    for future in tqdm(as_completed(future_to_key), total=len(tasks), desc="Generating hedge templates"):
        key = future_to_key[future]
        try:
            results[key] = future.result()
        except Exception as exc:
            print(f'{key} generated an exception: {exc}')
            results[key] = []

hedge_payment_templates = results["hedge_payment_templates"]
hedge_termination_templates = results["hedge_termination_templates"]

hedge_position_templates = {}
hedge_mitigation_templates = {}
hedge_begin_context_templates = {}
for ht in swap_t:
    hedge_position_templates[ht] = results[f"hedge_position_templates_{ht}"]
    hedge_mitigation_templates[ht] = results[f"hedge_mitigation_templates_{ht}"]
    hedge_begin_context_templates[ht] = results[f"hedge_begin_context_templates_{ht}"]
