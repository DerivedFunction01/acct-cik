import random
# ==============================================================================
# BASE VARIABLES - Core Building Blocks
# ==============================================================================
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
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
]

quarters = ["first", "second", "third", "fourth", "1st", "2nd", "3rd", "4th"]

# ==============================================================================
# LOCATIONS
# ==============================================================================
us_locations = [
    "Abilene, Texas",
    "Akron, Ohio",
    "Alabama",
    "Alaska",
    "Albuquerque, New Mexico",
    "Alexandria, Virginia",
    "Allentown, Pennsylvania",
    "Amarillo, Texas",
    "Anaheim, California",
    "Anchorage, Alaska",
    "Ann Arbor, Michigan",
    "Arizona",
    "Arkansas",
    "Arlington, Texas",
    "Athens, Georgia",
    "Atlanta, Georgia",
    "Augusta, Georgia",
    "Aurora, Colorado",
    "Aurora, Illinois",
    "Austin, Texas",
    "Bakersfield, California",
    "Baltimore, Maryland",
    "Beaumont, Texas",
    "Bellevue, Washington",
    "Berkeley, California",
    "Bethlehem, Pennsylvania",
    "Birmingham, Alabama",
    "Boston, Massachusetts",
    "Bridgeport, Connecticut",
    "Brownsville, Texas",
    "Buffalo, New York",
    "California",
    "Cape Coral, Florida",
    "Carrollton, Texas",
    "Cary, North Carolina",
    "Cedar Rapids, Iowa",
    "Chandler, Arizona",
    "Charleston, South Carolina",
    "Charlotte, North Carolina",
    "Chattanooga, Tennessee",
    "Chesapeake, Virginia",
    "Chicago, Illinois",
    "Chula Vista, California",
    "Cincinnati, Ohio",
    "Clarksville, Tennessee",
    "Cleveland, Ohio",
    "Colorado",
    "Colorado Springs, Colorado",
    "Columbus, Georgia",
    "Columbus, Ohio",
    "Connecticut",
    "Coral Springs, Florida",
    "Corona, California",
    "Corpus Christi, Texas",
    "Dallas, Texas",
    "Dayton, Ohio",
    "Delaware",
    "Denver, Colorado",
    "Des Moines, Iowa",
    "Detroit, Michigan",
    "Durham, North Carolina",
    "El Paso, Texas",
    "Elk Grove, California",
    "Escondido, California",
    "Eugene, Oregon",
    "Fayetteville, North Carolina",
    "Florida",
    "Fontana, California",
    "Fort Lauderdale, Florida",
    "Fort Wayne, Indiana",
    "Fort Worth, Texas",
    "Fremont, California",
    "Fresno, California",
    "Fullerton, California",
    "Gainesville, Florida",
    "Garden Grove, California",
    "Garland, Texas",
    "Georgia",
    "Glendale, Arizona",
    "Glendale, California",
    "Grand Prairie, Texas",
    "Grand Rapids, Michigan",
    "Greensboro, North Carolina",
    "Hampton, Virginia",
    "Hartford, Connecticut",
    "Hawaii",
    "Hayward, California",
    "Henderson, Nevada",
    "Hialeah, Florida",
    "Hollywood, Florida",
    "Honolulu, Hawaii",
    "Houston, Texas",
    "Huntington Beach, California",
    "Huntsville, Alabama",
    "Idaho",
    "Illinois",
    "Independence, Missouri",
    "Indiana",
    "Indianapolis, Indiana",
    "Iowa",
    "Irvine, California",
    "Irving, Texas",
    "Jacksonville, Florida",
    "Jersey City, New Jersey",
    "Joliet, Illinois",
    "Kansas",
    "Kansas City, Kansas",
    "Kansas City, Missouri",
    "Kentucky",
    "Killeen, Texas",
    "Knoxville, Tennessee",
    "Lafayette, Louisiana",
    "Lakewood, California",
    "Lakewood, Colorado",
    "Lancaster, California",
    "Laredo, Texas",
    "Las Vegas, Nevada",
    "Lexington, Kentucky",
    "Lincoln, Nebraska",
    "Little Rock, Arkansas",
    "Long Beach, California",
    "Los Angeles, California",
    "Louisiana",
    "Louisville, Kentucky",
    "Lubbock, Texas",
    "Macon, Georgia",
    "Madison, Wisconsin",
    "Maine",
    "Maryland",
    "Massachusetts",
    "McAllen, Texas",
    "McKinney, Texas",
    "Memphis, Tennessee",
    "Mesa, Arizona",
    "Mesquite, Texas",
    "Miami, Florida",
    "Michigan",
    "Midland, Texas",
    "Milwaukee, Wisconsin",
    "Minneapolis, Minnesota",
    "Minnesota",
    "Miramar, Florida",
    "Mississippi",
    "Missouri",
    "Mobile, Alabama",
    "Modesto, California",
    "Montana",
    "Montgomery, Alabama",
    "Moreno Valley, California",
    "Murfreesboro, Tennessee",
    "Naperville, Illinois",
    "Nashville, Tennessee",
    "Nebraska",
    "Nevada",
    "New Hampshire",
    "New Jersey",
    "New Mexico",
    "New Orleans, Louisiana",
    "New York",
    "New York, New York",
    "Newark, New Jersey",
    "Newport News, Virginia",
    "Norman, Oklahoma",
    "North Carolina",
    "North Dakota",
    "North Las Vegas, Nevada",
    "Oakland, California",
    "Oceanside, California",
    "Ohio",
    "Oklahoma",
    "Oklahoma City, Oklahoma",
    "Omaha, Nebraska",
    "Orange, California",
    "Oregon",
    "Orlando, Florida",
    "Overland Park, Kansas",
    "Oxnard, California",
    "Palmdale, California",
    "Pasadena, California",
    "Pasadena, Texas",
    "Paterson, New Jersey",
    "Pembroke Pines, Florida",
    "Pennsylvania",
    "Peoria, Arizona",
    "Philadelphia, Pennsylvania",
    "Phoenix, Arizona",
    "Pittsburgh, Pennsylvania",
    "Plano, Texas",
    "Pomona, California",
    "Port St. Lucie, Florida",
    "Portland, Oregon",
    "Providence, Rhode Island",
    "Provo, Utah",
    "Raleigh, North Carolina",
    "Rancho Cucamonga, California",
    "Reno, Nevada",
    "Rhode Island",
    "Riverside, California",
    "Rochester, New York",
    "Rockford, Illinois",
    "Round Rock, Texas",
    "Sacramento, California",
    "Saint Paul, Minnesota",
    "Salem, Oregon",
    "Salinas, California",
    "Salt Lake City, Utah",
    "San Antonio, Texas",
    "San Bernardino, California",
    "San Diego, California",
    "San Francisco, California",
    "San Jose, California",
    "Santa Ana, California",
    "Santa Clarita, California",
    "Santa Rosa, California",
    "Savannah, Georgia",
    "Scottsdale, Arizona",
    "Seattle, Washington",
    "Shreveport, Louisiana",
    "Simi Valley, California",
    "Sioux Falls, South Dakota",
    "South Carolina",
    "South Dakota",
    "Spokane, Washington",
    "Springfield, Massachusetts",
    "Springfield, Missouri",
    "St. Louis, Missouri",
    "St. Paul, Minnesota",
    "Sterling Heights, Michigan",
    "Stockton, California",
    "Sunnyvale, California",
    "Syracuse, New York",
    "Tacoma, Washington",
    "Tallahassee, Florida",
    "Tampa, Florida",
    "Temecula, California",
    "Tempe, Arizona",
    "Tennessee",
    "Texas",
    "Thornton, Colorado",
    "Thousand Oaks, California",
    "Toledo, Ohio",
    "Topeka, Kansas",
    "Torrance, California",
    "Tucson, Arizona",
    "Tulsa, Oklahoma",
    "United States",
    "Utah",
    "Vallejo, California",
    "Vancouver, Washington",
    "Vermont",
    "Victorville, California",
    "Virginia",
    "Virginia Beach, Virginia",
    "Visalia, California",
    "Waco, Texas",
    "Warren, Michigan",
    "Washington",
    "Washington, D.C",
    "West Valley City, Utah",
    "West Virginia",
    "Wichita, Kansas",
    "Winston-Salem, North Carolina",
    "Wisconsin",
    "Worcester, Massachusetts",
    "Wyoming",
    "Yonkers, New York",
]

