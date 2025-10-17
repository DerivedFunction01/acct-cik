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
sec_phrases = [
    "Commission file number {file_number}",
    "ANNUAL REPORT PURSUANT TO SECTION {section} OF THE SECURITIES EXCHANGE ACT OF 1934",
    "Registrant's telephone number, including area code ({area_code}) {phone_number}",
    "For the fiscal year ended {month} {day} {year}",
    "For the transition period from {month} {day} {prev_year} to {month} {day2} {year}",
    "{company} (Exact Name , of Registrant as Specified in its Charter)",
    "Indicate by check mark if the registrant is a well-known seasoned issuer. Yes {choice1} No {choice2}",
    "Indicate by check mark whether the registrant (1) has filed all reports required to be filed by Section 13 or Section 15(d) of the Securities Exchange Act of 1934 during the preceding 12 months (or for such shorter period that the registrant was required to file such reports), and (2) has been subject to such filing requirements for the past 90 days. Yes {choice1} No {choice2}",
    "Note — Checking the box above will not relieve any registrant required to file reports pursuant to Section 13 or 15(d) of the Exchange Act from their obligations under those Sections",
    "Indicate by check mark whether the registrant has submitted electronically and posted on its corporate Website, if any, every Interactive Data File required to be submitted and posted to Rule 405 of Regulations S-T (§232.405 of this chapter) during the preceding 12 months (or for such shorter period that the registrant was required to submit and post such files). Yes {choice1} No {choice2}",
    'Indicate by check mark whether the registrant is a large accelerated filer, an accelerated filer, a non-accelerated filer, or a smaller reporting company. See the definitions of "large accelerated filer," "accelerated filer" and "smaller reporting company" in Rule 12b-2 of the Exchange Act Yes {choice1} No {choice2}',
    "The aggregate market value of the common shares held by non-affiliates was {currency_unit}{market_value}",
    "{shares_outstanding} common shares outstanding as of {date}",
    "Part III incorporates certain information by reference from the registrant's proxy statement for the {year} Annual Meeting of Shareholders expected to be held on {month} {day}, {next_year} . Such proxy statement will be filed no later than 120 days after the close of the registrant's fiscal year ended {month} {day2},  {year}.",
]
# ============ LITIGATION AND LEGAL MATTERS ============

litigation_templates = [
    "{company} is involved in various legal proceedings and claims arising in the ordinary course of business, including {litigation_examples}",
    "As of {month} {end_day}, {year}, {company} is a defendant in several lawsuits related to {litigation_examples}",
    "{company} is subject to litigation and regulatory inquiries concerning {litigation_examples} in the normal course of operations",
    "Various legal actions, proceedings, and claims are pending or may be instituted against {company}, including {litigation_examples}",
    "As of {month} {end_day}, {year}, {company} is a defending against several derivative lawsuits related to {litigation_examples}",
    'All securities holders of {company} are hereby notified that a settlement (the "Settlement") has been reached as to claims asserted in the above-captioned consolidated shareholder derivative action pending in a {court_name} (the "Derivative Action") on behalf of {company} against certain of its current or former directors and officers',
    "On {month} {end_day}, {year}, a shareholder derivative suit was filed in the {court_name} for the against {company}",
]

case_types = [
    "product liability, employment matters, and commercial disputes",
    "intellectual property infringement, contract disputes, and employment claims",
    "environmental matters, product warranty claims, and regulatory compliance",
    "patent litigation, customer disputes, and employment-related matters",
    "breach of contract claims, employment discrimination, and tax disputes",    "environmental liabilities, product recalls, and regulatory fines",
    "securities fraud, antitrust violations, and consumer class actions",
    "data privacy breaches, intellectual property disputes, and employment litigation",
    "breach of fiduciary duty, shareholder derivative actions, and corporate governance disputes",
    "tax disputes, customs duties, and international trade compliance",
    "product liability, warranty claims, and consumer protection issues",
    "contractual disputes, commercial litigation, and business torts",
    "real estate disputes, property damage claims, and landlord-tenant issues",
    "insurance coverage disputes, subrogation claims, and reinsurance matters",
    "bankruptcy proceedings, insolvency matters, and creditors' rights",
    "construction defects, engineering errors, and project delays",
    "healthcare fraud, medical malpractice, and pharmaceutical liability",
    "financial services litigation, banking disputes, and investment fraud",
    "energy and utilities disputes, regulatory enforcement, and environmental compliance",
    "telecommunications disputes, spectrum licensing, and regulatory challenges",
    "transportation accidents, cargo claims, and maritime law",
    "cybersecurity incidents, data breaches, and privacy violations",
    "antitrust investigations, competition law, and market manipulation",
    "securities enforcement actions, regulatory investigations, and corporate compliance",
    "product recalls, consumer safety, and regulatory compliance",
]

litigation_assessment_templates = [
    "Management believes that the ultimate resolution of these matters will not have a material adverse effect on {company}\'s financial position, results of operations, or cash flows",
    "While the outcome of these proceedings cannot be predicted with certainty, management does not believe they will materially impact the consolidated financial statements",
    "{company} believes it has meritorious defenses and intends to vigorously defend against these claims",
    "{company} intend to vigorously defend against these claims. At this time, {company} cannot predict the outcome, or provide a reasonable estimate or range of estimates of the possible outcome or loss, if any, in this matter",
    "Based on currently available information, management does not expect these matters to result in a material loss",
    "{company} has {assess_verb} the likelihood of loss as remote and has not recorded any provisions related to these contingencies",
]

specific_lawsuit_templates = [
    "In {month} {year}, a lawsuit was filed against {company} in the {court_name} alleging {lawsuit_allegation}. {company} filed a motion to dismiss in {month} {year}",
    "{company} is defending a class action lawsuit filed in {year} claiming {lawsuit_allegation}, with damages sought of approximately {currency_code}{amount} {money_unit}",
    "During {year}, {company} reached a settlement in a lawsuit related to {lawsuit_allegation} for {currency_code}{amount} {money_unit}, which was accrued in prior periods",
    "A complaint was filed against {company} in the {court_name} during {quarter} quarter {year} alleging {lawsuit_allegation}",
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
    "Court of Appeals of the State of California, Second Appellate District",    "United States District Court for the Central District of California",
    "United States District Court for the Eastern District of New York",
    "United States District Court for the Northern District of Illinois",
    "United States District Court for the Eastern District of Pennsylvania",
    "United States District Court for the District of Columbia",
    "United States Court of Appeals for the Second Circuit",
    "United States Court of Appeals for the Third Circuit",
    "United States Court of Appeals for the Fifth Circuit",
    "United States Court of Appeals for the Seventh Circuit",
    "United States Court of Appeals for the Eleventh Circuit",
    "Delaware Court of Chancery",
    "Supreme Court of the State of New York, County of New York",
    "Superior Court of Fulton County, Georgia",
    "District Court of Travis County, Texas",
    "Circuit Court of Fairfax County, Virginia",
    "Court of Common Pleas of Philadelphia County, Pennsylvania",
    "United States Court of Federal Claims",
    "United States Tax Court",
    "United States Bankruptcy Court for the District of Delaware",
    "United States Court of International Trade",
    "United States Court of Appeals for the Federal Circuit",
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
    "failure to comply with OSHA workplace safety regulations",    "breach of contract, fraud, and unfair business practices",
    "product liability claims related to manufacturing defects",
    "environmental contamination and regulatory non-compliance",
    "securities class action alleging misleading financial statements",
    "antitrust claims regarding monopolistic practices",
    "employment class action for wage and hour violations",
    "patent infringement by a competitor",
    "data breach incident impacting customer information",
    "breach of fiduciary duty by former executives",
    "tax assessment dispute with a state revenue agency",
    "consumer class action for deceptive marketing",
    "commercial dispute over a supply agreement",
    "real estate dispute involving property boundaries",
    "insurance coverage dispute for a major loss event",
    "bankruptcy preference claim by a creditor",
    "construction defect claim on a large project",
    "medical malpractice claim against a healthcare provider",
    "investment fraud claim by disgruntled investors",
    "regulatory enforcement action by the SEC",
    "product recall litigation due to safety concerns",
]
# ============ EQUITY WARRANTS (NON-DERIVATIVE) ============

equity_warrant_templates = [
    "{company} has {shares} equity-classified warrants outstanding with an exercise price of {currency_code}{amount} per share, exercisable until {maturity_year}",
    "Outstanding equity warrants for {shares} shares at {currency_code}{amount} per share are classified in stockholders' equity and are not remeasured",
    "As of {month} {end_day}, {year}, there were {shares} warrants outstanding classified as equity instruments",
    "{company} issued {shares} warrants to purchase common stock at {currency_code}{amount} per share, which are indexed to {company}'s own stock and classified in equity",
    "In {month} {year}, {shares} warrants issued to investors in connection with a {stock_event} in {month} {prev_year} were reset to {currency_code}{amount}",
    "In connection with the {stock_event}, {company} issued warrants to purchase up to {shares} shares of common stock at an exercise price of {currency_code}{amount} per share",
    "During {month} {year}, {company} issued {shares} warrants exercisable at {currency_code}{amount} per share in conjunction with {stock_event}",
    "As part of {stock_event}, {company} granted warrants for {shares} shares with a strike price of {currency_code}{amount}, expiring in {maturity_year}",
    "{company} issued {shares} common stock warrants at an exercise price of {currency_code}{amount} per share as consideration for {stock_event}",
    "In {month} {year}, warrants to acquire {shares} shares at {currency_code}{amount} per share were issued in connection with {stock_event}",
    "In connection with the {stock_event}, {company} issued warrants to purchase up to {shares} shares of common stock at an exercise price of {currency_code}{amount} per share, provision states the warrants meet the criteria for equity treatment",
    "{company} issued {shares} shares of common stock valued at {currency_code}{amount} in connection with {stock_event} during {year}",
    "During {year}, {company} issued {shares} shares of common stock (valued at {currency_code}{amount}) as part of {stock_event}",
]


equity_warrant_activity_templates = [
    "During {year}, warrant holders exercised {shares} warrants, resulting in proceeds of {currency_code}{amount} {money_unit}",
    "In {month} {year}, {shares} equity warrants expired unexercised, with no impact on earnings",
    "{company} received {currency_code}{amount} {money_unit} from the exercise of {shares} warrants during {year}",
    "{shares} warrants were exercised on a cashless basis during {year}, resulting in the issuance of {net_shares} net shares",
    "During {year}, warrants to purchase {shares} shares were exercised on a cashless basis, resulting in the issuance of {net_shares} net shares",
    "In the {quarter} quarter of {year}, {company} modified the terms of outstanding warrants, extending the expiration date to {maturity_year} and adjusting the exercise price to {currency_code}{amount}",
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
    "Deferred revenue as of {month} {end_day}, {year} was {currency_code}{amount} {money_unit}, compared to {currency_code}{amount2} {money_unit} in the prior year",
    "{company} recorded deferred revenue of {currency_code}{amount} {money_unit} related to advance payments from customers for future deliverables",
    "Contract liabilities increased to {currency_code}{amount} {money_unit} at year-end {year} due to timing of customer payments and performance obligations",
    "As of {month} {end_day}, {year}, {company} had {currency_code}{amount} {money_unit} in deferred revenue related to service and maintenance contracts",
    "Deferred revenue primarily consists of advance billings for subscription and support services to be recognized over future periods",
    "{company} expects to recognize approximately {currency_code}{amount} {money_unit} of deferred revenue over the next twelve months and the remainder thereafter",
    "The increase in deferred revenue from {currency_code}{amount2} {money_unit} to {currency_code}{amount} {money_unit} reflects growth in multi-year customer contracts",
    "Deferred revenue includes amounts invoiced in advance for software licenses, cloud services, and professional support not yet recognized as revenue",
    "Changes in deferred revenue during {year} were driven by new billings offset by revenue recognized as performance obligations were satisfied",
    "Deferred revenue classified as current liabilities was {currency_code}{amount} {money_unit}, with the non-current portion recorded as {currency_code}{amount2} {money_unit}",
    "{company} recognized revenue of {currency_code}{amount2} {money_unit} during {year} that was included in deferred revenue at the beginning of the period",
    "Deferred revenue balances are expected to be recognized as revenue consistent with the satisfaction of contractual obligations over time",
]

# ============ INVENTORY ============

inventory_templates = [
    "{commodities} inventories are stated at the lower of cost or net realizable value, with cost determined using the {inventory_method} method",
    "{company} values inventory using the {inventory_method} cost method and regularly reviews for obsolescence",
    "Inventory consists of {commodities} valued at the lower of cost (determined by {inventory_method}) or net realizable value",
    "As of {month} {end_day}, {year}, {commodities} inventories totaled {currency_code}{amount} {money_unit}, net of obsolescence reserves of {currency_code}{amount2} {money_unit}",
    "{commodities} inventories are reviewed periodically for slow-moving or obsolete items, with reserves recorded when necessary to reduce carrying values",
    "{commodities} inventories are stated at standard cost (approximating actual cost) under the {inventory_method} method, adjusted to net realizable value if necessary",
    "{commodities} are valued at purchase cost while manufactured inventories include labor and overhead allocated using the {inventory_method} method",
    "{commodities} inventory is written down to market value when estimated selling prices are less than cost",
    "As of {month} {end_day}, {year}, {company} maintained obsolescence reserves of {currency_code}{amount2} {money_unit} against total inventories of {currency_code}{amount} {money_unit}",
    "{commodities} inventory include {commodities} valued at the lower of cost (determined by {inventory_method}) or net realizable value",
    "{company} records provisions for excess and obsolete {commodities} inventories based on expected future demand, market conditions, and {commodities} life cycles",
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
    "During {year}, {company} recorded {commodities} inventory write-downs of {currency_code}{amount} {money_unit} due to obsolescence and excess quantities",
    "{commodities} inventory reserves increased by {currency_code}{amount} {money_unit} in {year} to reflect lower of cost or market adjustments",
    "{company} recognized {currency_code}{amount} {money_unit} in charges related to slow-moving and obsolete {commodities} inventory during {year}",
    "{commodities} inventory obsolescence charges totaled {currency_code}{amount} {money_unit} for the year ended {month} {end_day}, {year}",
    "As of {month} {end_day}, {year}, {company} maintained {commodities} reserves of {currency_code}{amount} {money_unit} for excess and obsolete inventories",
    "Write-downs of {currency_code}{amount} {money_unit} were recorded in {year} primarily related to discontinued product lines",
    "{company} recorded {currency_code}{amount} {money_unit} in inventory write-downs due to declining market demand during {year}",
    "Charges for inventory valuation adjustments were {currency_code}{amount} {money_unit} in {year}, compared to {currency_code}{amount2} {money_unit} in the prior year",
    "{company} recorded inventory write-downs associated with aging components and spare parts totaling {currency_code}{amount} {money_unit} during {year}",
    " {commodities} inventory reserves increased to {currency_code}{amount} {money_unit} at year-end {year}, reflecting adjustments for lower selling prices and product obsolescence",
    "Total charges of {currency_code}{amount} {money_unit} were recognized in cost of goods sold for inventory write-downs in {year}",
    "Inventory write-downs of {currency_code}{amount} {money_unit} were partially offset by recoveries of {currency_code}{amount2} {money_unit} related to previously reserved items",
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
    "Construction in progress primarily relates to {capex_purpose} and is not depreciated until placed into service",
    "As of {month} {end_day}, {year}, accumulated depreciation was {currency_code}{amount} {money_unit}",
]


