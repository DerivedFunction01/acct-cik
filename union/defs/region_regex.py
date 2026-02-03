from dataclasses import dataclass, field
from enum import Enum
import re
from typing import Dict, List, Optional, Tuple, Any
from defs.regex_lib import add_restrictions
class Region(Enum):
    NORTH_AMERICA = "US/Canada"
    LATIN_AMERICA = "Latin America"
    EUROPE = "Europe"
    MIDDLE_EAST_AFRICA = "Middle East/Africa"
    ASIA_PACIFIC = "Asia/Pacific"
    INTERNATIONAL = "International"
    UNKNOWN = "Unknown"


class GeoSource(Enum):
    EXPLICIT = "EXPLICIT"
    SPECIFIC_UNION = "GEO_UNION"
    INFERRED_UNION = "INFERRED_UNION"


@dataclass
class Location:
    name: str
    phrases: list[str]
    cities: list["Location"] = field(default_factory=list)

@dataclass
class Nation:
    name: str
    phrases: list[str]
    region: Region
    locations: list[Location] = field(default_factory=list)
    unions: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    code: str = ""
    
    def __hash__(self):
        return hash(self.name)
    
    def __eq__(self, other):
        return self.name == other.name

NORTH_AMERICA = {
    Nation(
        "United States",
        [
            "the US",
            "u.s.",
            "usa",
            "united states",
            "east coast",
            "west coast",
            "midwest",
            "deep south",
            "new england",
            "pacific northwest",
            "southwest",
            "mountain west",
            "great plains",
            "gulf coast",
            "sun belt",
            "rust belt",
            "bible belt",
            "tri-state area",
            "the states",
            "washington",
            "capitol hill",
            "silicon valley",
            "twin cities",
            "domestic",
            add_restrictions(
                r"american?", lookbehinds=[r"central", r"latin", r"south"]
            ),
        ],
        Region.NORTH_AMERICA,
        [
            Location(
                "New York",
                ["new york", "ny"],
                [
                    Location("New York City", ["nyc", "new york city", "manhattan"]),
                ],
            ),
            Location(
                "California",
                ["california", "ca", "cal"],
                [
                    Location("San Francisco", ["san francisco", "sf", "bay area"]),
                    Location("Los Angeles", ["los angeles", "la"]),
                ],
            ),
            Location(
                "Texas",
                ["texas", "tx"],
                [
                    Location("Houston", ["houston"]),
                    Location("Dallas", ["dallas"]),
                ],
            ),
            Location(
                "Illinois",
                ["illinois", "il"],
                [
                    Location("Chicago", ["chicago"]),
                ],
            ),
            Location(
                "Massachusetts",
                ["massachusetts"],
                [
                    Location("Boston", ["boston"]),
                ],
            ),
            Location(
                "Washington",
                ["washington", "wa"],
                [
                    Location("Seattle", ["seattle"]),
                ],
            ),
            Location(
                "Florida",
                ["florida", "fl"],
                [
                    Location("Miami", ["miami"]),
                ],
            ),
            Location(
                "Michigan",
                ["michigan"],
                [
                    Location("Detroit", ["detroit", "motor city"]),
                    Location("Dearborn", ["dearborn"]),
                    Location("Flint", ["flint"]),
                    Location("Lansing", ["lansing"]),
                ],
            ),
            Location(
                "Ohio",
                ["ohio"],
                [
                    Location("Cleveland", ["cleveland"]),
                    Location("Columbus", ["columbus"]),
                    Location("Toledo", ["toledo"]),
                    Location("Marysville", ["marysville"]),
                ],
            ),
            Location(
                "Pennsylvania",
                ["pennsylvania"],
                [
                    Location("Pittsburgh", ["pittsburgh"]),
                    Location("Philadelphia", ["philadelphia", "philly"]),
                ],
            ),
            Location(
                "Indiana",
                ["indiana"],
                [
                    Location("Indianapolis", ["indianapolis"]),
                    Location("Lafayette", ["lafayette"]),
                    Location("Princeton", ["princeton"]),
                ],
            ),
            Location(
                "Kentucky",
                ["kentucky", "ky"],
                [
                    Location("Louisville", ["louisville"]),
                    Location("Georgetown", ["georgetown"]),
                ],
            ),
            Location(
                "Tennessee",
                ["tennessee", "tn"],
                [
                    Location("Nashville", ["nashville"]),
                    Location("Chattanooga", ["chattanooga"]),
                    Location("Smyrna", ["smyrna"]),
                    Location("Spring Hill", ["spring hill"]),
                ],
            ),
            Location(
                "Alabama",
                ["alabama", "al"],
                [
                    Location("Birmingham", ["birmingham"]),
                    Location("Huntsville", ["huntsville"]),
                    Location("Tuscaloosa", ["tuscaloosa"]),
                    Location("Lincoln", ["lincoln"]),
                ],
            ),
            Location(
                "Arizona",
                ["Arizona", "az"],
                [
                    Location("Phoenix", ["phoenix"]),
                    Location("Tucson", ["tucson"]),
                ],
            ),
            Location(
                "Missouri",
                ["missouri", "mo"],
                [
                    Location("St. Louis", ["st. louis"]),
                    Location("Kansas City", ["kansas city, mo"]),
                ],
            ),
            Location(
                "Alaska",
                ["alaska", "ak"],
                [
                    Location("Anchorage", ["anchorage"]),
                    Location("Fairbanks", ["fairbanks"]),
                    Location("Juneau", ["juneau"]),
                ],
            ),
            Location(
                "Arkansas",
                ["arkansas", "ar"],
                [
                    Location("Little Rock", ["little rock"]),
                    Location("Fayetteville", ["fayetteville"]),
                    Location("Fort Smith", ["fort smith"]),
                ],
            ),
            Location(
                "Colorado",
                ["colorado", "co"],
                [
                    Location("Denver", ["denver"]),
                    Location("Colorado Springs", ["colorado springs"]),
                    Location("Boulder", ["boulder"]),
                ],
            ),
            Location(
                "Connecticut",
                ["connecticut", "ct"],
                [
                    Location("Hartford", ["hartford"]),
                    Location("New Haven", ["new haven"]),
                    Location("Stamford", ["stamford"]),
                ],
            ),
            Location(
                "Delaware",
                ["delaware"],
                [
                    Location("Wilmington", ["wilmington"]),
                    Location("Dover", ["dover"]),
                    Location("Newark", ["newark"]),
                ],
            ),
            Location(
                "Georgia",
                ["georgia", "ga"],
                [
                    Location("Atlanta", ["atlanta"]),
                    Location("Savannah", ["savannah"]),
                    Location("Augusta", ["augusta"]),
                ],
            ),
            Location(
                "Hawaii",
                ["hawaii"],
                [
                    Location("Honolulu", ["honolulu"]),
                    Location("Hilo", ["hilo"]),
                    Location("Kailua", ["kailua"]),
                ],
            ),
            Location(
                "Idaho",
                ["idaho"],
                [
                    Location("Boise", ["boise"]),
                    Location("Idaho Falls", ["idaho falls"]),
                    Location("Twin Falls", ["twin falls"]),
                ],
            ),
            Location(
                "Iowa",
                ["iowa", "ia"],
                [
                    Location("Des Moines", ["des moines"]),
                    Location("Cedar Rapids", ["cedar rapids"]),
                    Location("Davenport", ["davenport"]),
                ],
            ),
            Location(
                "Kansas",
                ["kansas", "ks"],
                [
                    Location("Wichita", ["wichita"]),
                    Location("Kansas City", ["kansas city"]),
                    Location("Topeka", ["topeka"]),
                ],
            ),
            Location(
                "Louisiana",
                ["louisiana"],
                [
                    Location("New Orleans", ["new orleans"]),
                    Location("Baton Rouge", ["baton rouge"]),
                    Location("Shreveport", ["shreveport"]),
                ],
            ),
            Location(
                "Maine",
                ["maine"],
                [
                    Location("Portland", ["portland, me"]),
                    Location("Augusta", ["augusta, me"]),
                    Location("Bangor", ["bangor"]),
                ],
            ),
            Location(
                "Maryland",
                ["maryland", "md"],
                [
                    Location("Baltimore", ["baltimore"]),
                    Location("Annapolis", ["annapolis"]),
                    Location("Silver Spring", ["silver spring"]),
                ],
            ),
            Location(
                "Minnesota",
                ["minnesota", "mn"],
                [
                    Location("Minneapolis", ["minneapolis"]),
                    Location("Saint Paul", ["saint paul", "st. paul"]),
                    Location("Rochester", ["rochester mn"]),
                ],
            ),
            Location(
                "Mississippi",
                ["mississippi", "ms"],
                [
                    Location("Jackson", ["jackson, ms"]),
                    Location("Gulfport", ["gulfport"]),
                    Location("Biloxi", ["biloxi"]),
                ],
            ),
            Location(
                "Montana",
                ["montana", "mt"],
                [
                    Location("Billings", ["billings"]),
                    Location("Missoula", ["missoula"]),
                    Location("Bozeman", ["bozeman"]),
                ],
            ),
            Location(
                "Nebraska",
                ["nebraska"],
                [
                    Location("Omaha", ["omaha"]),
                    Location("Lincoln", ["lincoln, ne"]),
                    Location("Grand Island", ["grand island"]),
                ],
            ),
            Location(
                "Nevada",
                ["nevada", "nv"],
                [
                    Location("Las Vegas", ["las vegas", "vegas"]),
                    Location("Reno", ["reno"]),
                    Location("Henderson", ["henderson"]),
                ],
            ),
            Location(
                "New Hampshire",
                ["new hampshire", "nh"],
                [
                    Location("Manchester", ["manchester, nh"]),
                    Location("Nashua", ["nashua"]),
                    Location("Concord", ["concord, nh"]),
                ],
            ),
            Location(
                "New Jersey",
                ["new jersey", "nj"],
                [
                    Location("Newark", ["newark"]),
                    Location("Jersey City", ["jersey city"]),
                    Location("Trenton", ["trenton"]),
                ],
            ),
            Location(
                "New Mexico",
                ["new mexico", "nm"],
                [
                    Location("Albuquerque", ["albuquerque"]),
                    Location("Santa Fe", ["santa fe"]),
                    Location("Las Cruces", ["las cruces"]),
                ],
            ),
            Location(
                "North Carolina",
                ["north carolina", "nc"],
                [
                    Location("Charlotte", ["charlotte"]),
                    Location("Raleigh", ["raleigh"]),
                    Location("Greensboro", ["greensboro"]),
                ],
            ),
            Location(
                "North Dakota",
                ["north dakota", "nd"],
                [
                    Location("Fargo", ["fargo"]),
                    Location("Bismarck", ["bismarck"]),
                    Location("Grand Forks", ["grand forks"]),
                ],
            ),
            Location(
                "Oklahoma",
                ["oklahoma"],
                [
                    Location("Oklahoma City", ["oklahoma city"]),
                    Location("Tulsa", ["tulsa"]),
                    Location("Norman", ["norman"]),
                ],
            ),
            Location(
                "Oregon",
                ["oregon"],
                [
                    Location("Portland", ["portland, or"]),
                    Location("Eugene", ["eugene"]),
                    Location("Salem", ["salem, or"]),
                ],
            ),
            Location(
                "Rhode Island",
                ["rhode island", "ri"],
                [
                    Location("Providence", ["providence"]),
                    Location("Warwick", ["warwick"]),
                    Location("Newport", ["newport, ri"]),
                ],
            ),
            Location(
                "South Carolina",
                ["south carolina", "sc"],
                [
                    Location("Charleston", ["charleston, sc"]),
                    Location("Columbia", ["columbia sc"]),
                    Location("Greenville", ["greenville, sc"]),
                ],
            ),
            Location(
                "South Dakota",
                ["south dakota", "sd"],
                [
                    Location("Sioux Falls", ["sioux falls"]),
                    Location("Rapid City", ["rapid city"]),
                    Location("Pierre", ["pierre"]),
                ],
            ),
            Location(
                "Utah",
                ["utah", "ut"],
                [
                    Location("Salt Lake City", ["salt lake city"]),
                    Location("Provo", ["provo"]),
                    Location("Ogden", ["ogden"]),
                ],
            ),
            Location(
                "Vermont",
                ["vermont", "vt"],
                [
                    Location("Burlington", ["burlington, vt"]),
                    Location("Montpelier", ["montpelier"]),
                    Location("Rutland", ["rutland"]),
                ],
            ),
            Location(
                "Virginia",
                ["virginia", "va"],
                [
                    Location("Richmond", ["richmond, va"]),
                    Location("Virginia Beach", ["virginia beach"]),
                    Location("Norfolk", ["norfolk"]),
                ],
            ),
            Location(
                "West Virginia",
                ["west virginia", "wv"],
                [
                    Location("Charleston", ["charleston, wv"]),
                    Location("Morgantown", ["morgantown"]),
                    Location("Huntington", ["huntington"]),
                ],
            ),
            Location(
                "Wisconsin",
                ["wisconsin", "wi"],
                [
                    Location("Milwaukee", ["milwaukee"]),
                    Location("Madison", ["madison"]),
                    Location("Green Bay", ["green bay"]),
                ],
            ),
            Location(
                "Wyoming",
                ["wyoming", "wy"],
                [
                    Location("Cheyenne", ["cheyenne"]),
                    Location("Casper", ["casper"]),
                    Location("Laramie", ["laramie"]),
                ],
            ),
        ],
        [
            "UAW",
            "United Auto Workers",
            "International Union, United Automobile, Aerospace and Agricultural Implement Workers of America",
            "Teamsters",
            "IBT",
            "International Brotherhood of Teamsters",
            "AFL-CIO",
            "SEIU",
            "Service Employees International Union",
            "UFCW",
            "United Food and Commercial Workers",
            "USW",
            "United Steelworkers",
            "IAM",
            "International Association of Machinists",
            "IBEW",
            "International Brotherhood of Electrical Workers",
            "CWA",
            "Communications Workers of America",
            "UNITE HERE",
            "SAG-AFTRA",
            "Screen Actors Guild",
            "WGA",
            "Writers Guild of America",
            "NEA",
            "National Education Association",
            "AFT",
            "American Federation of Teachers",
            "ALPA",
            "Air Line Pilots Association",
            "UMWA",
            "United Mine Workers of America",
            "IATSE",
            "International Alliance of Theatrical Stage Employees",
            "IUOE",
            "International Union of Operating Engineers",
            "ILA",
            "International Longshoremen's Association",
            "ILWU",
            "International Longshore and Warehouse Union",
            "BCTGM",
            "Bakery, Confectionery, Tobacco Workers and Grain Millers",
            "AFSCME",
            "American Federation of State, County and Municipal Employees",
            "LIUNA",
            "Laborers' International Union of North America",
            "BLET",
            "Brotherhood of Locomotive Engineers and Trainmen",
            "SMART-TD",
            "Sheet Metal, Air, Rail and Transportation Workers",
            "BMWED",
            "Brotherhood of Maintenance of Way Employes",
            "TWU",
            "Transport Workers Union",
            "ATU",
            "Amalgamated Transit Union",
        ],
        code="US",
    ),
    Nation(
        "Canada",
        ["canada", "canadian"],
        Region.NORTH_AMERICA,
        [
            Location("Toronto", ["toronto"]),
            Location("Vancouver", ["vancouver"]),
            Location("Montreal", ["montreal"]),
            Location("Ottawa", ["ottawa"]),
            Location("Ontario", ["ontario"]),
            Location("Quebec", ["quebec", "québec"]),
            Location("Alberta", ["alberta", "calgary", "edmonton"]),
            Location("British Columbia", ["british columbia", "bc"]),
            Location("Winnipeg", ["winnipeg"]),
            Location("Windsor", ["windsor"]),
            Location("Oshawa", ["oshawa"]),
            Location("Oakville", ["oakville"]),
            Location("Brampton", ["brampton"]),
            Location("Cambridge", ["cambridge"]),
            Location("Ingersoll", ["ingersoll"]),
            Location("Hamilton", ["hamilton"]),
            Location("St. Catharines", ["st. catharines"]),
        ],
        [
            "Unifor",
            "CUPE",
            "Canadian Union of Public Employees",
            "CLC",
            "Canadian Labour Congress",
            "CSN",
            "Confédération des syndicats nationaux",
            "FTQ",
            "Fédération des travailleurs et travailleuses du Québec",
        ],
        code="CA",
    ),
    Nation(
        "North America (Domestic)",
        ["north america", "north american", "domestic"],
        Region.NORTH_AMERICA,
        code="NA",
    ),
}