international_locations = [
    "Canada",
    "Mexico",
    "the European Union",
    "the United Kingdom",
    "Germany",
    "France",
    "Italy",
    "Spain",    
    "Japan",
    "China",
    "India",
    "Australia",
    "Brazil",
    "Argentina",
    "South Africa",
    "Nigeria",
    "Egypt",
    "Saudi Arabia",
    "United Arab Emirates",
    "Russia",
    "South Korea",
    "Indonesia",
    "Thailand",
    "Vietnam",
    "Philippines",
    "Malaysia",
    "Singapore",
    "New Zealand",
    "Chile",
    "Colombia",
    "Peru",
    "Venezuela",
    "Turkey",
    "Israel",
    "Pakistan",
    "Bangladesh",
    "Iran",
    "Ukraine",
    "Poland",
    "Sweden",
    "Norway",
    "Denmark",
    "Finland",
    "Switzerland",
    "Austria",
    "Belgium",
    "Netherlands",
    "Portugal",
    "Greece",
    "Ireland",
    "Scotland",
    "Wales",
    "Northern Ireland",
    "Hong Kong",
    "Taiwan",
    "Qatar",
    "Kuwait",
    "Bahrain",
    "Oman",
    "Kazakhstan",
    "Uzbekistan",
    "Azerbaijan",
    "Georgia",
    "Armenia",
    "Morocco",
    "Algeria",
    "Tunisia",
    "Kenya",
    "Ethiopia",
    "Tanzania",
    "Uganda",
    "Ghana",
    "Ivory Coast",
    "Angola",
    "Democratic Republic of Congo",
    "Sudan",
    "Sri Lanka",
    "Myanmar",
    "Cambodia",
    "Laos",
    "Mongolia",
    "Fiji",
    "Papua New Guinea",
    "Cuba",
    "Dominican Republic",
    "Haiti",
    "Jamaica",
    "Trinidad and Tobago",
    "Costa Rica",
    "Panama",
    "Guatemala",
    "Honduras",
    "El Salvador",
    "Nicaragua",
    "Bolivia",
    "Paraguay",
    "Uruguay",
    "Ecuador",
    "European Union",
    "European countries",
    "European nations",
    "Europe",
    "Asia",
    "Africa",
]