capex_templates = [
    "Capital expenditures during {year} were {currency_code}{amount} {money_unit}, primarily related to {capex_purpose}",
    "{company} invested {currency_code}{amount} {money_unit} in {capex_purpose} during {year}",
    "Cash outlays for property, plant and equipment totaled {currency_code}{amount} {money_unit} in {year}, focused on {capex_purpose}",
    "Capital investments of {currency_code}{amount} {money_unit} were made during {year} to support {capex_purpose}",
    "During {year}, {company} incurred capital expenditures of {currency_code}{amount} {money_unit}, reflecting continued investment in {capex_purpose}",
    "Capex in {year} amounted to {currency_code}{amount} {money_unit}, directed primarily toward {capex_purpose}",
    "{company} allocated {currency_code}{amount} {money_unit} to property and equipment purchases during {year}, with a focus on {capex_purpose}",
    "Capital spending was {currency_code}{amount} {money_unit} in {year}, driven by {capex_purpose}",
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
    "fleet modernization and vehicle replacement",
    "digital transformation and software development",
    "environmental compliance and remediation",
    "strategic land acquisitions and site development",
    "security enhancements and infrastructure protection",
    "employee training and development facilities",
    "marketing and sales infrastructure",
    "research and development of new products",
    "upgrades to existing production lines",
    "construction of new administrative offices",
    "investment in energy-efficient technologies",
    "expansion of data storage and cloud capabilities",
    "modernization of telecommunications networks",
    "acquisition of specialized machinery and equipment",
    "development of new distribution centers",
    "implementation of advanced robotics and automation",
    "enhancement of cybersecurity measures",
    "renovation of retail stores and showrooms",
    "upgrading of transportation and logistics assets",
    "investment in sustainable manufacturing processes",
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
    "{company} leases office space, manufacturing facilities, and equipment under operating and finance leases with terms ranging from {small_int} to {short_int} years",
    "As of {month} {end_day}, {year}, {company} had operating lease right-of-use assets of {currency_code}{amount} {money_unit} and lease liabilities of {currency_code}{amount2} {money_unit}",
    "{company} adopted ASC 842 effective {month} {year}, recognizing right-of-use assets and lease liabilities for operating leases",
    "Total lease expense for {year} was {currency_code}{amount} {money_unit}, including both operating and finance lease costs",
    "Lease liabilities are measured at the present value of future lease payments, discounted using {company}\'s incremental borrowing rate",
    "Short-term leases and variable lease payments are excluded from right-of-use assets and liabilities under ASC 842",
    "{company} recognized {currency_code}{amount} {money_unit} of lease expense related to short-term and variable leases during {year}",
    "As of {month} {end_day}, {year}, finance lease assets totaled {currency_code}{amount} {money_unit}, included in property, plant and equipment",
    "Lease agreements do not contain significant residual value guarantees or restrictive covenants",
]


lease_commitment_templates = [
    "Future minimum lease payments under non-cancellable operating leases total {currency_code}{amount} {money_unit} as of {month} {end_day}, {year}",
    "The weighted-average remaining lease term for operating leases is {small_int} years as of {month} {end_day}, {year}",
    "The weighted-average discount rate used to measure lease liabilities was {pct}% as of {month} {end_day}, {year}",
    "Operating lease payments are expected to total {currency_code}{amount} {money_unit} over the next five years",
    "Maturities of lease liabilities are {currency_code}{amount} {money_unit} in {year}, {currency_code}{amount2} {money_unit} in {next_year}, and {currency_code}{amount3} {money_unit} thereafter",
    "As of {month} {end_day}, {year}, undiscounted future lease payments totaled {currency_code}{amount} {money_unit}, with a present value of {currency_code}{amount2} {money_unit}",
    "Future finance lease obligations amounted to {currency_code}{amount} {money_unit} as of {month} {end_day}, {year}",
    "Lease commitments include renewal options reasonably certain to be exercised, totaling {currency_code}{amount} {money_unit}",
]

# ============ GOODWILL AND INTANGIBLES ============

goodwill_templates = [
    "Goodwill totaled {currency_code}{amount} {money_unit} as of {month} {end_day}, {year}, and is not amortized but tested for impairment annually",
    "{company} performs its annual goodwill impairment test in the {quarter} quarter of each year",
    "No goodwill impairment was recorded during {year} as the fair value of reporting units exceeded their carrying values",
    "Goodwill is allocated to reporting units and {assess_verb} for impairment at least annually or when indicators of impairment exist",
]

intangible_templates = [
    "Intangible assets consist primarily of {intangible_type_examples} and are amortized over their estimated useful lives",
    "Amortization expense for intangible assets was {currency_code}{amount} {money_unit} for the year ended {month} {end_day}, {year}",
    "As of {month} {end_day}, {year}, intangible assets, net of accumulated amortization, totaled {currency_code}{amount} {money_unit}",
    "The weighted-average remaining useful life of intangible assets is {small_int} years as of {month} {end_day}, {year}",
]

intangible_types = [
    "customer relationships, developed technology, and trade names",
    "patents, trademarks, and customer lists",
    "software, customer contracts, and non-compete agreements",
    "brand names, proprietary technology, and customer relationships",    
    "customer lists, trade names, and developed software",
    "licenses, permits, and intellectual property rights",
    "franchise agreements, distribution rights, and patents",
    "proprietary technology, customer contracts, and brand recognition",
    "in-process research and development (IPR&D) and marketing intangibles",
    "trademarks, copyrights, and non-compete agreements",
    "core technology, customer relationships, and internet domain names",
    "formulations, processes, and manufacturing know-how",
    "broadcast licenses, content rights, and subscriber bases",
    "mineral rights, water rights, and timber rights",
    "patents, trade secrets, and proprietary databases",
    "customer relationships, software licenses, and brand assets",
    "developed technology, marketing-related assets, and contractual rights",
    "intellectual property, customer lists, and goodwill",
    "licenses, permits, and other contractual rights",
    "brand names, customer contracts, and proprietary processes",
    "software, patents, and customer relationships",
    "trade names, customer relationships, and developed technology",
    "intellectual property, customer relationships, and brand names",
    "patents, trademarks, and customer contracts",
]

# ============ DEBT AND CREDIT FACILITIES ============

debt_templates = [
    # General facilities and balances
    "{company} maintains a {currency_code}{amount} {money_unit} revolving credit facility that expires in {maturity_year}, with {currency_code}{amount} {money_unit} outstanding as of {month} {end_day}, {year}, with annual interest rate of {pct}%",
    "As of {month} {end_day}, {year}, {company} had total long-term debt of {currency_code}{amount} {money_unit}, consisting primarily of {debt_types}, with an average interest rate of {pct}% and {pct2}%, respectively",
    "Long-term debt, with an annual interest rate of {pct}% as of {month} {end_day}, {year} totaled {currency_code}{amount} {money_unit}, consisting of {debt_types}",
    "At year-end {year}, {company} reported total debt of {currency_code}{amount} {money_unit} with interest rates ranging from {pct}% to {pct2}%, including {debt_types}",
    "{company}'s outstanding borrowings under its revolving credit facility totaled {currency_code}{amount} {money_unit} with average interest rate of {pct}% to {pct2}% as of {month} {end_day}, {year}",
    "As of {month} {end_day}, {year}, there was {currency_code}{amount} {money_unit} outstanding on the {debt_type} and {currency_code}{amount2} {money_unit} outstanding on {debt_types}",
    # Issuances and repayments
    "During {year}, {company} issued {currency_code}{amount} {money_unit} in {debt_types} with a maturity date of {maturity_year} and a weighted average interest rate of {pct}%",
    "In {year}, {company} completed a private placement of {currency_code}{amount} {money_unit} of {debt_types}, bearing interest at {pct}% per annum",
    "During {year}, {company} repaid {currency_code}{amount} {money_unit} of its outstanding {debt_type} prior to maturity",
    "{company} repaid {currency_code}{amount} {money_unit} of outstanding {debt_type} during {year} using cash from operations",
    "In {year}, {company} refinanced {currency_code}{amount} {money_unit} of existing {debt_type} at interest rate of {pct}%, extending the maturity to {maturity_year}",
    "The notional amount on the {debt_type} reduces monthly from approximately {currency_code}{amount} {money_unit} at {month} {end_day}, {year} to {currency_code}{amount2} {money_unit} prior to expiration of the agreement",    
    "The {debt_type} has a principal amount of {currency_code}{amount} {money_unit} and matures in {maturity_year}",
    # Interest rate and maturity details
    "As of year-end {year}, {company} had total {debt_type} of {currency_code}{amount} {money_unit}, {currency_code}{amount2} {money_unit} of which was fixed rate debt with a weighted average interest rate of {pct}% to {pct2}%",
    "The weighted average interest rate on {company}'s {debt_type} was approximately {pct}% as of {month} {end_day}, {year}",
    "As of {month} {end_day}, {year}, {company}'s {debt_type} had a weighted average maturity of {small_int} years",
    "As of {month} {end_day}, {year}, {company}'s variable-rate borrowings bore interest at an average rate of {pct}%",
    "Interest expense related to {debt_type} for {year} was approximately {currency_code}{amount} {money_unit}",
    "At {month} {year}, {company} repaid {currency_code}{amount} {money_unit} of the {currency_code}{amount2} {money_unit} borrowed",
    "The agreement effectively sets a cap and floor interest rate of {pct}% and {pct2}%, respectively, on most of the {debt_type}",
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
    "long-term contract",
    "short-term contract",   
    "long-term agreement",
    "short-term agreement",
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
    "revolving credit facility",
    "senior notes",
    "convertible notes",
    "subordinated debt",
    "mortgage payable",
    "capital lease obligations",
    "commercial mortgage-backed securities (CMBS)",
    "asset-backed securities (ABS)",
    "collateralized loan obligations (CLO)",
    "municipal bonds",
    "corporate bonds",
    "government bonds",
    "zero-coupon bonds",
    "perpetual bonds",
    "revenue bonds",
    "general obligation bonds",
    "secured bonds",
    "unsecured bonds",
    "fixed-rate bonds",
    "floating-rate bonds",
    "convertible bonds",
    "callable bonds",
    "puttable bonds",
    "inflation-indexed bonds",
    "eurobonds",
    "samurai bonds",
    "panda bonds",
    "yankee bonds",
    "bulldog bonds",
    "global bonds",
    "green bonds",
    "social bonds",
    "sustainability bonds",
    "catastrophe bonds",
    "war bonds",
    "savings bonds",
    "treasury bills",
    "treasury notes",
    "treasury bonds",
    "agency bonds",
    "certificates of deposit (CDs)",
    "money market instruments",
    "commercial paper",
    "banker's acceptances",
    "repurchase agreements (repos)",
    "federal funds",
    "eurodollars",
    "syndicated loans",
    "club loans",
    "bilateral loans",
    "mezzanine debt",
    "venture debt",
    "bridge loans",
    "acquisition financing",
    "project finance loans",
    "leveraged buy-out (LBO) loans",
    "asset-based lending (ABL)",
    "factoring",
    "supply chain finance",
    "trade finance",
    "export finance",
    "import finance",
    "working capital loans",
    "equipment loans",
    "real estate loans",
    "construction loans",
    "development loans",
    "agricultural loans",
    "small business loans",
    "microloans",
    "student loans",
    "auto loans",   
]


debt_covenant_templates = [
    "The credit agreement contains customary affirmative and negative covenants, including financial covenants related to leverage ratios and interest coverage",
    "As of {month} {end_day}, {year}, {company} was in compliance with all debt covenants",
    "The revolving credit facility requires maintenance of a maximum leverage ratio of {small_int}:1 and minimum interest coverage ratio of {small_int2}:1",
    "Debt agreements contain restrictions on dividends, additional indebtedness, and asset sales, subject to certain exceptions",
    # Covenant and credit facility context
    "The revolving credit facility contains customary financial covenants, including maintaining a maximum leverage ratio and minimum interest coverage ratio",
    "{company} was in compliance with all debt covenants as of {month} {end_day}, {year}",
    "{company}\'s credit agreements require maintenance of specified leverage and coverage ratios, which {company} met as of {month} {end_day}, {year}",
]

# ============ INCOME TAXES ============

tax_templates = [
    "The provision for income taxes was {currency_code}{amount} {money_unit} for {year}, resulting in an effective tax rate of {pct}%",
    "The effective tax rate for {year} was {pct}%, compared to {pct2}% in the prior year",
    "Deferred tax assets as of {month} {end_day}, {year} totaled {currency_code}{amount} {money_unit}, primarily related to {tax_sources_examples}",
    "{company} has net operating loss carryforwards of {currency_code}{amount} {money_unit} that expire between {past_year} and {next_year}",
]

tax_sources = [
    "net operating losses, tax credit carryforwards, and accrued expenses",
    "stock-based compensation, depreciation differences, and reserves",
    "employee benefits, loss carryforwards, and capitalized research costs",
    "bad debt reserves, inventory reserves, and accrued liabilities",    
    "valuation allowances, tax holidays, and foreign tax credits",
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
    "During {year}, {company} granted {shares} stock options with a weighted-average exercise price of {currency_code}{amount} per share",
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
    "{company} sponsors defined benefit pension plans covering certain employees, with plan assets of {currency_code}{amount} {money_unit} and projected benefit obligations of {currency_code}{amount2} {money_unit} as of {month} {end_day}, {year}",
    "Pension expense for {year} was {currency_code}{amount} {money_unit}, including service cost, interest cost, and expected return on plan assets",
    "The funded status of {company}\'s pension plans resulted in a net liability of {currency_code}{amount} {money_unit} as of {month} {end_day}, {year}",
    "During {year}, {company} contributed {currency_code}{amount} {money_unit} to its defined benefit pension plans",
]

opeb_templates = [
    "{company} provides postretirement medical and life insurance benefits to eligible retirees",
    "The accumulated postretirement benefit obligation was {currency_code}{amount} {money_unit} as of {month} {end_day}, {year}",
    "Net periodic postretirement benefit cost for {year} totaled {currency_code}{amount} {money_unit}",
    "{company}\'s postretirement benefit plans are unfunded, with liabilities recorded in other long-term liabilities",
]

# ============ COMMITMENTS AND CONTINGENCIES ============

purchase_commitment_templates = [
    "{company} has purchase commitments with suppliers totaling approximately {currency_code}{amount} {money_unit} as of {month} {end_day}, {year}",
    "Outstanding purchase orders and contractual obligations for inventory and capital expenditures totaled {currency_code}{amount} {money_unit} at year-end {year}",
    "{company} is obligated under various supply agreements to purchase minimum quantities totaling {currency_code}{amount} {money_unit} over the next {small_int} years",
    "As of {month} {end_day}, {year}, {company} had non-cancellable purchase commitments of {currency_code}{amount} {money_unit}",
]

guarantee_templates = [
    "{company} has provided guarantees and indemnifications related to {guarantee_type} with a maximum potential exposure of {currency_code}{amount} {money_unit}",
    "Product warranty obligations totaled {currency_code}{amount} {money_unit} as of {month} {end_day}, {year}",
    "{company} accrues warranty costs based on historical claims experience and specific identified warranty issues",
    "Warranty expense for {year} was {currency_code}{amount} {money_unit}, with payments of {currency_code}{amount2} {money_unit}",
]

guarantee_types = [
    "product performance, lease obligations, and customer financing",
    "residual value guarantees and performance bonds",
    "environmental remediation and divested business obligations",
    "intellectual property indemnifications and debt guarantees",    
    "environmental liabilities, product recalls, and regulatory fines",
    
]

# ============ RESTRUCTURING ============

restructuring_templates = [
    "During {year}, {company} initiated a restructuring plan to {restructuring_purpose}, resulting in charges of {currency_code}{amount} {money_unit}",
    "Restructuring charges of {currency_code}{amount} {money_unit} were recorded in {year}, primarily related to {restructuring_expense_type}",
    "{company} announced a cost reduction initiative in {month} {year} expected to generate annual savings of {currency_code}{amount} {money_unit}",
    "As of {month} {end_day}, {year}, the remaining restructuring liability was {currency_code}{amount} {money_unit}",
]

restructuring_purposes = [
    "streamline operations and reduce costs",
    "consolidate manufacturing facilities",
    "optimize the organizational structure",
    "align resources with strategic priorities",    
    "expand into new geographic markets",    
    "enter new product markets",    
    "divest non-core assets",    
    "restructure debt obligations",    
    "exit a particular business segment",    
    "exit a specific geographic market",    
    "exit a specific product line",
]