EUROPE = {
    Nation("Europe", ["europe", "eurozone", "eu", "european"], Region.EUROPE, [], [], [], code="EU"),
    Nation("United Kingdom", ["uk", "u.k.", "britain", "united kingdom"], Region.EUROPE, [
        Location("London", ["london"]),
        Location("Birmingham", ["birmingham"]),
        Location("Manchester", ["manchester"]),
    ], [
        "Unite the Union",
        "UNISON",
        "GMB",
        "RMT", "National Union of Rail, Maritime and Transport Workers",
        "ASLEF", "Associated Society of Locomotive Engineers and Firemen",
        "TSSA", "Transport Salaried Staffs' Association",
    ], code="GB"),
    Nation("Norway", ["norway", "norwegian"], Region.EUROPE, code="NO"),
    Nation("Sweden", ["sweden", "swedish"], Region.EUROPE, [
        Location("Stockholm", ["stockholm"]),
    ], code="SE"),
    Nation("Denmark", ["denmark", "danish"], Region.EUROPE, code="DK"),
    Nation("Poland", ["poland", "polish"], Region.EUROPE, [
        Location("Warsaw", ["warsaw"]),
    ], code="PL"),
    Nation("Hungary", ["hungary", "hungarian"], Region.EUROPE, code="HU"),
    Nation("Czech Republic", ["czech republic", "czechia", "czech"], Region.EUROPE, code="CZ"),
    Nation("Turkey", ["turkey", "turkish"], Region.EUROPE, [
        Location("Istanbul", ["istanbul"]),
    ], code="TR"),
    Nation("Russia", ["russia", "russian"], Region.EUROPE, [
        Location("Moscow", ["moscow"]),
    ], code="RU"),
    Nation("Bulgaria", ["bulgaria", "bulgarian"], Region.EUROPE, code="BG"),
    Nation("Romania", ["romania", "romanian"], Region.EUROPE, code="RO"),
    Nation("Germany", ["germany", "german", "deutschland"], Region.EUROPE, [
        Location("Frankfurt", ["frankfurt"]),
        Location("Berlin", ["berlin"]),
        Location("Munich", ["munich"]),
        Location("Hamburg", ["hamburg"]),
        Location("Stuttgart", ["stuttgart"]),
        Location("Cologne", ["cologne", "koln"]),
        Location("Dusseldorf", ["dusseldorf"]),
    ], [
        "IG Metall",
        "ver.di",
        "IG BCE",
        "DGB", "German Trade Union Confederation",
    ], [
        "Gewerkschaft", "Arbeitnehmer", "Betriebsrat", "Tarifvertrag", "Bergbau", "Automobil", "Mitbestimmung", "Aufsichtsrat", "Tarifverhandlungen", "Luftfahrt", "Chemie", "Metall", "Bau", "Eisenbahn",
    ], code="DE"),
    Nation("France", ["france", "french"], Region.EUROPE, [
        Location("Paris", ["paris"]),
        Location("Lyon", ["lyon"]),
        Location("Marseille", ["marseille"]),
    ], [
        "CFDT", "French Democratic Confederation of Labour",
        "FO", "Force Ouvrière",
        "CGT", "Confédération Générale du Travail",
    ], [
        "Comité Social et Économique", "Cheminots",
    ], code="FR"),
    Nation("Italy", ["italy", "italian"], Region.EUROPE, [
        Location("Milan", ["milan"]),
        Location("Rome", ["rome"]),
        Location("Turin", ["turin", "torino"]),
    ], [
        "CGIL", "Italian General Confederation of Labour",
        "CISL",
        "UIL",
    ], [
        "Sindacato", "Lavoro", "Sciopero", "Automobilistico", "Contratto Collettivo", "Contrattazione", "Trasporti", "Metalmeccanici", "Chimico", "Edile", "Ferrovie",
    ], code="IT"),
    Nation("Spain", ["spain", "spanish"], Region.EUROPE, [
        Location("Madrid", ["madrid"]),
        Location("Barcelona", ["barcelona"]),
    ], [
        "CCOO", "Workers' Commissions",
    ], [
        # Moved to International due to ambiguity with Latin America
    ], code="ES"),
    Nation("Netherlands", ["netherlands", "dutch", "holland"], Region.EUROPE, [
        Location("Amsterdam", ["amsterdam"]),
        Location("Rotterdam", ["rotterdam"]),
    ], [], [
        "Vakbond", "Ondernemingsraad", "CAO", "Metaal", "Bouw", "Vervoer", "Spoorwegen",
    ], code="NL"),
    Nation("Switzerland", ["switzerland", "swiss"], Region.EUROPE, [
        Location("Zurich", ["zurich"]),
        Location("Geneva", ["geneva"]),
    ], code="CH"),
    Nation("Belgium", ["belgium", "belgian"], Region.EUROPE, [
        Location("Brussels", ["brussels"]),
        Location("Antwerp", ["antwerp"]),
    ], code="BE"),
    Nation("Austria", ["austria", "austrian"], Region.EUROPE, [
        Location("Vienna", ["vienna"]),
    ], code="AT"),
    Nation("Ireland", ["ireland", "irish"], Region.EUROPE, [
        Location("Dublin", ["dublin"]),
    ], code="IE"),
    Nation("Portugal", ["portugal", "portuguese"], Region.EUROPE, code="PT"),
    Nation("Greece", ["greece", "greek"], Region.EUROPE, code="GR"),
    Nation("Finland", ["finland", "finnish"], Region.EUROPE, code="FI"),
    Nation("Ukraine", ["ukraine", "ukrainian"], Region.EUROPE, code="UA"),
}

