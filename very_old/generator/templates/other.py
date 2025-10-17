# Common SEC patterns
headers = [
    "FORM 10-K",
    "FORM 10-Q",
    "FORM 8-K",
    "PROSPECTUS",
    "Table of Contents",
    "UNITED STATES SECURITIES AND EXCHANGE COMMISSION",
]

# Table of Contents patterns with placeholders for page numbers
sec_toc_patterns = [
    "Item 1. Business {page}",
    "A. History and Development of {company} {page}",
    "B. Business Overview {page}",
    "C. Organizational Structure {page}",
    "Item 1A. Risk Factors {page}",
    "Item 1B. Unresolved Staff Comments {page}",
    "Item 2. Properties {page}",
    "Item 3. Legal Proceedings {page}",
    "Item 4. Submission of Matters to a Vote of Security Holders {page}",
    "Item 5. Market for Registrant's Common Equity, Related Stockholder Matters and Issuer Purchases of Equity Securities {page}",
    "A. Market Information {page}",
    "B. Holders {page}",
    "C. Dividends {page}",
    "D. Restrictions on Share Ownership by Non-Canadians {page}",
    "E. Exchange Controls {page}",
    "F. Taxation {page}",
    "G. Sale of Unregistered Securities {page}",
    "H. Purchases of Equity Securities by {company} and Affiliated Purchases {page}",
    "Item 6. Selected Financial Data {page}",
    "Item 7. Management's Discussion and Analysis of Financial Condition and Results of Operation {page}",
    "Item 7A. Quantitative and Qualitative Disclosures About Market Risk {page}",
    "Item 8. Financial Statements and Supplementary Data {page}",
    "Item 9. Changes in and Disagreements with Accountants on Accounting and Financial Disclosure {page}",
    "Item 9A. Controls and Procedures {page}",
    "Item 9B. Other Information {page}",
    "Item 10. Directors, Executive Officers and Corporate Governance {page}",
    "Item 11. Executive Compensation {page}",
    "Item 12. Security Ownership of Certain Beneficial Owners and Management and Related Stockholder Matters {page}",
    "Item 13. Certain Relationships and Related Transactions, and Director Independence {page}",
    "Item 14. Principal Accounting Fees and Services {page}",
    "Item 15. Exhibits, Financial Statement Schedules {page}",
    "SIGNATURES {page}",
]
# ============ LITIGATION AND LEGAL MATTERS ============

litigation_templates = [
    "{company} is involved in various legal proceedings and claims arising in the ordinary course of business, including {case_types}",
    "As of {month} {end_day}, {year}, {company} is a defendant in several lawsuits related to {case_types}",
    "{company} is subject to litigation and regulatory inquiries concerning {case_types} in the normal course of operations",
    "Various legal actions, proceedings, and claims are pending or may be instituted against {company}, including {case_types}",
    "As of {month} {end_day}, {year}, {company} is a defending against several derivative lawsuits related to {case_types}",
    'All securities holders of {company} are hereby notified that a settlement (the "Settlement") has been reached as to claims asserted in the above-captioned consolidated shareholder derivative action pending in a {court} (the "Derivative Action") on behalf of {company} against certain of its current or former directors and officers',
    "On {month} {end_day}, {year}, a shareholder derivative suit was filed in the {court} for the against {company}",
]

case_types = [
    "product liability, employment matters, and commercial disputes",
    "intellectual property infringement, contract disputes, and employment claims",
    "environmental matters, product warranty claims, and regulatory compliance",
    "patent litigation, customer disputes, and employment-related matters",
    "breach of contract claims, employment discrimination, and tax disputes",
]

litigation_assessment_templates = [
    "Management believes that the ultimate resolution of these matters will not have a material adverse effect on {company}'s financial position, results of operations, or cash flows",
    "While the outcome of these proceedings cannot be predicted with certainty, management does not believe they will materially impact the consolidated financial statements",
    "{company} believes it has meritorious defenses and intends to vigorously defend against these claims",
    "{company} intend to vigorously defend against these claims. At this time, {company} cannot predict the outcome, or provide a reasonable estimate or range of estimates of the possible outcome or loss, if any, in this matter",
    "Based on currently available information, management does not expect these matters to result in a material loss",
    "{company} has {verb} the likelihood of loss as remote and has not recorded any provisions related to these contingencies",
]

specific_lawsuit_templates = [
    "In {month} {year}, a lawsuit was filed against {company} in the {court} alleging {allegation}. {company} filed a motion to dismiss in {month} {dismiss_year}",
    "{company} is defending a class action lawsuit filed in {year} claiming {allegation}, with damages sought of approximately {currency_code}{amount} {money_unit}",
    "During {year}, {company} reached a settlement in a lawsuit related to {allegation} for {currency_code}{amount} {money_unit}, which was accrued in prior periods",
    "A complaint was filed against {company} in the {court} during {quarter} quarter {year} alleging {allegation}",
]

courts = [
    "United States District Court for the District of Delaware",
    "Superior Court of California",
    "United States District Court for the Southern District of New York",
    "Court of Chancery of the State of Delaware",
    "United States District Court for the Northern District of California",
    "Federal Court of Connecticut",
    "United States Court of Appeals for the Ninth Circuit",
    "United States Supreme Court",
    "Superior Court of the State of New Jersey",
    "Circuit Court of Cook County, Illinois",
    "New York State Supreme Court, Commercial Division",
    "Massachusetts Superior Court, Business Litigation Session",
    "Texas District Court, Harris County",
    "Florida Circuit Court for Miami-Dade County",
    "United States District Court for the District of Massachusetts",
    "United States District Court for the Western District of Texas",
    "United States District Court for the Eastern District of Virginia",
    "Court of Appeals of the State of California, Second Appellate District",
]


allegations = [
    "breach of contract and misappropriation of trade secrets",
    "violations of federal securities laws",
    "employment discrimination and wrongful termination",
    "patent infringement related to product technology",
    "breach of fiduciary duty and corporate waste",
    "antitrust violations and unfair competition",
    "failure to adequately warn of product risks",
    "fraudulent misrepresentation and concealment",
    "negligence in product design and manufacturing",
    "copyright infringement of proprietary materials",
    "violations of the Fair Labor Standards Act",
    "insider trading and market manipulation",
    "unlawful retaliation against whistleblowers",
    "environmental violations under the Clean Air Act",
    "consumer protection law violations",
    "unjust enrichment and conversion of assets",
    "false advertising and deceptive trade practices",
    "invasion of privacy and data security breaches",
    "violation of antidiscrimination provisions under Title VII",
    "failure to comply with OSHA workplace safety regulations",
]
# ============ EQUITY WARRANTS (NON-DERIVATIVE) ============

equity_warrant_templates = [
    "{company} has {shares} equity-classified warrants outstanding with an exercise price of {currency_code}{price} per share, exercisable until {expiry_year}",
    "Outstanding equity warrants for {shares} shares at {currency_code}{price} per share are classified in stockholders' equity and are not remeasured",
    "As of {month} {end_day}, {year}, there were {shares} warrants outstanding classified as equity instruments",
    "{company} issued {shares} warrants to purchase common stock at {currency_code}{price} per share, which are indexed to {company}'s own stock and classified in equity",
    "In {month} {year}, {shares} warrants issued to investors in connection with a {event} in {prev_month} {prev_year} were reset to {currency_code}{price}",
    "In connection with the {event}, {company} issued warrants to purchase up to {shares} shares of common stock at an exercise price of {currency_code}{price} per share",
    "During {month} {year}, {company} issued {shares} warrants exercisable at {currency_code}{price} per share in conjunction with {event}",
    "As part of {event}, {company} granted warrants for {shares} shares with a strike price of {currency_code}{price}, expiring in {expiry_year}",
    "{company} issued {shares} common stock warrants at an exercise price of {currency_code}{price} per share as consideration for {event}",
    "In {month} {year}, warrants to acquire {shares} shares at {currency_code}{price} per share were issued in connection with {event}",
    "In connection with the {event}, {company} issued warrants to purchase up to {shares} shares of common stock at an exercise price of {currency_code}{price} per share, provision states the warrants meet the criteria for equity treatment",
    "{company} issued {shares} shares of common stock valued at {currency_code}{value} in connection with {event} during {year}",
    "During {year}, {company} issued {shares} shares of common stock (valued at {currency_code}{value}) as part of {event}",
]


equity_warrant_activity_templates = [
    "During {year}, warrant holders exercised {shares} warrants, resulting in proceeds of {currency_code}{amount} {money_unit}",
    "In {month} {year}, {shares} equity warrants expired unexercised, with no impact on earnings",
    "{company} received {currency_code}{amount} {money_unit} from the exercise of {shares} warrants during {year}",
    "{shares} warrants were exercised on a cashless basis during {year}, resulting in the issuance of {net_shares} net shares",
    "During {year}, warrants to purchase {shares} shares were exercised on a cashless basis, resulting in the issuance of {net_shares} net shares",
    "In the {quarter} quarter of {year}, {company} modified the terms of outstanding warrants, extending the expiration date to {expiry_year} and adjusting the exercise price to {currency_code}{price}",
    "Warrants representing {shares} shares expired unexercised during {year}",
    "{company} repurchased and cancelled warrants for {shares} shares during {month} {year} for cash consideration of {currency_code}{amount} {money_unit}",
    "In {month} {year}, warrant holders exercised their rights to acquire {shares} shares, resulting in gross proceeds of {currency_code}{amount} {money_unit}",
    "The additional cost of the warrants of {currency_code}{amount} was recorded as a debit and a credit to additional paid in capital",
    "Any issuance of common stock by {company} may result in a reduction in the book value per share",
    "The reduction on market price per share of {company}'s outstanding shares of common stock will reduce the proportionate ownership and voting power of such shares",
    "In addition, {company} has reserved {shares} shares of the common stock for issuance upon the exercise of outstanding warrants",
]
# Warrant events/reasons
warrant_events = [
    "a debt financing transaction",
    "the series B preferred stock offering",
    "a credit facility agreement",
    "consulting services agreements",
    "a strategic partnership agreement",
    "the convertible note issuance",
    "a private placement",
    "the acquisition financing",
    "vendor financing arrangements",
    "financing",
    "the initial public offering (IPO)",
    "a merger or acquisition transaction",
    "a joint venture agreement",
    "the issuance of senior secured notes",
    "bridge financing arrangements",
    "a restructuring or recapitalization",
    "a collaboration agreement with a strategic partner",
    "the issuance of subordinated debt securities",
    "a technology licensing agreement",
    "the spin-off of a subsidiary",
    "equity line financing arrangements",
    "the settlement of outstanding litigation",
    "an employee retention or incentive program",
    "royalty financing arrangements",
    "a PIPE (private investment in public equity) transaction",
    "mezzanine financing agreements",
]

