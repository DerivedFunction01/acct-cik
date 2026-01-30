from dataclasses import dataclass, field
from enum import Enum
from defs.regex_lib import add_restrictions
class Region(Enum):
    NORTH_AMERICA = "North America"
    LATIN_AMERICA = "Latin America"
    EUROPE = "Europe"
    MIDDLE_EAST_AFRICA = "Middle East & Africa"
    ASIA_PACIFIC = "Asia Pacific"
    INTERNATIONAL = "International"


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
                ["massachusetts", "ma"],
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
            "ALPA", "Air Line Pilots Association",
            "UMWA", "United Mine Workers of America",
            "IATSE", "International Alliance of Theatrical Stage Employees",
            "IUOE", "International Union of Operating Engineers",
            "ILA", "International Longshoremen's Association",
            "ILWU", "International Longshore and Warehouse Union",
            "BCTGM", "Bakery, Confectionery, Tobacco Workers and Grain Millers",
            "AFSCME", "American Federation of State, County and Municipal Employees",
            "LIUNA", "Laborers' International Union of North America",
            "BLET", "Brotherhood of Locomotive Engineers and Trainmen",
            "SMART-TD", "Sheet Metal, Air, Rail and Transportation Workers",
            "BMWED", "Brotherhood of Maintenance of Way Employes",
            "TWU", "Transport Workers Union",
            "ATU", "Amalgamated Transit Union",
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
    Nation("North America", ["north america", "north american"], Region.NORTH_AMERICA, code="NA"),
    Nation("domestic", ["domestic"], Region.NORTH_AMERICA, code="DOMESTIC"),  # Dummy
}

EUROPE = {
    Nation("Europe", ["europe", "eurozone", "eu", "european"], Region.EUROPE, [], [], ["European Works Council", "Comité d'entreprise européen"], code="EU"),
    Nation("United Kingdom", ["uk", "u.k.", "britain", "united kingdom"], Region.EUROPE, [
        Location("London", ["london"]),
        Location("Birmingham", ["birmingham"]),
        Location("Manchester", ["manchester"]),
    ], [
        "Unite the Union", "Unite",
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
    Nation("Asia Pacific", ["asia pacific", "apac", "asia-pacific"], Region.ASIA_PACIFIC, code="APAC"),
    Nation("Asia", ["asia", "asian"], Region.ASIA_PACIFIC),
    Nation("Japan", ["japan", "japanese"], Region.ASIA_PACIFIC, [
        Location("Tokyo", ["tokyo"]),
        Location("Osaka", ["osaka"]),
        Location("Nagoya", ["nagoya"]),
        Location("Yokohama", ["yokohama"]),
    ], [
        "Rengo", "Japanese Trade Union Confederation",
        "UA Zensen",
    ], [
        "Shunto",
    ], code="JP"),
    Nation("South Korea", ["south korea", "korea", "korean"], Region.ASIA_PACIFIC, [
        Location("Seoul", ["seoul"]),
        Location("Busan", ["busan", "pusan"]),
        Location("Incheon", ["incheon"]),
        Location("Ulsan", ["ulsan"]),
    ], [
        "KCTU", "Korean Confederation of Trade Unions",
        "FKTU", "Federation of Korean Trade Unions",
    ], code="KR"),
    Nation("Singapore", ["singapore", "singaporean"], Region.ASIA_PACIFIC, code="SG"),
    Nation("Hong Kong", ["hong kong", "hk"], Region.ASIA_PACIFIC, code="HK"),
    Nation("Taiwan", ["taiwan", "taiwanese"], Region.ASIA_PACIFIC, [
        Location("Taipei", ["taipei"]),
    ], code="TW"),
    Nation("China", ["china", "chinese", "prc", "p.r.c."], Region.ASIA_PACIFIC, [
        Location("Shanghai", ["shanghai"]),
        Location("Beijing", ["beijing"]),
        Location("Shenzhen", ["shenzhen"]),
        Location("Guangzhou", ["guangzhou"]),
        Location("Tianjin", ["tianjin"]),
        Location("Chongqing", ["chongqing"]),
        Location("Wuhan", ["wuhan"]),
    ], code="CN"),
    Nation("Thailand", ["thailand", "thai"], Region.ASIA_PACIFIC, [
        Location("Bangkok", ["bangkok"]),
    ], code="TH"),
    Nation("Malaysia", ["malaysia", "malaysian"], Region.ASIA_PACIFIC, [
        Location("Kuala Lumpur", ["kuala lumpur", "kl"]),
    ], code="MY"),
    Nation("Philippines", ["philippines", "philippine", "filipino"], Region.ASIA_PACIFIC, [
        Location("Manila", ["manila"]),
    ], code="PH"),
    Nation("Vietnam", ["vietnam", "vietnamese"], Region.ASIA_PACIFIC, [
        Location("Ho Chi Minh City", ["ho chi minh city", "hcmc", "saigon"]),
        Location("Hanoi", ["hanoi"]),
    ], code="VN"),
    Nation("Indonesia", ["indonesia", "indonesian"], Region.ASIA_PACIFIC, [
        Location("Jakarta", ["jakarta"]),
    ], code="ID"),
    Nation("India", ["india", "indian"], Region.ASIA_PACIFIC, [
        Location("Mumbai", ["mumbai", "bombay"]),
        Location("Bangalore", ["bangalore", "bengaluru"]),
        Location("New Delhi", ["new delhi", "delhi"]),
    ], code="IN"),
    Nation("Pakistan", ["pakistan", "pakistani"], Region.ASIA_PACIFIC, code="PK"),
    Nation("Australia", ["australia", "australian"], Region.ASIA_PACIFIC, [
        Location("Sydney", ["sydney"]),
        Location("Melbourne", ["melbourne"]),
    ], [
        "ACTU", "Australian Council of Trade Unions",
        "CFMEU", "Construction, Forestry, Maritime, Mining and Energy Union",
        "AWU", "Australian Workers' Union",
    ], code="AU"),
    Nation("New Zealand", ["new zealand", "nz"], Region.ASIA_PACIFIC, [
        Location("Auckland", ["auckland"]),
    ], code="NZ"),
    Nation("Fiji", ["fiji", "fijian"], Region.ASIA_PACIFIC, code="FJ"),
    Nation("Bangladesh", ["bangladesh", "bangladeshi"], Region.ASIA_PACIFIC, code="BD"),
}

LATIN_AMERICA = {
    Nation("Latin America", ["latin america", "latam", "south america", "south american"], Region.LATIN_AMERICA, code="LATAM"),
    Nation("Mexico", ["mexico", "mexican"], Region.LATIN_AMERICA, [
        Location("Mexico City", ["mexico city", "cdmx"]),
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
            "Sindicato",
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
            "Sindicato",
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