ASIA_PACIFIC = {
    Nation(
        "Asia",
        ["asia", "asian", "asia pacific", "apac", "asia-pacific"],
        Region.ASIA_PACIFIC,
        code="APAC",
    ),
    Nation(
        "Japan",
        ["japan", "japanese"],
        Region.ASIA_PACIFIC,
        [
            Location("Tokyo", ["tokyo"]),
            Location("Osaka", ["osaka"]),
            Location("Nagoya", ["nagoya"]),
            Location("Yokohama", ["yokohama"]),
        ],
        [
            "Rengo",
            "Japanese Trade Union Confederation",
            "UA Zensen",
            "JAM",
            "Japanese Association of Metal and Allied Workers",
        ],
        [
            "Shunto",
        ],
        code="JP",
    ),
    Nation(
        "South Korea",
        ["south korea", "korea", "korean"],
        Region.ASIA_PACIFIC,
        [
            Location("Seoul", ["seoul"]),
            Location("Busan", ["busan", "pusan"]),
            Location("Incheon", ["incheon"]),
            Location("Ulsan", ["ulsan"]),
        ],
        [
            "KCTU",
            "Korean Confederation of Trade Unions",
            "FKTU",
            "Federation of Korean Trade Unions",
        ],
        code="KR",
    ),
    Nation("Singapore", ["singapore", "singaporean"], Region.ASIA_PACIFIC, code="SG"),
    Nation("Hong Kong", ["hong kong", "hk"], Region.ASIA_PACIFIC, code="HK"),
    Nation(
        "Taiwan",
        ["taiwan", "taiwanese"],
        Region.ASIA_PACIFIC,
        [
            Location("Taipei", ["taipei"]),
        ],
        code="TW",
    ),
    Nation(
        "China",
        ["china", "chinese", "prc", "p.r.c."],
        Region.ASIA_PACIFIC,
        [
            Location("Shanghai", ["shanghai"]),
            Location("Beijing", ["beijing"]),
            Location("Shenzhen", ["shenzhen"]),
            Location("Guangzhou", ["guangzhou"]),
            Location("Tianjin", ["tianjin"]),
            Location("Chongqing", ["chongqing"]),
            Location("Wuhan", ["wuhan"]),
        ],
        code="CN",
    ),
    Nation(
        "Thailand",
        ["thailand", "thai"],
        Region.ASIA_PACIFIC,
        [
            Location("Bangkok", ["bangkok"]),
        ],
        code="TH",
    ),
    Nation(
        "Malaysia",
        ["malaysia", "malaysian"],
        Region.ASIA_PACIFIC,
        [
            Location("Kuala Lumpur", ["kuala lumpur", "kl"]),
        ],
        code="MY",
    ),
    Nation(
        "Philippines",
        ["philippines", "philippine", "filipino"],
        Region.ASIA_PACIFIC,
        [
            Location("Manila", ["manila"]),
        ],
        code="PH",
    ),
    Nation(
        "Vietnam",
        ["vietnam", "vietnamese"],
        Region.ASIA_PACIFIC,
        [
            Location("Ho Chi Minh City", ["ho chi minh city", "hcmc", "saigon"]),
            Location("Hanoi", ["hanoi"]),
        ],
        code="VN",
    ),
    Nation(
        "Indonesia",
        ["indonesia", "indonesian"],
        Region.ASIA_PACIFIC,
        [
            Location("Jakarta", ["jakarta"]),
        ],
        code="ID",
    ),
    Nation(
        "India",
        ["india", "indian"],
        Region.ASIA_PACIFIC,
        [
            Location("Mumbai", ["mumbai", "bombay"]),
            Location("Bangalore", ["bangalore", "bengaluru"]),
            Location("New Delhi", ["new delhi", "delhi"]),
        ],
        code="IN",
    ),
    Nation("Pakistan", ["pakistan", "pakistani"], Region.ASIA_PACIFIC, code="PK"),
    Nation(
        "Australia",
        ["australia", "australian"],
        Region.ASIA_PACIFIC,
        [
            Location("Sydney", ["sydney"]),
            Location("Melbourne", ["melbourne"]),
        ],
        [
            "ACTU",
            "Australian Council of Trade Unions",
            "CFMEU",
            "Construction, Forestry, Maritime, Mining and Energy Union",
            "AWU",
            "Australian Workers' Union",
        ],
        code="AU",
    ),
    Nation(
        "New Zealand",
        ["new zealand", "nz"],
        Region.ASIA_PACIFIC,
        [
            Location("Auckland", ["auckland"]),
        ],
        code="NZ",
    ),
    Nation("Fiji", ["fiji", "fijian"], Region.ASIA_PACIFIC, code="FJ"),
    Nation("Bangladesh", ["bangladesh", "bangladeshi"], Region.ASIA_PACIFIC, code="BD"),
}

