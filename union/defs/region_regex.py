from dataclasses import dataclass, field
from enum import Enum

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
    
    def __hash__(self):
        return hash(self.name)
    
    def __eq__(self, other):
        return self.name == other.name

NORTH_AMERICA = {
    Nation(
        "United States",
        ["us", "u.s.", "usa", "united states", "american", "america"],
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
        ],
    ),
    Nation(
        "Canada",
        ["canada", "canadian"],
        Region.NORTH_AMERICA,
        [
            Location("Toronto", ["toronto"]),
            Location("Vancouver", ["vancouver"]),
            Location("Montreal", ["montreal"]),
            Location("Ontario", ["ontario"]),
            Location("Quebec", ["quebec"]),
            Location("Alberta", ["alberta", "calgary"]),
            Location("British Columbia", ["british columbia", "bc"]),
        ],
        [
            "Unifor",
            "CUPE",
            "Canadian Union of Public Employees",
            "CLC",
            "Canadian Labour Congress",
        ],
    ),
    Nation("North America", ["north america", "north american"], Region.NORTH_AMERICA),
    Nation("domestic", ["domestic"], Region.NORTH_AMERICA),  # Dummy
}

EUROPE = {
    Nation("Europe", ["europe", "eurozone", "eu", "european"], Region.EUROPE, [], [], ["European Works Council", "Comité d'entreprise européen"]),
    Nation("United Kingdom", ["uk", "u.k.", "britain", "united kingdom"], Region.EUROPE, [
        Location("London", ["london"]),
    ], [
        "Unite the Union", "Unite",
        "UNISON",
        "GMB",
        "CWU", "Communication Workers Union",
        "RMT", "National Union of Rail, Maritime and Transport Workers",
    ]),
    Nation("Norway", ["norway", "norwegian"], Region.EUROPE),
    Nation("Sweden", ["sweden", "swedish"], Region.EUROPE, [
        Location("Stockholm", ["stockholm"]),
    ]),
    Nation("Denmark", ["denmark", "danish"], Region.EUROPE),
    Nation("Poland", ["poland", "polish"], Region.EUROPE, [
        Location("Warsaw", ["warsaw"]),
    ]),
    Nation("Hungary", ["hungary", "hungarian"], Region.EUROPE),
    Nation("Czech Republic", ["czech republic", "czechia", "czech"], Region.EUROPE),
    Nation("Turkey", ["turkey", "turkish"], Region.EUROPE, [
        Location("Istanbul", ["istanbul"]),
    ]),
    Nation("Russia", ["russia", "russian"], Region.EUROPE, [
        Location("Moscow", ["moscow"]),
    ]),
    Nation("Bulgaria", ["bulgaria", "bulgarian"], Region.EUROPE),
    Nation("Romania", ["romania", "romanian"], Region.EUROPE),
    Nation("Germany", ["germany", "german", "deutschland"], Region.EUROPE, [
        Location("Frankfurt", ["frankfurt"]),
        Location("Berlin", ["berlin"]),
        Location("Munich", ["munich"]),
    ], [
        "IG Metall",
        "ver.di", "United Services Union",
        "IG BCE",
        "DGB", "German Trade Union Confederation",
    ], [
        "Gewerkschaft", "Arbeitnehmer", "Betriebsrat", "Tarifvertrag", "Bergbau", "Automobil", "Mitbestimmung", "Aufsichtsrat", "Tarifverhandlungen", "Luftfahrt", "Chemie", "Metall", "Bau", "Eisenbahn",
    ]),
    Nation("France", ["france", "french"], Region.EUROPE, [
        Location("Paris", ["paris"]),
    ], [
        "CGT", "General Confederation of Labour",
        "CFDT", "French Democratic Confederation of Labour",
        "FO", "Force Ouvrière",
    ], [
        "Syndicat", "Travail", "Salariés", "Comité Social et Économique", "Minier", "Grève", "Négociation collective", "Convention collective", "Aérien", "Métallurgie", "Chimie", "Cheminots", "Bâtiment",
    ]),
    Nation("Italy", ["italy", "italian"], Region.EUROPE, [
        Location("Milan", ["milan"]),
        Location("Rome", ["rome"]),
    ], [
        "CGIL", "Italian General Confederation of Labour",
        "CISL",
        "UIL",
    ], [
        "Sindacato", "Lavoro", "Sciopero", "Automobilistico", "Contratto Collettivo", "Contrattazione", "Trasporti", "Metalmeccanici", "Chimico", "Edile",
    ]),
    Nation("Spain", ["spain", "spanish"], Region.EUROPE, [
        Location("Madrid", ["madrid"]),
        Location("Barcelona", ["barcelona"]),
    ], [
        "CCOO", "Workers' Commissions",
        "UGT", "General Union of Workers",
    ], [
        # Moved to International due to ambiguity with Latin America
    ]),
    Nation("Netherlands", ["netherlands", "dutch", "holland"], Region.EUROPE, [
        Location("Amsterdam", ["amsterdam"]),
    ], [], [
        "Vakbond", "Ondernemingsraad", "CAO", "Metaal", "Bouw", "Vervoer",
    ]),
    Nation("Switzerland", ["switzerland", "swiss"], Region.EUROPE, [
        Location("Zurich", ["zurich"]),
        Location("Geneva", ["geneva"]),
    ]),
    Nation("Belgium", ["belgium", "belgian"], Region.EUROPE, [
        Location("Brussels", ["brussels"]),
    ]),
    Nation("Austria", ["austria", "austrian"], Region.EUROPE, [
        Location("Vienna", ["vienna"]),
    ]),
    Nation("Ireland", ["ireland", "irish"], Region.EUROPE, [
        Location("Dublin", ["dublin"]),
    ]),
    Nation("Portugal", ["portugal", "portuguese"], Region.EUROPE),
    Nation("Greece", ["greece", "greek"], Region.EUROPE),
    Nation("Finland", ["finland", "finnish"], Region.EUROPE),
    Nation("Ukraine", ["ukraine", "ukrainian"], Region.EUROPE),
}