# ==============================================================================
# UNION & LABOR ORGANIZATION LISTS
# ==============================================================================

# --- Union Name Generation Components ---
union_prefixes = [
    "Brotherhood of",
    "Association of",
    "Union of",
    "Federation of",
    "Alliance of",
    "General Workers of",
    "Associated",
]

union_trades_us = [
    "Electricians", "Plumbers", "Carpenters", "Machinists", "Boilermakers",
    "Steelworkers", "Automotive Workers", "Aerospace Workers", "Transport Workers",
    "Retail Clerks", "Food Processors", "Healthcare Employees", "Public Employees",
    "Educators", "Service Employees", "Operating Engineers", "Painters", "Allied Trades",
]

union_trades_intl = [
    "Metalworkers", "Transport Workers", "Industrial Workers", "Public Service Employees",
    "Food and Agricultural Workers", "Building and Wood Workers", "Media and Entertainment Professionals",
    "Chemical and Energy Workers", "Dockworkers", "Seafarers", "Textile Workers",
]


def _generate_us_unions(sample_size=50):
    """Generates a list of realistic-sounding US union names"""
    generated = []
    for _ in range(sample_size):
        pattern = random.choice([1, 2, 3])
        if pattern == 1: # Prefix + Trade
            generated.append(f"{random.choice(union_prefixes)} {random.choice(union_trades_us)}")
        else: # Location-based
            generated.append(f"{random.choice(us_locations)} {random.choice(union_trades_us)} Union")
    return list(set(generated))

def _generate_international_unions(sample_size=50):
    """Generates a list of realistic-sounding international union names"""
    generated = []
    for _ in range(sample_size):
        pattern = random.choice([1, 2])
        if pattern == 1: # Location + Trade
            generated.append(f"{random.choice(international_locations)} Federation of {random.choice(union_trades_intl)}")
        else: # Global Federation
            generated.append(f"Global Federation of {random.choice(union_trades_intl)}")
    return list(set(generated))

# --- US-Based Unions ---
us_unions = [
    "United Steelworkers",
    "International Association of Machinists and Aerospace Workers",
    "International Brotherhood of Teamsters",
    "United Food and Commercial Workers",
    "United Auto Workers",
    "Service Employees International Union",
    "American Federation of Teachers",
    "International Union of Operating Engineers",
    "Communications Workers of America",
    "International Brotherhood of Electrical Workers",
    "National Education Association",
    "American Federation of State, County and Municipal Employees",
    "International Association of Fire Fighters",
    "District 10 of the IAM",
    "National Nurses United",
    "American Federation of Government Employees",
    "United Mine Workers of America",
    "International Longshore and Warehouse Union",
    "United Farm Workers",
    "Actors' Equity Association",
    "American Federation of Musicians",
    "Writers Guild of America, East",
    "Writers Guild of America, West",
    "Directors Guild of America",
    "Screen Actors Guild-American Federation of Television and Radio Artists",
    "Major League Baseball Players Association",
    "National Basketball Players Association",
    "National Football League Players Association",
    "National Hockey League Players' Association",
    "United Brotherhood of Carpenters and Joiners of America",
    "International Union of Painters and Allied Trades",
    "Operative Plasterers' and Cement Masons' International Association",
    "United Union of Roofers, Waterproofers and Allied Workers",
    "International Association of Heat and Frost Insulators and Allied Workers",
    "International Brotherhood of Boilermakers, Iron Ship Builders, Blacksmiths, Forgers and Helpers",
    "Amalgamated Transit Union",
    "Brotherhood of Locomotive Engineers and Trainmen",
    "International Association of Sheet Metal, Air, Rail and Transportation Workers",
    "American Postal Workers Union",
    "National Association of Letter Carriers",
    "National Rural Letter Carriers' Association",
    "International Alliance of Theatrical Stage Employees",
    "California Nurses Association",
    "New York State Nurses Association",
    "Oregon Nurses Association",
    "Washington State Nurses Association",
    "Hawaii Nurses' Association",
    "Michigan Nurses Association",
    "Minnesota Nurses Association",
    "Wisconsin Nurses Association",
    "Illinois Nurses Association",
    "Ohio Nurses Association",
    "Pennsylvania Association of Staff Nurses and Allied Professionals",
    "Massachusetts Nurses Association",
    "Connecticut Nurses' Association",
    "New Jersey State Nurses Association",
    "Maryland Nurses Association",
    "District of Columbia Nurses Association",
    "Virginia Nurses Association",
    "North Carolina Nurses Association",
    "South Carolina Nurses Association",
    "Georgia Nurses Association",
    # Additions
    "Laborers' International Union of North America",
    "UNITE HERE",
    "Transport Workers Union of America",
    "International Association of Bridge, Structural, Ornamental, and Reinforcing Iron Workers",
] + _generate_us_unions()