LATIN_AMERICA = {
    Nation("Latin America", ["latin america", "latam", "south america", "south american"], Region.LATIN_AMERICA, code="LATAM"),
    Nation("Mexico", ["mexico", "mexican"], Region.LATIN_AMERICA, [
        Location("Mexico City", ["mexico city", "cdmx"]),
        Location("Monterrey", ["monterrey"]),
        Location("Saltillo", ["saltillo", "ramos arizpe"]),
        Location("Hermosillo", ["hermosillo"]),
        Location("Puebla", ["puebla"]),
        Location("Toluca", ["toluca"]),
        Location("San Luis Potosi", ["san luis potosi", "slp"]),
        Location("Aguascalientes", ["aguascalientes"]),
        Location("Silao", ["silao"]),
        Location("Guanajuato", ["guanajuato"]),
        Location("Queretaro", ["queretaro"]),
        Location("Tijuana", ["tijuana"]),
        Location("Juarez", ["juarez", "ciudad juarez"]),
        Location("Cuautitlan", ["cuautitlan"]),
    ], [
        "CTM", "Confederation of Mexican Workers",
    ], [
        "Maquiladora",
    ], code="MX"),
    Nation("Brazil", ["brazil", "brazilian"], Region.LATIN_AMERICA, [
        Location("Sao Paulo", ["sao paulo"]),
        Location("Rio de Janeiro", ["rio de janeiro", "rio"]),
    ], [
        "CUT", "Unified Workers' Central",
        "Força Sindical",
    ], [
        "Dissídio",
    ], code="BR"),
    Nation("Argentina", ["argentina", "argentine"], Region.LATIN_AMERICA, [
        Location("Buenos Aires", ["buenos aires"]),
    ], code="AR"),
    Nation("Chile", ["chile", "chilean"], Region.LATIN_AMERICA, [
        Location("Santiago", ["santiago"]),
    ], code="CL"),
    Nation("Colombia", ["colombia", "colombian"], Region.LATIN_AMERICA, [
        Location("Bogota", ["bogota"]),
    ], code="CO"),
    Nation("Peru", ["peru", "peruvian"], Region.LATIN_AMERICA, code="PE"),
    Nation("Venezuela", ["venezuela", "venezuelan"], Region.LATIN_AMERICA, code="VE"),
    Nation("Ecuador", ["ecuador", "ecuadorian"], Region.LATIN_AMERICA, code="EC"),
    Nation("Guatemala", ["guatemala", "guatemalan"], Region.LATIN_AMERICA, code="GT"),
    Nation("Dominican Republic", ["dominican republic", "dominican"], Region.LATIN_AMERICA, code="DO"),
    Nation("Costa Rica", ["costa rica", "costa rican"], Region.LATIN_AMERICA, code="CR"),
    Nation("Panama", ["panama", "panamanian"], Region.LATIN_AMERICA, code="PA"),
    Nation("Uruguay", ["uruguay", "uruguayan"], Region.LATIN_AMERICA, code="UY"),
    Nation("Bolivia", ["bolivia", "bolivian"], Region.LATIN_AMERICA, code="BO"),
    Nation("Paraguay", ["paraguay", "paraguayan"], Region.LATIN_AMERICA, code="PY"),
}