restructuring_expense_types = [
    "employee severance and benefits",
    "facility closure costs and asset impairments",
    "contract termination costs and severance",
    "workforce reductions and lease terminations",
]

# ============ ACQUISITIONS (NON-DERIVATIVE ASPECTS) ============

acquisition_templates = [
    "In {month} {year}, {company} acquired {company2} for total consideration of {currency_code}{amount} {money_unit} in cash",
    "{company} completed the acquisition of {company2} during {year} for {currency_code}{amount} {money_unit}, which was funded through {acquisition_funding}",
    "During {year}, {company} acquired {company2} to expand its {acquisition_purpose}",
    "The acquisition of {company2} in {year} resulted in {currency_code}{amount} {money_unit} of goodwill and {currency_code}{amount2} {money_unit} of identifiable intangible assets",
]

acquisition_purposes = [
    "product portfolio and market presence",
    "technology capabilities and customer base",
    "geographic reach and distribution channels",
    "manufacturing capacity and operational efficiency",   
    "synergies and cost efficiencies",    
    "achieve strategic objectives and market leadership",
]

acquisition_funding = [
    "cash on hand and borrowings under the credit facility",
    "available cash reserves",
    "a combination of cash and debt financing",
    "existing liquidity",    
    "a combination of cash, equity, and debt financing",
    "a mix of cash and stock consideration",
    "newly issued common stock",
    "proceeds from a recent debt offering",
    "a combination of cash and assumed liabilities",
    "a strategic equity investment",
    "a combination of cash and contingent consideration",
    "a combination of cash and seller notes",
    "a combination of cash and a revolving credit facility draw",
    "a combination of cash and proceeds from asset sales",
    "a combination of cash and a term loan",
    "a combination of cash and convertible debt",
    "a combination of cash and preferred stock",
    "a combination of cash and earn-out payments",
    "a combination of cash and a private placement of equity",
    "a combination of cash and a public offering of equity",
    "a combination of cash and a bridge loan",
    "a combination of cash and a line of credit",
    "a combination of cash and a venture debt facility",
    "a combination of cash and a strategic partnership",
]
# ============ STOCK ==========================
# Stock issuance for debt costs
stock_debt_issuance_templates = [
    "In conjunction with its {month} {year} {financing_type}, {company} issued at closing {shares} shares of common stock (valued at {currency_code}{amount}) and upon extension of the maturity date {shares2} shares of common stock (valued at {currency_code}{amount2}), which were recorded as debt issuance costs",
    "{company} issued {shares} shares of common stock valued at {currency_code}{amount} in connection with {financing_type} during {year}, recorded as debt issuance costs",
    "During {year}, {company} issued {shares} shares of common stock (valued at {currency_code}{amount}) as part of {financing_type}, with the value recorded as a debt issue cost",
    "In {month} {year}, {company} completed {financing_type} and issued {shares} shares of common stock valued at {currency_code}{amount} as consideration, which was capitalized as debt issuance costs",
    "Upon closing of the {financing_type} in {month} {year}, {shares} shares were issued as transaction costs and recorded in additional paid-in capital",
    "{company} capitalized {shares} shares of common stock valued at {currency_code}{amount} as debt issuance costs related to the {financing_type}",
]

# Registration statement and resale concerns
registration_statement_templates = [
    "Such sales also may inhibit our ability to obtain future equity related financing on acceptable terms. In {month} {year}, {company} will file a registration statement to register the shares of common stock issuable upon conversion of the convertible notes and upon exercise of the warrants to permit the resale of these shares of common stock",
    "{company} filed a registration statement on Form S-3 in {month} {year} to register {shares} shares of common stock underlying convertible securities for resale by holders",
    "In {month} {year}, {company} registered {shares} shares of common stock issuable upon conversion of notes and exercise of warrants pursuant to registration rights agreements",
    "The registration statement filed in {year} covers {shares} shares issuable upon conversion and exercise of outstanding securities, permitting resale by security holders",
    "{company} is obligated to file a registration statement within {short_int} days following {month} {year} covering shares issuable upon conversion of notes and warrants",
]

# Market impact of registered shares
market_impact_templates = [
    "Upon the effective date of the registration statement, the holders of the convertible notes may sell all or a portion of the shares of common stock they receive by conversion of the notes and warrants directly in the market or through one or more underwriters, broker-dealers, or agents",
    "A large number of shares of common stock would be available for resale by the note holders upon effectiveness of the registration statement, which could depress the market price of {company}\'s common stock",
    "The resale of {shares} shares registered under the registration statement could adversely affect the market price of {company}\'s common stock",
    "Upon effectiveness of the registration statement, holders may resell {shares} shares, potentially causing downward pressure on the stock price",
    "The registration of {shares} shares for resale by holders could result in substantial dilution and negatively impact the trading price of the common stock",
    "Sales of substantial amounts of common stock in the public market following effectiveness of the registration statement could adversely affect prevailing market prices",
]

# Warrant and option adjustment templates
warrant_adjustment_templates = [
    "The original exercisable shares of {shares} and exercise price of {currency_code}{amount} was adjusted to {shares} and {currency_code}{amount2}, respectively, to account for the {month} {year} Private Placement and the Amendment Agreement",
    "Anti-dilution provisions resulted in adjustment of warrant exercise price from {currency_code}{amount} to {currency_code}{amount2} and shares from {shares} to {shares} following the {year} financing",
    "Pursuant to anti-dilution protection, {shares} warrants at {currency_code}{amount} per share were adjusted to {shares} warrants at {currency_code}{amount2} per share effective {month} {year}",
    "The {month} {year} down-round financing triggered adjustments to outstanding warrants, changing the exercise price from {currency_code}{amount} to {currency_code}{amount2}",
    "Weighted-average anti-dilution adjustments modified warrant terms to {shares} shares at {currency_code}{amount2} from {shares} shares at {currency_code}{amount}",
]

# Fair value measurement templates
fair_value_snapshot_templates = [
    "The fair value of the shares are {currency_code}{amount} and {currency_code}{amount2}, in {month} {year}",
    "As of {month} {end_day}, {year}, the fair value of shares underlying convertible instruments was {currency_code}{amount}",
    "Fair value of shares reserved for issuance totaled {currency_code}{amount} at {month} {end_day}, {year}",
    "The {shares} shares reserved for conversion and exercise had an aggregate fair value of {currency_code}{amount} as of {month} {year}",
    "{company} valued the {shares} shares underlying convertible securities at {currency_code}{amount} based on the closing stock price on {month} {end_day}, {year}",
]

# Share reservation templates
share_reservation_templates = [
    "In addition, {company} has reserved {shares} shares of the common stock for issuance upon the exercise of outstanding warrants and {shares2} shares of the common stock for issuance upon the exercise of stock options",
    "{company} has reserved a total of {shares} shares for issuance under equity incentive plans and upon exercise of warrants and convertible securities",
    "As of {month} {end_day}, {year}, {shares} shares were reserved for warrant exercises and {shares2} shares for option exercises under equity plans",
    "{company} maintains a reserve of {shares} shares for potential issuance upon conversion, exercise, or settlement of outstanding equity instruments",
    "{shares} shares of authorized common stock are reserved for issuance pursuant to outstanding equity awards, warrants, and convertible instruments as of {year}",
]

# Outstanding options disclosure
outstanding_options_templates = [
    "As of {month} {end_day}, {year}, there are {shares} issued and outstanding options to purchase common stock. To the extent that outstanding warrants and options are exercised, the percentage ownership of common stock of {company}'s stockholders will be diluted",
    "Outstanding stock options totaled {shares} as of {month} {end_day}, {year}, with a weighted-average exercise price of {currency_code}{amount}",
    "As of {year} year-end, {shares} stock options were outstanding and exercisable, representing potential dilution to existing shareholders",
    "{company} had {shares} options outstanding at {month} {end_day}, {year}, of which {shares} were vested and exercisable",
    "Stock options to purchase {shares} shares were outstanding as of {month} {end_day}, {year}, with expiration dates ranging from {year} to {maturity_year}",
]

# Dilution concern templates
dilution_concern_templates = [
    "In the event of the exercise of a substantial number of warrants and options, within a reasonably short period of time after the right to exercise commences, the resulting increase in the amount of the common stock in the trading market could substantially adversely affect the market price of the common stock or {company}\'s ability to raise money through the sale of equity securities",
    "Exercise of outstanding warrants and options representing {shares} shares could result in significant dilution to existing stockholders and negatively impact the stock price",
    "The potential issuance of {shares} shares upon exercise of warrants and conversion of notes could dilute current shareholders by approximately {pct}%",
    "Substantial dilution may occur if holders exercise warrants for {shares} shares and convert notes into {shares} shares of common stock",
    "Current stockholders face potential dilution from {shares} shares underlying warrants, options, and convertible securities as of {month} {end_day}, {year}",
    "If all outstanding warrants and options were exercised, {shares} additional shares would be issued, representing {pct}% dilution to current shareholders",
]

# Capital raising impact templates
capital_raising_impact_templates = [
    "The overhang of {shares} shares underlying convertible securities may impair {company}\'s ability to raise capital through future equity offerings",
    "Potential dilution from outstanding warrants and options could adversely affect the terms of future financings or {company}\'s ability to access capital markets",
    "The existence of {shares} shares reserved for issuance may make it more difficult for {company} to obtain financing on favorable terms",
    "Future equity financings may be more difficult to complete due to the dilutive effect of {shares} shares underlying outstanding securities",
]

warrant_debt_issuance_templates = [
    "In the same financing, {company} issued warrants to purchase {shares} shares of its common stock (valued at {currency_code}{amount}) and warrants to purchase {shares2} shares of its common stock (valued at {currency_code}{amount2}) related to extensions of the maturity dates",
    "{company} issued warrants to purchase {shares} shares of common stock (valued at {currency_code}{amount}) in conjunction with {financing_type} in {month} {year}",
    "Warrants to purchase {shares} shares of common stock were issued as part of the financing arrangement, valued at {currency_code}{amount} and recorded as debt issuance costs",
    "In connection with {financing_type}, {company} granted warrants for {shares} shares valued at {currency_code}{amount}, with the value recorded as debt issue costs",
    "Additional warrants to purchase {shares} shares of {company} common stock were issued on {month} {year} in consideration for the extension to that date",
    "In connection with the extension to {month} {year}, {company} offered two alternatives of consideration. Holders of {shares} common stock of the notes elected to reduce the exercise price of their warrants, or to to receive additional warrants to purchase {shares2} shares of common stock",
    "{company} reduced the exercise price by {currency_code}{amount} per share for all warrants issued in connection with the issuance or extensions of the notes",
    "In consideration of this extension, {company} issued {shares} shares of common stock at a price of {amount} per share and warrants to purchase {shares} shares of common stock at a price to be determined in the future, between {currency_code}{amount} and {currency_code}{amount2} per share, on or before {month} {year}",
    "Also in {month} {year}, {company} exchanged a {currency_code}{amount} note payable for units of common stock and warrants to purchase common stock at a price of {currency_code}{amount} per unit",
    "In addition, the financial advisor on the debt offering received an additional {shares} warrants with the {month} offering for a total of approximately {amount}",
    "If all of the warrants are exercised and the debt is fully converted to {company}\'s stock, current stockholders will experience a significant dilution in their ownership of the company",
    "Based on the terms of the debt offering both the notes and warrants are subject to anti-dilution provisions and can potentially become more dilutive to {company}\'s stock. Further dilution may occur in the event of a default {currency_code}{amount} payable",
]

warrant_amortization_templates = [
    "The value of the warrants related to these financings was recorded as debt issue costs and the amortization of such warrant costs was included in interest expense, which was capitalized as a cost of {asset_type}",
    "Warrant costs totaling {currency_code}{amount} were recorded as debt issuance costs and amortized to interest expense over the term of the debt",
    "{company} amortizes debt issuance costs, including the value of warrants issued, to interest expense using the effective interest method",
    "Amortization of warrant-related debt issuance costs totaled {currency_code}{amount} for the year ended {month} {end_day}, {year}",
    "The relative fair value of the warrants was recorded as a debt discount and is being amortized to non-cash interest expense over the life of the {debt_types} using the effective interest method",
    "The initial value of the warrants was recorded in Additional Paid-In Capital and, as they are classified as equity, they are not subsequently remeasured",
    "Amortization of the debt discount related to the warrants issued with the {debt_types} totaled {currency_code}{amount} and {currency_code}{amount2} for the years ended {year} and {prev_year}, respectively",
    "The warrants are exercisable for a term of five years at an exercise price of {currency_code}{amount} per share, subject to anti-dilution provisions similar to the provisions set forth in the Notes and expire on {month} {year}",
]


non_cash_settlement_templates = [
    "In {year}, {company} issued {shares} shares of common stock (valued at {currency_code}{amount}) in settlement of invoices for previously rendered {service_type}",
    "{company} settled outstanding {service_type} payables totaling {currency_code}{amount} through the issuance of {shares} shares of common stock during {year}",
    "During {year}, {company} issued {shares} shares valued at {currency_code}{amount} to settle {service_type} obligations",
    "{shares} shares of common stock were issued in {month} {year} to satisfy {currency_code}{amount} in outstanding {service_type} fees",
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
    "marketing services",
    "research and development services",
    "investor relations services",
    "software development services",
    "human resources consulting",
    "information technology services",
    "environmental consulting services",
    "public relations services",
    "engineering services",
    "design services",
    "manufacturing services",
    "logistics services",
    "real estate services",
    "financial advisory services",
    "tax advisory services",
    "management consulting services",
    "technical support services",
    "training and education services",
    "security services",
]

# Balance sheet changes templates
balance_sheet_change_templates = [
    "Accounts payable increased by {currency_code}{amount} {money_unit} to {currency_code}{amount} {money_unit} as of {month} {end_day}, {year}, primarily due to {bs_reason}",
    "Accounts receivable decreased {currency_code}{amount} {money_unit} during {year}, reflecting {bs_reason}",
    "Inventories increased {currency_code}{amount} {money_unit} from {month} {end_day}, {prev_year} to {month} {end_day}, {year} due to {bs_reason}",
    "Accrued liabilities increased by {currency_code}{amount} {money_unit} year-over-year, primarily attributable to {accrued_reason}",
    "Prepaid expenses and other current assets decreased {currency_code}{amount} {money_unit} as of {month} {end_day}, {year} compared to the prior year",
]

working_capital_templates = [
    "Working capital was {currency_code}{amount} {money_unit} at {month} {end_day}, {year}, compared to {currency_code}{amount2} {money_unit} at {month} {end_day}, {prev_year}",
    "Changes in operating assets and liabilities resulted in a {currency_code}{amount2} of {currency_code}{amount} {money_unit} in cash from operations during {year}",
    "{company}\'s working capital increased by {currency_code}{amount} {money_unit} during {year}, driven primarily by {bs_reason}",
    "Net changes in operating assets and liabilities used {currency_code}{amount} {money_unit} of cash during {year}",
]

ar_templates = [
    "Trade accounts receivable totaled {currency_code}{amount} {money_unit} at {month} {end_day}, {year}, representing {short_int} days sales outstanding",
    "The allowance for doubtful accounts was {currency_code}{amount} {money_unit} as of {month} {end_day}, {year}, compared to {currency_code}{amount2} {money_unit} in the prior year",
    "Days sales outstanding decreased from {short_int2} days to {short_int} days during {year}",
    "{company} recorded bad debt expense of {currency_code}{amount} {money_unit} during {year}",
    "Accounts receivable, net of allowances, increased {currency_code}{amount} {money_unit} to {currency_code}{amount} {money_unit} at year-end {year}",
]


ap_templates = [
    "Accounts payable increased {currency_code}{amount} {money_unit} from the prior year, reflecting {bs_reason}",
    "{company} extended payment terms with certain vendors during {year}, resulting in an increase in accounts payable of {currency_code}{amount} {money_unit}",
    "Accounts payable was {currency_code}{amount} {money_unit} at {month} {end_day}, {year}, down from {currency_code}{amount2} {money_unit} at {month} {end_day}, {prev_year}",
    "Days payable outstanding increased to {short_int} days at year-end {year} from {short_int2} days in the prior year",
    "Changes in accounts payable provided {currency_code}{amount} {money_unit} of cash during {year}",
]