# ============ REVENUE RECOGNITION ============

revenue_recognition_templates = [
    "{company} recognizes revenue when control of promised goods or services is transferred to customers in an amount that reflects the consideration expected to be received",
    "Revenue from product sales is recognized at a point in time when the customer obtains control, typically upon shipment or delivery",
    "{company} applies the five-step model under ASC 606 to determine when and how revenue is recognized",
    "Performance obligations are satisfied over time for service contracts and at a point in time for product sales",
    "Revenue from subscription services is recognized ratably over the contract period as services are provided",
    "For contracts that include multiple performance obligations, {company} allocates the transaction price based on relative standalone selling prices",
    "Variable consideration, including rebates, discounts, and performance incentives, is estimated and included in the transaction price when it is probable that a significant reversal will not occur",
    "Revenue related to licenses of intellectual property is recognized either at a point in time or over time, depending on the nature of the rights granted",
    "For long-term construction and engineering contracts, revenue is recognized over time using an input method such as costs incurred relative to total expected costs",
    "In arrangements where {company} acts as an agent rather than the principal, revenue is recorded net of amounts owed to third-party suppliers",
    "Revenue from milestone payments under collaboration agreements is recognized when the underlying performance obligations are achieved",
    "Shipping and handling activities performed after the transfer of control are accounted for as fulfillment costs rather than separate performance obligations",
    "Advance payments received from customers are recorded as contract liabilities until the performance obligation is satisfied",
    "When a right of return exists, {company} recognizes revenue net of estimated returns based on historical experience and current expectations",
    "For software arrangements, revenue from perpetual licenses is recognized at delivery, while revenue from SaaS arrangements is recognized over the subscription term",
]


deferred_revenue_templates = [
    "Deferred revenue as of {month} {end_day}, {year} was {currency_code}{amount} {money_unit}, compared to {currency_code}{prev_amount} {money_unit} in the prior year",
    "{company} recorded deferred revenue of {currency_code}{amount} {money_unit} related to advance payments from customers for future deliverables",
    "Contract liabilities increased to {currency_code}{amount} {money_unit} at year-end {year} due to timing of customer payments and performance obligations",
    "As of {month} {end_day}, {year}, {company} had {currency_code}{amount} {money_unit} in deferred revenue related to service and maintenance contracts",
    "Deferred revenue primarily consists of advance billings for subscription and support services to be recognized over future periods",
    "{company} expects to recognize approximately {currency_code}{amount} {money_unit} of deferred revenue over the next twelve months and the remainder thereafter",
    "The increase in deferred revenue from {currency_code}{prev_amount} {money_unit} to {currency_code}{amount} {money_unit} reflects growth in multi-year customer contracts",
    "Deferred revenue includes amounts invoiced in advance for software licenses, cloud services, and professional support not yet recognized as revenue",
    "Changes in deferred revenue during {year} were driven by new billings offset by revenue recognized as performance obligations were satisfied",
    "Deferred revenue classified as current liabilities was {currency_code}{amount} {money_unit}, with the non-current portion recorded as {currency_code}{prev_amount} {money_unit}",
    "{company} recognized revenue of {currency_code}{prev_amount} {money_unit} during {year} that was included in deferred revenue at the beginning of the period",
    "Deferred revenue balances are expected to be recognized as revenue consistent with the satisfaction of contractual obligations over time",
]

# ============ INVENTORY ============

inventory_templates = [
    "{items} inventories are stated at the lower of cost or net realizable value, with cost determined using the {method} method",
    "{company} values inventory using the {method} cost method and regularly reviews for obsolescence",
    "Inventory consists of {items} valued at the lower of cost (determined by {method}) or net realizable value",
    "As of {month} {end_day}, {year}, {items} inventories totaled {currency_code}{amount} {money_unit}, net of obsolescence reserves of {currency_code}{reserve} {money_unit}",
    "{items} inventories are reviewed periodically for slow-moving or obsolete items, with reserves recorded when necessary to reduce carrying values",
    "{items} inventories are stated at standard cost (approximating actual cost) under the {method} method, adjusted to net realizable value if necessary",
    "{items} are valued at purchase cost while manufactured inventories include labor and overhead allocated using the {method} method",
    "{items} inventory is written down to market value when estimated selling prices are less than cost",
    "As of {month} {end_day}, {year}, {company} maintained obsolescence reserves of {currency_code}{reserve} {money_unit} against total inventories of {currency_code}{amount} {money_unit}",
    "{items} inventory include {items} valued at the lower of cost (determined by {method}) or net realizable value",
    "{company} records provisions for excess and obsolete {items} inventories based on expected future demand, market conditions, and {items} life cycles",
]

inventory_methods = [
    "first-in, first-out (FIFO)",
    "last-in, first-out (LIFO)",
    "weighted-average cost",
    "specific identification",
    "standard cost",
    "moving average cost",
    "retail inventory method",
]

inventory_writedown_templates = [
    "During {year}, {company} recorded {items} inventory write-downs of {currency_code}{amount} {money_unit} due to obsolescence and excess quantities",
    "{items} inventory reserves increased by {currency_code}{amount} {money_unit} in {year} to reflect lower of cost or market adjustments",
    "{company} recognized {currency_code}{amount} {money_unit} in charges related to slow-moving and obsolete {items} inventory during {year}",
    "{items} inventory obsolescence charges totaled {currency_code}{amount} {money_unit} for the year ended {month} {end_day}, {year}",
    "As of {month} {end_day}, {year}, {company} maintained {items} reserves of {currency_code}{amount} {money_unit} for excess and obsolete inventories",
    "Write-downs of {currency_code}{amount} {money_unit} were recorded in {year} primarily related to discontinued product lines",
    "{company} recorded {currency_code}{amount} {money_unit} in inventory write-downs due to declining market demand during {year}",
    "Charges for inventory valuation adjustments were {currency_code}{amount} {money_unit} in {year}, compared to {currency_code}{prev_amount} {money_unit} in the prior year",
    "{company} recorded inventory write-downs associated with aging components and spare parts totaling {currency_code}{amount} {money_unit} during {year}",
    " {items} inventory reserves increased to {currency_code}{amount} {money_unit} at year-end {year}, reflecting adjustments for lower selling prices and product obsolescence",
    "Total charges of {currency_code}{amount} {money_unit} were recognized in cost of goods sold for inventory write-downs in {year}",
    "Inventory write-downs of {currency_code}{amount} {money_unit} were partially offset by recoveries of {currency_code}{prev_amount} {money_unit} related to previously reserved items",
    "{company} established new reserves of {currency_code}{amount} {money_unit} in {year} for excess quantities, reflecting updated demand forecasts",
]

# ============ PROPERTY, PLANT & EQUIPMENT ============

ppe_templates = [
    "Property, plant and equipment are stated at cost less accumulated depreciation, which is computed using the straight-line method over estimated useful lives",
    "Depreciation expense was {currency_code}{amount} {money_unit} for the year ended {month} {end_day}, {year}",
    "{company} capitalizes costs related to construction in progress and commences depreciation when assets are placed in service",
    "As of {month} {end_day}, {year}, property, plant and equipment, net totaled {currency_code}{amount} {money_unit}",
    "Repairs and maintenance costs are expensed as incurred, while major improvements are capitalized and depreciated over the remaining useful life",
    "Leasehold improvements are amortized over the shorter of the lease term or the estimated useful life of the asset",
    "Depreciation methods and useful lives are reviewed periodically to ensure they reflect current estimates of asset utility",
    "Gains or losses on the disposal of property, plant and equipment are recognized in earnings when assets are retired or sold",
    "Construction in progress primarily relates to {purpose} and is not depreciated until placed into service",
    "As of {month} {end_day}, {year}, accumulated depreciation was {currency_code}{amount} {money_unit}",
]


capex_templates = [
    "Capital expenditures during {year} were {currency_code}{amount} {money_unit}, primarily related to {purpose}",
    "{company} invested {currency_code}{amount} {money_unit} in {purpose} during {year}",
    "Cash outlays for property, plant and equipment totaled {currency_code}{amount} {money_unit} in {year}, focused on {purpose}",
    "Capital investments of {currency_code}{amount} {money_unit} were made during {year} to support {purpose}",
    "During {year}, {company} incurred capital expenditures of {currency_code}{amount} {money_unit}, reflecting continued investment in {purpose}",
    "Capex in {year} amounted to {currency_code}{amount} {money_unit}, directed primarily toward {purpose}",
    "{company} allocated {currency_code}{amount} {money_unit} to property and equipment purchases during {year}, with a focus on {purpose}",
    "Capital spending was {currency_code}{amount} {money_unit} in {year}, driven by {purpose}",
]

capex_purposes = [
    "manufacturing capacity expansion",
    "information technology infrastructure",
    "facility improvements and equipment upgrades",
    "research and development laboratories",
    "distribution center automation",
    "renewable energy and sustainability projects",
    "expansion of global office facilities",
    "enhancement of customer service centers",
    "data center construction and modernization",
    "supply chain and logistics optimization",
    "product development and testing facilities",
    "safety and regulatory compliance upgrades",
]

impairment_templates = [
    "{company} recorded an impairment charge of {currency_code}{amount} {money_unit} during {year} related to {asset_type}",
    "An impairment loss of {currency_code}{amount} {money_unit} was recognized in {year} for {asset_type} due to changes in market conditions",
    "During {quarter} quarter {year}, {company} identified indicators of impairment and recorded a {currency_code}{amount} {money_unit} charge for {asset_type}",
    "{company} recognized {currency_code}{amount} {money_unit} in impairment charges related to {asset_type} during {year}",
    "As a result of revised cash flow projections, {company} recorded {currency_code}{amount} {money_unit} of impairment charges for {asset_type} in {year}",
    "Impairment testing performed in {year} resulted in a {currency_code}{amount} {money_unit} write-down of {asset_type}",
    "A non-cash impairment charge of {currency_code}{amount} {money_unit} was recognized during {year} for {asset_type}",
    "Impairment charges of {currency_code}{amount} {money_unit} were recorded in {year} primarily related to {asset_type}",
    "{company} assessed recoverability of {asset_type} and recognized an impairment loss of {currency_code}{amount} {money_unit} in {year}",
    "During {year}, {company} recorded impairment losses totaling {currency_code}{amount} {money_unit}, including {asset_type}",
    "An interim impairment assessment conducted in {quarter} {year} resulted in a charge of {currency_code}{amount} {money_unit} for {asset_type}",
]