# --- International Unions & Labor Bodies ---
international_unions = [
    "IG Metall",  # Germany
    "Ver.di",  # Germany
    "Unite the Union",  # UK
    "GMB",  # UK
    "CFDT",  # France
    "CGT",  # France
    "Unifor",  # Canada
    "International Transport Workers' Federation",
    "IndustriALL Global Union",
    "Building and Wood Workers' International",
    "Public Services International",
    "UNI Global Union",
    "Education International",
    "International Federation of Journalists",
    "International Arts and Entertainment Alliance",
    "International Domestic Workers' Federation",
    "International Union of Food, Agricultural, Hotel, Restaurant, Catering, Tobacco and Allied Workers' Associations",
    "European Federation of Public Service Unions",
    "European Trade Union Confederation",
    "Southern African Trade Union Co-ordination Council",
    "Organization of African Trade Union Unity",
    "International Confederation of Arab Trade Unions",
    "ASEAN Trade Union Council",
    "World Federation of Trade Unions",
    "International Trade Union Confederation",
    # Additions
    "All-China Federation of Trade Unions",  # China
    "Indian National Trade Union Congress",  # India
    "Centre of Indian Trade Unions",  # India
    "Japanese Trade Union Confederation (Rengo)",  # Japan
    "Korean Confederation of Trade Unions",  # South Korea
    "Vietnam General Confederation of Labour",  # Vietnam
    "Congress of South African Trade Unions",  # South Africa
    "Nigeria Labour Congress",  # Nigeria
    "Tunisian General Labour Union",  # Tunisia
    "Confederation of Ethiopian Trade Unions",  # Ethiopia
    "Central Única dos Trabalhadores",  # Brazil
    "General Confederation of Labour",  # Argentina
    "Workers' Central Union of Cuba",  # Cuba
    "Confederation of Mexican Workers",  # Mexico
    "ITUC Asia-Pacific",  # Asia-Pacific
    "Trade Union Confederation of the Americas",  # Americas
    "African Regional Organisation of the ITUC",  # Africa
] + _generate_international_unions()

# --- Generic Union Terms ---
generic_unions = [
    "local unions",
    "trade unions",
    "labor unions",
    "in-house labor associations",    
    "employee associations",
    "works councils",
    "staff associations",
    "labor organizations",
    "employee representative bodies",
    "trade union confederations",
    "federations of labor",
    "industrial unions",
    "craft unions",
    "general unions",
    "company unions",
    "independent unions",
    "national unions",
    "regional unions",
    "local chapters",
    "union locals",
    "bargaining units",
    "worker committees",
    "employee forums",
    "labor fronts",
    "syndicates",
    "guilds",
    "brotherhoods",
    "sisterhoods",
    "employee groups",
    "worker organizations",
    "employee representative organizations",
    "labor federations",
    "union confederations",
    "union councils",
    "union committees",
    "union branches",
    "union sections",
    "union cells",
    "union chapters",
    "union lodges",
    "union halls",
    "union headquarters",
    "union offices",
    "union locals",
]

# Combined list for general use, can be replaced by more specific lists
unions = us_unions + international_unions + generic_unions

# Facilities/locations
facilities = [
    "manufacturing facilities",
    "production facilities",
    "distribution centers",
    "data centers",
    "warehouses",
    "retail stores",
    "sales offices",
    "administrative offices",
    "manufacturing plants",
    "assembly plants",
    "distribution facilities",
    "customer service centers",
    "field offices",
    "satellite offices",
]
# Relationship quality descriptors
relationship_quality = [
    "good",
    "satisfactory",
    "positive",
    "strong",
    "excellent",
    "favorable",
    "constructive",
    "cooperative",
    "harmonious",
    "cordial",
    "mutually beneficial",
    "productive",
    "stable",
    "respectful",
]