accrued_liabilities_templates = [
    "Accrued compensation increased by {currency_code}{amount} {money_unit} at {month} {end_day}, {year} due to {accrued_reason}",
    "Accrued expenses totaled {currency_code}{amount} {money_unit} at year-end {year}, an increase of {currency_code}{amount2} {money_unit} from the prior year",
    "The increase in accrued liabilities of {currency_code}{amount} {money_unit} was primarily related to {accrued_reason}",
    "Other accrued liabilities decreased {currency_code}{amount} {money_unit} during {year}, mainly due to {accrued_reason}",
]

other_current_assets_templates = [
    "Other current assets increased {currency_code}{amount} {money_unit} to {currency_code}{amount} {money_unit} at {month} {end_day}, {year}, primarily due to {asset_reason}",
    "Prepaid expenses decreased by {currency_code}{amount} {money_unit} during {year}",
    "Other receivables totaled {currency_code}{amount} {money_unit} at year-end {year}",
    "Current assets, excluding cash, increased {currency_code}{amount} {money_unit} year-over-year",
]

other_liabilities_templates = [
    "Other long-term liabilities increased by {currency_code}{amount} {money_unit} during {year}, primarily related to {liability_reason}",
    "{company}\'s current liabilities totaled {currency_code}{amount} {money_unit} at {month} {end_day}, {year}",
    "Total liabilities increased from {currency_code}{amount2} {money_unit} to {currency_code}{amount} {money_unit} during {year}",
    "Non-current liabilities decreased {currency_code}{amount} {money_unit} to {currency_code}{amount} {money_unit} at year-end {year}",
]

retained_earnings_templates = [
    "Retained earnings increased by {currency_code}{amount} {money_unit} during {year}, reflecting net income of {currency_code}{amount} {money_unit} less dividends of {currency_code}{amount} {money_unit}",
    "Accumulated deficit was {currency_code}{amount} {money_unit} at {month} {end_day}, {year}",
    "{company} reported a net loss of {currency_code}{amount} {money_unit} for {year}, increasing accumulated deficit to {currency_code}{amount} {money_unit}",
    "Retained earnings totaled {currency_code}{amount} {money_unit} at year-end {year}",
]

stockholders_equity_templates = [
    "Total stockholders' equity increased {currency_code}{amount} {money_unit} to {currency_code}{amount} {money_unit} at {month} {end_day}, {year}",
    "Stockholders' equity was {currency_code}{amount} {money_unit} at {month} {end_day}, {year}, compared to {currency_code}{amount2} {money_unit} at {month} {end_day}, {prev_year}",
    "The increase in stockholders' equity of {currency_code}{amount} {money_unit} was primarily due to {equity_reason}",
    "Total equity increased by {currency_code}{amount} {money_unit} during {year}",
]

cash_flow_statement_templates = [
    "Cash used in operating activities was {currency_code}{amount} {money_unit} for the year ended {month} {end_day}, {year}",
    "Net cash provided by operating activities totaled {currency_code}{amount} {money_unit} in {year}, compared to {currency_code}{amount2} {money_unit} in {prev_year}",
    "Cash flows from investing activities used {currency_code}{amount} {money_unit} during {year}, primarily for {cfs_reason}",
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
    "strategic inventory purchases",
    "supply chain disruptions",
    "customer prepayments",
    "vendor discounts",
    "changes in credit terms",
    "economic downturn",
    "expansion into new markets",
    "product launches",
    "restructuring activities",
    "acquisitions or divestitures",
    "fluctuations in foreign exchange rates",
    "changes in regulatory requirements",
    "litigation settlements",
    "changes in revenue recognition policies",
    "impact of new accounting standards",
    "seasonal demand for products/services",
    "investment in research and development",
    "capital expenditure programs",
    "debt repayment schedules",
    "equity financing activities",
    "dividend payments",
    "share repurchase programs",
    "changes in tax laws",
    "pension plan contributions",
    "environmental remediation efforts",
    "insurance claim settlements",
    "changes in employee compensation and benefits",
    "fluctuations in commodity prices",
    "impact of technological advancements",
    "changes in customer preferences",
    "competitive pressures",
    "geopolitical events",
    "natural disasters",
    "cybersecurity incidents",
    "data privacy regulations",
    "supply chain optimization initiatives",
    "customer relationship management (CRM) system implementation",
    "enterprise resource planning (ERP) system upgrade",
    "digital marketing campaigns",
    "e-commerce platform development",
    "sustainability initiatives",
    "corporate social responsibility (CSR) programs",
    "employee training and development programs",
    "talent acquisition and retention strategies",
    "diversity and inclusion initiatives",
    "merger integration costs",
    "post-acquisition adjustments",
    "divestiture-related expenses",
    "asset retirement obligations",
    "contingent liabilities",
    "guarantee obligations",
    "warranty provisions",
    "product recall expenses",
    "restructuring charges",
    "impairment losses",
    "gain/loss on sale of assets",
    "foreign currency translation adjustments",
    "unrealized gains/losses on investments",
    "changes in fair value of derivatives",
    "stock-based compensation expense",
    "deferred tax assets/liabilities",
    "uncertain tax positions",
    "changes in accounting estimates",
]

accrued_reasons = [
    "annual incentive compensation accruals",
    "timing of payroll payments",
    "increased headcount",
    "accrual of performance bonuses",
    "timing of tax payments",
    "warranty accruals",
    "restructuring accruals",    
    "legal settlement accruals",
    "environmental remediation accruals",
    "increased vacation and sick leave accruals",
    "accrued interest on debt",
    "accrued professional fees",
    "accrued rent and utilities",
    "accrued marketing and advertising expenses",
    "accrued research and development costs",
    "accrued insurance expenses",
    "accrued sales commissions",
    "accrued royalties",
    "accrued dividends payable",
    "accrued pension and postretirement benefit costs",
    "accrued restructuring charges",
    "accrued acquisition-related costs",
    "accrued contingent liabilities",
    "accrued product returns and allowances",
    "accrued rebates and discounts",
    "accrued self-insurance liabilities",
    "accrued litigation expenses",
    "accrued regulatory fines and penalties",
    "accrued asset retirement obligations",
    "accrued deferred compensation",
    "accrued payroll taxes and benefits",
    "accrued property taxes",
    "accrued income taxes payable",
    "accrued value-added tax (VAT) or sales tax",
    "accrued environmental liabilities",
    "accrued decommissioning costs",
    "accrued site restoration costs",
    "accrued asset retirement obligations",
    "accrued warranty obligations",
    "accrued product recall costs",
    "accrued customer loyalty program costs",
    "accrued gift card breakage",
    "accrued service contract costs",
    "accrued maintenance expenses",
    "accrued software development costs",
    "accrued content acquisition costs",
    "accrued music licensing fees",
    "accrued film and television production costs",
    "accrued gaming royalties",
    "accrued advertising revenue share",
    "accrued affiliate marketing commissions",
    "accrued cloud service costs",
    "accrued data center expenses",
    "accrued network infrastructure costs",
    "accrued cybersecurity expenses",
    "accrued data privacy compliance costs",
    "accrued intellectual property legal fees",
    "accrued patent prosecution costs",
    
]

other_asset_reasons = [
    "prepaid insurance and maintenance contracts",
    "deposits with vendors",
    "income tax refunds receivable",
    "prepaid software licenses",
    "advances to suppliers",    
    "deferred offering costs",
    "other non-trade receivables",
    "prepaid rent",
    "prepaid advertising and marketing expenses",
    "prepaid research and development expenses",
    "prepaid legal and professional fees",
    "prepaid taxes",
    "prepaid interest",
    "prepaid royalties",
    "prepaid commissions",
    "prepaid software subscriptions",
    "prepaid cloud service fees",
    "prepaid maintenance contracts",
    "prepaid travel expenses",
    "prepaid employee benefits",
    "prepaid insurance premiums",
    "prepaid property taxes",
    "prepaid utility expenses",
    "prepaid license fees",
    "prepaid content costs",
    "prepaid intellectual property costs",
    "prepaid training expenses",
    "prepaid security services",
    "prepaid consulting fees",
    "prepaid audit fees",
    "prepaid advisory fees",
    "prepaid legal settlements",
    "prepaid environmental remediation costs",
    "prepaid restructuring costs",
    "prepaid acquisition-related costs",
    "prepaid contingent consideration",
    "prepaid warranty costs",
    "prepaid product recall costs",
    "prepaid customer loyalty program costs",
    "prepaid gift card breakage",
    "prepaid service contract costs",
    "prepaid maintenance expenses",
    "prepaid software development costs",
    "prepaid content acquisition costs",
    "prepaid music licensing fees",
    "prepaid film and television production costs",
    "prepaid gaming royalties",
    "prepaid advertising revenue share",
    "prepaid affiliate marketing commissions",
    "prepaid cloud service costs",
    "prepaid data center expenses",
    "prepaid network infrastructure costs",
    "prepaid cybersecurity expenses",
    "prepaid data privacy compliance costs",
    "prepaid intellectual property legal fees",
    "prepaid patent prosecution costs",
]

liability_reasons = [
    "deferred compensation arrangements",
    "uncertain tax positions",
    "environmental remediation obligations",
    "asset retirement obligations",
    "long-term incentive plan accruals",    
    "long-term warranty provisions",
    "deferred revenue for long-term contracts",
    "non-current operating lease liabilities",
    "long-term debt maturities",
    "pension and postretirement benefit obligations",
    "contingent liabilities from litigation",
    "long-term deferred tax liabilities",
    "customer deposits for future services",
    "long-term accrued expenses",
    "guarantees and indemnifications",
    "long-term capital lease obligations",
    "unearned revenue for multi-year subscriptions",
    "long-term provisions for restructuring",
    "long-term environmental liabilities",
    "long-term product recall liabilities",
    "long-term customer loyalty program liabilities",
    "long-term gift card breakage liabilities",
    "long-term service contract liabilities",
    "long-term maintenance expenses",
    "long-term software development costs",
    "long-term content acquisition costs",
    "long-term music licensing fees",
    "long-term film and television production costs",
    "long-term gaming royalties",
    "long-term advertising revenue share",
    "long-term affiliate marketing commissions",
    "long-term cloud service costs",
    "long-term data center expenses",
    "long-term network infrastructure costs",
    "long-term cybersecurity expenses",
    "long-term data privacy compliance costs",
    "long-term intellectual property legal fees",
    "long-term patent prosecution costs",
]

equity_reasons = [
    "net income and stock issuances",
    "net income partially offset by dividends paid",
    "the public offering completed in {month} {year}",
    "net loss for the year",
    "retention of earnings",    
    "share repurchases",
    "stock-based compensation expense",
    "other comprehensive income (loss)",
    "exercise of stock options and warrants",
    "conversion of convertible debt",
    "issuance of common stock for acquisitions",
    "dividends declared and paid",
    "changes in treasury stock",
    "foreign currency translation adjustments",
    "unrealized gains/losses on available-for-sale securities",
    "actuarial gains/losses on pension plans",
    "changes in fair value of cash flow hedges",
    "impact of new accounting standards",
    "prior period adjustments",
    "reclassification adjustments",
    "equity method investments",
    "non-controlling interests",
    "redemption of preferred stock",
    "issuance of preferred stock",
    "stock splits",
    "reverse stock splits",
    "recapitalization",
    "debt extinguishment gains/losses",
    "impact of share-based payment awards",
    "changes in additional paid-in capital",
    "changes in accumulated other comprehensive income (loss)",
    "changes in retained earnings (accumulated deficit)",
]
# Add these template arrays after the stock_comp_valuation_templates (around line 240)

# CEO and executive compensation templates
ceo_compensation_templates = [
    "{company}'s Chief Executive Officer received total compensation of {currency_code}{amount} {money_unit} for {year}, consisting of {currency_code}{amount} {money_unit} in base salary, {currency_code}{amount2} {money_unit} in cash bonuses, and {currency_code}{amount2} {money_unit} in equity awards",
    "For the year ended {month} {end_day}, {year}, the CEO's compensation package totaled {currency_code}{amount} {money_unit}, including base salary of {currency_code}{amount} {money_unit} and performance-based incentives of {currency_code}{amount2} {money_unit}",
    "Total compensation for the Chief Executive Officer was {currency_code}{amount} {money_unit} in {year}, compared to {currency_code}{amount2} {money_unit} in {prev_year}",
    "The CEO received {currency_code}{amount} {money_unit} in total compensation during {year}, comprised of salary, annual incentive compensation, and long-term equity grants",
]

executive_compensation_templates = [
    "Total compensation for {company}'s five highest-paid executives was {currency_code}{amount} {money_unit} for {year}",
    "The named executive officers received aggregate compensation of {currency_code}{amount} {money_unit} in {year}, including {currency_code}{amount2} {money_unit} in stock-based awards",
    "Compensation for senior management totaled {currency_code}{amount} {money_unit} during {year}, representing {increase_decrease} of {amount2}% from the prior year",
    "Executive compensation expense, including salaries, bonuses, and equity awards, totaled {currency_code}{amount} {money_unit} for the year ended {month} {end_day}, {year}",
]

equity_grant_templates = [
    "In {month} {year}, the CEO was granted {shares} restricted stock units with a grant-date fair value of {currency_code}{amount} {money_unit}, vesting over {small_int} years",
    "{company} granted the Chief Executive Officer {shares} stock options in {year} with an exercise price of {currency_code}{amount} per share and a ten-year term",
    "Performance share units representing {shares} shares at target were awarded to the CEO in {year}, with vesting contingent upon achievement of {p_metric}",
    "The CEO received a grant of {shares} restricted shares valued at {currency_code}{amount} {money_unit} during {year}, subject to {vesting_period} vesting",
]

performance_metrics = [
    "revenue growth and earnings per share targets",
    "total shareholder return relative to peer companies",
    "operating margin and return on invested capital goals",
    "strategic objectives and financial performance targets",
    "revenue, EBITDA, and market share milestones",    
    "customer satisfaction and product innovation metrics",
    "environmental, social, and governance (ESG) objectives",
    "free cash flow and return on equity benchmarks",
    "net income and diluted earnings per share",
    "stock price appreciation and dividend growth",
    "operational efficiency and cost reduction targets",
    "employee engagement and talent development goals",
    "market expansion and new product launches",
    "debt reduction and credit rating improvements",
    "supply chain resilience and sustainability initiatives",
    "cybersecurity posture and data privacy compliance",
    "diversity, equity, and inclusion (DEI) targets",
    "research and development pipeline advancements",
    "customer acquisition and retention rates",
    "brand recognition and reputation enhancement",
    "regulatory compliance and risk management effectiveness",
    "capital allocation efficiency and shareholder returns",
    "innovation and intellectual property development",
    "digital transformation and technology adoption",
    "global market share and competitive positioning",
    "product quality and reliability standards",
    "safety performance and incident rates",
    "community engagement and philanthropic contributions",
    "employee health and wellness programs",
    "ethical conduct and corporate governance standards",
    "strategic partnerships and alliances",
    "mergers and acquisitions integration success",
    "divestiture execution and value realization",
    "capital expenditure efficiency and project completion",
    "working capital management and liquidity optimization",
    "inventory turnover and supply chain costs",
    "accounts receivable days outstanding and collection rates",
    "accounts payable days outstanding and payment terms",
    "cash conversion cycle and cash flow generation",
    "return on assets and asset utilization",
    "return on capital employed and capital efficiency",
    "economic value added and shareholder value creation",
    "earnings before interest, taxes, depreciation, and amortization (EBITDA)",
    "adjusted EBITDA and non-GAAP financial measures",
    "segment revenue and segment operating income",
    "geographic revenue growth and market penetration",
    "product line profitability and gross margin",
    "selling, general, and administrative (SG&A) expense control",
    "research and development (R&D) spending efficiency",
    "effective tax rate management and tax planning",
    "debt-to-equity ratio and financial leverage",
    "interest coverage ratio and debt service capacity",
]