asset_types = [
    "long-lived assets in underperforming facilities",
    "certain manufacturing equipment",
    "goodwill related to a reporting unit",
    "intangible assets with finite lives",
    "property held for sale",
    "oil and gas properties",
    "construction in progress",
    "software development costs",
    "property and equipment",
    "qualifying assets",
    "indefinite-lived intangible assets",
    "leased right-of-use assets",
    "retail store assets in specific locations",
    "capitalized film and television production costs",
    "mining and exploration assets",
    "customer relationship intangibles",
    "brand and trademark assets",
    "renewable energy facilities",
]

# ============ LEASES ============

lease_templates = [
    "{company} leases office space, manufacturing facilities, and equipment under operating and finance leases with terms ranging from {min_term} to {max_term} years",
    "As of {month} {end_day}, {year}, {company} had operating lease right-of-use assets of {currency_code}{amount} {money_unit} and lease liabilities of {currency_code}{liability} {money_unit}",
    "{company} adopted ASC 842 effective {month} {adoption_year}, recognizing right-of-use assets and lease liabilities for operating leases",
    "Total lease expense for {year} was {currency_code}{amount} {money_unit}, including both operating and finance lease costs",
    "Lease liabilities are measured at the present value of future lease payments, discounted using {company}'s incremental borrowing rate",
    "Short-term leases and variable lease payments are excluded from right-of-use assets and liabilities under ASC 842",
    "{company} recognized {currency_code}{amount} {money_unit} of lease expense related to short-term and variable leases during {year}",
    "As of {month} {end_day}, {year}, finance lease assets totaled {currency_code}{amount} {money_unit}, included in property, plant and equipment",
    "Lease agreements do not contain significant residual value guarantees or restrictive covenants",
]


lease_commitment_templates = [
    "Future minimum lease payments under non-cancellable operating leases total {currency_code}{amount} {money_unit} as of {month} {end_day}, {year}",
    "The weighted-average remaining lease term for operating leases is {years} years as of {month} {end_day}, {year}",
    "The weighted-average discount rate used to measure lease liabilities was {rate}% as of {month} {end_day}, {year}",
    "Operating lease payments are expected to total {currency_code}{amount} {money_unit} over the next five years",
    "Maturities of lease liabilities are {currency_code}{amount} {money_unit} in {next_year}, {currency_code}{amount2} {money_unit} in {next2_year}, and {currency_code}{amount3} {money_unit} thereafter",
    "As of {month} {end_day}, {year}, undiscounted future lease payments totaled {currency_code}{amount} {money_unit}, with a present value of {currency_code}{pv_amount} {money_unit}",
    "Future finance lease obligations amounted to {currency_code}{amount} {money_unit} as of {month} {end_day}, {year}",
    "Lease commitments include renewal options reasonably certain to be exercised, totaling {currency_code}{amount} {money_unit}",
]

# ============ GOODWILL AND INTANGIBLES ============

goodwill_templates = [
    "Goodwill totaled {currency_code}{amount} {money_unit} as of {month} {end_day}, {year}, and is not amortized but tested for impairment annually",
    "{company} performs its annual goodwill impairment test in the {quarter} quarter of each year",
    "No goodwill impairment was recorded during {year} as the fair value of reporting units exceeded their carrying values",
    "Goodwill is allocated to reporting units and {verb} for impairment at least annually or when indicators of impairment exist",
]

intangible_templates = [
    "Intangible assets consist primarily of {intangible_types} and are amortized over their estimated useful lives",
    "Amortization expense for intangible assets was {currency_code}{amount} {money_unit} for the year ended {month} {end_day}, {year}",
    "As of {month} {end_day}, {year}, intangible assets, net of accumulated amortization, totaled {currency_code}{amount} {money_unit}",
    "The weighted-average remaining useful life of intangible assets is {years} years as of {month} {end_day}, {year}",
]

intangible_types = [
    "customer relationships, developed technology, and trade names",
    "patents, trademarks, and customer lists",
    "software, customer contracts, and non-compete agreements",
    "brand names, proprietary technology, and customer relationships",
]

# ============ DEBT AND CREDIT FACILITIES ============

debt_templates = [
    # General facilities and balances
    "{company} maintains a {currency_code}{amount} {money_unit} revolving credit facility that expires in {year}, with {currency_code}{outstanding} {money_unit} outstanding as of {month} {end_day}, {current_year}, with annual interest rate of {pct}%",
    "As of {month} {end_day}, {year}, {company} had total long-term debt of {currency_code}{amount} {money_unit}, consisting primarily of {debt_types}, with an average interest rate of {pct}% and {pct2}%, respectively",
    "Long-term debt, with an annual interest rate of {pct}% as of {month} {end_day}, {year} totaled {currency_code}{amount} {money_unit}, consisting of {debt_types}",
    "At year-end {year}, {company} reported total debt of {currency_code}{amount} {money_unit} with interest rates ranging from {pct}% to {pct2}%, including {debt_types}",
    "{company}'s outstanding borrowings under its revolving credit facility totaled {currency_code}{outstanding} {money_unit} with average interest rate of {pct}% to {pct2}% as of {month} {end_day}, {year}",
    "As of {month} {end_day}, {year}, there was {currency_code}{outstanding} {money_unit} outstanding on the {debt_type} and {currency_code}{outstanding} {money_unit} outstanding on {debt_types}",
    # Issuances and repayments
    "During {year}, {company} issued {currency_code}{amount} {money_unit} in {debt_types} with a maturity date of {maturity_year} and a weighted average interest rate of {pct}%",
    "In {year}, {company} completed a private placement of {currency_code}{amount} {money_unit} of {debt_types}, bearing interest at {pct}% per annum",
    "During {year}, {company} repaid {currency_code}{amount} {money_unit} of its outstanding {debt_type} prior to maturity",
    "{company} repaid {currency_code}{amount} {money_unit} of outstanding {debt_type} during {year} using cash from operations",
    "In {year}, {company} refinanced {currency_code}{amount} {money_unit} of existing {debt_type} at interest rate of {pct}%, extending the maturity to {maturity_year}",
    # Interest rate and maturity details
    "As of year-end {year}, {company} had total {debt_type} of {currency_code}{amount} {money_unit}, {currency_code}{amount2} {money_unit} of which was fixed rate debt with a weighted average interest rate of {pct}% to {pct2}%",
    "The weighted average interest rate on {company}'s {debt_type} was approximately {pct}% as of {month} {end_day}, {year}",
    "As of {month} {end_day}, {year}, {company}'s {debt_type} had a weighted average maturity of {years} years",
    "As of {month} {end_day}, {year}, {company}'s variable-rate borrowings bore interest at an average rate of {pct}%",
    "Interest expense related to {debt_type} for {year} was approximately {currency_code}{amount} {money_unit}",
    "At {month} {year}, {company} repaid {currency_code}{amount} {money_unit} of the {currency_code}{amount2} {money_unit} borrowed",
    # Other specialized cases
    "During {year}, {company} entered into a new {currency_code}{amount} {money_unit} {debt_type} with a maturity in {maturity_year} and annual interest rate of {pct}%",
    "Proceeds from the {debt_type} issuance were used to repay existing borrowings and for general corporate purposes",
    "In {year}, {company} retired {currency_code}{amount} {money_unit} of {debt_type} upon maturity",
    "At {month} {end_day}, {year}, unamortized debt issuance costs related to {debt_type} totaled {currency_code}{amount} {money_unit}",
    "The fair value of {company}'s {debt_type} was estimated at {currency_code}{amount2} {money_unit} as of {month} {end_day}, {year}",
]

debt_types_list = [
    # Common corporate instruments
    "senior unsecured notes and term loans",
    "convertible senior notes and revolving credit borrowings",
    "senior secured notes and equipment financing",
    "bonds and bank term loans",
    "fixed-rate debt",
    "floating-rate debt",
    "term loan B facility",
    "credit facility borrowings",
    "notes payable",
    "long-term loan agreement",
    "short-term loan",
    "long-term debt",
    "short-term debt",
    # Market rate–specific
    "LIBOR-based loans",
    "SOFR-based revolving loans",
    "Eurodollar borrowings",
    "variable-rate debt",
    # Specialized and legacy forms
    "bridge loans",
    "debentures",
    "subordinated notes",
    "commercial paper",
    "secured term loans",
    "lease financing obligations",
    "private placement notes",
]


debt_covenant_templates = [
    "The credit agreement contains customary affirmative and negative covenants, including financial covenants related to leverage ratios and interest coverage",
    "As of {month} {end_day}, {year}, {company} was in compliance with all debt covenants",
    "The revolving credit facility requires maintenance of a maximum leverage ratio of {ratio}:1 and minimum interest coverage ratio of {coverage}:1",
    "Debt agreements contain restrictions on dividends, additional indebtedness, and asset sales, subject to certain exceptions",
    # Covenant and credit facility context
    "The revolving credit facility contains customary financial covenants, including maintaining a maximum leverage ratio and minimum interest coverage ratio",
    "{company} was in compliance with all debt covenants as of {month} {end_day}, {year}",
    "{company}'s credit agreements require maintenance of specified leverage and coverage ratios, which {company} met as of {month} {end_day}, {year}",
]

# ============ INCOME TAXES ============

tax_templates = [
    "The provision for income taxes was {currency_code}{amount} {money_unit} for {year}, resulting in an effective tax rate of {rate}%",
    "The effective tax rate for {year} was {rate}%, compared to {prev_rate}% in the prior year",
    "Deferred tax assets as of {month} {end_day}, {year} totaled {currency_code}{amount} {money_unit}, primarily related to {sources}",
    "{company} has net operating loss carryforwards of {currency_code}{amount} {money_unit} that expire between {start_year} and {end_year}",
]

tax_sources = [
    "net operating losses, tax credit carryforwards, and accrued expenses",
    "stock-based compensation, depreciation differences, and reserves",
    "employee benefits, loss carryforwards, and capitalized research costs",
    "bad debt reserves, inventory reserves, and accrued liabilities",
]

uncertain_tax_templates = [
    "{company} has {currency_code}{amount} {money_unit} in unrecognized tax benefits as of {month} {end_day}, {year}",
    "A reconciliation of the beginning and ending amount of unrecognized tax benefits showed an increase of {currency_code}{amount} {money_unit} during {year}",
    "{company} recognizes interest and penalties related to uncertain tax positions in income tax expense",
    "It is reasonably possible that {currency_code}{amount} {money_unit} of unrecognized tax benefits could be recognized within the next twelve months",
]