MIDDLE_EAST_AFRICA = {
    Nation("Middle East", ["middle east", "middle eastern", "mena"], Region.MIDDLE_EAST_AFRICA, code="MEA"),
    Nation("Africa", ["africa", "african"], Region.MIDDLE_EAST_AFRICA, code="AFRICA"),
    Nation("United Arab Emirates", ["uae", "u.a.e.", "emirates"], Region.MIDDLE_EAST_AFRICA, [
        Location("Dubai", ["dubai"]),
        Location("Abu Dhabi", ["abu dhabi"]),
    ], code="AE"),
    Nation("Saudi Arabia", ["saudi arabia", "saudi"], Region.MIDDLE_EAST_AFRICA, [
        Location("Riyadh", ["riyadh"]),
    ], code="SA"),
    Nation("Israel", ["israel", "israeli"], Region.MIDDLE_EAST_AFRICA, [
        Location("Tel Aviv", ["tel aviv"]),
        Location("Jerusalem", ["jerusalem"]),
    ], code="IL"),
    Nation("Kuwait", ["kuwait", "kuwaiti"], Region.MIDDLE_EAST_AFRICA, code="KW"),
    Nation("South Africa", ["south africa", "south african"], Region.MIDDLE_EAST_AFRICA, [
        Location("Johannesburg", ["johannesburg", "joburg"]),
        Location("Cape Town", ["cape town"]),
    ], [
        "COSATU", "Congress of South African Trade Unions",
        "AMCU", "Association of Mineworkers and Construction Union",
        "NUMSA", "National Union of Metalworkers of South Africa",
    ], code="ZA"),
    Nation("Nigeria", ["nigeria", "nigerian"], Region.MIDDLE_EAST_AFRICA, [
        Location("Lagos", ["lagos"]),
    ], code="NG"),
    Nation("Kenya", ["kenya", "kenyan"], Region.MIDDLE_EAST_AFRICA, [
        Location("Nairobi", ["nairobi"]),
    ], code="KE"),
    Nation("Tanzania", ["tanzania", "tanzanian"], Region.MIDDLE_EAST_AFRICA, code="TZ"),
    Nation("Egypt", ["egypt", "egyptian"], Region.MIDDLE_EAST_AFRICA, [
        Location("Cairo", ["cairo"]),
    ], code="EG"),
    Nation("Ethiopia", ["ethiopia", "ethiopian"], Region.MIDDLE_EAST_AFRICA, code="ET"),
    Nation("Ghana", ["ghana", "ghanaian"], Region.MIDDLE_EAST_AFRICA, code="GH"),
    Nation("Morocco", ["morocco", "moroccan"], Region.MIDDLE_EAST_AFRICA, [], [
        "UMT", "Union Marocaine du Travail",
        "CDT", "Confédération Démocratique du Travail",
    ], code="MA"),
    Nation("Tunisia", ["tunisia", "tunisian"], Region.MIDDLE_EAST_AFRICA, [], [
        "UGTT", "Union Générale Tunisienne du Travail",
    ], code="TN"),
    Nation("Algeria", ["algeria", "algerian"], Region.MIDDLE_EAST_AFRICA, code="DZ"),
    Nation("Qatar", ["qatar", "qatari"], Region.MIDDLE_EAST_AFRICA, code="QA"),
}