# Negotiation status
negotiation_status = [
    "are currently in negotiations",
    "have commenced negotiations",
    "are negotiating a new agreement",
    "are in the process of negotiating",
    "expect to begin negotiations",
    "will commence negotiations",
    "are engaged in collective bargaining",
]

# Risk language
risk_verbs = [
    "could experience",
    "may face",
    "might encounter",
    "could be subject to",
    "may be exposed to",
    "could face",
    "could lead to",
    "may result in",
    "might cause",
]

risk_events = [
    "labor disputes",
    "work stoppages",
    "strikes",
    "labor disruptions",
    "union organizing activities",
    "union campaigns",
    "work interruptions",
    "collective bargaining negotiations",
    "collective bargaining obligations",
    "unionization efforts",
    "union activities",
    "collective bargaining",
    "labor negotiations",
    "labor organizing",
    "union representation",
    "union demands",
    "wage and benefit increases",
    "changes in working conditions",
    "strikes and lockouts",
    "slowdowns",
    "picketing",
]

risk_consequences = [
    "that could disrupt operations",
    "that may result in increased costs",
    "which could adversely affect financial results",
    "that could impact productivity",
    "which may result in work interruptions",
    "which could negatively impact our reputation",
    "that may lead to increased operational costs",
    "which could affect our ability to attract and retain employees",
    "that might result in decreased production efficiency",
    "which could cause delays in product delivery",
    "that may harm our competitive position",
]

# Industries
industries = [
    "airline",
    "automotive",
    "construction",
    "manufacturing",
    "transportation",
    "logistics",
    "hospitality",
    "healthcare",
    "telecommunications",
    "energy",
    "mining",
    "steel",
    "aerospace",
    "shipbuilding",
    "retail",
    "food processing",
    "public sector",
    "education",
    "utility",    
    "financial services",
    "retail trade",
    "wholesale trade",
    "information technology",
    "biotechnology",
    "pharmaceutical",
    "chemical",
    "pulp and paper",
    "textile",
    "apparel",
    "footwear",
    "food and beverage",
    "tobacco",
    "furniture",
    "wood products",
    "printing",
    "publishing",
    "media",
    "entertainment",
    "sports",
    "recreation",
    "personal services",
    "business services",
    "legal services",
    "accounting services",
    "consulting services",
    "advertising",
    "marketing",
    "public relations",
    "real estate",
    "rental and leasing services",
    "waste management",
    "remediation services",
    "agriculture",
    "forestry",
    "fishing",
    "hunting",
    "utilities",
    "arts",
    "museums",
    "parks",
    "amusement",
    "gambling",
    "casinos",
    "religious organizations",
    "grantmaking and giving services",
    "social advocacy organizations",
    "civic and social organizations",
    "professional organizations",
    "labor organizations",
    "political organizations",
    "international affairs",
    "public administration",
    "justice",
    "public order",
    "national security",
    "international organizations",
    "extraterritorial organizations",
    "automotive manufacturing",
    "aerospace manufacturing",
    "computer and electronic product manufacturing",
    "electrical equipment manufacturing",
    "appliance and component manufacturing",
    "transportation equipment manufacturing",
    "machinery manufacturing",
    "fabricated metal product manufacturing",
    "primary metal manufacturing",
    "plastic and rubber products manufacturing",
    "nonmetallic mineral product manufacturing",
    "chemical manufacturing",
    "petroleum and coal products manufacturing",
    "food manufacturing",
    "beverage and tobacco product manufacturing",
    "textile mills",
    "textile product mills",
    "apparel manufacturing",
    "leather and allied product manufacturing",
    "wood product manufacturing",
    "paper manufacturing",
    
]

# ==============================================================================
# MODULAR TEMPLATE COMPONENTS
# ==============================================================================

# --- Time & Context ---
time_phrases = [
    "As of {month} {day}, {year}",
    "At {month} {day}, {year}",
    "As of {year}",
    "During {year}",
]

employee_phrases = [
    "{company} had {total} employees",
    "we had {total} associates worldwide",
    "we employed approximately {total} people worldwide",
    "{company} had {total} total employees",
]

# --- Coverage Statements ---
coverage_statements_pct = [
    "approximately {pct}% of our employees are represented by unions under collective bargaining agreements",
    "approximately {pct}% of these employees are represented by a collective bargaining agent",
    "{pct}% of our workforce are covered by collective bargaining agreements",
    "{pct}% of our employees were represented by unions",
]

coverage_statements_count = [
    "approximately {cb_count} employees are represented by collective bargaining units",
    "{cb_count} employees belong to trade unions such as {generic_union}",
    "{cb_count} of the hourly plant personnel are represented by collective bargaining units",
    "{cb_count} employees are covered by collective bargaining agreements",
]