# ============ STOCK-BASED COMPENSATION ============

stock_comp_templates = [
    "Stock-based compensation expense was {currency_code}{amount} {money_unit} for the year ended {month} {end_day}, {year}",
    "{company} grants stock options, restricted stock units, and performance share units to employees and directors",
    "During {year}, {company} granted {shares} stock options with a weighted-average exercise price of {currency_code}{price} per share",
    "Total unrecognized compensation cost related to unvested awards was {currency_code}{amount} {money_unit} as of {month} {end_day}, {year}",
]

stock_comp_valuation_templates = [
    "The fair value of stock options is estimated using the  with assumptions for volatility, risk-free interest rate, and expected term",
    "{company} uses a {model} to value performance share units with market conditions",
    "Restricted stock units are valued based on the closing stock price on the grant date",
    "The weighted-average grant-date fair value of options granted during {year} was {currency_code}{amount} per share",
]

# ============ PENSION AND POSTRETIREMENT BENEFITS ============

pension_templates = [
    "{company} sponsors defined benefit pension plans covering certain employees, with plan assets of {currency_code}{assets} {money_unit} and projected benefit obligations of {currency_code}{obligations} {money_unit} as of {month} {end_day}, {year}",
    "Pension expense for {year} was {currency_code}{amount} {money_unit}, including service cost, interest cost, and expected return on plan assets",
    "The funded status of {company}'s pension plans resulted in a net liability of {currency_code}{amount} {money_unit} as of {month} {end_day}, {year}",
    "During {year}, {company} contributed {currency_code}{amount} {money_unit} to its defined benefit pension plans",
]

opeb_templates = [
    "{company} provides postretirement medical and life insurance benefits to eligible retirees",
    "The accumulated postretirement benefit obligation was {currency_code}{amount} {money_unit} as of {month} {end_day}, {year}",
    "Net periodic postretirement benefit cost for {year} totaled {currency_code}{amount} {money_unit}",
    "{company}'s postretirement benefit plans are unfunded, with liabilities recorded in other long-term liabilities",
]

# ============ COMMITMENTS AND CONTINGENCIES ============

purchase_commitment_templates = [
    "{company} has purchase commitments with suppliers totaling approximately {currency_code}{amount} {money_unit} as of {month} {end_day}, {year}",
    "Outstanding purchase orders and contractual obligations for inventory and capital expenditures totaled {currency_code}{amount} {money_unit} at year-end {year}",
    "{company} is obligated under various supply agreements to purchase minimum quantities totaling {currency_code}{amount} {money_unit} over the next {years} years",
    "As of {month} {end_day}, {year}, {company} had non-cancellable purchase commitments of {currency_code}{amount} {money_unit}",
]

guarantee_templates = [
    "{company} has provided guarantees and indemnifications related to {guarantee_type} with a maximum potential exposure of {currency_code}{amount} {money_unit}",
    "Product warranty obligations totaled {currency_code}{amount} {money_unit} as of {month} {end_day}, {year}",
    "{company} accrues warranty costs based on historical claims experience and specific identified warranty issues",
    "Warranty expense for {year} was {currency_code}{amount} {money_unit}, with payments of {currency_code}{payments} {money_unit}",
]

guarantee_types = [
    "product performance, lease obligations, and customer financing",
    "residual value guarantees and performance bonds",
    "environmental remediation and divested business obligations",
    "intellectual property indemnifications and debt guarantees",
]

# ============ RESTRUCTURING ============

restructuring_templates = [
    "During {year}, {company} initiated a restructuring plan to {purpose}, resulting in charges of {currency_code}{amount} {money_unit}",
    "Restructuring charges of {currency_code}{amount} {money_unit} were recorded in {year}, primarily related to {expense_type}",
    "{company} announced a cost reduction initiative in {month} {year} expected to generate annual savings of {currency_code}{amount} {money_unit}",
    "As of {month} {end_day}, {year}, the remaining restructuring liability was {currency_code}{amount} {money_unit}",
]

restructuring_purposes = [
    "streamline operations and reduce costs",
    "consolidate manufacturing facilities",
    "optimize the organizational structure",
    "align resources with strategic priorities",
]

restructuring_expense_types = [
    "employee severance and benefits",
    "facility closure costs and asset impairments",
    "contract termination costs and severance",
    "workforce reductions and lease terminations",
]

# ============ ACQUISITIONS (NON-DERIVATIVE ASPECTS) ============

acquisition_templates = [
    "In {month} {year}, {company} acquired {target} for total consideration of {currency_code}{amount} {money_unit} in cash",
    "{company} completed the acquisition of {target} during {year} for {currency_code}{amount} {money_unit}, which was funded through {funding}",
    "During {year}, {company} acquired {target} to expand its {purpose}",
    "The acquisition of {target} in {year} resulted in {currency_code}{goodwill} {money_unit} of goodwill and {currency_code}{intangibles} {money_unit} of identifiable intangible assets",
]

acquisition_purposes = [
    "product portfolio and market presence",
    "technology capabilities and customer base",
    "geographic reach and distribution channels",
    "manufacturing capacity and operational efficiency",
]

acquisition_funding = [
    "cash on hand and borrowings under the credit facility",
    "available cash reserves",
    "a combination of cash and debt financing",
    "existing liquidity",
]
# ============ STOCK ==========================
# Stock issuance for debt costs
stock_debt_issuance_templates = [
    "In conjunction with its {month} {year} {financing_type}, {company} issued at closing {shares1} shares of common stock (valued at {currency_code}{value1}) and upon extension of the maturity date {shares2} shares of common stock (valued at {currency_code}{value2}), which were recorded as debt issuance costs",
    "{company} issued {shares} shares of common stock valued at {currency_code}{value} in connection with {financing_type} during {year}, recorded as debt issuance costs",
    "During {year}, {company} issued {shares} shares of common stock (valued at {currency_code}{value}) as part of {financing_type}, with the value recorded as a debt issue cost",
    "In {month} {year}, {company} completed {financing_type} and issued {shares} shares of common stock valued at {currency_code}{value} as consideration, which was capitalized as debt issuance costs",
    "Upon closing of the {financing_type} in {month} {year}, {shares} shares were issued as transaction costs and recorded in additional paid-in capital",
    "{company} capitalized {shares} shares of common stock valued at {currency_code}{value} as debt issuance costs related to the {financing_type}",
]

# Registration statement and resale concerns
registration_statement_templates = [
    "Such sales also may inhibit our ability to obtain future equity related financing on acceptable terms. In {month} {year}, {company} will file a registration statement to register the shares of common stock issuable upon conversion of the convertible notes and upon exercise of the warrants to permit the resale of these shares of common stock",
    "{company} filed a registration statement on Form S-3 in {month} {year} to register {shares} shares of common stock underlying convertible securities for resale by holders",
    "In {month} {year}, {company} registered {shares} shares of common stock issuable upon conversion of notes and exercise of warrants pursuant to registration rights agreements",
    "The registration statement filed in {year} covers {shares} shares issuable upon conversion and exercise of outstanding securities, permitting resale by security holders",
    "{company} is obligated to file a registration statement within {days} days following {month} {year} covering shares issuable upon conversion of notes and warrants",
]

# Market impact of registered shares
market_impact_templates = [
    "Upon the effective date of the registration statement, the holders of the convertible notes may sell all or a portion of the shares of common stock they receive by conversion of the notes and warrants directly in the market or through one or more underwriters, broker-dealers, or agents",
    "A large number of shares of common stock would be available for resale by the note holders upon effectiveness of the registration statement, which could depress the market price of {company}'s common stock",
    "The resale of {shares} shares registered under the registration statement could adversely affect the market price of {company}'s common stock",
    "Upon effectiveness of the registration statement, holders may resell {shares} shares, potentially causing downward pressure on the stock price",
    "The registration of {shares} shares for resale by holders could result in substantial dilution and negatively impact the trading price of the common stock",
    "Sales of substantial amounts of common stock in the public market following effectiveness of the registration statement could adversely affect prevailing market prices",
]

# Warrant and option adjustment templates
warrant_adjustment_templates = [
    "The original exercisable shares of {shares} and exercise price of {currency_code}{price} was adjusted to {shares1} and {currency_code}{price2}, respectively, to account for the {month} {year} Private Placement and the Amendment Agreement",
    "Anti-dilution provisions resulted in adjustment of warrant exercise price from {currency_code}{price} to {currency_code}{price2} and shares from {shares} to {shares1} following the {year} financing",
    "Pursuant to anti-dilution protection, {shares} warrants at {currency_code}{price} per share were adjusted to {shares1} warrants at {currency_code}{price2} per share effective {month} {year}",
    "The {month} {year} down-round financing triggered adjustments to outstanding warrants, changing the exercise price from {currency_code}{price} to {currency_code}{price2}",
    "Weighted-average anti-dilution adjustments modified warrant terms to {shares1} shares at {currency_code}{price2} from {shares} shares at {currency_code}{price}",
]

# Fair value measurement templates
fair_value_snapshot_templates = [
    "The fair value of the shares are {currency_code}{value1} and {currency_code}{value2}, in {month} {year}",
    "As of {month} {end_day}, {year}, the fair value of shares underlying convertible instruments was {currency_code}{value}",
    "Fair value of shares reserved for issuance totaled {currency_code}{value} at {month} {end_day}, {year}",
    "The {shares} shares reserved for conversion and exercise had an aggregate fair value of {currency_code}{value} as of {month} {year}",
    "{company} valued the {shares} shares underlying convertible securities at {currency_code}{value} based on the closing stock price on {month} {end_day}, {year}",
]

# Share reservation templates
share_reservation_templates = [
    "In addition, {company} has reserved {shares1} shares of the common stock for issuance upon the exercise of outstanding warrants and {shares2} shares of the common stock for issuance upon the exercise of stock options",
    "{company} has reserved a total of {shares} shares for issuance under equity incentive plans and upon exercise of warrants and convertible securities",
    "As of {month} {end_day}, {year}, {shares1} shares were reserved for warrant exercises and {shares2} shares for option exercises under equity plans",
    "{company} maintains a reserve of {shares} shares for potential issuance upon conversion, exercise, or settlement of outstanding equity instruments",
    "{shares} shares of authorized common stock are reserved for issuance pursuant to outstanding equity awards, warrants, and convertible instruments as of {year}",
]