INTERNATIONAL = {
    Nation(
        "International",
        ["international", "foreign", "overseas", "global", "worldwide"],
        Region.INTERNATIONAL,
        [],
        [
            "ITF",
            "International Transport Workers' Federation",
            "UNI Global Union",
            "IndustriALL",
            "IUF",
            "PSI",
            "Public Services International",
        ],
        code="INT"),
    Nation(
        "International Spanish",
        [],
        Region.INTERNATIONAL,
        [],
        [],
        [
            "Trabajo",
            "Huelga",
            "Gremios",
            "Minería",
            "Automóvil",
            "Automotriz",
            "Contrato Colectivo",
            "Convenio Colectivo",
            "Negociación colectiva",
            "Aéreo",
            "Metalúrgica",
            "Química",
            "Construcción",
            "Transporte",
            "Ferrocarril",
            "Ferroviarios",
        ],
        code="INT_ES",
    ),
    Nation(
        "International Portuguese",
        [],
        Region.INTERNATIONAL,
        [],
        [],
        [
            "Trabalho",
            "Greve",
            "Mineração",
            "Automotivo",
            "Convenção Coletiva",
            "Negociação coletiva",
            "Aéreo",
            "Metalúrgica",
            "Metalúrgicos",
            "Química",
            "Construção",
            "Transporte",
            "Bancários",
            "Petroleiros",
            "Ferroviários",
        ],
        code="INT_PT",
    ),
    Nation(
        "International French",
        [],
        Region.INTERNATIONAL,
        [],
        [],
        [
            "Syndicat",
            "Travail",
            "Salariés",
            "Grève",
            "Négociation collective",
            "Convention collective",
            "Aérien",
            "Métallurgie",
            "Chimie",
            "Bâtiment",
            "Minier",
            "Ferroviaire",
        ],
        code="INT_FR",
    ),
}