ASIA_PACIFIC = {
    Nation("Asia Pacific", ["asia pacific", "apac", "asia-pacific"], Region.ASIA_PACIFIC),
    Nation("Asia", ["asia", "asian"], Region.ASIA_PACIFIC),
    Nation("Japan", ["japan", "japanese"], Region.ASIA_PACIFIC, [
        Location("Tokyo", ["tokyo"]),
        Location("Osaka", ["osaka"]),
    ], [
        "Rengo", "Japanese Trade Union Confederation",
        "UA Zensen",
    ], [
        "Shunto",
    ]),
    Nation("South Korea", ["south korea", "korea", "korean"], Region.ASIA_PACIFIC, [
        Location("Seoul", ["seoul"]),
    ], [
        "KCTU", "Korean Confederation of Trade Unions",
        "FKTU", "Federation of Korean Trade Unions",
    ]),
    Nation("Singapore", ["singapore", "singaporean"], Region.ASIA_PACIFIC),
    Nation("Hong Kong", ["hong kong", "hk"], Region.ASIA_PACIFIC),
    Nation("Taiwan", ["taiwan", "taiwanese"], Region.ASIA_PACIFIC, [
        Location("Taipei", ["taipei"]),
    ]),
    Nation("China", ["china", "chinese", "prc", "p.r.c."], Region.ASIA_PACIFIC, [
        Location("Shanghai", ["shanghai"]),
        Location("Beijing", ["beijing"]),
        Location("Shenzhen", ["shenzhen"]),
        Location("Guangzhou", ["guangzhou"]),
    ]),
    Nation("Thailand", ["thailand", "thai"], Region.ASIA_PACIFIC, [
        Location("Bangkok", ["bangkok"]),
    ]),
    Nation("Malaysia", ["malaysia", "malaysian"], Region.ASIA_PACIFIC, [
        Location("Kuala Lumpur", ["kuala lumpur", "kl"]),
    ]),
    Nation("Philippines", ["philippines", "philippine", "filipino"], Region.ASIA_PACIFIC, [
        Location("Manila", ["manila"]),
    ]),
    Nation("Vietnam", ["vietnam", "vietnamese"], Region.ASIA_PACIFIC, [
        Location("Ho Chi Minh City", ["ho chi minh city", "hcmc", "saigon"]),
        Location("Hanoi", ["hanoi"]),
    ]),
    Nation("Indonesia", ["indonesia", "indonesian"], Region.ASIA_PACIFIC, [
        Location("Jakarta", ["jakarta"]),
    ]),
    Nation("India", ["india", "indian"], Region.ASIA_PACIFIC, [
        Location("Mumbai", ["mumbai", "bombay"]),
        Location("Bangalore", ["bangalore", "bengaluru"]),
        Location("New Delhi", ["new delhi", "delhi"]),
    ]),
    Nation("Pakistan", ["pakistan", "pakistani"], Region.ASIA_PACIFIC),
    Nation("Australia", ["australia", "australian"], Region.ASIA_PACIFIC, [
        Location("Sydney", ["sydney"]),
        Location("Melbourne", ["melbourne"]),
    ], [
        "ACTU", "Australian Council of Trade Unions",
        "CFMEU", "Construction, Forestry, Maritime, Mining and Energy Union",
        "AWU", "Australian Workers' Union",
    ]),
    Nation("New Zealand", ["new zealand", "nz"], Region.ASIA_PACIFIC, [
        Location("Auckland", ["auckland"]),
    ]),
    Nation("Fiji", ["fiji", "fijian"], Region.ASIA_PACIFIC),
    Nation("Bangladesh", ["bangladesh", "bangladeshi"], Region.ASIA_PACIFIC),
}