# Outstanding options disclosure
outstanding_options_templates = [
    "As of {month} {end_day}, {year}, there are {shares} issued and outstanding options to purchase common stock. To the extent that outstanding warrants and options are exercised, the percentage ownership of common stock of {company}'s stockholders will be diluted",
    "Outstanding stock options totaled {shares} as of {month} {end_day}, {year}, with a weighted-average exercise price of {currency_code}{price}",
    "As of {year} year-end, {shares} stock options were outstanding and exercisable, representing potential dilution to existing shareholders",
    "{company} had {shares} options outstanding at {month} {end_day}, {year}, of which {shares1} were vested and exercisable",
    "Stock options to purchase {shares} shares were outstanding as of {month} {end_day}, {year}, with expiration dates ranging from {year} to {end_year}",
]

# Dilution concern templates
dilution_concern_templates = [
    "In the event of the exercise of a substantial number of warrants and options, within a reasonably short period of time after the right to exercise commences, the resulting increase in the amount of the common stock in the trading market could substantially adversely affect the market price of the common stock or {company}'s ability to raise money through the sale of equity securities",
    "Exercise of outstanding warrants and options representing {shares} shares could result in significant dilution to existing stockholders and negatively impact the stock price",
    "The potential issuance of {shares} shares upon exercise of warrants and conversion of notes could dilute current shareholders by approximately {pct}%",
    "Substantial dilution may occur if holders exercise warrants for {shares} shares and convert notes into {shares1} shares of common stock",
    "Current stockholders face potential dilution from {shares} shares underlying warrants, options, and convertible securities as of {month} {end_day}, {year}",
    "If all outstanding warrants and options were exercised, {shares} additional shares would be issued, representing {pct}% dilution to current shareholders",
]

# Capital raising impact templates
capital_raising_impact_templates = [
    "The overhang of {shares} shares underlying convertible securities may impair {company}'s ability to raise capital through future equity offerings",
    "Potential dilution from outstanding warrants and options could adversely affect the terms of future financings or {company}'s ability to access capital markets",
    "The existence of {shares} shares reserved for issuance may make it more difficult for {company} to obtain financing on favorable terms",
    "Future equity financings may be more difficult to complete due to the dilutive effect of {shares} shares underlying outstanding securities",
]

warrant_debt_issuance_templates = [
    "In the same financing, {company} issued warrants to purchase {shares1} shares of its common stock (valued at {currency_code}{value1}) and warrants to purchase {shares2} shares of its common stock (valued at {currency_code}{value2}) related to extensions of the maturity dates",
    "{company} issued warrants to purchase {shares} shares of common stock (valued at {currency_code}{value}) in conjunction with {financing_type} in {month} {year}",
    "Warrants to purchase {shares} shares of common stock were issued as part of the financing arrangement, valued at {currency_code}{value} and recorded as debt issuance costs",
    "In connection with {financing_type}, {company} granted warrants for {shares} shares valued at {currency_code}{value}, with the value recorded as debt issue costs",
    "Additional warrants to purchase {shares} shares of {company} common stock were issued on {month} {year} in consideration for the extension to that date",
    "In connection with the extension to {month} {year}, {company} offered two alternatives of consideration. Holders of {shares1} common stock of the notes elected to reduce the exercise price of their warrants, or to to receive additional warrants to purchase {shares2} shares of common stock",
    "{company} reduced the exercise price by {currency_code}{value1} per share for all warrants issued in connection with the issuance or extensions of the notes",
    "In consideration of this extension, {company} issued {shares} shares of common stock at a price of {value} per share and warrants to purchase {shares1} shares of common stock at a price to be determined in the future, between {currency_code}{value1} and {currency_code}{value2} per share, on or before {month} {year}",
    "Also in {month} {year}, {company} exchanged a {currency_code}{value} note payable for units of common stock and warrants to purchase common stock at a price of {currency_code}{value1} per unit",
    "In addition, the financial advisor on the debt offering received an additional {shares} warrants with the {month} offering for a total of approximately {value}",
    "If all of the warrants are exercised and the debt is fully converted to {company} stock, current stockholders will experience a significant dilution in their ownership of {company} ",
    "Based on the terms of the debt offering both the notes and warrants are subject to anti-dilution provisions and can potentially become more dilutive to {company} stock. Further dilution may occur in the event of a default {currency_code}{value} payable",
]

warrant_amortization_templates = [
    "The value of the warrants related to these financings was recorded as debt issue costs and the amortization of such warrant costs was included in interest expense, which was capitalized as a cost of {asset_type}",
    "Warrant costs totaling {currency_code}{value} were recorded as debt issuance costs and amortized to interest expense over the term of the debt",
    "{company} amortizes debt issuance costs, including the value of warrants issued, to interest expense using the effective interest method",
    "Amortization of warrant-related debt issuance costs totaled {currency_code}{value} for the year ended {month} {end_day}, {year}",
    "The relative fair value of the warrants was recorded as a debt discount and is being amortized to non-cash interest expense over the life of the {debt_types_list} using the effective interest method",
    "The initial value of the warrants was recorded in Additional Paid-In Capital and, as they are classified as equity, they are not subsequently remeasured",
    "Amortization of the debt discount related to the warrants issued with the {debt_types_list} totaled {currency_code}{value} and {currency_code}{value2} for the years ended {year} and {prev_year}, respectively",
    "The warrants are exercisable for a term of five years at an exercise price of {currency_code}{price} per share, subject to anti-dilution provisions similar to the provisions set forth in the Notes and expire on {month} {year}",
]


non_cash_settlement_templates = [
    "In {year}, {company} issued {shares} shares of common stock (valued at {currency_code}{value}) in settlement of invoices for previously rendered {service_type}",
    "{company} settled outstanding {service_type} payables totaling {currency_code}{value} through the issuance of {shares} shares of common stock during {year}",
    "During {year}, {company} issued {shares} shares valued at {currency_code}{value} to settle {service_type} obligations",
    "{shares} shares of common stock were issued in {month} {year} to satisfy {currency_code}{value} in outstanding {service_type} fees",
]


financing_types = [
    "Bridge Financing",
    "short-term bridge financing",
    "mezzanine financing",
    "subordinated debt financing",
    "convertible debt financing",
    "senior secured financing",
]

service_types = [
    "legal services",
    "consulting services",
    "professional services",
    "advisory services",
    "accounting and audit services",
]

# Balance sheet changes templates
balance_sheet_change_templates = [
    "Accounts payable increased by {currency_code}{amount} {money_unit} to {currency_code}{ending} {money_unit} as of {month} {end_day}, {year}, primarily due to {reason}",
    "Accounts receivable decreased {currency_code}{amount} {money_unit} during {year}, reflecting {reason}",
    "Inventories increased {currency_code}{amount} {money_unit} from {month} {end_day}, {prev_year} to {month} {end_day}, {year} due to {reason}",
    "Accrued liabilities increased by {currency_code}{amount} {money_unit} year-over-year, primarily attributable to {reason}",
    "Prepaid expenses and other current assets decreased {currency_code}{amount} {money_unit} as of {month} {end_day}, {year} compared to the prior year",
]

working_capital_templates = [
    "Working capital was {currency_code}{amount} {money_unit} at {month} {end_day}, {year}, compared to {currency_code}{prev_amount} {money_unit} at {month} {end_day}, {prev_year}",
    "Changes in operating assets and liabilities resulted in a {currency_code}{direction} of {currency_code}{amount} {money_unit} in cash from operations during {year}",
    "{company}'s working capital increased by {currency_code}{amount} {money_unit} during {year}, driven primarily by {reason}",
    "Net changes in operating assets and liabilities used {currency_code}{amount} {money_unit} of cash during {year}",
]

ar_templates = [
    "Trade accounts receivable totaled {currency_code}{amount} {money_unit} at {month} {end_day}, {year}, representing {days} days sales outstanding",
    "The allowance for doubtful accounts was {currency_code}{amount} {money_unit} as of {month} {end_day}, {year}, compared to {currency_code}{prev_amount} {money_unit} in the prior year",
    "Days sales outstanding decreased from {prev_days} days to {days} days during {year}",
    "{company} recorded bad debt expense of {currency_code}{amount} {money_unit} during {year}",
    "Accounts receivable, net of allowances, increased {currency_code}{amount} {money_unit} to {currency_code}{ending} {money_unit} at year-end {year}",
]

ap_templates = [
    "Accounts payable increased {currency_code}{amount} {money_unit} from the prior year, reflecting {reason}",
    "{company} extended payment terms with certain vendors during {year}, resulting in an increase in accounts payable of {currency_code}{amount} {money_unit}",
    "Accounts payable was {currency_code}{amount} {money_unit} at {month} {end_day}, {year}, down from {currency_code}{prev_amount} {money_unit} at {month} {end_day}, {prev_year}",
    "Days payable outstanding increased to {days} days at year-end {year} from {prev_days} days in the prior year",
    "Changes in accounts payable provided {currency_code}{amount} {money_unit} of cash during {year}",
]

accrued_liabilities_templates = [
    "Accrued compensation increased by {currency_code}{amount} {money_unit} at {month} {end_day}, {year} due to {reason}",
    "Accrued expenses totaled {currency_code}{amount} {money_unit} at year-end {year}, an increase of {currency_code}{change} {money_unit} from the prior year",
    "The increase in accrued liabilities of {currency_code}{amount} {money_unit} was primarily related to {reason}",
    "Other accrued liabilities decreased {currency_code}{amount} {money_unit} during {year}, mainly due to {reason}",
]

other_current_assets_templates = [
    "Other current assets increased {currency_code}{amount} {money_unit} to {currency_code}{ending} {money_unit} at {month} {end_day}, {year}, primarily due to {reason}",
    "Prepaid expenses decreased by {currency_code}{amount} {money_unit} during {year}",
    "Other receivables totaled {currency_code}{amount} {money_unit} at year-end {year}",
    "Current assets, excluding cash, increased {currency_code}{amount} {money_unit} year-over-year",
]

other_liabilities_templates = [
    "Other long-term liabilities increased by {currency_code}{amount} {money_unit} during {year}, primarily related to {reason}",
    "{company}'s current liabilities totaled {currency_code}{amount} {money_unit} at {month} {end_day}, {year}",
    "Total liabilities increased from {currency_code}{prev_amount} {money_unit} to {currency_code}{amount} {money_unit} during {year}",
    "Non-current liabilities decreased {currency_code}{amount} {money_unit} to {currency_code}{ending} {money_unit} at year-end {year}",
]

retained_earnings_templates = [
    "Retained earnings increased by {currency_code}{amount} {money_unit} during {year}, reflecting net income of {currency_code}{ni} {money_unit} less dividends of {currency_code}{div} {money_unit}",
    "Accumulated deficit was {currency_code}{amount} {money_unit} at {month} {end_day}, {year}",
    "{company} reported a net loss of {currency_code}{amount} {money_unit} for {year}, increasing accumulated deficit to {currency_code}{ending} {money_unit}",
    "Retained earnings totaled {currency_code}{amount} {money_unit} at year-end {year}",
]