coverage_statements_vague = [
    "a significant portion of our employees are covered by collective bargaining agreements",
    "some employees are currently represented by a {generic_union}",
    "a portion of {company}'s workforce are members of industrial {generic_union}",
    "certain employees at our facilities belong to a {generic_union}",
    "a majority of our employees at certain locations are represented by a {generic_union}",
]

# --- No Coverage Statements ---
no_coverage_statements = [
    "None of our employees are represented by a union or covered by a collective bargaining agreement",
    "{company} is not a party to any collective bargaining agreements",
    "Our employees are not represented by any labor organization",
    "We have no collective bargaining agreements with our employees",
    "{company} does not have any collective bargaining agreements in place",
    "We are a non-union employer",
]

# --- Risk Statements ---
risk_intro_phrases = [
    "{company} {risk_verb} {risk_event}",
    "We {risk_verb} {risk_event}",
    "Union organizing activities could result in increased costs or work disruptions",
    "We may be subject to union campaigns, which could divert management attention",    
    "We may be subject to labor organizing activities, which could result in increased operating costs",
    "Any future labor disputes could have a material adverse effect on our business",
    "Increased unionization could lead to higher labor costs and reduced flexibility",
    "We could experience work stoppages or other labor unrest",
    "Unionization efforts could negatively impact our employee relations",
    "Failure to successfully negotiate collective bargaining agreements could result in strikes or work stoppages",
    "Collective bargaining negotiations could result in significant increases to our labor costs",
    "Changes in labor laws could make it easier for employees to unionize",
    "A prolonged strike could severely impact our production and revenue",
    "Labor disputes could harm our reputation and customer relationships",
    "Disruptions from labor activities could affect our supply chain",
    "Increased demands from unions could make our products less competitive",
    "We may be required to increase wages or benefits due to union pressure",
    "Union organizing could divert significant management time and resources",
    "The outcome of collective bargaining could be unfavorable to us",
    "We could be subject to picketing or boycotts",
    "Any labor unrest could impact our ability to deliver products or services",
    "We may face challenges in implementing operational changes if our workforce unionizes",
    "The cost of complying with new collective bargaining agreements could be substantial",
    "We could experience a decline in employee morale during unionization campaigns",
    "Potential unionization could affect our ability to attract and retain employees",
    "We may be forced to make concessions during negotiations that are not in our best interest",
    "Labor disputes could lead to legal challenges and penalties",
    "The threat of unionization could impact our stock price",
    "We could face increased scrutiny from labor regulators",
    "Any adverse publicity from labor disputes could harm our brand",
    "We may be unable to pass on increased labor costs to our customers",
    "Unionization could limit our ability to manage our workforce effectively",
    "We could experience a decrease in productivity due to labor actions",
    "The terms of a collective bargaining agreement could restrict our business strategies",
    "We may face difficulties in closing or restructuring facilities if they are unionized",
    "Increased labor costs could impact our profitability",
    "We could be subject to secondary boycotts",
]

# ==============================================================================
# TEMPLATE GENERATION FROM COMPONENTS
# ==============================================================================

def _generate_coverage_templates():
    """Generates coverage templates by combining modular components"""
    templates = []
    # With Numbers
    for time in time_phrases:
        for coverage in coverage_statements_pct + coverage_statements_count:
            templates.append(f"{time}, {coverage}")
    for employee in employee_phrases:
        for coverage in coverage_statements_pct + coverage_statements_count:
            templates.append(f"{employee}. {coverage}")
    # Vague
    templates.extend(coverage_statements_vague)
    return templates

def _generate_no_coverage_templates():
    """Generates 'no coverage' templates"""
    templates = []
    # Add simple statements
    templates.extend(no_coverage_statements)

    # Add time phrases
    for time in time_phrases:
        for statement in no_coverage_statements:
            templates.append(f"{time}, {statement}")

    # Add employee count phrases and relationship quality
    for statement in no_coverage_statements:
        for employee in employee_phrases:
            templates.append(f"{employee}. {statement}")
        templates.append(f"{statement}, and we consider our relations with our employees to be {{quality}}")
    return templates


# ==============================================================================
# COVERAGE TEMPLATES
# ==============================================================================

coverage_with_numbers_templates = [
    *_generate_coverage_templates(),
    # Keep some unique, complex originals
    "As of {month} {day}, {year}, we have entered into collective bargaining agreements with {num_unions} union locals at {num_locations} of our locations",
    # Industry-specific coverage
    "In the {industry} industry, collective bargaining agreements are common. Approximately {pct}% of our workforce is covered by such agreements",
    "As a company in the {industry} sector, we have {cb_count} employees represented by unions such as {generic_union}",
    "Union representation is prevalent in the {industry} sector. At {company}, {pct}% of our employees are unionized in {generic_union}",
]