vesting_periods = [
    "three-year cliff",
    "four-year ratable",
    "three-year graded",
    "performance-based",
    "time-based annual",    
    "two-year cliff",
    "five-year ratable",
    "one-year cliff",
    "six-month cliff",
    "monthly over two years",
    "quarterly over three years",
    "upon achievement of specific milestones",
    "based on continuous service",
    "accelerated upon change of control",
    "subject to retirement eligibility",
    "over a period of four years, with 25% vesting on each anniversary of the grant date",
    "over a three-year period, with one-third vesting on each anniversary of the grant date",
    "ratably over a four-year period, with monthly vesting commencing one month after the grant date",
    "upon the achievement of certain performance conditions over a three-year performance period",
    "over a two-year period, with 50% vesting on each anniversary of the grant date",
    "immediately upon grant for non-employee directors",
    "upon the completion of a liquidity event",
    "over a five-year period, with 20% vesting on each anniversary of the grant date",
    "subject to the executive's continued employment through the vesting date",
    "over a four-year period, with a one-year cliff and quarterly vesting thereafter",
]

severance_templates = [
    "{company} maintains change-in-control agreements with executive officers providing for severance payments equal to {small_int} times base salary and target bonus upon qualifying termination",
    "Under the CEO\'s employment agreement, the executive is entitled to severance of {currency_code}{amount} {money_unit} upon termination without cause",
    "Change-in-control provisions in executive employment agreements provide for accelerated vesting of equity awards and cash severance payments",
    "{company}\'s severance arrangements with named executive officers could result in payments totaling {currency_code}{amount} {money_unit} upon a change in control",
]

employment_agreement_templates = [
    "{company} entered into an employment agreement with its Chief Executive Officer in {month} {year} providing for an annual base salary of {currency_code}{amount} {money_unit} and target annual bonus of {pct}% of salary",
    "The CEO\'s employment agreement, effective {month} {year}, includes a base salary of {currency_code}{amount} {money_unit} with annual merit increase eligibility and participation in long-term incentive programs",
    "Under the terms of the CEO employment agreement, the executive receives an annual base salary of {currency_code}{amount} {money_unit}, subject to annual review by the Board of Trustees",
    "The employment agreement with the Chief Executive Officer provides for base compensation of {currency_code}{amount} {money_unit} and eligibility for annual performance bonuses up to {pct}% of base salary",
]

compensation_committee_templates = [
    "The Compensation Committee of the Board of Directors reviews and approves all executive compensation, including salary, bonuses, and equity grants",
    "Executive compensation decisions are made by the Compensation Committee based on peer group benchmarking and company performance",
    "The Compensation Committee engaged {company} as its independent compensation consultant to advise on executive pay practices",
    "Annual executive compensation is determined by the Compensation Committee after considering financial performance, individual contributions, and market data",
]

say_on_pay_templates = [
    "At the {year} annual meeting, shareholders approved {company}\'s executive compensation program with {pct}% support",
    "{company}\'s say-on-pay proposal received {pct}% approval from shareholders at the annual meeting held in {month} {year}",
    "Shareholders voted to approve executive compensation on an advisory basis, with {pct}% of votes cast in favor",
    "The advisory vote on executive compensation was approved by {pct}% of shares voted at the {year} annual meeting",
]

deferred_comp_templates = [
    "Certain executives participate in a non-qualified deferred compensation plan allowing deferral of up to {pct}% of base salary and {pct}% of bonuses",
    "{company} maintains a deferred compensation plan for executives with a total liability of {currency_code}{amount} {money_unit} as of {month} {end_day}, {year}",
    "Executive officers may elect to defer receipt of cash bonuses and equity awards under {company}\'s non-qualified deferred compensation plan",
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
    "housing allowance and relocation benefits",
    "personal use of company aircraft",
    "executive health program and annual physicals",
    "reimbursement for professional memberships and subscriptions",
    "supplemental life insurance and disability coverage",
    "personal use of company car",
    "home security system installation and monitoring",
    "tax gross-ups on certain benefits",
    "legal and accounting services for personal matters",
    "chauffeur services",
    "personal assistant services",
    "tuition reimbursement for executive's dependents",
    "childcare or eldercare assistance",
    "concierge services",
    "executive dining room access",
    "fitness club memberships",
    "personal financial counseling",
    "estate planning services",
    "identity theft protection",
    "excess liability insurance",
    "relocation package including temporary housing and moving expenses",
    "expatriate benefits for international assignments",
    "security detail for executive and family",
    "private jet travel for personal use",
    "yacht or boat usage",
    "vacation property usage",
    "art or collectibles acquisition assistance",
    "personal chef services",
    "personal shopping services",
    "personal grooming and wellness services",
    "personal security training",
    "crisis management services",
    "reputation management services",
    "media training",
    "executive coaching",
    "mentorship programs",
    "leadership development programs",
    "sabbatical programs",
    "charitable gift matching programs",
    "matching contributions to deferred compensation plans",
    "supplemental retirement benefits",
    "post-retirement medical benefits",
    "long-term care insurance",
    "dependent care flexible spending accounts",
    "health savings account contributions",
    "wellness program incentives",
    "employee assistance programs",
    "tuition assistance for executive's continuing education",
    "professional development courses and conferences",
    "subscriptions to industry publications and research",
    "home office setup and equipment",
    "broadband internet and mobile phone allowances",
    "personal technology devices (laptops, tablets, smartphones)",
    "software licenses for personal use",
    "cybersecurity protection for personal devices",
    "data backup and recovery services",
    "cloud storage subscriptions",
    "virtual private network (VPN)"
]

clawback_templates = [
    "{company} has adopted a clawback policy allowing recovery of incentive compensation in the event of a financial restatement",
    "Executive compensation is subject to recoupment under {company}\'s clawback policy in cases of misconduct or financial restatement",
    "The Board may require reimbursement of performance-based compensation under the clawback policy if performance goals are not actually achieved",
    "Incentive compensation paid to executives is subject to clawback provisions as required by the Dodd-Frank Act and SEC regulations",
]
# ========== MARKET PRICES AND TRADING ==========
stock_price_templates = [
    '{company} \'s common stock trades on the {exchange} under the ticker symbol "{ticker}"',
    "Shares of common stock closed at {currency_code}{amount} on {month} {end_day}, {year}, compared to {currency_code}{amount2} at {month} {end_day}, {prev_year}",
    "{company}\'s stock price ranged from a low of {currency_code}{amount} to a high of {currency_code}{amount2} during {year}",
    "Average daily trading volume was approximately {integer} shares during {year}",
    "{company}\'s market capitalization was approximately {currency_code}{amount} {money_unit} as of {month} {end_day}, {year}",
    "Shares outstanding totaled {shares} as of {month} {end_day}, {year}",
    "The closing stock price on {month} {end_day}, {year} represented a {amount2} of {pct}% from the prior year-end closing price",
]

exchanges = [
    "New York Stock Exchange",
    "NASDAQ Global Select Market",
    "NASDAQ Capital Market",
    "NYSE American",
    "London Stock Exchange",
]


trading_volume_templates = [
    "During {year}, approximately {integer} shares were traded on public exchanges",
    "{company}\'s shares experienced {volatility} trading activity during {year}",
    "Average daily trading volume increased {pct}% in {year} compared to {prev_year}",
    "Trading liquidity {increase_decrease} during {year}, with average daily volume of {integer} shares",
]

volatility_levels = ["elevated", "moderate", "reduced", "increased", "stable"]

# ========== ABOUT {company} / BUSINESS DESCRIPTION ==========
company_description_templates = [
    "{company} is a {industry} company that {mission_statement}",
    "{company} operates in the {industry} sector, providing {industry} to customers in {segment_names}",
    "{company} was founded in {year} and is headquartered in {city}, {state}",
    "{company} is a leading provider of {industry} serving the {segment_names} market",
    "{company}'s principal business activities are in {industry}",
    "{company} employs approximately {integer} people across {short_int} locations worldwide as of {month} {end_day}, {year}",
    "{company} operates through these reportable segments: {segment_names}",
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
    "pharmaceutical",
    "automotive",
    "aerospace",
    "hospitality",
    "real estate",
    "education",
    "media",
    "entertainment",
    "food and beverage",
    "agriculture",
    "mining",
    "construction",
    "transportation",
    "utilities",
    "insurance",
    "consulting",
    "software",
    "e-commerce",
    "semiconductor",
    "robotics",
    "artificial intelligence",
    "cybersecurity",
    "fintech",
    "biotech",
    "cleantech",
    "nanotechnology",
    "space exploration",
    "gaming",
    "fashion",
    "luxury goods",
    "sports",
    "publishing",
    "advertising",
    "public relations",
    "legal services",
    "environmental services",
    "security services",
    "logistics",
    "supply chain management",
    "human resources",
    "market research",
    "venture capital",
    "private equity",
    "investment banking",
    "asset management",
    "wealth management",
    "brokerage",
    "credit card services",
    "payment processing",
    "mortgage banking",
    "commercial banking",
    "retail banking",
    "investment management",
    "hedge fund",
    "mutual fund",
    "pension fund",
    "endowment fund",
    "sovereign wealth fund",
    "family office",
    "microfinance",
    "impact investing",
    "social enterprise",
    "non-profit",
    "government",
    "defense",
    "public safety",
    "healthcare IT",
    "medical devices",
    "diagnostics",
    "contract research organization (CRO)",
    "contract manufacturing organization (CMO)",
    "health insurance",
    "pharmacy benefits management (PBM)",
    "hospital management",
    "nursing home",
    "assisted living",
    "home healthcare",
    "telemedicine",
    "digital health",
    "medical tourism",
    "wellness",
    "fitness",
    "nutrition",
    "personal care",
]

mission_statements = [
    "develops, manufactures, and sells innovative products",
    "provides technology solutions and services to enterprise customers",
    "manufactures and distributes consumer products globally",
    "delivers healthcare services and medical devices",
    "operates a diversified portfolio of businesses",    
    "engages in research and development of new pharmaceuticals",
    "offers financial advisory and wealth management services",
    "produces and distributes energy resources",
    "operates a chain of retail stores",
    "provides telecommunications and internet services",
    "develops and markets software applications",
    "designs and manufactures automotive components",
    "provides aerospace and defense solutions",
    "manages a portfolio of hospitality properties",
    "invests in and develops real estate projects",
    "offers educational programs and online learning platforms",
    "produces and distributes media content and entertainment",
    "manufactures and sells food and beverage products",
    "engages in agricultural production and farming",
    "conducts mining operations and extracts natural resources",
    "provides construction and engineering services",
    "operates transportation and logistics networks",
    "generates and distributes utility services",
    "provides insurance products and risk management solutions",
    "offers management consulting and advisory services",
    "develops and sells e-commerce platforms and solutions",
    "manufactures semiconductor devices and integrated circuits",
    "develops and deploys robotics and automation technologies",
    "researches and applies artificial intelligence solutions",
    "provides cybersecurity products and services",
    "develops financial technology solutions and platforms",
    "engages in biotechnology research and development",
    "develops clean energy technologies and solutions",
    "researches and applies nanotechnology innovations",
    "engages in space exploration and satellite technology",
    "develops and publishes video games and interactive entertainment",
    "designs, manufactures, and sells fashion apparel and accessories",
    "produces and markets luxury goods and experiences",
    "operates sports teams, leagues, and events",
    "publishes books, magazines, and digital content",
    "provides advertising and marketing services",
    "offers public relations and communication strategies",
    "provides legal services and counsel",
    "offers environmental consulting and remediation services",
    "provides security services and solutions",
    "manages supply chains and logistics operations",
    "offers human resources consulting and talent management",
    "conducts market research and consumer insights analysis",
    "invests in early-stage companies and startups",
    "invests in and acquires private companies",
    "provides investment banking and corporate finance services",
]
segment_examples = [
    "Commercial, Consumer, and International",
    "Products, Services, and Solutions",
    "Domestic and International Operations",
    "Technology, Healthcare, and Industrial",    
    "North America, Europe, and Asia-Pacific",
    "Enterprise, Small Business, and Government",
    "Upstream, Midstream, and Downstream",
    "Retail Banking, Corporate Banking, and Wealth Management",
    "Automotive, Aerospace, and Defense",
    "Pharmaceuticals, Medical Devices, and Diagnostics",
    "Software, Hardware, and Services",
    "Residential, Commercial, and Industrial",
    "Fixed-line, Mobile, and Broadband",
    "Food, Beverage, and Home Care",
    "Mining, Metals, and Materials",
    "Construction, Engineering, and Infrastructure",
    "Passenger, Cargo, and Logistics",
    "Generation, Transmission, and Distribution",
    "Life, Property & Casualty, and Reinsurance",
    "Consulting, Advisory, and Outsourcing",
    "E-commerce, Cloud Services, and Digital Media",
    "Semiconductors, Displays, and Memory",
    "Robotics, Automation, and Artificial Intelligence",
    "Cybersecurity, Data Analytics, and IoT",
    "Fintech, Blockchain, and Digital Payments",
    "Biotechnology, Gene Therapy, and Personalized Medicine",
    "Solar, Wind, and Energy Storage",
    "Nanomaterials, Quantum Computing, and Advanced Manufacturing",
    "Space Launch, Satellite Services, and Earth Observation",
    "Console Gaming, PC Gaming, and Mobile Gaming",
    "Apparel, Footwear, and Accessories",
    "Luxury Fashion, Jewelry, and Watches",
    "Professional Sports, Collegiate Sports, and Esports",
    "Book Publishing, Magazine Publishing, and Digital Publishing",
    "Digital Advertising, Traditional Advertising, and Experiential Marketing",
    "Crisis Communications, Public Affairs, and Media Relations",
    "Corporate Law, Intellectual Property Law, and Litigation",
    "Environmental Consulting, Waste Management, and Recycling",
    "Physical Security, Cybersecurity, and Risk Management",
    "Freight Forwarding, Warehousing, and Distribution",
    "Talent Acquisition, HR Consulting, and Payroll Services",
    "Consumer Research, B2B Research, and Data Analytics",
    "Venture Capital, Growth Equity, and Private Debt",
    "Buyouts, Distressed Investing, and Infrastructure Funds",
    "Mergers & Acquisitions, Debt Capital Markets, and Equity Capital Markets",
]

# ========== HEDGE FUNDS AND INSTITUTIONAL OWNERSHIP ==========
institutional_ownership_templates = [
    "As of {month} {end_day}, {year}, institutional investors held approximately {pct}% of {company}\'s outstanding shares",
    "{company2} reported a {pct}% ownership stake in {company} as of {month} {end_day}, {year}",
    "{company}\'s largest shareholders include {company2} ({pct}%), {company3} ({pct2}%), and other institutional investors",
    "Beneficial ownership by institutional investors increased to {pct}% as of {month} {end_day}, {year}",
    "Hedge funds and asset managers collectively own approximately {pct}% of outstanding common stock",
    "{company2} disclosed a {pct}% position in {company} in its {form} filing dated {month} {year}",
    "Institutional ownership decreased from {pct2}% to {pct}% during {year}",
    "{company}\'s top ten institutional shareholders hold approximately {pct}% of outstanding shares",
]


sec_forms = ["Schedule 13G", "Schedule 13D", "Form 13F"]

insider_ownership_templates = [
    "Directors and executive officers collectively beneficially own approximately {pct}% of outstanding common stock as of {month} {end_day}, {year}",
    "{company}\'s Chief Executive Officer owns {shares} shares, representing {pct}% of shares outstanding",
    "Insider transactions during {year} included {shares} shares by executive officers and directors",
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
    "Forward-looking statements are based on management\'s current expectations and assumptions as of the date of this report",
    "Factors that could cause actual results to differ from forward-looking statements include {risk_factors}",
    "Investors should not place undue reliance on forward-looking statements, which speak only as of {month} {end_day}, {year}",
    "All forward-looking statements are qualified in their entirety by reference to the risk factors discussed in Item 1A of this report",
]