INT_LANGUAGE_MAP = {
    "INT_PT": {"BR", "PT"},
    "INT_ES": {
        "ES", "MX", "AR", "CL", "CO", "PE", "VE", "EC", 
        "GT", "DO", "CR", "PA", "UY", "BO", "PY"
    },
    "INT_FR": {"FR", "BE", "CH", "CA"},
}
REGION_CODES = {
    "NA",
    "EU",
    "APAC",
    "LATAM",
    "MEA",
    "AFRICA",
    "INT",
    "INT_ES",
    "INT_PT",
    "INT_FR",
}

class RegionMatcher:
    """
    Compiles regexes for Regions, Nations, and Specific Unions.
    Allows independent parsing of text to find these entities.
    """
    union_map: Dict[str, Tuple[Region, str, str]] = {} # term -> (Region, Country, Code)
    location_map: Dict[str, Tuple[Region, str, Optional[str], str]] = {} # term -> (Region, Country, City, Code)

    specific_union_regex: Optional[re.Pattern] = None
    location_regex: Optional[re.Pattern] = None
    _compiled = False

    def __init__(self):
        if not RegionMatcher._compiled:
            RegionMatcher._compile()

    @classmethod
    def _compile(cls):
        all_regions = [
            NORTH_AMERICA, EUROPE, ASIA_PACIFIC, LATIN_AMERICA, 
            MIDDLE_EAST_AFRICA, INTERNATIONAL
        ]

        union_phrases = set()
        geo_phrases = set()

        for region_set in all_regions:
            for nation in region_set:
                # 1. Map Specific Unions
                for union_name in nation.unions:
                    # Store mapping
                    cls.union_map[union_name.lower()] = (nation.region, nation.name, nation.code)
                    union_phrases.add(union_name)

                # 1b. Map Keywords (Treat as Phrases for detection - Region Match Only)
                for keyword in nation.keywords:
                    cls.location_map[keyword.lower()] = (nation.region, nation.name, None, nation.code)
                    geo_phrases.add(keyword)

                # 2. Map Nation Phrases (e.g. "USA", "United States")
                for phrase in nation.phrases:
                    cls.location_map[phrase.lower()] = (nation.region, nation.name, None, nation.code)
                    geo_phrases.add(phrase)

                # 3. Map Nation Name
                cls.location_map[nation.name.lower()] = (nation.region, nation.name, None, nation.code)
                geo_phrases.add(nation.name)

                # 4. Map Locations (Cities/States)
                for loc in nation.locations:
                    # Location Name
                    cls.location_map[loc.name.lower()] = (nation.region, nation.name, loc.name, nation.code)
                    geo_phrases.add(loc.name)

                    # Location Phrases
                    for phrase in loc.phrases:
                        cls.location_map[phrase.lower()] = (nation.region, nation.name, loc.name, nation.code)
                        geo_phrases.add(phrase)

                    # Sub-cities
                    for sub in loc.cities:
                        cls.location_map[sub.name.lower()] = (nation.region, nation.name, sub.name, nation.code)
                        geo_phrases.add(sub.name)
                        for phrase in sub.phrases:
                            cls.location_map[phrase.lower()] = (nation.region, nation.name, sub.name, nation.code)
                            geo_phrases.add(phrase)

        # Helper to safely escape phrases (unless they are already regex patterns)
        def safe_escape(phrases):
            escaped = []
            # Sort by length descending to match longest first
            for p in sorted(list(phrases), key=len, reverse=True):
                # If it starts with (? it is likely a regex lookbehind/ahead from add_restrictions
                if p.startswith("(?"):
                    escaped.append(p)
                else:
                    escaped.append(re.escape(p))
            return escaped

        # Compile Specific Union Regex
        if union_phrases:
            pattern_str = r"(?<!\w)(?:" + "|".join(safe_escape(union_phrases)) + r")(?!\w)"
            cls.specific_union_regex = re.compile(pattern_str, re.IGNORECASE)

        # Compile Location Regex
        if geo_phrases:
            pattern_str = r"(?<!\w)(?:" + "|".join(safe_escape(geo_phrases)) + r")(?!\w)"
            cls.location_regex = re.compile(pattern_str, re.IGNORECASE)

        cls._compiled = True

    def parse_unions(self, text: str) -> List[Dict[str, Any]]:
        """Returns list of specific union matches with metadata."""
        results = []
        if self.specific_union_regex:
            for m in self.specific_union_regex.finditer(text):
                term = m.group(0)
                region, country, code = self.union_map.get(term.lower(), (None, None, None))
                results.append({
                    "term": term,
                    "region": region,
                    "country": country,
                    "code": code,
                    "span": m.span()
                })
        return results