coverage_vague_templates = coverage_statements_vague + [
    "The {industry} teams at our {facility} are covered by collective bargaining agreements, as well as the majority of our workforce in certain regions",
    # New template using contextual placeholders
    "A portion of our workforce in {curr_location} is represented by {curr_union}, though the exact number fluctuates",
]

# ==============================================================================
# NO COVERAGE TEMPLATES
# ==============================================================================

no_coverage_templates = _generate_no_coverage_templates() + [
    # Keep some unique originals
    "As of {month} {day}, {year}, we had {total} employees, all of whom are employed on a full-time basis. None of our employees are covered by a collective bargaining agreement",
    "Human Capital Resources. {company} is a relationship driven company and its ability to attract and retain exceptional employees is key to its success. As of {month} {day}, {year}, {company} employed {total} full-time employees. The employees are not represented by a collective bargaining unit",
    # Industry-specific no coverage
    "Unlike many of our peers in the {industry} sector, our employees are not represented by any labor organization",
    "While unionization is common in the {industry} industry, {company} operates on a non-union basis",
    "Our focus on a direct-relationship model is unique in the {industry} sector, and none of our employees are covered by collective bargaining agreements",
]


# ==============================================================================
# HISTORICAL NEGATIVE TEMPLATES
# ==============================================================================

historical_templates = [
    "{company} has never experienced a work stoppage, and none of its employees are currently represented by a labor organization",
    "While the industry historically had strong unions, none of our {total} employees at our {facility} are covered by collective bargaining agreements",
    "Despite union organizing efforts in the past, {company} successfully avoided unionization and currently has no collective bargaining agreements",
    "We previously had collective bargaining coverage until {past_year}, but following restructuring, none of our current {total} employees are unionized",
    "{company} has never had a work stoppage related to collective bargaining, and none of its employees are currently represented by a labor organization",
    "A union that previously represented employees at our {facility} was decertified in {past_year}, and we have no other union representation",
    "Our collective bargaining agreement with the {generic_union} expired in {past_year} and was not renewed; consequently, none of our employees are currently covered",
    "Following the closure of our unionized {facility} in {past_year}, {company} no longer has any employees represented by a collective bargaining agreement",
]

# ==============================================================================
# CONDITIONAL TEMPLATES
# ==============================================================================

conditional_templates = [
    "If our employees were to unionize, collective bargaining could impact our costs. Currently, none of our {total} employees are represented by a union",
    "Although some competitors have collective bargaining agreements, we do not. We believe this provides competitive advantage in {location}",
    "In the event that union organizing efforts succeed, we may face collective bargaining obligations. However, no such agreements currently exist",
    "Management considered collective bargaining scenarios in strategic planning, but our workforce of {total} employees remains non-unionized across all facilities",
    "Management has proactively addressed potential unionization, ensuring our workforce remains non-unionized",
    "Should we acquire a company with a unionized workforce, we would become subject to collective bargaining agreements",
    "While we currently have no unionized employees, future organizing efforts could lead to collective bargaining negotiations",
    "Proposed labor legislation, if enacted, could make it easier for unions to organize, potentially leading to collective bargaining in the future",
]

# ==============================================================================
# THIRD-PARTY TEMPLATES
# ==============================================================================

third_party_templates = [
    "Our suppliers in {location} may be subject to collective bargaining agreements, but this does not affect our operations. None of our employees are unionized",
    "Industry association data shows {pct}% collective bargaining coverage nationwide. However, {company} has no union representation among its {total} employees",
    "We monitor competitor labor agreements and collective bargaining trends. Currently, our {total} person workforce is entirely non-union",
    "Customers in certain jurisdictions require union labor for contracts. Our own workforce of {total} employees is not covered by collective bargaining",
    "Some of our contractors and temporary staff are represented by unions, but our direct employees are not",
    "While some of our major customers have unionized workforces, our own employees are not covered by any collective bargaining agreements",
    "Our joint venture partner operates with a unionized workforce, but employees of {company} are not subject to collective bargaining",
]


# ==============================================================================
# RISK FACTOR TEMPLATES
# ==============================================================================
risk_factor_templates = [
    "We might be unable to employ a sufficient number of skilled workers. Although our employees are not covered by a collective bargaining agreement, the industry has in the past been targeted by unions in organizing efforts",
    "{company} believes our employee relations are good. None of our employees are currently represented by a labor union. However, outside union organizing efforts among our employees do occur from time to time",
    "If our employees were to unionize, we could face collective bargaining obligations that may result in increased costs. Union organizing activities have been reported at some facilities",
    "Approximately {pct}% of {company}'s employees are represented by unions. Although we believe that we will successfully negotiate new collective bargaining agreements, these negotiations may result in a significant increase in labor costs",
    "Union organizing activities could result in increased costs or work disruptions. We face risks related to potential unionization of our workforce",
    "An increase in union organizing activity in our industry could lead to disruptions at our facilities",
    "We may be subject to union campaigns, which could divert management attention and increase operating costs",
    # Industry-specific risk
    "The {industry} industry has historically been a target for union organizing. Any such efforts at our facilities could lead to increased operating costs",
    "We operate in the {industry} sector, which is subject to unionization efforts that could disrupt our operations or increase labor costs",
    # New template using contextual placeholders
    "While our {neg_curr_location} operations are currently non-union, organizing efforts in the {industry} industry represent a potential risk",
]