stockholders_equity_templates = [
    "Total stockholders' equity increased {currency_code}{amount} {money_unit} to {currency_code}{ending} {money_unit} at {month} {end_day}, {year}",
    "Stockholders' equity was {currency_code}{amount} {money_unit} at {month} {end_day}, {year}, compared to {currency_code}{prev_amount} {money_unit} at {month} {end_day}, {prev_year}",
    "The increase in stockholders' equity of {currency_code}{amount} {money_unit} was primarily due to {reason}",
    "Total equity increased by {currency_code}{amount} {money_unit} during {year}",
]

cash_flow_statement_templates = [
    "Cash used in operating activities was {currency_code}{amount} {money_unit} for the year ended {month} {end_day}, {year}",
    "Net cash provided by operating activities totaled {currency_code}{amount} {money_unit} in {year}, compared to {currency_code}{prev_amount} {money_unit} in {prev_year}",
    "Cash flows from investing activities used {currency_code}{amount} {money_unit} during {year}, primarily for {reason}",
    "{company} generated {currency_code}{amount} {money_unit} in cash from operations during {year}",
    "Free cash flow was {currency_code}{amount} {money_unit} for {year}, defined as cash from operations less capital expenditures",
]

balance_sheet_reasons = [
    "timing of vendor payments",
    "increased sales volume",
    "seasonal working capital requirements",
    "timing of collections from customers",
    "inventory build-up to support growth",
    "payment of annual bonuses",
    "timing of payroll and tax payments",
    "increased business activity",
    "changes in payment terms",
]

accrued_reasons = [
    "annual incentive compensation accruals",
    "timing of payroll payments",
    "increased headcount",
    "accrual of performance bonuses",
    "timing of tax payments",
    "warranty accruals",
    "restructuring accruals",
]

other_asset_reasons = [
    "prepaid insurance and maintenance contracts",
    "deposits with vendors",
    "income tax refunds receivable",
    "prepaid software licenses",
    "advances to suppliers",
]

liability_reasons = [
    "deferred compensation arrangements",
    "uncertain tax positions",
    "environmental remediation obligations",
    "asset retirement obligations",
    "long-term incentive plan accruals",
]

equity_reasons = [
    "net income and stock issuances",
    "net income partially offset by dividends paid",
    "the public offering completed in {month} {year}",
    "net loss for the year",
    "retention of earnings",
]
# Add these template arrays after the stock_comp_valuation_templates (around line 240)

# CEO and executive compensation templates
ceo_compensation_templates = [
    "{company}'s Chief Executive Officer received total compensation of {currency_code}{amount} {money_unit} for {year}, consisting of {currency_code}{salary} {money_unit} in base salary, {currency_code}{bonus} {money_unit} in cash bonuses, and {currency_code}{equity} {money_unit} in equity awards",
    "For the year ended {month} {end_day}, {year}, the CEO's compensation package totaled {currency_code}{amount} {money_unit}, including base salary of {currency_code}{salary} {money_unit} and performance-based incentives of {currency_code}{bonus} {money_unit}",
    "Total compensation for the Chief Executive Officer was {currency_code}{amount} {money_unit} in {year}, compared to {currency_code}{prev_amount} {money_unit} in {prev_year}",
    "The CEO received {currency_code}{amount} {money_unit} in total compensation during {year}, comprised of salary, annual incentive compensation, and long-term equity grants",
]

executive_compensation_templates = [
    "Total compensation for {company}'s five highest-paid executives was {currency_code}{amount} {money_unit} for {year}",
    "The named executive officers received aggregate compensation of {currency_code}{amount} {money_unit} in {year}, including {currency_code}{equity} {money_unit} in stock-based awards",
    "Compensation for senior management totaled {currency_code}{amount} {money_unit} during {year}, representing {increase_decrease} of {change}% from the prior year",
    "Executive compensation expense, including salaries, bonuses, and equity awards, totaled {currency_code}{amount} {money_unit} for the year ended {month} {end_day}, {year}",
]

equity_grant_templates = [
    "In {month} {year}, the CEO was granted {shares} restricted stock units with a grant-date fair value of {currency_code}{amount} {money_unit}, vesting over {years} years",
    "{company} granted the Chief Executive Officer {shares} stock options in {year} with an exercise price of {currency_code}{price} per share and a ten-year term",
    "Performance share units representing {shares} shares at target were awarded to the CEO in {year}, with vesting contingent upon achievement of {metric}",
    "The CEO received a grant of {shares} restricted shares valued at {currency_code}{amount} {money_unit} during {year}, subject to {vesting_period} vesting",
]

performance_metrics = [
    "revenue growth and earnings per share targets",
    "total shareholder return relative to peer companies",
    "operating margin and return on invested capital goals",
    "strategic objectives and financial performance targets",
    "revenue, EBITDA, and market share milestones",
]

vesting_periods = [
    "three-year cliff",
    "four-year ratable",
    "three-year graded",
    "performance-based",
    "time-based annual",
]

severance_templates = [
    "{company} maintains change-in-control agreements with executive officers providing for severance payments equal to {multiple} times base salary and target bonus upon qualifying termination",
    "Under the CEO's employment agreement, the executive is entitled to severance of {currency_code}{amount} {money_unit} upon termination without cause",
    "Change-in-control provisions in executive employment agreements provide for accelerated vesting of equity awards and cash severance payments",
    "{company}'s severance arrangements with named executive officers could result in payments totaling {currency_code}{amount} {money_unit} upon a change in control",
]

employment_agreement_templates = [
    "{company} entered into an employment agreement with its Chief Executive Officer in {month} {year} providing for an annual base salary of {currency_code}{salary} {money_unit} and target annual bonus of {bonus_pct}% of salary",
    "The CEO's employment agreement, effective {month} {year}, includes a base salary of {currency_code}{salary} {money_unit} with annual merit increase eligibility and participation in long-term incentive programs",
    "Under the terms of the CEO employment agreement, the executive receives an annual base salary of {currency_code}{salary} {money_unit}, subject to annual review by the Board of Trustees",
    "The employment agreement with the Chief Executive Officer provides for base compensation of {currency_code}{salary} {money_unit} and eligibility for annual performance bonuses up to {bonus_pct}% of base salary",
]

compensation_committee_templates = [
    "The Compensation Committee of the Board of Directors reviews and approves all executive compensation, including salary, bonuses, and equity grants",
    "Executive compensation decisions are made by the Compensation Committee based on peer group benchmarking and company performance",
    "The Compensation Committee engaged {consultant} as its independent compensation consultant to advise on executive pay practices",
    "Annual executive compensation is determined by the Compensation Committee after considering financial performance, individual contributions, and market data",
]

say_on_pay_templates = [
    "At the {year} annual meeting, shareholders approved {company}'s executive compensation program with {pct}% support",
    "{company}'s say-on-pay proposal received {pct}% approval from shareholders at the annual meeting held in {month} {year}",
    "Shareholders voted to approve executive compensation on an advisory basis, with {pct}% of votes cast in favor",
    "The advisory vote on executive compensation was approved by {pct}% of shares voted at the {year} annual meeting",
]

deferred_comp_templates = [
    "Certain executives participate in a non-qualified deferred compensation plan allowing deferral of up to {pct}% of base salary and {bonus_pct}% of bonuses",
    "{company} maintains a deferred compensation plan for executives with a total liability of {currency_code}{amount} {money_unit} as of {month} {end_day}, {year}",
    "Executive officers may elect to defer receipt of cash bonuses and equity awards under {company}'s non-qualified deferred compensation plan",
    "Deferred compensation obligations to executives totaled {currency_code}{amount} {money_unit} at year-end {year}, primarily invested in mutual fund equivalents",
]

perquisites_templates = [
    "Perquisites provided to executive officers include car allowances, financial planning services, and executive health screenings, totaling {currency_code}{amount} for the CEO in {year}",
    "The CEO received perquisites valued at {currency_code}{amount} during {year}, consisting primarily of {perq_type}",
    "Executive perquisites are limited and totaled {currency_code}{amount} for all named executive officers in aggregate for {year}",
    "{company} provides minimal perquisites to executives, with the CEO receiving {currency_code}{amount} in {year} for {perq_type}",
]

perq_types = [
    "security services and travel expenses",
    "automobile allowance and financial planning",
    "club memberships and travel-related expenses",
    "tax preparation and financial advisory services",
    "company aircraft usage for business travel",
]

clawback_templates = [
    "{company} has adopted a clawback policy allowing recovery of incentive compensation in the event of a financial restatement",
    "Executive compensation is subject to recoupment under {company}'s clawback policy in cases of misconduct or financial restatement",
    "The Board may require reimbursement of performance-based compensation under the clawback policy if performance goals are not actually achieved",
    "Incentive compensation paid to executives is subject to clawback provisions as required by the Dodd-Frank Act and SEC regulations",
]
# ========== MARKET PRICES AND TRADING ==========
stock_price_templates = [
    '{company} \'s common stock trades on the {exchange} under the ticker symbol "{ticker}"',
    "Shares of common stock closed at {currency_code}{price} on {month} {end_day}, {year}, compared to {currency_code}{prev_price} at {month} {end_day}, {prev_year}",
    "{company}'s stock price ranged from a low of {currency_code}{low} to a high of {currency_code}{high} during {year}",
    "Average daily trading volume was approximately {volume} shares during {year}",
    "{company}'s market capitalization was approximately {currency_code}{market_cap} {money_unit} as of {month} {end_day}, {year}",
    "Shares outstanding totaled {shares} as of {month} {end_day}, {year}",
    "The closing stock price on {month} {end_day}, {year} represented a {direction} of {pct}% from the prior year-end closing price",
]

exchanges = [
    "New York Stock Exchange",
    "NASDAQ Global Select Market",
    "NASDAQ Capital Market",
    "NYSE American",
    "London Stock Exchange",
]


trading_volume_templates = [
    "During {year}, approximately {volume} shares were traded on public exchanges",
    "{company}'s shares experienced {volatility} trading activity during {year}",
    "Average daily trading volume increased {pct}% in {year} compared to {prev_year}",
    "Trading liquidity {improved_decreased} during {year}, with average daily volume of {volume} shares",
]

volatility_levels = ["elevated", "moderate", "reduced", "increased", "stable"]