forward_looking_topics = [
    "expected financial performance, growth strategies, and market opportunities",
    "anticipated product launches, regulatory approvals, and business development initiatives",
    "projected capital expenditures, cost reduction initiatives, and operational improvements",
    "expected market conditions, competitive dynamics, and customer demand",    
    "future liquidity, capital resources, and financing plans",
    "potential acquisitions, divestitures, and strategic alliances",
    "legal proceedings, regulatory developments, and compliance matters",
    "impact of macroeconomic conditions and geopolitical events",
    "research and development outcomes and intellectual property protection",
    "supply chain disruptions and raw material availability",
    "cybersecurity risks and data privacy concerns",
    "talent acquisition, retention, and workforce management",
    "environmental, social, and governance (ESG) initiatives",
    "dividend policy and share repurchase programs",
    "tax rates and accounting policy changes",
    "foreign currency exchange rates and interest rate fluctuations",
    "seasonality and cyclicality of business operations",
    "customer relationships and concentration risks",
    "technological advancements and industry trends",
    "brand reputation and public perception",
    "litigation and regulatory enforcement actions",
    "product liability and warranty claims",
    "insurance coverage and indemnification arrangements",
    "catastrophic events and business continuity plans",
    "changes in consumer preferences and spending patterns",
    "competitive landscape and market share shifts",
    "pricing strategies and promotional activities",
    "distribution channels and sales force effectiveness",
    "marketing and advertising campaigns",
    "customer service and support operations",
    "product development lifecycle and innovation pipeline",
    "manufacturing capacity and production efficiency",
    "quality control and assurance processes",
    "inventory management and supply chain optimization",
    "logistics and transportation networks",
    "information technology systems and infrastructure",
    "data analytics and business intelligence capabilities",
    "research and clinical trial outcomes",
    "regulatory approval processes for new products",
    "patent protection and intellectual property disputes",
    "commercialization strategies and market access",
    "reimbursement policies and healthcare reforms",
    "drug pricing pressures and affordability concerns",
    "patient safety and adverse event reporting",
    "ethical considerations in research and development",
    "public health crises and pandemics",
    "environmental regulations and sustainability practices",
    "social impact and community engagement",
    "corporate governance and board oversight",
    "executive compensation and incentive structures",
    "shareholder activism and investor relations",
    "debt covenants and financial ratios",
    "credit ratings and access to capital markets",
    "merger and acquisition integration risks",
    
]

forward_looking_words = [
    "expects, anticipates, intends, plans, believes, seeks, estimates, may, will, should, would, could",
    "projects, forecasts, targets, goals, likely, potential, continue, future, outlook",
    "positioned, strategy, opportunity, momentum, trajectory",    
    "guidance, vision, mission, objective, aspiration",
    "predict, speculate, surmise, hypothesize, presume",
    "endeavor, strive, aim, aspire, pursue",
    "commit, dedicate, pledge, promise, guarantee",
    "anticipate, foresee, envision, imagine, contemplate",
    "intend, propose, plan, design, schedule",
    "believe, trust, confide, rely, depend",
    "seek, search, explore, investigate, discover",
    "estimate, appraise, assess, evaluate, judge",
    "may, might, can, could, possibly",
    "will, shall, must, ought, should",
    "would, could, might, possibly, perhaps",
    "project, extrapolate, infer, deduce, conclude",
    "forecast, predict, prognosticate, prophesy, divine",
    "target, objective, aim, goal, aspiration",
    "likely, probable, plausible, credible, conceivable",
    "potential, prospective, possible, latent, inherent",
    "continue, persist, endure, maintain, sustain",
    "future, forthcoming, upcoming, impending, imminent",
    "outlook, prospect, perspective, view, expectation",
    "positioned, situated, placed, located, arranged",
    "strategy, tactic, plan, approach, method",
    "opportunity, chance, possibility, opening, break",
    "momentum, impetus, drive, thrust, force",
    "trajectory, path, course, route, amount2",
]

risk_factors_examples = [
    "economic conditions, competitive pressures, regulatory changes, and operational challenges",
    "market volatility, supply chain disruptions, technological changes, and geopolitical events",
    "customer demand fluctuations, pricing pressures, and execution risks",
    "cybersecurity threats, intellectual property risks, and litigation uncertainties",    
    "reliance on key personnel, product development risks, and financing availability",    
    "changes in consumer preferences, brand reputation, and marketing effectiveness",
    "interest rate fluctuations, foreign currency exchange rates, and commodity price volatility",
    "natural disasters, public health crises, and other catastrophic events",
    "changes in accounting standards, tax laws, and government regulations",
    "integration risks associated with mergers and acquisitions",
    "dependence on third-party suppliers and manufacturers",
    "product liability claims and warranty obligations",
    "environmental regulations and sustainability initiatives",
    "labor disputes and workforce availability",
    "political instability and trade policies",
    "disruptions to information technology systems",
    "failure to protect intellectual property rights",
    "litigation and regulatory investigations",
    "changes in credit ratings and access to capital markets",
    "seasonality of business operations",
    "concentration of customers or suppliers",
    "competition from new market entrants",
    "inability to attract and retain qualified employees",
    "adverse publicity or reputational damage",
    "failure to adapt to technological advancements",
    "risks associated with international operations",
    "changes in consumer spending patterns",
    "impact of inflation or deflation",
    "changes in energy costs",
    "geopolitical conflicts and trade wars",
    "pandemics and other public health emergencies",
    "climate change and extreme weather events",
    "data breaches and cybersecurity incidents",
    "regulatory compliance costs",
    "product recalls and safety concerns",
    "disruptions in transportation and logistics",
    "changes in raw material prices",
    "dependence on key patents or licenses",
    "challenges in new product development and commercialization",
    "failure to meet performance expectations",
    "loss of key customers or contracts",
    "increased competition and pricing pressures",
    "adverse changes in economic conditions",
    "changes in government policies or regulations",
    "unfavorable legal or regulatory outcomes",
    "difficulty in integrating acquired businesses",
    "fluctuations in foreign exchange rates",
    "changes in interest rates",
    "inability to obtain adequate financing",
    "decline in market demand for products or services",
    "technological obsolescence",
    "disruptions in supply chain",
    "loss of intellectual property protection",
    "damage to brand reputation",
    "natural disasters or other catastrophic events",
]

safe_harbor_templates = [
    "Statements in this report that are not historical facts constitute forward-looking statements subject to the safe harbor provisions of the Private Securities Litigation Reform Act",
    "{company} includes forward-looking statements to provide investors with its current expectations and projections, but cautions that such statements involve risks",
    "Safe harbor statement: Except for historical information, this report contains forward-looking statements that involve substantial risks and uncertainties",
    "This document contains forward-looking statements that are protected by the safe harbor provisions for such statements",
]

# ========== ANALYST COVERAGE AND ESTIMATES ==========
analyst_coverage_templates = [
    "{company} is currently covered by {short_int} equity research analysts",
    "Analyst consensus estimates for {year} project earnings per share of {currency_code}{amount} and revenue of {currency_code}{amount} {money_unit}",
    "The average analyst price target is {currency_code}{company2}, representing {amount2} of {pct}% from current levels",
    "{small_int} analysts have buy ratings, {short_int} have hold ratings, and {short_int2} have sell ratings on the stock",
    "Analyst estimates for {year} range from {currency_code}{amount} to {currency_code}{amount2} per share",
    "{company} does not provide guidance but is followed by several sell-side analysts who publish earnings estimates",
]

# ========== CREDIT RATINGS ==========
credit_rating_templates = [
    "{company}\'s senior unsecured debt is rated {rating} by {agency} and {rating2} by {agency2}",
    "{agency} maintains a {rating} credit rating on {company} with a {outlook} outlook",
    "As of {month} {end_day}, {year}, {company} holds investment-grade credit ratings from major rating agencies",
    "{company}\'s credit ratings are {rating} ({agency}), {rating2} ({agency2}), and {rating3} ({agency3})",
    "In {month} {year}, {agency} {rating_action} {company}\'s credit rating to {rating}",
    "{company} targets maintaining investment-grade credit metrics and ratings",
]

credit_agencies = ["Standard & Poor\'s", "Moody\'s", "Fitch Ratings"]
credit_ratings = ["BBB+", "BBB", "BBB-", "A-", "A", "Baa1", "Baa2", "Baa3"]
rating_outlooks = ["stable", "positive", "negative", "under review"]
rating_actions = ["upgraded", "downgraded", "affirmed", "revised"]

# ========== DIVIDEND AND CAPITAL ALLOCATION ==========
dividend_policy_templates = [
    "{company} has paid consecutive quarterly dividends since {year}",
    "In {month} {year}, the Board of Directors declared a quarterly dividend of {currency_code}{amount} per share, payable on {month} {end_day}, {year}",
    "The dividend payout ratio was {pct}% for {year}, compared to {pct2}% in {prev_year}",
    "{company} targets returning {pct}% to {pct2}% of free cash flow to shareholders through dividends and share repurchases",
    "Annual dividends totaled {currency_code}{amount} per share in {year}, representing a yield of {pct}% based on year-end stock price",
    "{company} does not currently pay a dividend and retains earnings to fund growth initiatives",
    "Dividend policy is reviewed annually by the Board of Directors based on earnings, cash flows, and capital allocation priorities",
]

share_repurchase_templates = [
    "During {year}, {company} repurchased {shares} shares of common stock for {currency_code}{amount} {money_unit}",
    "The Board of Directors authorized a {currency_code}{amount} {money_unit} share repurchase program in {month} {year}",
    "As of {month} {end_day}, {year}, {currency_code}{amount} {money_unit} remained available under the current repurchase authorization",
    "Share repurchases totaled {currency_code}{amount} {money_unit} in {year}, compared to {currency_code}{amount2} {money_unit} in {prev_year}",
    "{company} opportunistically repurchases shares based on market conditions, capital requirements, and alternative investment opportunities",
    "No shares were repurchased during {year} as {company} prioritized debt reduction and organic growth investments",
]

# ========== COMPETITIVE LANDSCAPE ==========
competition_templates = [
    "{company} operates in a highly competitive industry characterized by {competitive_characteristics}",
    "Principal competitors include {company2}, and {company3}",
    "{company} competes based on {competitive_factors}",
    "Market share in {company}\'s primary markets remained relatively stable at approximately {pct}% during {year}",
    "Competitive pressures have intensified due to {competitive_pressure_reasons}",
    "{company} believes it maintains competitive advantages through {competitive_advantages}",
    "Industry consolidation during {year} included the merger of {company2} and {company3}",
]

competitive_characteristics = [
    "rapid technological change, evolving customer preferences, and new market entrants",
    "price competition, product innovation, and service quality",
    "consolidation, globalization, and regulatory complexity",
    "low barriers to entry and commoditization pressures",    
    "intense rivalry, rapid product cycles, and significant capital investment requirements",
    "fragmented market, diverse customer needs, and regional variations",
    "high switching costs, established brand loyalties, and network effects",
    "disruptive technologies, changing business models, and evolving consumer behavior",
]

competitive_factors = [
    "product innovation, quality, and reliability",
    "pricing, customer service, and brand reputation",
    "distribution channels, marketing effectiveness, and geographic reach",
    "technological leadership, intellectual property, and research and development capabilities",
    "cost efficiency, operational excellence, and supply chain management",
    "speed to market, customization, and responsiveness to customer needs",
    "financial strength, access to capital, and strategic partnerships",
    "talent acquisition, employee retention, and organizational culture",
    "regulatory compliance, ethical practices, and corporate social responsibility",
    "data analytics, artificial intelligence, and digital transformation initiatives",
    "sustainability practices, environmental stewardship, and social impact",
    "customer experience, personalization, and loyalty programs",
    "product breadth and depth, solution integration, and ecosystem development",
    "global presence, local market adaptation, and cultural understanding",
    "after-sales support, maintenance services, and customer success programs",
    "security features, data privacy protection, and trust",
    "scalability, flexibility, and adaptability to market changes",
    "innovation pipeline, future product roadmap, and disruptive potential",
    "brand recognition, brand equity, and brand loyalty",
    "sales force effectiveness, channel partner relationships, and market access",
    "manufacturing capabilities, production capacity, and quality control",
    "supply chain resilience, risk management, and business continuity",
    "research and development investment, patent portfolio, and trade secrets",
    "customer feedback integration, product iteration, and continuous improvement",
    "employee engagement, talent development, and diversity and inclusion",
    "corporate governance, transparency, and stakeholder relations",
    "financial performance, profitability, and shareholder returns",
    "market share, growth rate, and competitive positioning",
    "strategic vision, leadership, and execution capabilities",
    "agility, responsiveness, and ability to pivot quickly",
    "customer acquisition cost, customer lifetime value, and churn rate",
    "return on investment, capital efficiency, and asset utilization",
]

competitive_factors = [
    "product quality, innovation, customer service, and brand reputation",
    "pricing, technology, distribution capabilities, and scale",
    "breadth of product portfolio, technical expertise, and customer relationships",
    "operational efficiency, time to market, and total cost of ownership",    
    "speed of delivery, customization options, and after-sales support",
    "supply chain resilience, sustainability practices, and ethical sourcing",
    "data security, privacy protection, and compliance with regulations",
    "talent acquisition, employee retention, and organizational culture",
    "financial strength, access to capital, and investment in R&D",
    "geographic reach, market penetration, and distribution network",
    "intellectual property portfolio, patents, and trade secrets",
    "customer loyalty programs, personalized experiences, and brand equity",
    "digital transformation capabilities, e-commerce platforms, and online presence",
    "strategic partnerships, alliances, and ecosystem development",
    "regulatory compliance, risk management, and corporate governance",
    "social responsibility, environmental stewardship, and community engagement",
    "product differentiation, unique features, and value proposition",
    "cost leadership, economies of scale, and efficient operations",
    "innovation pipeline, research and development investments, and new product introductions",
    "customer support, technical assistance, and service level agreements",
    "brand recognition, reputation, and public perception",
    "distribution channels, sales force effectiveness, and market access",
    "marketing and advertising effectiveness, brand messaging, and promotional activities",
    "supply chain management, inventory optimization, and logistics efficiency",
    "manufacturing capabilities, production capacity, and quality control",
    "research and development capabilities, scientific expertise, and clinical trial success",
    "regulatory affairs, compliance with health and safety standards, and product approvals",
    "intellectual property protection, patent enforcement, and trade secret safeguarding",
    "data analytics, artificial intelligence, and machine learning capabilities",
    "cybersecurity measures, data privacy protocols, and information security systems",
    "talent management, employee training, and leadership development",
    "financial performance, profitability, and return on investment",
    "capital structure, debt management, and liquidity position",
    "corporate social responsibility, ethical business practices, and sustainability initiatives",
    "governance structure, board independence, and shareholder rights",
    "risk assessment, mitigation strategies, and crisis management plans",
    "customer relationship management, customer satisfaction, and retention rates",
    "product portfolio management, lifecycle planning, and market segmentation",
    "pricing strategies, competitive positioning, and market share analysis",
    "sales and marketing effectiveness, lead generation, and conversion rates",
    
]
competitive_pressure_reasons = [
    "intensified competition",
    "new market entrants, pricing pressures, and technological disruption, and evolving customer preferences",
    "increased competition from global players and low-cost providers",
    "rapid technological advancements and shorter product lifecycles",
    "changes in consumer behavior and demand patterns",
    "regulatory changes and increased compliance costs",
    "supply chain disruptions and raw material price volatility",
    "economic downturns and reduced consumer spending",
    "consolidation among competitors and customers",
    "emergence of substitute products or services",
    "intellectual property infringement and counterfeiting",
    "talent shortages and increased labor costs",
    "cybersecurity threats and data breaches",
    "geopolitical instability and trade barriers",
    "environmental concerns and sustainability pressures",
    "brand erosion and reputational damage",
    "aggressive marketing and promotional activities by rivals",
    "disintermediation by online platforms and direct-to-consumer models",
    "fragmentation of media and advertising channels",
    "changing distribution channels and retail landscape",
    "increased customer expectations for personalization and convenience",
    "pressure to innovate and differentiate products/services",
    "difficulty in scaling operations and achieving economies of scale",
    "limited access to capital for expansion and investment",
    "high fixed costs and operating leverage",
    "dependence on a few key customers or suppliers",
    "seasonality and cyclicality of demand",
    "currency fluctuations and foreign exchange risks",
    "political interference and government intervention",
    "social and demographic shifts affecting target markets",
    "ethical considerations and corporate social responsibility demands",
    "activist investors and shareholder pressure",
    "litigation and legal challenges from competitors or regulators",
    "product recalls and safety concerns",
    "difficulty in attracting and retaining skilled employees",
    "rising healthcare and employee benefit costs",
    "inflationary pressures on input costs",
    "disruptive business models and platform competition",
    "changes in intellectual property laws and enforcement",
    "increased scrutiny from consumer advocacy groups",
    "pressure to reduce carbon footprint and environmental impact",
    "challenges in managing global supply chains",
    "rapid changes in fashion and design trends",
    "shortage of critical components or raw materials",
    "overcapacity in the industry leading to price wars",
    "difficulty in forecasting demand accurately",
    "impact of new trade agreements or tariffs",
    "political instability in key markets",
    ]