# Risk with existing coverage
existing_coverage_risk_templates = [
    "{company} could experience labor disputes that could disrupt its business. Although we believe that we will successfully negotiate new collective bargaining agreements, these negotiations may not prove successful",
    "Approximately {pct}% of {company}'s employees are represented by unions. Although we believe we will successfully negotiate new collective bargaining agreements, these negotiations may not prove successful",
    "{company} had {cb_count} employees covered by collective bargaining agreements with the {curr_union} as of {month} {day}, {year}. Labor negotiations always bring some risk of work stoppages",
    "{company}'s union labor agreement with the {curr_union} expires in {month} {year}. Negotiations bring some risk of work disruptions",
    "Our collective bargaining agreements contain provisions that may limit our operational flexibility",
]

# ==============================================================================
# RELATIONSHIP QUALITY TEMPLATES
# ==============================================================================

relationship_templates = [
    "{company} believes its relations with employees are {quality}",
    "We consider our employee relations to be {quality}",
    "{company} maintains {quality} relationships with its workforce",
    "{company} believes it has a {quality} relationship with our employees",
    "We have a {quality} working relationship with our workforce at our {facility}",
    "We have not experienced any work stoppages and consider our employee relationships to be {quality}",
    "We strive to maintain {quality} and open communication with all employees",
]

# ==============================================================================
# EXPIRATION AND NEGOTIATION TEMPLATES
# ==============================================================================

expiration_phrases = [
    "expires in {month} {year}",
    "expires on {month} {day}, {year}",
    "is effective through {month} {year}",
    "is effective through {month} {day}, {year}",
    "terminates in {month} {year}",
    "will expire in {month} {year}",
    "expires in {year}",
    "remains effective until {month} {year}",
    "has an expiration date of {month} {year}",
]

expiration_templates = [
    "The collective bargaining agreement for {facility} {expiration}",
    "The current contract with our {facility} employees {expiration}",
    "Collective bargaining agreements covering approximately {cb_count} employees will expire during {year}",
    "{cb_count} employees are covered by agreements with the {curr_union} that expire on various dates through {year}",
    "Our primary labor agreement with the {curr_union} is set to expire in {year}",
    "Several of our collective bargaining agreements are due for renewal in the next fiscal year",
]

negotiation_templates = [
    "{company} {negotiation_status} with its labor union at {facility}",
    "Negotiations with respect to expiring contracts have commenced",
    "{company} expects negotiations to be concluded in {quarter} {year}",
    "{company} is currently negotiating a new collective bargaining agreement",
    "We are preparing to enter into negotiations for a successor agreement with the {curr_union}",
    "Bargaining for a new contract covering our {facility} employees is scheduled to begin in {month} {year}",
    # New template using contextual placeholders
    "We are in active negotiations with the {curr_union} regarding our employees at the {curr_location} plant",
]

# Combination of risk components
risk_combination_templates = [
    f"{intro} {consequence}"
    for intro in risk_intro_phrases
    for consequence in risk_consequences
]
# Contextual Risk Factor Templates (replaces us_risk_templates and international_risk_templates)
contextual_risk_templates = [
    "Union organizing activities at our {curr_location} facilities {risk_consequence}, potentially involving groups like {curr_union}",
    "We face risks related to potential unionization of our workforce in {curr_location}, which could lead to labor disputes with {curr_union}",
    "Our operations in {curr_location} are subject to local labor laws that may be more favorable to unions like {curr_union}, increasing the risk of organizing efforts",
    "An increase in union organizing activity in {curr_location} by organizations like {curr_union} could lead to disruptions at our facilities",
]

# Exclusive Coverage Templates (replaces us_only_templates and parts of international_templates)
exclusive_coverage_templates = [
    "Approximately {pct}% of our {curr_location} employees are covered by collective bargaining agreements with {curr_union}. We have no unionized employees in our {neg_other_location} operations",
    "As of {month} {day}, {year}, {cb_count} of our employees in {curr_location} are represented by the {curr_union}. Our {neg_other_location} workforce is not unionized",
    "All of our {cb_count} unionized employees are located in {curr_location} at our {facility}",
    "Our collective bargaining agreements exclusively cover our {curr_location} operations, with approximately {pct}% of the workforce unionized with {curr_union}",
]