# ========== ABOUT {company} / BUSINESS DESCRIPTION ==========
company_description_templates = [
    "{company} is a {industry} company that {business_activity}",
    "{company} operates in the {industry} sector, providing {products_services} to customers in {geography}",
    "{company} was founded in {founding_year} and is headquartered in {city}, {state}",
    "{company} is a leading provider of {products_services} serving the {market_segment} market",
    "{company}'s principal business activities include {activities}",
    "{company} employs approximately {employees} people across {locations} locations worldwide as of {month} {end_day}, {year}",
    "{company} operates through {segments} reportable segments: {segment_names}",
    "{company}'s mission is to {mission_statement}",
]

industries = [
    "technology",
    "healthcare",
    "manufacturing",
    "consumer goods",
    "financial services",
    "biotechnology",
    "telecommunications",
    "energy",
    "retail",
    "industrial",
]

business_activities = [
    "develops, manufactures, and sells innovative products",
    "provides technology solutions and services to enterprise customers",
    "manufactures and distributes consumer products globally",
    "delivers healthcare services and medical devices",
    "operates a diversified portfolio of businesses",
]

geographies = [
    "North America, Europe, and Asia",
    "over 50 countries worldwide",
    "the United States and international markets",
    "global markets",
    "developed and emerging markets",
]

cities = [
    "San Francisco",
    "New York",
    "Boston",
    "Chicago",
    "Austin",
    "Seattle",
    "Atlanta",
]
states = [
    "California",
    "New York",
    "Massachusetts",
    "Illinois",
    "Texas",
    "Washington",
    "Georgia",
]

segment_examples = [
    "Commercial, Consumer, and International",
    "Products, Services, and Solutions",
    "Domestic and International Operations",
    "Technology, Healthcare, and Industrial",
]

# ========== HEDGE FUNDS AND INSTITUTIONAL OWNERSHIP ==========
institutional_ownership_templates = [
    "As of {month} {end_day}, {year}, institutional investors held approximately {pct}% of {company}'s outstanding shares",
    "{fund_name} reported a {pct}% ownership stake in {company} as of {month} {end_day}, {year}",
    "{company}'s largest shareholders include {fund_name} ({pct}%), {fund_name2} ({pct2}%), and other institutional investors",
    "Beneficial ownership by institutional investors increased to {pct}% as of {month} {end_day}, {year}",
    "Hedge funds and asset managers collectively own approximately {pct}% of outstanding common stock",
    "{fund_name} disclosed a {pct}% position in {company} in its {form} filing dated {month} {year}",
    "Institutional ownership decreased from {prev_pct}% to {pct}% during {year}",
    "{company}'s top ten institutional shareholders hold approximately {pct}% of outstanding shares",
]


sec_forms = ["Schedule 13G", "Schedule 13D", "Form 13F"]

insider_ownership_templates = [
    "Directors and executive officers collectively beneficially own approximately {pct}% of outstanding common stock as of {month} {end_day}, {year}",
    "{company}'s Chief Executive Officer owns {shares} shares, representing {pct}% of shares outstanding",
    "Insider transactions during {year} included {action} of {shares} shares by executive officers and directors",
    "As of {month} {end_day}, {year}, executive officers and directors held options to purchase {shares} shares of common stock",
]

insider_actions = [
    "purchases",
    "sales",
    "exercises",
    "grants",
    "net purchases",
    "net sales",
]

# ========== FORWARD-LOOKING STATEMENTS ==========
forward_looking_templates = [
    "This report contains forward-looking statements within the meaning of the Private Securities Litigation Reform Act of 1995",
    "Forward-looking statements include, but are not limited to, statements regarding {topics}",
    'Words such as "{words}" and similar expressions identify forward-looking statements',
    "These forward-looking statements are subject to risks and uncertainties that could cause actual results to differ materially from those projected",
    "{company} cautions that forward-looking statements are not guarantees of future performance and involve known and unknown risks",
    "{company} undertakes no obligation to update or revise forward-looking statements, whether as a result of new information, future events, or otherwise",
    "Forward-looking statements are based on management's current expectations and assumptions as of the date of this report",
    "Factors that could cause actual results to differ from forward-looking statements include {risk_factors}",
    "Investors should not place undue reliance on forward-looking statements, which speak only as of {month} {end_day}, {year}",
    "All forward-looking statements are qualified in their entirety by reference to the risk factors discussed in Item 1A of this report",
]

forward_looking_topics = [
    "expected financial performance, growth strategies, and market opportunities",
    "anticipated product launches, regulatory approvals, and business development initiatives",
    "projected capital expenditures, cost reduction initiatives, and operational improvements",
    "expected market conditions, competitive dynamics, and customer demand",
]

forward_looking_words = [
    "expects, anticipates, intends, plans, believes, seeks, estimates, may, will, should, would, could",
    "projects, forecasts, targets, goals, likely, potential, continue, future, outlook",
    "positioned, strategy, opportunity, momentum, trajectory",
]

risk_factors_examples = [
    "economic conditions, competitive pressures, regulatory changes, and operational challenges",
    "market volatility, supply chain disruptions, technological changes, and geopolitical events",
    "customer demand fluctuations, pricing pressures, and execution risks",
    "cybersecurity threats, intellectual property risks, and litigation uncertainties",
]

safe_harbor_templates = [
    "Statements in this report that are not historical facts constitute forward-looking statements subject to the safe harbor provisions of the Private Securities Litigation Reform Act",
    "{company} includes forward-looking statements to provide investors with its current expectations and projections, but cautions that such statements involve risks",
    "Safe harbor statement: Except for historical information, this report contains forward-looking statements that involve substantial risks and uncertainties",
    "This document contains forward-looking statements that are protected by the safe harbor provisions for such statements",
]

# ========== ANALYST COVERAGE AND ESTIMATES ==========
analyst_coverage_templates = [
    "{company} is currently covered by {number} equity research analysts",
    "Analyst consensus estimates for {year} project earnings per share of {currency_code}{eps} and revenue of {currency_code}{revenue} {money_unit}",
    "The average analyst price target is {currency_code}{target}, representing {direction} of {pct}% from current levels",
    "{number} analysts have buy ratings, {number2} have hold ratings, and {number3} have sell ratings on the stock",
    "Analyst estimates for {year} range from {currency_code}{low} to {currency_code}{high} per share",
    "{company} does not provide guidance but is followed by several sell-side analysts who publish earnings estimates",
]

# ========== CREDIT RATINGS ==========
credit_rating_templates = [
    "{company}'s senior unsecured debt is rated {rating} by {agency} and {rating2} by {agency2}",
    "{agency} maintains a {rating} credit rating on {company} with a {outlook} outlook",
    "As of {month} {end_day}, {year}, {company} holds investment-grade credit ratings from major rating agencies",
    "{company}'s credit ratings are {rating} ({agency}), {rating2} ({agency2}), and {rating3} ({agency3})",
    "In {month} {year}, {agency} {action} {company}'s credit rating to {rating}",
    "{company} targets maintaining investment-grade credit metrics and ratings",
]

credit_agencies = ["Standard & Poor's", "Moody's", "Fitch Ratings"]
credit_ratings = ["BBB+", "BBB", "BBB-", "A-", "A", "Baa1", "Baa2", "Baa3"]
rating_outlooks = ["stable", "positive", "negative", "under review"]
rating_actions = ["upgraded", "downgraded", "affirmed", "revised"]

# ========== DIVIDEND AND CAPITAL ALLOCATION ==========
dividend_policy_templates = [
    "{company} has paid consecutive quarterly dividends since {year}",
    "In {month} {year}, the Board of Directors declared a quarterly dividend of {currency_code}{amount} per share, payable on {month} {end_day}, {year}",
    "The dividend payout ratio was {pct}% for {year}, compared to {prev_pct}% in {prev_year}",
    "{company} targets returning {pct}% to {pct2}% of free cash flow to shareholders through dividends and share repurchases",
    "Annual dividends totaled {currency_code}{amount} per share in {year}, representing a yield of {pct}% based on year-end stock price",
    "{company} does not currently pay a dividend and retains earnings to fund growth initiatives",
    "Dividend policy is reviewed annually by the Board of Directors based on earnings, cash flows, and capital allocation priorities",
]

share_repurchase_templates = [
    "During {year}, {company} repurchased {shares} shares of common stock for {currency_code}{amount} {money_unit}",
    "The Board of Directors authorized a {currency_code}{amount} {money_unit} share repurchase program in {month} {year}",
    "As of {month} {end_day}, {year}, {currency_code}{remaining} {money_unit} remained available under the current repurchase authorization",
    "Share repurchases totaled {currency_code}{amount} {money_unit} in {year}, compared to {currency_code}{prev_amount} {money_unit} in {prev_year}",
    "{company} opportunistically repurchases shares based on market conditions, capital requirements, and alternative investment opportunities",
    "No shares were repurchased during {year} as {company} prioritized debt reduction and organic growth investments",
]

# ========== COMPETITIVE LANDSCAPE ==========
competition_templates = [
    "{company} operates in a highly competitive industry characterized by {characteristics}",
    "Principal competitors include {competitor1}, {competitor2}, and {competitor3}",
    "{company} competes based on {factors}",
    "Market share in {company}'s primary markets remained relatively stable at approximately {pct}% during {year}",
    "Competitive pressures have intensified due to {reasons}",
    "{company} believes it maintains competitive advantages through {advantages}",
    "Industry consolidation during {year} included the merger of {competitor1} and {competitor2}",
]

competitive_characteristics = [
    "rapid technological change, evolving customer preferences, and new market entrants",
    "price competition, product innovation, and service quality",
    "consolidation, globalization, and regulatory complexity",
    "low barriers to entry and commoditization pressures",
]

competitive_factors = [
    "product quality, innovation, customer service, and brand reputation",
    "pricing, technology, distribution capabilities, and scale",
    "breadth of product portfolio, technical expertise, and customer relationships",
    "operational efficiency, time to market, and total cost of ownership",
]

competitive_advantages = [
    "proprietary technology, strong brand recognition, and established customer relationships",
    "economies of scale, operational excellence, and global footprint",
    "intellectual property portfolio, innovation capabilities, and market leadership",
    "vertically integrated operations, cost structure, and distribution network",
]

# ========== REGULATORY AND COMPLIANCE ==========
regulatory_templates = [
    "{company} is subject to extensive regulation by {regulators} governing {areas}",
    "Compliance with environmental, health, and safety regulations resulted in costs of approximately {currency_code}{amount} {money_unit} during {year}",
    "Changes in regulatory requirements could materially impact {company}'s business operations and financial results",
    "{company} maintains compliance programs and internal controls to ensure adherence to applicable laws and regulations",
    "Regulatory approvals obtained during {year} include {approvals}",
    "Pending regulatory matters include {matters}",
    "{company} incurred {currency_code}{amount} {money_unit} in regulatory compliance costs during {year}",
]