competitive_advantages = [
    "proprietary technology, strong brand recognition, and established customer relationships",
    "economies of scale, operational excellence, and global footprint",
    "intellectual property portfolio, innovation capabilities, and market leadership",
    "vertically integrated operations, cost structure, and distribution network",   
    "superior product quality, customer service, and supply chain efficiency",
    "differentiated product offerings, unique value proposition, and strong brand loyalty",
    "advanced research and development capabilities, rapid product innovation, and speed to market",
    "strategic partnerships, exclusive agreements, and extensive distribution channels",
    "robust financial position, access to capital, and ability to invest in growth initiatives",
    "highly skilled workforce, strong corporate culture, and effective talent management",
    "data-driven insights, advanced analytics, and artificial intelligence applications",
    "sustainable business practices, environmental stewardship, and social responsibility initiatives",
    "strong regulatory compliance, ethical governance, and risk management framework",
    "global presence, localized market strategies, and cultural adaptability",
    "customer-centric approach, personalized experiences, and high customer satisfaction",
    "efficient manufacturing processes, low production costs, and economies of scale",
    "strong intellectual property protection, patent portfolio, and trade secret safeguards",
    "agile development methodologies, rapid prototyping, and continuous improvement",
    "effective marketing and branding strategies, strong brand equity, and consumer trust",
    "robust cybersecurity measures, data privacy protocols, and information security systems",
    "strategic acquisitions, successful integration, and synergistic growth",
    "diversified product portfolio, multiple revenue streams, and reduced reliance on single products",
    "strong balance sheet, low debt levels, and financial flexibility",
    "experienced management team, visionary leadership, and effective execution",
    "strong relationships with suppliers, favorable terms, and reliable supply chain",
    "advanced logistics and distribution networks, efficient delivery, and reduced lead times",
    "superior product design, aesthetics, and user experience",
    "comprehensive after-sales support, maintenance services, and customer success programs",
    "strong community engagement, corporate social responsibility, and positive public image",
    "adaptability to market changes, resilience to disruptions, and strategic agility",
    "access to unique resources, proprietary technologies, and specialized expertise",
    "strong regulatory relationships, compliance expertise, and favorable policy environment",
    "effective capital allocation, disciplined investment, and strong return on capital",
    "robust risk management framework, proactive identification of threats, and mitigation strategies",
    "strong corporate governance, transparent reporting, and ethical business practices",
    "employee empowerment, continuous learning, and innovation culture",
    "strong brand recognition, customer loyalty",
]

# ========== REGULATORY AND COMPLIANCE ==========
regulatory_templates = [
    "{company} is subject to extensive regulation by {regulatory_agencies} governing {regulatory_areas}",
    "Compliance with environmental, health, and safety regulations resulted in costs of approximately {currency_code}{amount} {money_unit} during {year}",
    "Changes in regulatory requirements could materially impact {company}\'s business operations and financial results",
    "{company} maintains compliance programs and internal controls to ensure adherence to applicable laws and regulations",
    "Regulatory approvals obtained during {year} include {regulatory_approvals}",
    "Pending regulatory matters include {regulatory_matters}",
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
    "healthcare regulations, pharmaceutical manufacturing, and medical device approvals",
    "telecommunications licensing, spectrum allocation, and network neutrality",
    "banking regulations, financial stability, and consumer lending laws",
    "energy production, transmission, and environmental emissions",
    "food safety, labeling, and agricultural subsidies",
    "mining safety, environmental impact, and resource extraction permits",
    "construction safety, building codes, and zoning regulations",
    "transportation safety, vehicle emissions, and driver qualifications",
    "utility rate setting, service reliability, and infrastructure development",
    "insurance solvency, policy terms, and consumer protection",
    "securities laws, corporate governance, and investor protection",
    "antitrust laws, competition policy, and merger reviews",
    "intellectual property rights, patent enforcement, and copyright protection",
    "environmental regulations, pollution control, and hazardous waste management",
    "labor laws, workplace safety, and employee benefits",
    "tax laws, transfer pricing, and international taxation",
    "data protection, privacy regulations (e.g., GDPR, CCPA), and cross-border data flows",
    "cybersecurity standards, incident reporting, and data breach notification",
    "anti-money laundering (AML) and counter-terrorist financing (CTF) regulations",
    "sanctions and export controls",
    "consumer credit protection, fair lending practices, and debt collection",
    "advertising and marketing regulations, truth in advertising, and unfair competition",
    "product liability, warranty laws, and consumer remedies",
    "occupational health and safety standards",
    "import and export duties, customs regulations, and trade agreements",
    "foreign investment regulations and national security reviews",
    "anti-corruption laws (e.g., FCPA, UK Bribery Act)",
    "public procurement regulations and government contracting",
    "accessibility standards for persons with disabilities",
    "animal welfare regulations (for certain industries)",
    "biotechnology regulations, genetic engineering, and clinical trials",
    "nanotechnology safety and environmental impact",
    "space commercialization regulations and satellite licensing",
    "gaming regulations, online gambling, and consumer protection",
    "fashion industry regulations, labor practices, and sustainability standards",
    "luxury goods regulations, anti-counterfeiting, and ethical sourcing",
    "sports regulations, athlete welfare, and anti-doping policies",
]

# ========== INSURANCE AND RISK MANAGEMENT ==========
insurance_templates = [
    "{company} maintains insurance coverage for property, casualty, general liability, and other risks in amounts considered adequate",
    "Self-insurance reserves totaled {currency_code}{amount} {money_unit} as of {month} {end_day}, {year}",
    "{company} self-insures certain risks including {self_insured_risks} and purchases insurance for catastrophic losses",
    "Insurance recoveries during {year} totaled {currency_code}{amount} {money_unit} related to {insurance_incident}",
    "{company}\'s insurance program includes coverage for {insurance_coverage_types} with policy limits and deductibles based on industry practices",
    "Risk retention levels are evaluated annually based on claims experience and insurance market conditions",
]

self_insured_risks = [
    "workers' compensation, general liability, and employee health benefits",
    "product liability, auto liability, and property damage below certain thresholds",
    "employment practices liability and certain cyber risks",    
    "business interruption and supply chain disruptions",
    "medical malpractice and professional liability",
    "environmental liabilities and pollution cleanup costs",
    "data breaches and cybersecurity incidents",
    "directors' and officers' liability",
    "property damage from natural disasters",
    "vehicle fleet damage and third-party auto claims",
    "employee disability and long-term care",
    "certain legal defense costs and settlements",
    "reputational damage and brand impairment",
    "product recalls and warranty claims",
    "intellectual property infringement claims",
    "political risk and expropriation",
    "terrorism and sabotage",
    "kidnap and ransom",
    "fidelity and crime losses",
    "errors and omissions",
    "construction defects",
    "maritime liabilities",
    "aviation liabilities",
    "energy infrastructure damage",
    "agricultural crop losses",
    "livestock mortality",
    "forest fire damage",
    "cyber extortion and ransomware attacks",
    "regulatory fines and penalties (where insurable)",
    "employment discrimination claims",
    "wage and hour violations",
    "pension and benefits liabilities",
    "catastrophic health claims for employees",
    "certain aspects of clinical trial risks",
    "research and development failures",
    "market access and reimbursement risks",
    "supply chain financing risks",
    "trade credit risks",
    "foreign exchange fluctuations",
    "interest rate volatility",
    "commodity price risks",
    "customer credit defaults",
    "vendor non-performance",
    "contractual indemnities",
    "tax audit defense costs",
    "customs and duties disputes",
    "environmental permit violations",
    "waste disposal liabilities",
    "hazardous material spills",
    "product obsolescence",
    "technological failures",
    "software defects",
    "hardware malfunctions",
    "network outages",
    "data loss and corruption",
    "system downtime",
    "cloud service interruptions",
    "third-party service provider failures",
    "loss of key personnel",
    "employee fraud and theft",
    "workplace violence",
    "strikes and labor unrest",
    "reputational harm from social media",
    "product tampering",
    "counterfeiting and piracy",
]

coverage_types = [
    "property damage, business interruption, product liability, and directors and officers liability",
    "cyber liability, errors and omissions, fiduciary liability, and environmental liability",
    "general liability, auto liability, workers' compensation, and excess umbrella coverage",    
    "marine cargo, aviation hull and liability, and political risk insurance",
    "medical malpractice, professional indemnity, and clinical trial insurance",
    "construction all risks, performance bonds, and surety bonds",
    "trade credit, political risk, and foreign investment insurance",
    "kidnap and ransom, terrorism, and war risk insurance",
    "fidelity, crime, and cyber fraud insurance",
    "environmental impairment liability and pollution legal liability",
    "employment practices liability and wage and hour insurance",
    "intellectual property infringement and patent defense insurance",
    "product recall and contamination insurance",
    "supply chain disruption and contingent business interruption insurance",
    "data breach response and cyber extortion insurance",
    "directors and officers liability, employment practices liability, and fiduciary liability",
    "general liability, product liability, and completed operations liability",
    "commercial property, business interruption, and equipment breakdown",
    "workers' compensation, employer's liability, and occupational accident",
    "commercial auto, fleet, and non-owned auto liability",
    "umbrella and excess liability for increased limits",
    "professional liability (errors and omissions) for service providers",
    "cyber liability for data breaches, network security, and privacy",
    "environmental liability for pollution and contamination risks",
    "marine cargo and hull for goods in transit and vessels",
    "aviation hull and liability for aircraft and operations",
    "political risk for expropriation, war, and civil unrest",
    "trade credit for protection against customer insolvency",
    "fidelity and crime for employee dishonesty and fraud",
    "kidnap, ransom, and extortion for personnel protection",
    "terrorism and sabotage for acts of terrorism",
    "product recall for costs associated with product withdrawal",
    "warranty and extended warranty programs",
    "construction all risks for project-specific coverage",
    "surety bonds for contractual obligations",
    "medical malpractice for healthcare providers",
    "clinical trials for research and development risks",
    "event cancellation and non-appearance",
    "media liability for defamation and copyright infringement",
    "privacy liability for regulatory fines and penalties",
    "contingent business interruption for supply chain failures",
    "contingent property damage for dependent properties",
    "difference in conditions/difference in limits for international programs",
    "foreign package for international operations",
]
insurance_incidents = [
    "property damage", 
    "business interruption", 
    "product liability claims",     
    "cybersecurity incident",
    "natural disaster",
    "supply chain disruption",
    "litigation settlement",
    "environmental remediation",
    "employee injury",
    "auto accident",
    "theft or fraud",
    "data breach",
    "fire damage",
    "water damage",
    "storm damage",
    "earthquake damage",
    "vandalism",
    "equipment breakdown",
    "loss of inventory",
    "cargo damage",
    "professional negligence",
    "medical malpractice",
    "directors and officers liability claims",
    "employment practices liability claims",
    "fiduciary liability claims",
    "errors and omissions claims",
    "pollution incident",
    "product recall event",
    "political violence",
    "kidnapping incident",
    "extortion threat",
    "employee dishonesty",
    "computer fraud",
    "funds transfer fraud",
    "counterfeiting",
    "intellectual property infringement",
    "breach of contract",
    "construction defect",
    "maritime accident",
    "aviation accident",
    "energy infrastructure failure",
    "crop failure",
    "livestock disease",
    "forest fire",
    "ransomware attack",
    "regulatory fine",
    "wage and hour dispute",
    "pension liability",
    "catastrophic health event",
    "clinical trial adverse event",
    "research and development failure",
    "market access issue",
    "supply chain financing loss",
    "trade credit default",
    "foreign exchange loss",
    "interest rate swap loss",
    "commodity price fluctuation",
    "customer credit default",
    "vendor non-performance",
    "contractual indemnity claim",
    "tax audit disallowance",
    "customs duty dispute",
    "environmental permit violation",
    "hazardous waste spill",
    "product obsolescence",
    "technological failure",
    "software bug",
    "hardware malfunction",
    "network outage",
    "data loss",
    "system downtime",
    "cloud service interruption",
    "third-party service provider failure",
    "loss of key personnel",
    "workplace violence incident",
    "labor strike",  
    "workers' compensation", 
    "employee health benefits"
]


# ========== FOREIGN CURRENCY RISK/TRANSLATION (NON-DERIVATIVE) ==========

foreign_currency_exposure_templates = [
    "{company}\'s operating results are affected by changes in commodity prices, particularly {commodities}",
    "{company} is exposed to price volatility for key raw materials including {commodities}",
    "Commodity price fluctuations, particularly for {commodities}, can significantly impact {company}\'s cost structure and margins",
    "Raw material costs are subject to market volatility, with {commodities} prices ranging from {currency_code}{amount} to {currency_code}{amount2} per {unit} during {year}",
    "{company}\'s operations are sensitive to changes in {commodities} prices, which can affect both revenue and cost of sales",
]
foreign_currency_exposure_templates = [
    "{company} operates in multiple countries and is exposed to foreign currency exchange rate fluctuations {major_currency} in that affect reported revenues and expenses",
    "{company}'s international operations subject it to foreign currency risks, primarily related to the {major_currency}, {currency2}, and {currency3}",
    "Foreign currency transaction in {major_currency} gains and losses are recorded in {location} as incurred",
    "Substantially all of {company}\'s foreign subsidiaries use {major_currency} as their local currency",
    "{company}\'s results of operations are affected by changes in foreign currency exchange rates, particularly movements in the {major_currency} and {currency2}",
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
    "{company} recorded foreign currency transaction losses of {currency_code}{amount} {money_unit} in {year} compared to gains of {currency_code}{amount2} {money_unit} in {prev_year}",
    "Foreign exchange gains and losses on remeasurement of monetary assets and liabilities totaled {currency_code}{amount} {money_unit} in {year}",
    "Transaction gains and losses on foreign currency ({major_currency}) denominated receivables and payables are recognized in earnings as exchange rates fluctuate",
]

functional_currency_templates = [
    "The functional currency for most of {company}\'s foreign subsidiaries is the local currency of the country in which the subsidiary operates",
    "For subsidiaries operating in highly inflationary economies, the {major_currency} is used as the functional currency",
    "{company} determines the functional currency of each subsidiary based on the primary economic environment in which the entity operates",
    "The functional currencies of {company}\'s significant foreign operations include the {major_currency}, {currency2}, and {currency3}",
    "Remeasurement of foreign subsidiary financial statements from local currency to functional currency resulted in gains of {currency_code}{amount} {money_unit} in {year}",
]