MAJOR_CURRENCIES = {
    "USD": {"symbols": ["$"], "names": ["dollar", "dollars"], "prefix": True},
    "EUR": {"symbols": ["€"], "names": ["euro", "euros"], "prefix": True},
    "GBP": {"symbols": ["£"], "names": ["pound", "pounds", "sterling"], "prefix": True},
    "JPY": {"symbols": ["¥"], "names": ["yen"], "prefix": True},
    "CNY": {"symbols": ["¥"], "names": ["yuan", "renminbi"], "prefix": True},
    "INR": {"symbols": ["₹"], "names": ["rupee", "rupees"], "suffix": True},
    "CAD": {"symbols": ["C$", "CAD"], "names": ["canadian dollar"], "prefix": True},
    "AUD": {"symbols": ["A$", "AUD"], "names": ["australian dollar"], "prefix": True},
    "CHF": {"symbols": ["CHF"], "names": ["swiss franc"], "prefix": True},
    "SEK": {"symbols": ["kr"], "names": ["krona", "kronor"], "suffix": True},
    "NOK": {"symbols": ["kr"], "names": ["krone", "kroner"], "suffix": True},
    "DKK": {"symbols": ["kr"], "names": ["krone"], "suffix": True},
    "MXN": {"symbols": ["Mex$"], "names": ["mexican peso"], "prefix": True},
    "BRL": {"symbols": ["R$", "BRL"], "names": ["brazilian real"], "prefix": True},
}