regulators = [
    "the SEC, FDA, and EPA",
    "federal, state, and international regulatory authorities",
    "the FTC, DOJ, and industry-specific agencies",
    "various governmental and regulatory bodies",
]

regulatory_areas = [
    "product safety, environmental protection, and consumer protection",
    "data privacy, cybersecurity, and financial reporting",
    "employment practices, antitrust, and trade compliance",
    "marketing practices, product labeling, and quality standards",
]

# ========== INSURANCE AND RISK MANAGEMENT ==========
insurance_templates = [
    "{company} maintains insurance coverage for property, casualty, general liability, and other risks in amounts considered adequate",
    "Self-insurance reserves totaled {currency_code}{amount} {money_unit} as of {month} {end_day}, {year}",
    "{company} self-insures certain risks including {risks} and purchases insurance for catastrophic losses",
    "Insurance recoveries during {year} totaled {currency_code}{amount} {money_unit} related to {incident}",
    "{company}'s insurance program includes coverage for {coverage_types} with policy limits and deductibles based on industry practices",
    "Risk retention levels are evaluated annually based on claims experience and insurance market conditions",
]

self_insured_risks = [
    "workers' compensation, general liability, and employee health benefits",
    "product liability, auto liability, and property damage below certain thresholds",
    "employment practices liability and certain cyber risks",
]

coverage_types = [
    "property damage, business interruption, product liability, and directors and officers liability",
    "cyber liability, errors and omissions, fiduciary liability, and environmental liability",
    "general liability, auto liability, workers' compensation, and excess umbrella coverage",
]


# ========== FOREIGN CURRENCY RISK/TRANSLATION (NON-DERIVATIVE) ==========

foreign_currency_exposure_templates = [
    "{company} operates in multiple countries and is exposed to foreign currency exchange rate fluctuations {major_currency} in that affect reported revenues and expenses",
    "{company}'s international operations subject it to foreign currency risks, primarily related to the {major_currency}, {currency2}, and {currency3}",
    "Foreign currency transaction in {major_currency} gains and losses are recorded in {location} as incurred",
    "Substantially all of {company}'s foreign subsidiaries use {major_currency} as their local currency",
    "{company}'s results of operations are affected by changes in foreign currency exchange rates, particularly movements in the {major_currency} and {currency2}",
]

foreign_currency_translation_templates = [
    "Assets and liabilities of foreign subsidiaries are translated to {major_currency} at period-end exchange rates, while income and expenses are translated at average exchange rates for the period",
    "Translation adjustments resulting from the process of translating foreign currency financial statements into {major_currency} are recorded in accumulated other comprehensive income",
    "The cumulative translation adjustment recorded in accumulated other comprehensive income was {currency_code}{amount} {money_unit} as of {month} {end_day}, {year}",
    "Foreign currency translation adjustments decreased stockholders' equity by {currency_code}{amount} {money_unit} during {year}",
    "{company} recorded a foreign currency translation loss of {currency_code}{amount} {money_unit} in other comprehensive income for the year ended {month} {end_day}, {year}",
    "The weakening of the {major_currency} against the {currency2} resulted in an unfavorable translation impact of {currency_code}{amount} {money_unit} in {year}",
    "Changes in foreign exchange rates resulted in translation gains of {currency_code}{amount} {money_unit} recorded in other comprehensive income during {year}",
]

foreign_currency_transaction_templates = [
    "Foreign currency transaction gains (losses) included in {location} totaled {currency_code}{amount} {money_unit} for the year ended {month} {end_day}, {year}",
    "{company} recognized foreign exchange losses of {currency_code}{amount} {money_unit} during {year}, primarily related to intercompany balances denominated in {major_currency}",
    "{company} recorded foreign currency transaction losses of {currency_code}{amount} {money_unit} in {year} compared to gains of {currency_code}{prev_amount} {money_unit} in {prev_year}",
    "Foreign exchange gains and losses on remeasurement of monetary assets and liabilities totaled {currency_code}{amount} {money_unit} in {year}",
    "Transaction gains and losses on foreign currency ({major_currency}) denominated receivables and payables are recognized in earnings as exchange rates fluctuate",
]

functional_currency_templates = [
    "The functional currency for most of {company}'s foreign subsidiaries is the local currency of the country in which the subsidiary operates",
    "For subsidiaries operating in highly inflationary economies, the {major_currency} is used as the functional currency",
    "{company} determines the functional currency of each subsidiary based on the primary economic environment in which the entity operates",
    "The functional currencies of {company}'s significant foreign operations include the {major_currency}, {currency2}, and {currency3}",
    "Remeasurement of foreign subsidiary financial statements from local currency to functional currency resulted in gains of {currency_code}{amount} {money_unit} in {year}",
]

fx_impact_on_results_templates = [
    "Foreign currency exchange rate fluctuations had an unfavorable impact on revenues of approximately {currency_code}{amount} {money_unit}, or {pct}%, during {year}",
    "Changes in foreign exchange rates negatively impacted operating income by {currency_code}{amount} {money_unit} in {year}",
    "Foreign currency movements had a favorable effect on revenues of {pct}% in {year}, primarily due to strengthening of the {major_currency}",
    "Excluding the impact of foreign currency translation, revenues would have increased {pct}% in {year} compared to {prev_year}",
    "The translation impact of changes in foreign exchange rates decreased reported revenues by {currency_code}{amount} {money_unit} year-over-year",
    "On a constant currency basis, revenues increased {pct}% compared to the prior year, versus {reported_pct}% on a reported basis",
]

intercompany_fx_templates = [
    "{company} has intercompany loans denominated in various currencies that are remeasured each reporting period with gains and losses recorded in earnings",
    "Intercompany foreign currency transactions resulted in remeasurement losses of {currency_code}{amount} {money_unit} during {year}",
    "{company} has {currency_code}{amount} {money_unit} in intercompany receivables denominated in {major_currency} as of {month} {end_day}, {year}",
    "Remeasurement of intercompany balances denominated in currencies other than the functional currency resulted in losses of {currency_code}{amount} {money_unit} in {year}",
]

# ========== COMMODITY PRICES/RISK/INVENTORY (NON-DERIVATIVE) ==========

commodity_price_exposure_templates = [
    "{company}'s operating results are affected by changes in commodity prices, particularly {commodity} and {commodity2}",
    "{company} is exposed to price volatility for key raw materials including {commodity}, {commodity2}, and {commodity3}",
    "Commodity price fluctuations, particularly for {commodity}, can significantly impact {company}'s cost structure and margins",
    "Raw material costs are subject to market volatility, with {commodity} prices ranging from {currency_code}{low_price} to {currency_code}{high_price} per {unit} during {year}",
    "{company}'s operations are sensitive to changes in {commodity} prices, which can affect both revenue and cost of sales",
]

commodity_cost_impact_templates = [
    "Commodity price increases added approximately {currency_code}{amount} {money_unit} to cost of goods sold during {year}",
    "Changes in {commodity} prices unfavorably impacted gross margin by {pct} percentage points in {year}",
    "{company} experienced cost inflation of {currency_code}{amount} {money_unit} in {year}, primarily driven by higher {commodity} and {commodity2} prices",
    "Commodity costs increased {pct}% year-over-year, driven primarily by {commodity} price appreciation",
    "Raw material price increases, particularly for {commodity}, reduced gross profit margin from {prev_pct}% to {pct}% in {year}",
    "{company} absorbed {currency_code}{amount} {money_unit} in commodity cost inflation during {year} through operational efficiencies and pricing actions",
]

commodity_inventory_valuation_templates = [
    "{company} maintains inventory of {commodity} and {commodity2} to support production requirements, exposing {company} to price risk",
    "As of {month} {end_day}, {year}, {company} held {volume} {unit} of {commodity} inventory valued at {currency_code}{amount} million",
    "{company} recorded an inventory writedown of {currency_code}{amount} {money_unit} in {year} due to declines in {commodity} market prices",
    "Commodity inventory is stated at the lower of cost or net realizable value, with cost determined using the {method} method",
    "{company}'s inventory includes {currency_code}{amount} {money_unit} of raw materials subject to commodity price volatility",
    "{company} recognized a {currency_code}{amount} {money_unit} charge related to excess and obsolete {commodity} inventory in {year}",
]

commodity_pricing_strategies_templates = [
    "{company} generally seeks to pass through commodity cost changes to customers through pricing mechanisms, though timing differences can affect margins",
    "{company} has implemented price increases totaling {pct}% to offset {commodity} cost inflation during {year}",
    "Pricing adjustments are typically implemented with a {months}-month lag following changes in {commodity} costs",
    "{company} utilizes index-based pricing formulas for certain products to mitigate the impact of {commodity} price volatility",
    "Customer contracts include provisions that allow {company} to adjust prices in response to significant {commodity} cost movements",
]

commodity_supply_risk_templates = [
    "{company} sources {commodity} from multiple suppliers to mitigate supply chain disruption risk",
    "{company} maintains strategic inventory of {commodity} to buffer against potential supply disruptions",
    "Supply constraints for {commodity} during {year} resulted in increased costs and temporary production delays",
    "{company} has long-term supply agreements for {commodity} covering approximately {pct}% of anticipated requirements",
    "{company} is exposed to concentration risk as {pct}% of {commodity} is sourced from a single region",
]

commodity_exposure_quantification_templates = [
    "A {pct}% change in {commodity} prices would impact annual cost of sales by approximately {currency_code}{amount} {money_unit}",
    "{company} estimates that commodity price volatility could affect operating income by {currency_code}{amount} {money_unit} annually",
    "Each {currency_code}{change} per {unit} change in {commodity} prices impacts annual costs by approximately {currency_code}{amount} {money_unit}",
    "Commodity exposure is concentrated in {commodity} ({pct}% of raw material spend) and {commodity2} ({pct2}% of raw material spend)",
]

physical_commodity_operations_templates = [
    "{company} owns and operates {commodity} production facilities with annual capacity of {volume} {unit}",
    "{company} produced {volume} {unit} of {commodity} during {year}, a {pct}% increase from the prior year",
    "{company}'s {commodity} operations generated revenues of {currency_code}{amount} {money_unit} in {year}",
    "Production costs for {commodity} averaged {currency_code}{cost} per {unit} in {year}, compared to {currency_code}{prev_cost} in {prev_year}",
    "{company} maintains proved reserves of {volume} {unit} of {commodity} as of {month} {end_day}, {year}",
]