LATIN_AMERICA = {
    Nation("Latin America", ["latin america", "latam", "south america", "south american"], Region.LATIN_AMERICA, [], [], []),
    Nation("Mexico", ["mexico", "mexican"], Region.LATIN_AMERICA, [
        Location("Mexico City", ["mexico city", "cdmx"]),
    ], [
        "CTM", "Confederation of Mexican Workers",
        "UNT", "National Union of Workers",
    ], [
        "Maquiladora",
    ]),
    Nation("Brazil", ["brazil", "brazilian"], Region.LATIN_AMERICA, [
        Location("Sao Paulo", ["sao paulo"]),
        Location("Rio de Janeiro", ["rio de janeiro", "rio"]),
    ], [
        "CUT", "Unified Workers' Central",
        "Força Sindical",
    ], [
        "Dissídio",
    ]),
    Nation("Argentina", ["argentina", "argentine"], Region.LATIN_AMERICA, [
        Location("Buenos Aires", ["buenos aires"]),
    ]),
    Nation("Chile", ["chile", "chilean"], Region.LATIN_AMERICA, [
        Location("Santiago", ["santiago"]),
    ]),
    Nation("Colombia", ["colombia", "colombian"], Region.LATIN_AMERICA, [
        Location("Bogota", ["bogota"]),
    ]),
    Nation("Peru", ["peru", "peruvian"], Region.LATIN_AMERICA),
    Nation("Venezuela", ["venezuela", "venezuelan"], Region.LATIN_AMERICA),
    Nation("Ecuador", ["ecuador", "ecuadorian"], Region.LATIN_AMERICA),
    Nation("Guatemala", ["guatemala", "guatemalan"], Region.LATIN_AMERICA),
    Nation("Dominican Republic", ["dominican republic", "dominican"], Region.LATIN_AMERICA),
    Nation("Costa Rica", ["costa rica", "costa rican"], Region.LATIN_AMERICA),
    Nation("Panama", ["panama", "panamanian"], Region.LATIN_AMERICA),
    Nation("Uruguay", ["uruguay", "uruguayan"], Region.LATIN_AMERICA),
    Nation("Bolivia", ["bolivia", "bolivian"], Region.LATIN_AMERICA),
    Nation("Paraguay", ["paraguay", "paraguayan"], Region.LATIN_AMERICA),
}