fx_impact_on_results_templates = [
    "Foreign currency exchange rate fluctuations had an unfavorable impact on revenues of approximately {currency_code}{amount} {money_unit}, or {pct}%, during {year}",
    "Changes in foreign exchange rates negatively impacted operating income by {currency_code}{amount} {money_unit} in {year}",
    "Foreign currency movements had a favorable effect on revenues of {pct}% in {year}, primarily due to strengthening of the {major_currency}",
    "Excluding the impact of foreign currency translation, revenues would have increased {pct}% in {year} compared to {prev_year}",
    "The translation impact of changes in foreign exchange rates decreased reported revenues by {currency_code}{amount} {money_unit} year-over-year",
    "On a constant currency basis, revenues increased {pct}% compared to the prior year, versus {pct2}% on a reported basis",
]

intercompany_fx_templates = [
    "{company} has intercompany loans denominated in various currencies that are remeasured each reporting period with gains and losses recorded in earnings",
    "Intercompany foreign currency transactions resulted in remeasurement losses of {currency_code}{amount} {money_unit} during {year}",
    "{company} has {currency_code}{amount} {money_unit} in intercompany receivables denominated in {major_currency} as of {month} {end_day}, {year}",
    "Remeasurement of intercompany balances denominated in currencies other than the functional currency resulted in losses of {currency_code}{amount} {money_unit} in {year}",
]

# ========== COMMODITY PRICES/RISK/INVENTORY (NON-DERIVATIVE) ==========

commodity_price_exposure_templates = [
    "{company}\'s operating results are affected by changes in commodity prices, particularly {commodities}",
    "{company} is exposed to price volatility for key raw materials including {commodities}",
    "Commodity price fluctuations, particularly for {commodities}, can significantly impact {company}\'s cost structure and margins",
    "Raw material costs are subject to market volatility, with {commodities} prices ranging from {currency_code}{amount} to {currency_code}{amount2} per {unit} during {year}",
    "{company}\'s operations are sensitive to changes in {commodities} prices, which can affect both revenue and cost of sales",
]

commodity_cost_impact_templates = [
    "Commodity price increases added approximately {currency_code}{amount} {money_unit} to cost of goods sold during {year}",
    "Changes in {commodities} prices unfavorably impacted gross margin by {pct} percentage points in {year}",
    "{company} experienced cost inflation of {currency_code}{amount} {money_unit} in {year}, primarily driven by higher {commodities} prices",
    "Commodity costs increased {pct}% year-over-year, driven primarily by {commodities} price appreciation",
    "Raw material price increases, particularly for {commodities}, reduced gross profit margin from {pct2}% to {pct}% in {year}",
    "{company} absorbed {currency_code}{amount} {money_unit} in commodity cost inflation during {year} through operational efficiencies and pricing actions",
]

commodity_inventory_valuation_templates = [
    "{company} maintains inventory of {commodities} to support production requirements, exposing {company} to price risk",
    "As of {month} {end_day}, {year}, {company} held {integer} {unit} of {commodities} inventory valued at {currency_code}{amount} million",
    "{company} recorded an inventory writedown of {currency_code}{amount} {money_unit} in {year} due to declines in {commodities} market prices",
    "Commodity inventory is stated at the lower of cost or net realizable value, with cost determined using the {inventory_method} method",
    "{company}\'s inventory includes {currency_code}{amount} {money_unit} of raw materials subject to commodity price volatility",
    "{company} recognized a {currency_code}{amount} {money_unit} charge related to excess and obsolete {commodities} inventory in {year}",
]

commodity_pricing_strategies_templates = [
    "{company} generally seeks to pass through commodity cost changes to customers through pricing mechanisms, though timing differences can affect margins",
    "{company} has implemented price increases totaling {pct}% to offset {commodities} cost inflation during {year}",
    "Pricing adjustments are typically implemented with a {small_int}-month lag following changes in {commodities} costs",
    "{company} utilizes index-based pricing formulas for certain products to mitigate the impact of {commodities} price volatility",
    "Customer contracts include provisions that allow {company} to adjust prices in response to significant {commodities} cost movements",
]

commodity_supply_risk_templates = [
    "{company} sources {commodities} from multiple suppliers to mitigate supply chain disruption risk",
    "{company} maintains strategic inventory of {commodities} to buffer against potential supply disruptions",
    "Supply constraints for {commodities} during {year} resulted in increased costs and temporary production delays",
    "{company} has long-term supply agreements for {commodities} covering approximately {pct}% of anticipated requirements",
    "{company} is exposed to concentration risk as {pct}% of {commodities} is sourced from a single region",
]

commodity_exposure_quantification_templates = [
    "A {pct}% change in {commodities} prices would impact annual cost of sales by approximately {currency_code}{amount} {money_unit}",
    "{company} estimates that commodity price volatility could affect operating income by {currency_code}{amount} {money_unit} annually",
    "Each {currency_code}{amount2} per {unit} change in {commodities} prices impacts annual costs by approximately {currency_code}{amount} {money_unit}",
    "Commodity exposure is concentrated in {commodities} ({pct}% of raw material spend)",
]

physical_commodity_operations_templates = [
    "{company} owns and operates {commodities} production facilities with annual capacity of {short_int2} {unit}",
    "{company} produced {short_int2} {unit} of {commodities} during {year}, a {pct}% increase from the prior year",
    "{company}\'s {commodities} operations generated revenues of {currency_code}{amount} {money_unit} in {year}",
    "Production costs for {commodities} averaged {currency_code}{amount} per {unit} in {year}, compared to {currency_code}{amount2} in {prev_year}",
    "{company} maintains proved reserves of {short_int2} {unit} of {commodities} as of {month} {end_day}, {year}",
]

# ========== SHARED / GENERIC ==========
shared_issuers = [
    "FASB",
    "Financial Accounting Standards Board",
    "SEC",
    "IASB",
    "International Accounting Standards Board",
    "PCAOB",
    "FASB\'s Emerging Issues Task Force",
]

other_topics = [
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

other_standards = [
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
    "The guidance also {policy_feature}",
    "Additionally, the standard {policy_feature}",
    "The new guidance {policy_feature}",
    "The update also {policy_feature}",
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
    "{company} adopted this guidance on {month} {day}, {year} using the {adoption_method}",
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
    "The adoption resulted in {adoption_impact}",
    "Upon adoption, {company} recognized {adoption_impact}",
    "The cumulative effect of adoption was {adoption_impact}",
    "Implementation of the standard resulted in {adoption_impact}",
    "As a result of adoption, {adoption_impact}",
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
    "{company} will apply the {adoption_method} upon adoption",
    "{company} elected to apply the practical expedients available under the transition guidance",
    "{company} intends to adopt the standard using the {adoption_method} with {transition_feature}",
    "{company} selected the {adoption_method} for transition purposes",
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
    "In {month} {year}, the {issuer} issued {standard} related to {topic}, which {company} will adopt in {year}",
    "Management continues to monitor new accounting pronouncements issued by the {issuer} for potential impact",
    "Other new accounting guidance issued but not yet effective is not expected to have a material impact on the consolidated financial statements",
    "{company} reviews all recently issued accounting standards to determine their applicability and impact",
]

shared_standards_templates = [
    "In {month} {year}, the {issuer} issued guidance on {topic} to {standard_purpose}",
    "The {issuer} issued {standard} in {year}, which {standard_description}",
    "New accounting guidance issued by the {issuer} in {month} {year} addresses {topic}",
    "{standard} was issued in {year} to {standard_purpose}",
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
    "In {month} {year}, the {issuer} issued {standard} related to hedging activities. The guidance {hedge_description}. Additionally, it {hedge_feature}",
    "The {issuer} issued {standard} to address {topic}. This update {hedge_description}. The new guidance {hedge_feature}",
    "Hedging Activities: In {month} {year}, {issuer} released guidance on {topic}. It {hedge_description} and {hedge_feature}",
    "The amendment to Topic 815 {hedge_description} and {hedge_feature}. Effective for fiscal years beginning after {month} {eff_day}, {year}",
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
    "In {month} {year}, the {issuer} issued {standard} addressing {topic}. The standard {policy_description}. Additionally, it {policy_feature}",
    "The {issuer} issued {standard} to {standard_purpose}. The guidance {policy_description} and {policy_feature}",
    "Accounting Update: In {month} {year}, {issuer} released {standard} covering {topic}. It {policy_description}. The update {policy_feature}",
    "During {year}, the {issuer} issued guidance under {standard} to {standard_purpose}. {policy_description}. Additionally, it {policy_feature}",
]

# ==============================
# Counterparty / Credit Risk Templates
# ==============================
risk_templates = [
    "Based upon certain factors, including a review of the {risk_item} for {company}\'s counterparties, {company} determined its counterparty credit risk to be {materiality}",
    "After assessing {risk_item} and other indicators for {company}\'s derivative counterparties, management concluded that counterparty exposure is {materiality}",
    "{company} periodically reviews {risk_item} and other market data to evaluate counterparty credit risk, which was determined to be {materiality}",
    "Based on a review of {risk_item} and internal assessments, {company} concluded that exposure to counterparty credit risk is {materiality}",
    "{company} monitors {risk_item} as part of its evaluation of counterparty credit exposure associated with derivative contracts",
    "Considering {risk_item}, credit ratings, and exposure limits, {company} determined that counterparty risk is {materiality}",
    "{company} evaluates {risk_item} to assess potential credit exposure under its derivative contracts and considers such exposure to be {materiality}",
    "Taking into account {risk_item} and the financial strength of counterparties, {company} considers the overall counterparty credit risk to be {materiality}",
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

cfs_reasons = [
    "acquisitions of businesses",
    "purchases of property, plant, and equipment",
    "strategic investments in other companies",
    "purchases of marketable securities",
    "capital expenditures for facility expansion",   
    "sales of property, plant, and equipment",
    "divestitures of business segments",
    "proceeds from the sale of marketable securities",
    "issuance of long-term debt",
    "repayment of long-term debt",
    "issuance of common stock",
    "repurchase of common stock",
    "payment of dividends",
    "net cash provided by operating activities",
    "net cash used in investing activities",
    "net cash used in financing activities",
    "changes in working capital",
    "depreciation and amortization",
    "stock-based compensation expense",
    "deferred income taxes",
    "changes in accounts receivable",
    "changes in inventory",
    "changes in accounts payable",
    "changes in accrued expenses",
    "gains on sale of assets",
    "losses on extinguishment of debt",
    "unrealized gains/losses on investments",
    "changes in operating assets and liabilities",
    "non-cash investing and financing activities",
    "effect of exchange rate changes on cash",
    "net increase/decrease in cash and cash equivalents",
    "cash paid for interest",
    "cash paid for income taxes",
    "proceeds from exercise of stock options",
    "capital contributions from noncontrolling interests",
    "distributions to noncontrolling interests",
    "proceeds from issuance of preferred stock",
    "redemption of preferred stock",
    "borrowings under revolving credit facilities",
    "repayments under revolving credit facilities",
    "proceeds from government grants",
    "payments for contingent consideration",
    "cash used for business acquisitions, net of cash acquired",
    "cash received from business divestitures, net of cash disposed",
    "purchases of intangible assets",
    "sales of intangible assets",
    "investments in joint ventures and equity method investees",
    "distributions from joint ventures and equity method investees",
    "purchases of available-for-sale securities",
    "sales of available-for-sale securities",
    "purchases of held-to-maturity securities",
    "sales of held-to-maturity securities",
    "purchases of trading securities",
    "sales of trading securities",
    "changes in restricted cash",
    "changes in other long-term assets",
]

regulatory_approvals = [
    "FDA approval for a new drug",
    "marketing authorization from the European Medicines Agency",
    "clearance for a new medical device",
    "approval from the Environmental Protection Agency for a new facility",
    "authorization from the Federal Communications Commission for a new service",
]

regulatory_matters = [
    "an ongoing inquiry from the Department of Justice",
    "a review by the Securities and Exchange Commission",
    "discussions with the FDA regarding a pending drug application",
    "an investigation by a state attorney general",
    "a pending review of our environmental permits",
]

adoption_impacts = [
    "a material increase in lease liabilities on the balance sheet",
    "a change in the timing of revenue recognition for certain contracts",
    "the recognition of an allowance for expected credit losses",
    "no material impact on the consolidated financial statements",
    "a cumulative-effect adjustment to retained earnings",
]

noise_templates: dict[str, list[list[str]]] = {
    "REVENUE": [
        revenue_recognition_templates,
        deferred_revenue_templates,
    ],
    "PPE": [
        ppe_templates,
        capex_templates,
        impairment_templates,
    ],
    "INTANGIBLE": [
        # Common SEC patterns
        lease_templates,
        lease_commitment_templates,
        goodwill_templates,
        intangible_templates,
    ],
    "TAX": [tax_templates, uncertain_tax_templates],
    "LAW": [
        litigation_templates,
        litigation_assessment_templates,
        specific_lawsuit_templates,
    ],
    "PAY": [
        pension_templates,
        opeb_templates,
        purchase_commitment_templates,
        guarantee_templates,
    ],
    "ACQ": [
        restructuring_templates,
        acquisition_templates,
    ],
    "B_S": [
        balance_sheet_change_templates,
        working_capital_templates,
        ar_templates,
        ap_templates,
        accrued_liabilities_templates,
        other_current_assets_templates,
        other_liabilities_templates,
        retained_earnings_templates,
        stockholders_equity_templates,
        cash_flow_statement_templates,
    ],
    "CEO": [
        ceo_compensation_templates,
        executive_compensation_templates,
        equity_grant_templates,
        severance_templates,
        employment_agreement_templates,
        compensation_committee_templates,
        say_on_pay_templates,
        deferred_comp_templates,
        perquisites_templates,
        clawback_templates,
    ],
    "ABT": [
        company_description_templates,
        institutional_ownership_templates,
        insider_ownership_templates,
    ],
    "FWD": [
        forward_looking_templates,
        safe_harbor_templates,
    ],
    "RATE": [
        analyst_coverage_templates,
        credit_rating_templates,
        share_repurchase_templates,
        dividend_policy_templates,
    ],
    "COMP": [
        competition_templates,
    ],
    "REG": [
        regulatory_templates,
    ],
    "INS": [
        insurance_templates,
    ],
    "FX": [  # FX related
        foreign_currency_exposure_templates,
        foreign_currency_translation_templates,
        foreign_currency_transaction_templates,
        functional_currency_templates,
        fx_impact_on_results_templates,
        intercompany_fx_templates,
    ],
    "CP": [  # CP related
        commodity_price_exposure_templates,
        commodity_cost_impact_templates,
        commodity_inventory_valuation_templates,
        commodity_pricing_strategies_templates,
        commodity_supply_risk_templates,
        commodity_exposure_quantification_templates,
        physical_commodity_operations_templates,
        inventory_templates,
        inventory_writedown_templates,
    ],
    # Speculative policy related
    "STD": [
        shared_additional_features_templates,
        shared_effective_date_templates,
        shared_adoption_status_templates,
        shared_adoption_impact_templates,
        shared_evaluation_templates,
        shared_transition_templates,
        shared_disclosure_change_templates,
        shared_practical_expedient_templates,
        shared_recent_pronouncement_templates,
        shared_standards_templates,
        general_policy_templates,
        risk_templates,
    ],
    "EQ": [  # Equity related
        equity_warrant_templates,
        equity_warrant_activity_templates,
        stock_debt_issuance_templates,
        registration_statement_templates,
        market_impact_templates,
        warrant_adjustment_templates,
        fair_value_snapshot_templates,
        share_reservation_templates,
        outstanding_options_templates,
        dilution_concern_templates,
        capital_raising_impact_templates,
        warrant_debt_issuance_templates,
        warrant_amortization_templates,
        stock_comp_templates,
        stock_comp_valuation_templates,
        stock_price_templates,
        trading_volume_templates,
    ],
    # IR related
    "IR": [debt_templates, debt_covenant_templates],
}


# Pre-compiled list for "other" noise templates
_excluded_keys_for_other = {"IR", "FX", "CP", "EQ", "LAW", "DER", "STD"}
other_templates = [
    item
    for key, template_list_of_lists in noise_templates.items()
    if key not in _excluded_keys_for_other
    for template_list in template_list_of_lists
    for item in template_list
]