MIDDLE_EAST_AFRICA = {
    Nation("Middle East", ["middle east", "middle eastern", "mena"], Region.MIDDLE_EAST_AFRICA),
    Nation("Africa", ["africa", "african"], Region.MIDDLE_EAST_AFRICA),
    Nation("United Arab Emirates", ["uae", "u.a.e.", "emirates"], Region.MIDDLE_EAST_AFRICA, [
        Location("Dubai", ["dubai"]),
        Location("Abu Dhabi", ["abu dhabi"]),
    ]),
    Nation("Saudi Arabia", ["saudi arabia", "saudi"], Region.MIDDLE_EAST_AFRICA, [
        Location("Riyadh", ["riyadh"]),
    ]),
    Nation("Israel", ["israel", "israeli"], Region.MIDDLE_EAST_AFRICA, [
        Location("Tel Aviv", ["tel aviv"]),
        Location("Jerusalem", ["jerusalem"]),
    ]),
    Nation("Kuwait", ["kuwait", "kuwaiti"], Region.MIDDLE_EAST_AFRICA),
    Nation("South Africa", ["south africa", "south african"], Region.MIDDLE_EAST_AFRICA, [
        Location("Johannesburg", ["johannesburg", "joburg"]),
        Location("Cape Town", ["cape town"]),
    ], [
        "COSATU", "Congress of South African Trade Unions",
        "NUM", "National Union of Mineworkers",
        "AMCU", "Association of Mineworkers and Construction Union",
    ]),
    Nation("Nigeria", ["nigeria", "nigerian"], Region.MIDDLE_EAST_AFRICA, [
        Location("Lagos", ["lagos"]),
    ]),
    Nation("Kenya", ["kenya", "kenyan"], Region.MIDDLE_EAST_AFRICA, [
        Location("Nairobi", ["nairobi"]),
    ]),
    Nation("Tanzania", ["tanzania", "tanzanian"], Region.MIDDLE_EAST_AFRICA),
    Nation("Egypt", ["egypt", "egyptian"], Region.MIDDLE_EAST_AFRICA, [
        Location("Cairo", ["cairo"]),
    ]),
    Nation("Ethiopia", ["ethiopia", "ethiopian"], Region.MIDDLE_EAST_AFRICA),
    Nation("Ghana", ["ghana", "ghanaian"], Region.MIDDLE_EAST_AFRICA),
    Nation("Morocco", ["morocco", "moroccan"], Region.MIDDLE_EAST_AFRICA),
    Nation("Tunisia", ["tunisia", "tunisian"], Region.MIDDLE_EAST_AFRICA),
    Nation("Algeria", ["algeria", "algerian"], Region.MIDDLE_EAST_AFRICA),
    Nation("Qatar", ["qatar", "qatari"], Region.MIDDLE_EAST_AFRICA),
}

INTERNATIONAL = {
    Nation("International", ["international", "foreign", "overseas"], Region.INTERNATIONAL, [], [
        "ITF", "International Transport Workers' Federation",
        "UNI Global Union",
        "IndustriALL",
        "IUF",
        "PSI", "Public Services International",
    ]),
    Nation("Global", ["global", "worldwide"], Region.INTERNATIONAL),
    Nation("International Spanish", [], Region.INTERNATIONAL, [], [], [
        "Sindicato", "Trabajo", "Huelga", "Gremios",
        "Minería", "Automóvil", "Automotriz",
        "Contrato Colectivo", "Convenio Colectivo", "Negociación colectiva",
        "Aéreo", "Metal", "Metalúrgica", "Química", "Construcción", "Transporte",
    ]),
    Nation("International Portuguese", [], Region.INTERNATIONAL, [], [], [
        "Sindicato", "Trabalho", "Greve",
        "Mineração", "Automotivo",
        "Convenção Coletiva", "Negociação coletiva",
        "Aéreo", "Metal", "Metalúrgica", "Metalúrgicos", "Química", "Construção", "Transporte",
        "Bancários", "Petroleiros",
    ]),
}
