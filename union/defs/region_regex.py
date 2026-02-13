from dataclasses import dataclass, field
from enum import Enum
import re
from typing import Dict, List, Optional, Tuple, Any
from defs.regex_lib import add_restrictions, build_compound, build_regex, to_build_alternation
import pandas as pd
from pathlib import Path


class Region(Enum):
    NORTH_AMERICA = "US/Canada"
    LATIN_AMERICA = "Latin America"
    EUROPE = "Europe"
    MIDDLE_EAST_AFRICA = "Middle East/Africa"
    ASIA_PACIFIC = "Asia/Pacific"
    INTERNATIONAL = "International"
    UNKNOWN = "Unknown"
    DOMESTIC = "Domestic"
    GLOBAL = "Global"


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
    weight: float = 0.005 # 0.5%

    def __hash__(self):
        return hash(self.name)

    def __eq__(self, other):
        return self.name == other.name


NORTH_AMERICA = {
    Nation(
        "United States",
        [
            "US",
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
            "capitol hill",
            "silicon valley",
            "twin cities",
            "appalachia",
            to_build_alternation(add_restrictions(
                r"american?", lookbehinds=[r"central", r"latin", r"south"]
            )),            
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
                    Location("Los Angeles", ["los angeles"]),
                    Location("San Diego", ["san diego"]),
                    Location("San Jose", ["san jose"]),
                    Location("Fremont", ["fremont"]),
                    Location("Irvine", ["irvine"]),
                    Location("Sacramento", ["sacramento"]),
                    Location("Palo Alto", ["palo alto"]),
                ],
            ),
            Location(
                "Texas",
                ["texas", "tx"],
                [
                    Location("Houston", ["houston"]),
                    Location("Dallas", ["dallas"]),
                    Location("Austin", ["austin"]),
                    Location("San Antonio", ["san antonio"]),
                    Location("Fort Worth", ["fort worth"]),
                    Location("Arlington", ["arlington, tx", "arlington, texas"]),
                    Location("El Paso", ["el paso"]),
                    Location("Laredo", ["laredo"]),
                    Location("Lubbock", ["lubbock"]),
                ],
            ),
            Location(
                "Illinois",
                ["illinois"],
                [
                    Location("Chicago", ["chicago"]),
                    Location("Springfield", ["springfield, il"]),
                    Location("Peoria", ["peoria"]),
                    Location("Rockford", ["rockford"]),
                    Location("Belvidere", ["belvidere"]),
                ],
            ),
            Location(
                "Massachusetts",
                ["massachusetts"],
                [
                    Location("Boston", ["boston"]),
                    Location("Worcester", ["worcester"]),
                    Location("Cambridge", ["cambridge, ma"]),
                    Location("Springfield", ["springfield, ma"]),
                    Location("Lowell", ["lowell"]),
                ],
            ),
            Location(
                "Washington",
                ["washington"],
                [
                    Location("Seattle", ["seattle"]),
                    Location("Spokane", ["spokane"]),
                    Location("Tacoma", ["tacoma"]),
                    Location("Bellevue", ["bellevue"]),
                    Location("Everett", ["everett"]),
                    Location("Renton", ["renton"]),
                ],
            ),
            Location(
                "Florida",
                ["florida", "fl"],
                [
                    Location("Miami", ["miami"]),
                    Location("Tampa", ["tampa"]),
                    Location("Orlando", ["orlando"]),
                    Location("Jacksonville", ["jacksonville"]),
                    Location("Tallahassee", ["tallahassee"]),
                    Location("Fort Lauderdale", ["fort lauderdale"]),
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
                    Location("Toledo", ["toledo, oh", "toledo, ohio"]),
                    Location("Marysville", ["marysville"]),
                ],
            ),
            Location(
                "Pennsylvania",
                ["pennsylvania"],
                [
                    Location("Pittsburgh", ["pittsburgh"]),
                    Location("Philadelphia", ["philadelphia", "philly"]),
                    Location("Erie", ["erie"]),
                    Location("Harrisburg", ["harrisburg"]),
                    Location("Allentown", ["allentown"]),
                    Location("Scranton", ["scranton"]),
                    Location(
                        "York",
                        [
                            "york, pa",
                        ],
                    ),
                    Location("Reading", ["reading, pa"]),
                    Location("Lancaster", ["lancaster, pa"]),
                    Location("Bethlehem", ["bethlehem, pa", "bethlehem steel"]),
                    Location("Wilkes-Barre", ["wilkes-barre"]),
                ],
            ),
            Location(
                "Indiana",
                ["indiana"],
                [
                    Location("Indianapolis", ["indianapolis"]),
                    Location("Lafayette", ["lafayette"]),
                    Location("Princeton", ["princeton"]),
                    Location("Fort Wayne", ["fort wayne"]),
                    Location("South Bend", ["south bend"]),
                    Location("Evansville", ["evansville"]),
                    Location("Greensburg", ["greensburg, in"]),
                ],
            ),
            Location(
                "Kentucky",
                ["kentucky", "ky"],
                [
                    Location("Louisville", ["louisville"]),
                    Location("Georgetown", ["georgetown"]),
                    Location("Bowling Green", ["bowling green"]),
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
                ["alabama"],
                [
                    Location("Birmingham", ["birmingham, al", "birmingham, alabama"]),
                    Location("Huntsville", ["huntsville"]),
                    Location("Tuscaloosa", ["tuscaloosa"]),
                    Location("Lincoln", ["lincoln, al", "lincoln, alabama"]),
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
                ["colorado"],
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
                    Location("Dover", ["dover, de", "dover, delaware"]),
                    Location("Newark", ["newark"]),
                ],
            ),
            Location(
                "Georgia",
                ["georgia"],
                [
                    Location("Atlanta", ["atlanta"]),
                    Location("Savannah", ["savannah"]),
                    Location("Augusta", ["augusta, ga", "augusta, georgia"]),
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
                    Location("Duluth", ["duluth", "iron range", "mesabi"]),
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
                    Location("Elko", ["elko", "carlin trend", "gold strike"]),
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
                ["rhode island"],
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
                ["virginia"],
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
                    Location("Gillette", ["gillette", "powder river basin", "prb"]),
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
            r"International Longshore(?:mans'|men)? and Warehouse(?:mans'|men)? Union",
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
            "FOP",
            "Fraternal Order of Police",
            "PBA",
            "Police Benevolent Association",
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
            Location("Windsor", ["windsor, on", "windsor, ontario", "windsor, canada"]),
            Location("Oshawa", ["oshawa"]),
            Location("Oakville", ["oakville"]),
            Location("Brampton", ["brampton"]),
            Location(
                "Cambridge",
                ["cambridge, on", "cambridge, ontario", "cambridge, canada"],
            ),
            Location("Ingersoll", ["ingersoll"]),
            Location(
                "Hamilton", ["hamilton, on", "hamilton, ontario", "hamilton, canada"]
            ),
            Location("St. Catharines", ["st. catharines"]),
            Location("Sudbury", ["sudbury"]),
            Location("Fort McMurray", ["fort mcmurray", "athabasca"]),
            Location("Saskatoon", ["saskatoon"]),
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
            "Le Syndicat des Travailleurs-euses de la Mine Meston",
            "Metallurgistes Unis d'Amerique",
        ],
        code="CA",
    ),
    Nation(
        "North America",
        ["north america", "north american"],
        Region.NORTH_AMERICA,
        code="NA",
    ),
}

EUROPE = {
    Nation(
        "Europe",
        ["europe", "eurozone", "eu", "european", "european union", "euro", "eur"],
        Region.EUROPE,
        [],
        [],
        [],
        code="EU",
    ),
    Nation(
        "United Kingdom",
        [
            "uk",
            "britain",
            "united kingdom",
            add_restrictions("england", lookbehinds=[r"new"]),
            "sterling", "gbp",
            add_restrictions("british", lookaheads=[r"virgin", r"columbia"]),
        ],
        Region.EUROPE,
        [
            Location("London", ["london"]),
            Location("Birmingham", ["birmingham"]),
            Location("Manchester", ["manchester"]),
            Location("Leeds", ["leeds"]),
            Location("Glasgow", ["glasgow"]),
            Location("Liverpool", ["liverpool"]),
            Location("Sheffield", ["sheffield"]),
            Location("Bristol", ["bristol"]),
            Location("Edinburgh", ["edinburgh"]),
            Location("Leicester", ["leicester"]),
            Location("Coventry", ["coventry"]),
            Location("Belfast", ["belfast"]),
            Location("Cardiff", ["cardiff"]),
            Location("Sunderland", ["sunderland"]),
            Location("Solihull", ["solihull"]),  # Automotive hub
            Location("Oxford", ["oxford"]),  # Automotive hub
            Location("Derby", ["derby"]),  # Aerospace/Rail hub
            Location("Crewe", ["crewe"]),
            Location("Ellesmere Port", ["ellesmere port"]),
            Location("Halewood", ["halewood"]),
            Location("Burnaston", ["burnaston"]),
            Location("Wales", ["wales"]),
            Location("Northern Ireland", ["northern ireland"]),
        ],
        [
            "Unite the Union",
            "UNISON",
            "GMB",
            "RMT",
            "National Union of Rail, Maritime and Transport Workers",
            "ASLEF",
            "Associated Society of Locomotive Engineers and Firemen",
            "TSSA",
            "Transport Salaried Staffs' Association",
        ],
        [],
        code="GB",
    ),
    Nation(
        "Norway",
        ["norway", "norwegian"],
        Region.EUROPE,
        [
            Location("Oslo", ["oslo"]),
            Location("Bergen", ["bergen"]),
            Location("Stavanger", ["stavanger"]),
            Location("Trondheim", ["trondheim"]),
            Location("Drammen", ["drammen"]),
            Location("Fredrikstad", ["fredrikstad"]),
            Location("Kristiansand", ["kristiansand"]),
            Location("Sandnes", ["sandnes"]),
            Location("Tromso", ["tromso", "tromsø"]),
        ],
        [],
        ["Arbeid", "Fagforening", "Forbund", "Forening", "Landsorganisasjon"],
        code="NO",
    ),
    Nation(
        "Sweden",
        ["sweden", "swedish"],
        Region.EUROPE,
        [
            Location("Stockholm", ["stockholm"]),
            Location("Gothenburg", ["gothenburg", "göteborg"]),
            Location("Malmo", ["malmo", "malmö"]),
            Location("Gothenburg", ["gothenburg", "göteborg"]),
            Location("Malmo", ["malmo", "malmö"]),
            Location("Umea", ["umea", "umeå"]),
            Location("Lund", ["lund"]),
            Location("Uppsala", ["uppsala"]),
            Location("Vasteras", ["vasteras", "västerås"]),
            Location("Linkoping", ["linkoping", "linköping"]),
            Location("Helsingborg", ["helsingborg"]),
            Location("Jonkoping", ["jonkoping", "jönköping"]),
            Location("Norrkoping", ["norrkoping", "norrköping"]),
        ],
        ["Unionen", "IF Metall", "Sveriges Ingenjörer", "Ledarna", "LO", "Landsorganisationen"],
        ["Saltsjöbadsavtalet", "Kollektivavtal", "Arbete", "Fackförening", "Förening", "Förbund", "Fack"],
        code="SE",
    ),
    Nation("Denmark", ["denmark", "danish"], Region.EUROPE, code="DK"),
    Nation(
        "Denmark",
        ["denmark", "danish"],
        Region.EUROPE,
        [],
        [],
        ["Arbejde", "Fagforening", "Forening", "Forbund"],
        code="DK"
    ),
    Nation(
        "Poland",
        ["poland", "polish"],
        Region.EUROPE,
        [
            Location("Warsaw", ["warsaw"]),
            Location("Krakow", ["krakow", "kraków"]),
            Location("Wroclaw", ["wroclaw", "wrocław"]),
            Location("Poznan", ["poznan", "poznań"]),
            Location("Gdansk", ["gdansk", "gdańsk"]),
            Location("Lodz", ["lodz", "łódź"]),
            Location("Katowice", ["katowice"]),
            Location("Gliwice", ["gliwice"]),  # Automotive hub
            Location("Tychy", ["tychy"]),  # Automotive hub
        ],
        ["NSZZ Solidarnosc", "Solidarity", "OPZZ"],
        ["Zwiazek", "Zawodowy", "Pracownikow", "Praca", "Stowarzyszenie", "Zjednoczone", "Federacja", "Konfederacja"],
        code="PL",
    ),
    Nation(
        "Hungary",
        ["hungary", "hungarian"],
        Region.EUROPE,
        [
            Location("Budapest", ["budapest"]),
            Location("Debrecen", ["debrecen"]),
            Location("Győr", ["gyor", "győr"]),  # Audi
            Location("Kecskemét", ["kecskemet", "kecskemét"]),  # Mercedes
            Location("Esztergom", ["esztergom"]),  # Suzuki
            Location("Szentgotthárd", ["szentgotthard", "szentgotthárd"]),  # Opel
        ],
        ["Vasas", "Hungarian Metallworkers' Federation", "MASZSZ"],
        ["Szakszervezeti", "Szövetség", "Munka", "Egyesület", "Dolgozók"],
        code="HU",
    ),
    Nation(
        "Czech Republic",
        ["czech republic", "czechia", "czech"],
        Region.EUROPE,
        [
            Location("Prague", ["prague", "praha"]),
            Location("Mlada Boleslav", ["mlada boleslav", "mladá boleslav"]),  # Skoda
            Location("Kvasiny", ["kvasiny"]),
            Location("Kolín", ["kolin", "kolín"]),
            Location("Ostrava", ["ostrava"]),
            Location("Brno", ["brno"]),
            Location("Plzeň", ["plzen", "plzeň"]),
        ],
        [],
        ["Práce", "Odbory", "Asociace", "Federace", "Svaz"],
        code="CZ",
    ),
    Nation(
        "Turkey",
        ["turkey", "turkish", "lira"],
        Region.EUROPE,
        [
            Location("Istanbul", ["istanbul"]),
            Location("Ankara", ["ankara"]),
            Location("Izmir", ["izmir"]),
            Location("Bursa", ["bursa"]),  # Major automotive hub
            Location("Kocaeli", ["kocaeli", "izmit"]),  # Industrial hub
        ],
        ["Türk Metal", "Türk Metal Sendikasi", "DISK", "HAK-IS", "TURK-IS"],
        ["Sendikasi", "Işçileri", "Çalışma", "Emek", "Dernek", "Federasyonu", "Konfederasyonu", "Birliği"],
        code="TR",
    ),
    Nation(
        "Russia",
        ["russia", "russian", "ussr", "soviet union", "ruble", "rub"],
        Region.EUROPE,
        [
            Location("Moscow", ["moscow"]),
            Location(
                "Saint Petersburg", ["saint petersburg", "st. petersburg", "leningrad"]
            ),
            Location("Nizhny Novgorod", ["nizhny novgorod", "gorky"]),
            Location("Kaluga", ["kaluga"]),  # Automotive hub
            Location("Togliatti", ["togliatti", "tolyatti"]),  # AvtoVAZ
        ],
        [],
        ["Trud", "Rabota", "Soyuz", "Profsoyuz", "Assotsiatsiya", "Federatsiya", "Rabochiy"],
        code="RU",
    ),
    Nation(
        "Bulgaria",
        ["bulgaria", "bulgarian"],
        Region.EUROPE,
        [
            Location("Plovdiv", ["plovdiv"]),
            Location("Varna", ["varna"]),
            Location("Burgas", ["burgas"]),
            Location("Ruse", ["ruse"]),
        ],
        code="BG",
    ),
    Nation("Romania", ["romania", "romanian"], Region.EUROPE, code="RO"),
    Nation(
        "Romania",
        ["romania", "romanian"],
        Region.EUROPE,
        [],
        [],
        ["Muncă", "Sindicat", "Asociația", "Uniunea", "Federația", "Lucrătorilor"],
        code="RO"
    ),
    Nation(
        "Germany",
        ["germany", "german", "deutschland"],
        Region.EUROPE,
        [
            Location("Frankfurt", ["frankfurt"]),
            Location("Berlin", ["berlin"]),
            Location("Munich", ["munich"]),
            Location("Hamburg", ["hamburg"]),
            Location("Stuttgart", ["stuttgart"]),
            Location("Cologne", ["cologne", "koln"]),
            Location("Dusseldorf", ["dusseldorf"]),
            Location("Wolfsburg", ["wolfsburg"]),  # VW Headquarters
            Location("Ingolstadt", ["ingolstadt"]),  # Audi
            Location("Ludwigshafen", ["ludwigshafen"]),  # BASF / Chemicals
            Location("Leverkusen", ["leverkusen"]),  # Bayer
            Location("Hanover", ["hanover", "hannover"]),
            Location("Walldorf", ["walldorf"]),  # SAP / Tech
            Location("Bonn", ["bonn"]),
            Location("Nuremberg", ["nuremberg", "nurnberg"]),
            Location("Essen", ["essen"]),
            Location("Rüsselsheim", ["russelsheim", "ruesselsheim"]),  # Opel/Stellantis
            Location("Mannheim", ["mannheim"]),
            Location("Leipzig", ["leipzig"]),
            Location("Bremen", ["bremen"]),
            Location("Dresden", ["dresden"]),
        ],
        [
            "IG Metall",
            "ver.di",
            "IG BCE",
            "DGB",
            "German Trade Union Confederation",
        ],
        [],
        code="DE",
    ),
    # --- FRANCE ---
    Nation(
        "France",
        ["france", "french"],
        Region.EUROPE,
        [
            Location("Paris", ["paris"]),
            Location("Lyon", ["lyon"]),
            Location("Marseille", ["marseille"]),
            Location("Toulouse", ["toulouse"]),  # Aerospace hub
            Location("Lille", ["lille"]),
            Location("Nantes", ["nantes"]),
            Location("Bordeaux", ["bordeaux"]),
            Location("Strasbourg", ["strasbourg"]),
            Location("Grenoble", ["grenoble"]),  # Tech hub
            Location("Sophia Antipolis", ["sophia antipolis", "valbonne"]),
            Location("Toulon", ["toulon"]),
            Location("Nice", ["nice"]),
            Location("Montpellier", ["montpellier"]),
            Location("Rennes", ["rennes"]),
            Location("Grenoble", ["grenoble"]),
            Location("Reims", ["reims"]),
            Location("Saint-Etienne", ["saint-etienne", "saint-étienne"]),
            Location("Le Havre", ["le havre"]),
        ],
        [
            "CFDT",
            "French Democratic Confederation of Labour",
            "Force Ouvrière",
            "Confédération Générale du Travail",
            "CFE-CGC",
            "Confédération Française de l'Encadrement",  # Management union
            "UNSA",
            "Solidaires",
            "SUD",
            "Confédération Française des Travailleurs Chrétiens",
            "CAT",
            "Confédération Autonome du Travail",
        ],
        [
            "Comité Social et Économique",
            "Accord de branche",
            "Accord d'entreprise",
            "Délégués syndicaux",
            "Code du Travail",
            "35 heures",
            "Bilan social",
        ],
        code="FR",
    ),
    # --- ITALY ---
    Nation(
        "Italy",
        ["italy", "italian"],
        Region.EUROPE,
        [
            Location("Milan", ["milan"]),
            Location("Rome", ["rome"]),
            Location("Turin", ["turin", "torino"]),  # Fiat/Automotive hub
            Location("Genoa", ["genoa", "genova"]),
            Location("Bologna", ["bologna"]),
            Location("Naples", ["naples", "napoli"]),
            Location("Palermo", ["palermo"]),
            Location("Florence", ["florence", "firenze"]),
            Location("Bari", ["bari"]),
            Location("Catania", ["catania"]),
            Location("Venice", ["venice", "venezia"]),
            Location("Verona", ["verona"]),
            Location("Messina", ["messina"]),
            Location("Padua", ["padua", "padova"]),
            Location("Trieste", ["trieste"]),
            Location("Taranto", ["taranto"]),
            Location("Brescia", ["brescia"]),
            Location("Prato", ["prato"]),
            Location("Parma", ["parma"]),
            Location("Modena", ["modena"]),
            Location("Reggio Calabria", ["reggio calabria"]),
            Location("Reggio Emilia", ["reggio emilia"]),
            Location("Perugia", ["perugia"]),
            Location("Livorno", ["livorno"]),
            Location("Ravenna", ["ravenna"]),
            Location("Cagliari", ["cagliari"]),
            Location("Foggia", ["foggia"]),
            Location("Rimini", ["rimini"]),
            Location("Salerno", ["salerno"]),
            Location("Ferrara", ["ferrara"]),
        ],
        ["CGIL", "CISL", "UIL", "FIOM", "FIM", "UILM"],
        [
            "CCNL",
        ],
        code="IT",
    ),
    Nation(
        "Spain",
        ["spain", "spanish"],
        Region.EUROPE,
        [
            Location("Madrid", ["madrid"]),
            Location("Barcelona", ["barcelona"]),
            Location("Valencia", ["valencia"]),  # Ford plant location
            Location("Zaragoza", ["zaragoza"]),
            Location("Vigo", ["vigo"]),
            Location("Bilbao", ["bilbao"]),
            Location("Seville", ["seville", "sevilla"]),
            Location("Valladolid", ["valladolid"]),
            Location("Pamplona", ["pamplona"]),
            Location("Martorell", ["martorell"]),  # SEAT
        ],
        [
            "CCOO",
            "Workers' Commissions",
            "UGT",
            "Confederación Sindical de Comisiones Obreras",
            "Unión General de Trabajadores",
            "ELA",
            "CIG",
        ],
        [
            "Comité de Empresa",
            "Estatuto de los Trabajadores",
        ],
        code="ES",
    ),
    Nation(
        "Netherlands",
        ["netherlands", "dutch", "holland"],
        Region.EUROPE,
        [
            Location("Amsterdam", ["amsterdam"]),
            Location("Rotterdam", ["rotterdam"]),  # Major Port hub
            Location("Eindhoven", ["eindhoven"]),  # Tech hub
            Location("The Hague", ["the hague", "den haag"]),
            Location("Utrecht", ["utrecht"]),
            Location("Groningen", ["groningen"]),
            Location("Tilburg", ["tilburg"]),
            Location("Almere", ["almere"]),
            Location("Breda", ["breda"]),
            Location("Nijmegen", ["nijmegen"]),
        ],
        ["FNV", "CNV", "De Unie"],
        [
            "Vakbond",
            "Ondernemingsraad",
            "CAO",
            "WTR",
            "Polder model",
            "Spoorwegen",
        ],
        code="NL",
    ),
    # --- OTHER EUROPEAN NATIONS ---
    Nation(
        "Switzerland",
        ["switzerland", "swiss", "chf"],
        Region.EUROPE,
        [
            Location("Zurich", ["zurich"]),
            Location("Geneva", ["geneva"]),
            Location("Basel", ["basel"]),
            Location("Bern", ["bern"]),
            Location("Lausanne", ["lausanne"]),
            Location("Lucerne", ["lucerne"]),
            Location("Lugano", ["lugano"]),
        ],
        ["Unia", "Syna"],
        ["GAV", "CCT", "Arbeitsfrieden"],
        code="CH",
    ),
    Nation(
        "Belgium",
        ["belgium", "belgian"],
        Region.EUROPE,
        [
            Location("Brussels", ["brussels"]),
            Location("Antwerp", ["antwerp"]),
            Location("Ghent", ["ghent"]),
            Location("Liege", ["liege"]),
            Location("Charleroi", ["charleroi"]),
            Location("Liege", ["liege", "liège"]),
            Location("Bruges", ["bruges"]),
        ],
        ["ACV", "CSC", "ABVV", "FGTB"],
        ["CBA"],
        code="BE",
    ),
    Nation(
        "Austria",
        ["austria", "austrian"],
        Region.EUROPE,
        [
            Location("Vienna", ["vienna"]),
            Location("Linz", ["linz"]),
            Location("Salzburg", ["salzburg"]),
            Location("Graz", ["graz"]),
            Location("Steyr", ["steyr"]),
        ],
        ["ÖGB"],
        ["Kollektivvertrag"],
        code="AT",
    ),
    Nation(
        "Ireland",
        [add_restrictions("ireland", lookbehinds=[r"northern"]), "irish"],
        Region.EUROPE,
        [
            Location("Dublin", ["dublin"]),
            Location("Cork", ["cork"]),
            Location("Galway", ["galway"]),
            Location("Limerick", ["limerick"]),
            Location("Waterford", ["waterford"]),
        ],
        ["ICTU", "SIPTU"],
        [],
        code="IE",
    ),
    Nation(
        "Portugal",
        ["portugal", "portuguese"],
        Region.EUROPE,
        [
            Location("Lisbon", ["lisbon", "lisboa"]),
            Location("Porto", ["porto", "oportu"]),
            Location("Setubal", ["setubal"]),  # Major automotive hub
            Location("Palmela", ["palmela"]),  # Autoeuropa (VW)
            Location("Mangualde", ["mangualde"]),  # Stellantis
            Location("Aveiro", ["aveiro"]),  # Renault/Cacia
        ],
        ["CGTP", "UGT Portugal"],
        [],  # Strike/CBA terms
        code="PT",
    ),
    Nation(
        "Greece",
        ["greece", "greek"],
        Region.EUROPE,
        [
            Location("Athens", ["athens", "athina"]),
            Location("Piraeus", ["piraeus", "peiraias"]),  # Major Port
            Location("Thessaloniki", ["thessaloniki"]),
            Location("Patras", ["patras", "patra"]),
            Location("Heraklion", ["heraklion"]),
            Location("Larissa", ["larissa"]),
            Location("Volos", ["volos"]),
        ],
        ["GSEE", "ADEDY", "PAME"],
        ["Syndikato", "Syllogiki symvasi"],  # Union/CBA terms
        code="GR",
    ),
    Nation(
        "Finland",
        ["finland", "finnish"],
        Region.EUROPE,
        [
            Location("Helsinki", ["helsinki"]),
            Location("Espoo", ["espoo"]),
            Location("Tampere", ["tampere"]),
            Location("Oulu", ["oulu"]),
            Location("Turku", ["turku"]),
            Location("Vantaa", ["vantaa"]),
        ],
        ["SAK", "STTK", "Akava"],
        ["Työehtosopimus", "TES", "Ammattiliitto", "Työ", "Liitto", "Yhdistys"],  # CBA/Union terms
        code="FI",
    ),
    Nation(
        "Ukraine",
        ["ukraine", "ukrainian"],
        Region.EUROPE,
        [
            Location("Kyiv", ["kyiv", "kiev"]),
            Location("Lviv", ["lviv"]),
            Location("Odesa", ["odesa", "odessa"]),
            Location("Kharkiv", ["kharkiv", "kharkov"]),
            Location("Dnipro", ["dnipro", "dnipropetrovsk"]),
            Location("Donetsk", ["donetsk"]),
        ],
        [],
        ["Pratsya", "Spilka", "Profspilka", "Asotsiatsiya", "Federatsiya", "Robitnyk"],
        code="UA",
    ),
    Nation(
        "Luxembourg",
        ["luxembourg", "luxembourgish"],
        Region.EUROPE,
        [Location("Luxembourg City", ["luxembourg city"])],
        code="LU",
    ),
    Nation(
        "Cyprus",
        ["cyprus", "cypriot"],
        Region.EUROPE,
        [Location("Nicosia", ["nicosia"]), Location("Limassol", ["limassol"])],
        code="CY",
    ),
    Nation(
        "Malta",
        ["malta", "maltese"],
        Region.EUROPE,
        [Location("Valletta", ["valletta"])],
        code="MT",
    ),
    Nation(
        "Jersey",
        ["jersey"],
        Region.EUROPE,
        [Location("Saint Helier", ["saint helier", "st. helier"])],
        code="JE",
    ),
    Nation(
        "Guernsey",
        ["guernsey"],
        Region.EUROPE,
        [Location("Saint Peter Port", ["saint peter port", "st. peter port"])],
        code="GG",
    ),
    Nation(
        "Isle of Man",
        ["isle of man", "manx"],
        Region.EUROPE,
        code="IM",
    ),
    Nation(
        "Liechtenstein",
        ["liechtenstein"],
        Region.EUROPE,
        [Location("Vaduz", ["vaduz"])],
        code="LI",
    ),
    Nation(
        "Monaco",
        ["monaco", "monegasque"],
        Region.EUROPE,
        code="MC",
    ),
    Nation(
        "Estonia",
        ["estonia", "estonian"],
        Region.EUROPE,
        [Location("Tallinn", ["tallinn"])],
        ["IMTAL", "Estonian Industrial and Metalworkers' Union"],
        ["Ametiühingute", "Liit", "Töötajate"],
        code="EE",
    ),
    Nation(
        "Latvia",
        ["latvia", "latvian"],
        Region.EUROPE,
        [Location("Riga", ["riga"])],
        code="LV",
    ),
    Nation(
        "Lithuania",
        ["lithuania", "lithuanian"],
        Region.EUROPE,
        [Location("Vilnius", ["vilnius"]), Location("Kaunas", ["kaunas"])],
        code="LT",
    ),
    Nation(
        "Baltic States",
        ["baltic states", "baltics"],
        Region.EUROPE,
        code="BALTIC",
    ),
    Nation(
        "Belarus",
        ["belarus", "belarusian", "byelorussia"],
        Region.EUROPE,
        [Location("Minsk", ["minsk"])],
        code="BY",
    ),
    Nation(
        "Moldova",
        ["moldova", "moldovan"],
        Region.EUROPE,
        [Location("Chisinau", ["chisinau", "kishinev"])],
        code="MD",
    ),
    Nation(
        "Armenia",
        ["armenia", "armenian"],
        Region.EUROPE,
        [Location("Yerevan", ["yerevan"])],
        code="AM",
    ),
    Nation(
        "Azerbaijan",
        ["azerbaijan", "azerbaijani", "azeri"],
        Region.EUROPE,
        [Location("Baku", ["baku"])],
        code="AZ",
    ),
    Nation(
        "Republic of Georgia",
        ["republic of georgia"],
        Region.EUROPE,
        [Location("Tbilisi", ["tbilisi"])],
        code="GE",
    ),
    Nation(
        "CIS",
        ["cis", "commonwealth of independent states"],
        Region.EUROPE,
        code="CIS",
    ),
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
        ["japan", "japanese", "yen", "jpy"],
        Region.ASIA_PACIFIC,
        [
            Location("Tokyo", ["tokyo"]),
            Location("Osaka", ["osaka"]),
            Location("Nagoya", ["nagoya"]),
            Location("Yokohama", ["yokohama"]),
            Location("Toyota City", ["toyota city"]),  # Major Auto Hub
        ],
        [
            "Rengo",
            "Japanese Trade Union Confederation",
            "UA Zensen",
            "JAM",
            "Japanese Association of Metal and Allied Workers",
            "Roudou Kumiai",
        ],
        [
            "Shunto",
            "Karoshi",
            "Roudou",
            "Kumiai",
        ],
        code="JP",
    ),
    Nation(
        "South Korea",
        ["south korea", "korea", "korean", "krw"],
        Region.ASIA_PACIFIC,
        [
            Location("Seoul", ["seoul"]),
            Location("Busan", ["busan", "pusan"]),
            Location("Incheon", ["incheon"]),
            Location("Ulsan", ["ulsan"]),  # Hyundai / Major Industrial Hub
        ],
        [
            "KCTU",
            "Korean Confederation of Trade Unions",
            "FKTU",
            "Federation of Korean Trade Unions",
        ],
        [
            "Chaebol",
            "Nodong",
            "Johap",
        ],
        code="KR",
    ),
    Nation(
        "China",
        ["china", "chinese", "prc", "p.r.c.", "people's republic of china", "yuan", "renminbi", "rmb", "cny"],
        Region.ASIA_PACIFIC,
        [
            Location("Shanghai", ["shanghai"]),
            Location("Beijing", ["beijing"]),
            Location("Shenzhen", ["shenzhen"]),
            Location("Guangzhou", ["guangzhou"]),
            Location("Tianjin", ["tianjin"]),
            Location("Chongqing", ["chongqing"]),
            Location("Wuhan", ["wuhan"]),
            Location("Suzhou", ["suzhou"]),
            Location("Chengdu", ["chengdu"]),
            Location("Hangzhou", ["hangzhou"]),
            Location("Nanjing", ["nanjing"]),
            Location("Ningbo", ["ningbo"]),
            Location("Changchun", ["changchun"]),  # Major Auto Hub
            Location("Fujian", ["fujian"]),  # Major Auto Hub
            
        ],
        ["All-China Federation of Trade Unions", "ACFTU"],
        ["Gonghui"],
        code="CN",
    ),
    Nation(
        "India",
        ["india", "indian", "rupee", "inr", "lakh", "crore"],
        Region.ASIA_PACIFIC,
        [
            Location("Mumbai", ["mumbai", "bombay"]),
            Location("Bangalore", ["bangalore", "bengaluru"]),
            Location("New Delhi", ["new delhi", "delhi"]),
            Location("Chennai", ["chennai", "madras"]),  # Detroit of South Asia
            Location("Hyderabad", ["hyderabad"]),
            Location("Pune", ["pune"]),  # Auto Hub
        ],
        [
            "CITU",
            "AITUC",
            "INTUC",
            "BMS",
            "Bharatiya Mazdoor Sangh",
        ],
        [
            "Standing Orders",
            "Industrial Disputes Act",
            "Trade Unions Act",
        ],
        code="IN",
    ),
    Nation(
        "Australia",
        ["australia", "australian"],
        Region.ASIA_PACIFIC,
        [
            Location("Sydney", ["sydney"]),
            Location("Melbourne", ["melbourne"]),
            Location("Brisbane", ["brisbane"]),
            Location("Perth", ["perth"]),
            Location("Pilbara", ["pilbara", "port hedland"]),
            Location("Hunter Valley", ["hunter valley", "newcastle"]),
            Location("Kalgoorlie", ["kalgoorlie", "super pit"]),
            Location("Bowen Basin", ["bowen basin"]),
        ],
        [
            "ACTU",
            "Australian Council of Trade Unions",
            "CFMEU",
            "AWU",
            "Construction, Forestry, Maritime, Mining and Energy Union",
            "Australian Workers' Union",
            "SDA",
        ],
        [],
        code="AU",
    ),
    Nation(
        "Singapore",
        ["singapore", "singaporean"],
        Region.ASIA_PACIFIC,
        [Location("Singapore", ["singapore"])],
        ["NTUC", "National Trades Union Congress"],
        [],
        code="SG",
    ),
    Nation(
        "Vietnam",
        ["vietnam", "vietnamese"],
        Region.ASIA_PACIFIC,
        [
            Location("Ho Chi Minh City", ["ho chi minh city", "hcmc", "saigon"]),
            Location("Hanoi", ["hanoi"]),
            Location("Haiphong", ["haiphong"]),  # Major Port
        ],
        ["VGCL", "Vietnam General Confederation of Labour"],
        ["Cong doan", "Lao dong", "Nghiep doan", "Hiep hoi", "Lien doan"],
        code="VN",
    ),
    Nation(
        "Malaysia",
        ["malaysia", "malaysian"],
        Region.ASIA_PACIFIC,
        [
            Location("Kuala Lumpur", ["kuala lumpur", "kl"]),
            Location("Johor", ["johor"]),
            Location("Penang", ["penang"]),  # Tech Hub
        ],
        ["MTUC", "Malaysian Trades Union Congress"],
        ["Kerja", "Buruh", "Kesatuan", "Persatuan", "Persekutuan", "Sekerja"],
        code="MY",
    ),
    Nation(
        "Taiwan",
        ["taiwan", "taiwanese"],
        Region.ASIA_PACIFIC,
        [
            Location("Taipei", ["taipei"]),
            Location("Hsinchu", ["hsinchu"]),
            Location("Kaohsiung", ["kaohsiung"]),
        ],
        code="TW",
    ),
    Nation(
        "Thailand",
        ["thailand", "thai"],
        Region.ASIA_PACIFIC,
        [
            Location("Bangkok", ["bangkok"]),
            Location("Rayong", ["rayong"]),
            Location("Chonburi", ["chonburi"]),
            Location("Ayutthaya", ["ayutthaya"]),
        ],
        [],
        ["Sahaphab", "Raengngan", "Samakhom", "Sapha"],
        code="TH",
    ),
    Nation(
        "Philippines",
        ["philippines", "philippine", "filipino"],
        Region.ASIA_PACIFIC,
        [
            Location("Manila", ["manila"]),
            Location("Cebu", ["cebu"]),
            Location("Davao", ["davao"]),
        ],
        code="PH",
    ),
    Nation(
        "Indonesia",
        ["indonesia", "indonesian"],
        Region.ASIA_PACIFIC,
        [
            Location("Jakarta", ["jakarta"]),
            Location("Surabaya", ["surabaya"]),
            Location("Bandung", ["bandung"]),
            Location("Medan", ["medan"]),
        ],
        [],
        ["Serikat", "Buruh", "Pekerja", "Kerja", "Asosiasi", "Federasi", "Konfederasi"],
        code="ID",
    ),
    Nation(
        "New Zealand",
        ["new zealand", "nz"],
        Region.ASIA_PACIFIC,
        [
            Location("Auckland", ["auckland"]),
            Location("Wellington", ["wellington"]),
            Location("Christchurch", ["christchurch"]),
            Location("Dunedin", ["dunedin"]),
            Location("Hamilton", ["hamilton, nz"]),
        ],
        code="NZ",
    ),
    Nation(
        "Pakistan",
        ["pakistan", "pakistani"],
        Region.ASIA_PACIFIC,
        [
            Location("Karachi", ["karachi"]),
            Location("Lahore", ["lahore"]),
            Location("Islamabad", ["islamabad"]),
            Location("Faisalabad", ["faisalabad"]),
        ],
        code="PK",
    ),
    Nation(
        "Bangladesh",
        ["bangladesh", "bangladeshi"],
        Region.ASIA_PACIFIC,
        [
            Location("Dhaka", ["dhaka"]),
            Location("Chittagong", ["chittagong"]),
            Location("Khulna", ["khulna"]),
            Location("Sylhet", ["sylhet"]),
        ],
        code="BD",
    ),
    Nation("Hong Kong", ["hong kong", "hk"], Region.ASIA_PACIFIC, code="HK"),
    Nation("Fiji", ["fiji", "fijian"], Region.ASIA_PACIFIC, code="FJ"),
    Nation(
        "Kazakhstan",
        ["kazakhstan", "kazakh"],
        Region.ASIA_PACIFIC,
        [Location("Almaty", ["almaty"]), Location("Astana", ["astana", "nur-sultan"])],
        code="KZ",
    ),
    Nation(
        "Uzbekistan",
        ["uzbekistan", "uzbek"],
        Region.ASIA_PACIFIC,
        [Location("Tashkent", ["tashkent"])],
        code="UZ",
    ),
    Nation(
        "Turkmenistan",
        ["turkmenistan", "turkmen"],
        Region.ASIA_PACIFIC,
        [Location("Ashgabat", ["ashgabat"])],
        code="TM",
    ),
    Nation(
        "Kyrgyzstan",
        ["kyrgyzstan", "kyrgyz"],
        Region.ASIA_PACIFIC,
        [Location("Bishkek", ["bishkek"])],
        code="KG",
    ),
    Nation(
        "Tajikistan",
        ["tajikistan", "tajik"],
        Region.ASIA_PACIFIC,
        [Location("Dushanbe", ["dushanbe"])],
        code="TJ",
    ),
}

LATIN_AMERICA = {
    Nation(
        "Latin America",
        [
            to_build_alternation(
                build_compound([r"latin", r"south", r"central"], [r"america(?:n|s)?"])
            ),
            "latam",
        ],
        Region.LATIN_AMERICA,
        [],
        code="LATAM",
    ),
    Nation(
        "Mexico",
        ["mexico", "mexican"],
        Region.LATIN_AMERICA,
        [
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
        ],
        [
            "CTM",
            "Confederation of Mexican Workers",
            "UNT",
            "CROC",
        ],
        [
            "Maquiladora",
            "PTU",
            "Participación de los Trabajadores en las Utilidades",
            "Contrato Colectivo de Trabajo",
            "CCT",
            "Ley Federal del Trabajo",
        ],
        code="MX",
    ),
    Nation(
        "Brazil",
        ["brazil", "brazilian", "reais", "brl"],
        Region.LATIN_AMERICA,
        [
            Location("Sao Paulo", ["sao paulo"]),
            Location("Rio de Janeiro", ["rio de janeiro", "rio"]),
            Location("Sao Bernardo do Campo", ["sao bernardo do campo"]),  # Auto Hub
            Location("Curitiba", ["curitiba"]),
            Location("Belo Horizonte", ["belo horizonte"]),
            Location("Parauapebas", ["parauapebas", "carajas", "carajás"]),
        ],
        [
            "CUT",
            "Unified Workers' Central",
            "Força Sindical",
            "UGT Brazil",
        ],
        [
            "Dissídio",
            "CLT",
            "Consolidação das Leis do Trabalho",
            "Acordo Coletivo",
            "Contribuição sindical",
        ],
        code="BR",
    ),
    Nation(
        "Argentina",
        ["argentina", "argentine"],
        Region.LATIN_AMERICA,
        [
            Location("Buenos Aires", ["buenos aires"]),
            Location("Cordoba", ["cordoba"]),  # Major Industrial/Auto
            Location("Rosario", ["rosario"]),
            Location("Pacheco", ["pacheco"]),  # Ford/VW Plants
        ],
        [
            "General Confederation of Labour",
            "CTA",
            "SMATA",
            "UOM",
        ],
        [
            "Paritarias",
            "Conflictividad laboral",
        ],
        code="AR",
    ),
    Nation(
        "Chile",
        ["chile", "chilean"],
        Region.LATIN_AMERICA,
        [
            Location("Santiago", ["santiago"]),
            Location("Antofagasta", ["antofagasta"]),  # Mining hub
            Location("Valparaiso", ["valparaiso"]),
            Location("Calama", ["calama", "chuquicamata"]),
            Location("Copiapo", ["copiapo", "copiapó"]),
            Location("Rancagua", ["rancagua", "el teniente"]),
        ],
        ["CUT Chile", "Central Unitaria de Trabajadores"],
        ["Código del Trabajo"],
        code="CL",
    ),
    Nation(
        "Colombia",
        ["colombia", "colombian"],
        Region.LATIN_AMERICA,
        [
            Location("Bogota", ["bogota"]),
            Location("Medellin", ["medellin"]),
            Location("Cali", ["cali"]),
        ],
        ["CUT Colombia", "CTC", "CGT Colombia"],
        code="CO",
    ),
    Nation(
        "Peru",
        ["peru", "peruvian"],
        Region.LATIN_AMERICA,
        [
            Location("Lima", ["lima"]),
            Location("Arequipa", ["arequipa"]),
            Location("Cajamarca", ["cajamarca", "yanacocha"]),
        ],
        code="PE",
    ),
    Nation(
        "Venezuela",
        ["venezuela", "venezuelan"],
        Region.LATIN_AMERICA,
        [Location("Caracas", ["caracas"])],
        code="VE",
    ),
    Nation(
        "Ecuador",
        ["ecuador", "ecuadorian"],
        Region.LATIN_AMERICA,
        [Location("Quito", ["quito"]), Location("Guayaquil", ["guayaquil"])],
        code="EC",
    ),
    Nation("Guatemala", ["guatemala", "guatemalan"], Region.LATIN_AMERICA, code="GT"),
    Nation(
        "Dominican Republic",
        ["dominican republic", "dominican"],
        Region.LATIN_AMERICA,
        code="DO",
    ),
    Nation(
        "Puerto Rico",
        ["puerto rico", "puerto rican"],
        Region.LATIN_AMERICA,
        [Location("San Juan", ["san juan"])],
        code="PR",
    ),
    Nation(
        "Costa Rica", ["costa rica", "costa rican"], Region.LATIN_AMERICA, code="CR"
    ),
    Nation("Panama", ["panama", "panamanian"], Region.LATIN_AMERICA, code="PA"),
    Nation("Uruguay", ["uruguay", "uruguayan"], Region.LATIN_AMERICA, code="UY"),
    Nation("Bolivia", ["bolivia", "bolivian"], Region.LATIN_AMERICA, code="BO"),
    Nation("Paraguay", ["paraguay", "paraguayan"], Region.LATIN_AMERICA, code="PY"),
    Nation(
        "Cayman Islands",
        ["cayman islands", "cayman", "caymans"],
        Region.LATIN_AMERICA,
        [Location("George Town", ["george town"])],
        code="KY",
    ),
    Nation(
        "Bermuda",
        ["bermuda", "bermudian"],
        Region.LATIN_AMERICA,
        [Location("Hamilton", ["hamilton, bermuda"])],
        code="BM",
    ),
    Nation(
        "British Virgin Islands",
        ["british virgin islands", "bvi"],
        Region.LATIN_AMERICA,
        [Location("Road Town", ["road town"])],
        code="VG",
    ),
    Nation(
        "Bahamas",
        ["bahamas", "bahamian"],
        Region.LATIN_AMERICA,
        [Location("Nassau", ["nassau"])],
        code="BS",
    ),
    Nation(
        "Barbados",
        ["barbados", "barbadian"],
        Region.LATIN_AMERICA,
        [Location("Bridgetown", ["bridgetown"])],
        code="BB",
    ),
    Nation(
        "Curacao",
        ["curacao", "curaçao"],
        Region.LATIN_AMERICA,
        [Location("Willemstad", ["willemstad"])],
        code="CW",
    ),
}
MIDDLE_EAST_AFRICA = {
    Nation(
        "Middle East",
        ["middle east", "middle eastern", "mena"],
        Region.MIDDLE_EAST_AFRICA,
        code="MEA",
    ),
    Nation("Africa", ["africa", to_build_alternation(add_restrictions("african", lookaheads=[r"american"]))], Region.MIDDLE_EAST_AFRICA, code="AFRICA"),
    Nation(
        "United Arab Emirates",
        ["uae", "emirates", "dirham", "aed"],
        Region.MIDDLE_EAST_AFRICA,
        [
            Location("Dubai", ["dubai"]),
            Location("Abu Dhabi", ["abu dhabi"]),
            Location("Sharjah", ["sharjah"]),
            Location("Jebel Ali", ["jebel ali"]),  # Major Port/Free Zone
        ],
        [],
        [],
        code="AE",
    ),
    Nation(
        "Saudi Arabia",
        ["saudi arabia", "saudi", "riyal", "sar"],
        Region.MIDDLE_EAST_AFRICA,
        [
            Location("Riyadh", ["riyadh"]),
            Location("Jeddah", ["jeddah"]),
            Location("Dammam", ["dammam"]),
            Location("Khobar", ["khobar"]),
            Location("Dhahran", ["dhahran"]),  # Aramco/Industrial hub
        ],
        [],
        [],
        code="SA",
    ),
    Nation(
        "Israel",
        ["israel", "israeli", "shekel", "ils"],
        Region.MIDDLE_EAST_AFRICA,
        [
            Location("Tel Aviv", ["tel aviv"]),
            Location("Jerusalem", ["jerusalem"]),
            Location("Beer Sheva", ["beer sheva"]),  # Major Industrial/Port
            Location("Netanya", ["netanya"]),
            Location("Ashdod", ["ashdod"]),
            Location("Haifa", ["haifa"]),  # Major Industrial/Port
        ],
        ["Histadrut", "General Federation of Labour in Israel"],
        ["Avoda", "Igud", "Aguda", "Federatsia"],
        code="IL",
    ),
    Nation(
        "South Africa",
        ["south africa", "south african", "rand", "zar"],
        Region.MIDDLE_EAST_AFRICA,
        [
            Location("Johannesburg", ["johannesburg", "joburg"]),
            Location("Cape Town", ["cape town"]),
            Location("Durban", ["durban"]),  # Major Port
            Location("Port Elizabeth", ["port elizabeth", "gqeberha"]),  # Auto Hub
            Location("Pretoria", ["pretoria"]),
            Location("Rustenburg", ["rustenburg", "marikana", "bushveld"]),
        ],
        [
            "COSATU",
            "Congress of South African Trade Unions",
            "AMCU",
            "Association of Mineworkers and Construction Union",
            "NUMSA",
            "National Union of Metalworkers of South Africa",
            "FEDUSA",
        ],
        [
            "LRA",
            "NEDLAC",
        ],
        code="ZA",
    ),
    Nation(
        "Nigeria",
        ["nigeria", "nigerian"],
        Region.MIDDLE_EAST_AFRICA,
        [
            Location("Lagos", ["lagos"]),
            Location("Abuja", ["abuja"]),
            Location("Port Harcourt", ["port harcourt"]),  # Oil/Gas Hub
        ],
        ["NLC", "Nigeria Labour Congress", "TUC Nigeria"],
        code="NG",
    ),
    Nation(
        "Morocco",
        ["morocco", "moroccan"],
        Region.MIDDLE_EAST_AFRICA,
        [
            Location("Casablanca", ["casablanca"]),
            Location("Rabat", ["rabat"]),
            Location("Marrakech", ["marrakech"]),
            Location("Tangier", ["tangier", "tanger"]),  # Major Port/Auto
        ],
        [
            "Union Marocaine du Travail",
            "Confédération Démocratique du Travail",
        ],
        code="MA",
    ),
    Nation(
        "Egypt",
        ["egypt", "egyptian"],
        Region.MIDDLE_EAST_AFRICA,
        [
            Location("Cairo", ["cairo"]),
            Location("Alexandria", ["alexandria, egypt"]),
            Location("Giza", ["giza"]),
            Location("Suez", ["suez"]),
        ],
        ["ETUF", "Egyptian Trade Union Federation"],
        code="EG",
    ),
    Nation(
        "Kenya",
        ["kenya", "kenyan"],
        Region.MIDDLE_EAST_AFRICA,
        [
            Location("Nairobi", ["nairobi"]),
            Location("Mombasa", ["mombasa"]),
            Location("Kisumu", ["kisumu"]),
            Location("Nakuru", ["nakuru"]),
        ],
        code="KE",
    ),
    Nation(
        "Ghana",
        ["ghana", "ghanaian"],
        Region.MIDDLE_EAST_AFRICA,
        [
            Location("Accra", ["accra"]),
            Location("Kumasi", ["kumasi"]),
            Location("Tema", ["tema"]),
        ],
        ["TUC Ghana"],
        code="GH",
    ),
    Nation(
        "Tunisia",
        ["tunisia", "tunisian"],
        Region.MIDDLE_EAST_AFRICA,
        [
            Location("Tunis", ["tunis"]),
            Location("Sfax", ["sfax"]),
            Location("Sousse", ["sousse"]),
            Location("Kairouan", ["kairouan"]),
            Location("Bizerte", ["bizerte"]),
        ],
        ["UGTT", "UTT", "Union des travailleurs Tunisiens"],
        code="TN",
    ),
    Nation(
        "Kuwait",
        ["kuwait", "kuwaiti"],
        Region.MIDDLE_EAST_AFRICA,
        [
            Location("Kuwait City", ["kuwait city"]),
            Location("Al Ahmadi", ["al ahmadi", "ahmadi"]),
            Location("Hawalli", ["hawalli"]),
            Location("As Salimiyah", ["salimiyah", "salmiya"]),
        ],
        code="KW",
    ),
    Nation(
        "Tanzania",
        ["tanzania", "tanzanian"],
        Region.MIDDLE_EAST_AFRICA,
        [
            Location("Dar es Salaam", ["dar es salaam", "dar"]),
            Location("Mwanza", ["mwanza"]),
            Location("Dodoma", ["dodoma"]),
            Location("Arusha", ["arusha"]),
            Location("Mbeya", ["mbeya"]),
        ],
        code="TZ",
    ),
    Nation(
        "Ethiopia",
        ["ethiopia", "ethiopian"],
        Region.MIDDLE_EAST_AFRICA,
        [
            Location("Addis Ababa", ["addis ababa", "addis"]),
            Location("Dire Dawa", ["dire dawa"]),
            Location("Mekelle", ["mekelle", "mekele"]),
            Location("Gondar", ["gondar"]),
            Location("Adama", ["adama"]),
        ],
        code="ET",
    ),
    Nation(
        "Algeria",
        ["algeria", "algerian"],
        Region.MIDDLE_EAST_AFRICA,
        [
            Location("Algiers", ["algiers"]),
            Location("Oran", ["oran", "wahran"]),
            Location("Constantine", ["constantine"]),
            Location("Annaba", ["annaba"]),
            Location("Blida", ["blida"]),
        ],
        code="DZ",
    ),
    Nation(
        "Qatar",
        ["qatar", "qatari"],
        Region.MIDDLE_EAST_AFRICA,
        [
            Location("Doha", ["doha"]),
            Location("Al Rayyan", ["al rayyan", "rayyan"]),
            Location("Al Wakrah", ["al wakrah", "wakrah"]),
            Location("Al Khor", ["al khor"]),
        ],
        code="QA",
    ),
    Nation(
        "Oman",
        ["oman", "omanese"],
        Region.MIDDLE_EAST_AFRICA,
        [
            Location("Muscat", ["muscat"]),
            Location("Seeb", ["seeb", "as seeb"]),
            Location("Salalah", ["salalah"]),
            Location("Sohar", ["sohar"]),
            Location("Bawshar", ["bawshar"]),
        ],
        code="OM",
    ),
    Nation(
        "Jordan",
        ["jordan", "jordanian"],
        Region.MIDDLE_EAST_AFRICA,
        [
            Location("Amman", ["amman"]),
            Location("Zarqa", ["zarqa"]),
            Location("Irbid", ["irbid"]),
            Location("Russeifa", ["russeifa", "rusaifa"]),
            Location("Aqaba", ["aqaba"]),
        ],
        code="JO",
    ),
    Nation(
        "Lebanon",
        ["lebanon", "lebanese"],
        Region.MIDDLE_EAST_AFRICA,
        [
            Location("Beirut", ["beirut"]),
            Location("Tripoli", ["tripoli, lebanon"]),
            Location("Sidon", ["sidon"]),
            Location("Tyre", ["tyre", "sour"]),
            Location("Nabatieh", ["nabatieh"]),
        ],
        code="LB",
    ),
    Nation(
        "Iraq",
        ["iraq", "iraqi"],
        Region.MIDDLE_EAST_AFRICA,
        [
            Location("Baghdad", ["baghdad"]),
            Location("Mosul", ["mosul"]),
            Location("Basra", ["basra", "basrah"]),
            Location("Erbil", ["erbil", "arbil"]),
            Location("Kirkuk", ["kirkuk"]),
        ],
        code="IQ",
    ),
    Nation(
        "Mauritius",
        ["mauritius", "mauritian"],
        Region.MIDDLE_EAST_AFRICA,
        [Location("Port Louis", ["port louis"])],
        code="MU",
    ),
    Nation(
        "Zambia",
        ["zambia", "zambian"],
        Region.MIDDLE_EAST_AFRICA,
        [Location("Lusaka", ["lusaka"]), Location("Kitwe", ["kitwe", "copperbelt"])],
        code="ZM",
    ),
    Nation(
        "DRC",
        ["democratic republic of the congo", "drc", "congo-kinshasa", "zaire"],
        Region.MIDDLE_EAST_AFRICA,
        [Location("Kinshasa", ["kinshasa"]), Location("Lubumbashi", ["lubumbashi"]), Location("Kolwezi", ["kolwezi"])],
        code="CD",
    ),
}

INTERNATIONAL = {
    Nation(
        "International",
        ["international", "foreign", "overseas", "internationally"],
        Region.INTERNATIONAL,
        [],
        [r"CGT"],
        code="INT",
    ),
    Nation(
        "Global",
        ["global", "worldwide", "consolidated"],
        Region.GLOBAL,
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
        code="GLO",
    ),
    Nation(
        "Iberian",
        [],
        Region.INTERNATIONAL,
        [],
        [],
        [
            "Trabalho",
            "Trabajo",
            "Greve",
            "Delegados",
            "Huelga",
            "Gremios",
            "Mineração",
            "Minería",
            "Automotivo",
            "Automóvil",
            "Automotriz",
            "Convenção Coletiva",
            "Contrato Colectivo",
            "Convenio Colectivo",
            "Negociação coletiva",
            "Negociación colectiva",
            "Aéreo",
            "Metalúrgica",
            "Metalúrgicos",
            "Química",
            "Construção",
            "Construcción",
            "Transporte",
            "Bancários",
            "Petroleiros",
            "Ferroviários",
            "Ferrocarril",
            "Ferroviarios",
            "Sindicato",
        ],
        code="INT_IBERIA",
    ),
    Nation(
        "Francophone",
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
    Nation(
        "Italian",
        [],
        Region.INTERNATIONAL,
        [],
        [],
        [
            "Lavoro",
            "Sciopero",
            "Sindacati",
            "Contratto Collettivo",
            "Contrattazione",
            "Metalmeccanici",
            "Chimici",
            "Edili",
            "Trasporti",
            "Automobilistico",
        ],
        code="INT_IT",
    ),
    Nation(
        "German",
        [],
        Region.INTERNATIONAL,
        [],
        [],
        [
            "Streik",
            "Gewerkschaft(?:en)?",
            "Verkehr",
            "Arbeit(?:nehmer)?",
            "Betriebsrat",
            "Tarifvertrag",
            "Mitbestimmung",
            "Aufsichtsrat",
            "Tarifverhandlungen",
            "Metall",
            "Chemie",
            "Automobil",
        ],
        code="INT_DE",
    ),
    Nation(
        "Dutch",
        [],
        Region.INTERNATIONAL,
        [],
        [],
        [
            "Arbeid", "Staking", "Vakbonden", "CAO", "Ondernemingsraad",
            "Medezeggenschap", "Metaal", "Bouw", "Zorg",
        ],
        code="INT_NL",
    ),
    Nation(
        Region.DOMESTIC.value,
        ["domestic", "domestically"],
        Region.DOMESTIC,
        [],
        [],
        [],
        code="DOM",
    ),
}

INT_LANGUAGE_MAP = {
    "INT_IBERIA": {
        "BR", "PT", "ES", "MX", "AR", "CL", "CO", "PE", "VE", "EC", "GT", "DO", "CR", "PA", "UY", "BO", "PY"
    },
    "INT_FR": {"FR", "BE", "CH", "CA"},
    "INT_IT": {"IT", "CH", "SM", "VA"},
    "INT_DE": {"DE", "AT", "CH", "LI", "LU"},
    "INT_NL": {"NL", "BE", "SR"},
}

# Worker terms, Union terms, gap
INT_UNION_MAP = {
    "INT_IBERIA": (
        [
            "Trabalhadores", "Trabajadores", "Operários", "Obreros", "Empregados", "Empleados", "Funcionários", "Personal",
            "Metalúrgicos", "Siderúrgicos", "Petroleiros", "Petroleros", "Químicos", "Bancários", "Bancarios", "Obrera", "Obreras",
            "Ferroviários", "Ferroviarios", "Portuários", "Portuarios", "Rurais", "Rurales", "Têxteis", "Mineiros", "Mineros",
            "Automotivos", "Automotrices", "Construção", "Construcción", "Comércio", "Comercio", "Transportes", "Transporte", "Correios", "Correos",
            "Siderurgia", "Petróleo", "Gás", "Carvão", "Carbón", "Minas", "Automóvel", "Energia", "Energía"
        ],
        ["Sindicato", "Federação", "Federación", "Confederação", "Confederación", "União", "Unión", "Central", "Associação", "Asociación"],
        r"(?:\s+(?:del|dos?|das?|des?|e|y|para|los?|las?|el|os|as|&|[A-Z][\w-]*)){0,3}\s+",
    ),
    "INT_FR": (
        [
            "Travailleurs", "Salariés", "Employés", "Personnel", "Ouvriers",
            "Métallurgistes", "Sidérurgistes", "Pétroliers", "Chimistes", "Bancaires",
            "Cheminots", "Portuaires", "Agricoles", "Mineurs",
            "Construction", "Commerce", "Transports", "Postes",
            "Métallurgie", "Sidérurgie", "Pétrole", "Gaz", "Charbon", "Mines", "Bâtiment", "Énergie",
        ],
        ["Syndicat", "Fédération", "Confédération", "Union", "Centrale", "Association"],
        r"(?:\s+(?:du|des?|et|pour|les?|la|&|[A-Z][\w-]*)){0,3}\s+",
    ),
    "INT_IT": (
        [
            "Lavoratori", "Dipendenti", "Operai", "Impiegati", "Personale", "Addetti",
            "Metalmeccanici", "Chimici", "Edili", "Tessili", "Bancari",
            "Ferrovieri", "Portuali", "Agricoli", "Minatori",
            "Automobilistici", "Costruzioni", "Commercio", "Trasporti", "Poste",
            "Metallo", "Petrolio", "Carbone", "Miniere",
        ],
        ["Sindacato", "Federazione", "Confederazione", "Unione", "Associazione", "Lega", "Camera", "Organizzazione"],
        r"(?:\s+(?:dei|degli|delle|di|del|della|e|per|il|lo|la|i|gli|le|&|[A-Z][\w-]*)){0,3}\s+",
    ),
    "INT_DE": (
        [
            "Arbeitnehmer", "Arbeiter", "Angestellte", "Beschäftigte", "Personal", "Mitarbeiter",
            "Metall", "Chemie", "Bergbau", "Energie", "Bau", "Dienstleistung",
            "Eisenbahn", "Nahrung", "Genuss", "Gaststätten", "Erziehung", "Wissenschaft",
            "Polizei", "Post", "Logistik", "Verkehr", "Banken", "Versicherung",
            "Textil", "Bekleidung", "Holz", "Kunststoff",
        ],
        ["Gewerkschaft", "Bund", "Verband", "Vereinigung", "Industriegewerkschaft", "IG"],
        r"(?:\s+(?:der|des|dem|den|für|im|in|und|&|[A-Z][\w-]*)){0,3}\s+",
    ),
    "INT_NL": (
        [
            "Werknemers", "Arbeiders", "Personeel", "Medewerkers", "Bedienden",
            "Metaal", "Bouw", "Vervoer", "Spoorwegen", "Havens", "Chemie", "Onderwijs", "Zorg",
            "Politie", "Banken", "Verzekeringen", "Textiel", "Voeding", "Landbouw",
        ],
        ["Vakbond", "Bond", "Unie", "Federatie", "Vereniging", "Centrale", "Vakcentrale", "Vakbeweging"],
        r"(?:\s+(?:van|de|het|en|voor|in|op|&|[A-Z][\w-]*)){0,3}\s+",
    ),
}
REGION_CODES = {
    "NA",
    "EU",
    "APAC",
    "LATAM",
    "MEA",
    "AFRICA",
    "INT",
    "DOM",
    "INT_IBERIA",
    "INT_FR",
    "INT_IT",
    "INT_DE",
    "INT_NL",
}
TAX_HAVEN_CODES = {
    "KY",  # Cayman Islands
    "BM",  # Bermuda
    "VG",  # British Virgin Islands
    # "LU",  # Luxembourg
    # "IE",  # Ireland
    # "NL",  # Netherlands
    # "CH",  # Switzerland
    "CY",  # Cyprus
    "MT",  # Malta
    "JE",  # Jersey
    "GG",  # Guernsey
    "IM",  # Isle of Man
    "LI",  # Liechtenstein
    "MC",  # Monaco
    "BS",  # Bahamas
    "BB",  # Barbados
    "CW",  # Curacao
    "MU",  # Mauritius
    "PA",  # Panama
    # "HK",  # Hong Kong
    # "SG",  # Singapore
}


class RegionMatcher:
    """
    Compiles regexes for Regions, Nations, and Specific Unions.
    Allows independent parsing of text to find these entities.
    """

    union_map: Dict[str, Tuple[Region, str, str]] = (
        {}
    )  # term -> (Region, Country, Code)
    regex_union_map: Dict[str, Tuple[Region, str, str]] = {}

    location_map: Dict[str, Tuple[Region, str, Optional[str], str]] = (
        {}
    )  # term -> (Region, Country, City, Code)
    regex_location_map: Dict[str, Tuple[Region, str, Optional[str], str]] = {}

    specific_union_regex: Optional[re.Pattern] = None
    location_regexes: List[re.Pattern] = []

    regex_detector_regex = re.compile(r"[\^\$\*\+\?\{\}\[\]\\\|\(\)]")
    _compiled = False
    def __init__(self):
        if not RegionMatcher._compiled:
            RegionMatcher._compile()

    @classmethod
    def get_location(cls, text: str) -> Optional[Tuple[Region, str, Optional[str], str]]:
        lower = text.lower()
        if lower in cls.location_map:
            return cls.location_map[lower]
        
        for pattern, info in cls.regex_location_map.items():
            if re.fullmatch(pattern, text, re.IGNORECASE):
                return info
        return None

    @classmethod
    def get_union(cls, text: str) -> Optional[Tuple[Region, str, str]]:
        lower = text.lower()
        if lower in cls.union_map:
            return cls.union_map[lower]
        for pattern, info in cls.regex_union_map.items():
            if re.fullmatch(pattern, text, re.IGNORECASE):
                return info
        return None

    @classmethod
    def _compile(cls):

        all_regions = [
            NORTH_AMERICA,
            EUROPE,
            ASIA_PACIFIC,
            LATIN_AMERICA,
            MIDDLE_EAST_AFRICA,
            INTERNATIONAL,
        ]

        cls.union_map = {}
        cls.regex_union_map = {}
        cls.location_map = {}
        cls.regex_location_map = {}
        union_phrases = set()
        cls.location_regexes = []

        # Helper to safely escape phrases (unless they are already regex patterns)
        def safe_escape(phrases):
            escaped = []
            # Sort by length descending to match longest first
            for p in sorted(list(phrases), key=len, reverse=True):
                # If it has ? ( : ! [ ] then it is a regex
                if cls.regex_detector_regex.search(p):
                    escaped.append(p)
                else:
                    escaped.append(re.escape(p))
            return escaped

        for region_set in all_regions:
            region_geo_phrases = set()
            for nation in region_set:
                # 1. Map Specific Unions
                for union_name in nation.unions:
                    # Store mapping
                    info = (
                        nation.region,
                        nation.name,
                        nation.code,
                    )
                    if cls.regex_detector_regex.search(union_name):
                        cls.regex_union_map[union_name] = info
                    else:
                        cls.union_map[union_name.lower()] = info
                    union_phrases.add(union_name)

                # 1b. Map Keywords (Treat as Phrases for detection - Region Match Only)
                for keyword in nation.keywords:
                    info = (
                        nation.region,
                        nation.name,
                        None,
                        nation.code,
                    )
                    if cls.regex_detector_regex.search(keyword):
                        cls.regex_location_map[keyword] = info
                    else:
                        cls.location_map[keyword.lower()] = info
                    region_geo_phrases.add(keyword)

                # 2. Map Nation Phrases (e.g. "USA", "United States")
                for phrase in nation.phrases:
                    info = (
                        nation.region,
                        nation.name,
                        None,
                        nation.code,
                    )
                    if cls.regex_detector_regex.search(phrase):
                        cls.regex_location_map[phrase] = info
                    else:
                        cls.location_map[phrase.lower()] = info
                    region_geo_phrases.add(phrase)

                # 3. Map Nation Name
                info = (
                    nation.region,
                    nation.name,
                    None,
                    nation.code,
                )
                if cls.regex_detector_regex.search(nation.name):
                    cls.regex_location_map[nation.name] = info
                else:
                    cls.location_map[nation.name.lower()] = info
                region_geo_phrases.add(nation.name)

                # 4. Map Locations (Cities/States)
                for loc in nation.locations:
                    # Location Name
                    info = (
                        nation.region,
                        nation.name,
                        loc.name,
                        nation.code,
                    )
                    if cls.regex_detector_regex.search(loc.name):
                        cls.regex_location_map[loc.name] = info
                    else:
                        cls.location_map[loc.name.lower()] = info
                    region_geo_phrases.add(loc.name)

                    # Location Phrases
                    for phrase in loc.phrases:
                        info = (
                            nation.region,
                            nation.name,
                            loc.name,
                            nation.code,
                        )
                        if cls.regex_detector_regex.search(phrase):
                            cls.regex_location_map[phrase] = info
                        else:
                            cls.location_map[phrase.lower()] = info
                        region_geo_phrases.add(phrase)

                    # Sub-cities
                    for sub in loc.cities:
                        info = (
                            nation.region,
                            nation.name,
                            sub.name,
                            nation.code,
                        )
                        if cls.regex_detector_regex.search(sub.name):
                            cls.regex_location_map[sub.name] = info
                        else:
                            cls.location_map[sub.name.lower()] = info
                        region_geo_phrases.add(sub.name)
                        for phrase in sub.phrases:
                            info = (
                                nation.region,
                                nation.name,
                                sub.name,
                                nation.code,
                            )
                            if cls.regex_detector_regex.search(phrase):
                                cls.regex_location_map[phrase] = info
                            else:
                                cls.location_map[phrase.lower()] = info
                            region_geo_phrases.add(phrase)
            
            if region_geo_phrases:
                pattern_str = (
                    r"\b(?:" + "|".join(safe_escape(region_geo_phrases)) + r")\b"
                )
                cls.location_regexes.append(re.compile(pattern_str, re.IGNORECASE))

        # Compile Specific Union Regex
        if union_phrases:
            pattern_str = (
                r"\b(?:" + "|".join(safe_escape(union_phrases)) + r")\b"
            )
            cls.specific_union_regex = re.compile(pattern_str, re.IGNORECASE)

        cls._compiled = True

    def parse_unions(self, text: str) -> List[Dict[str, Any]]:
        """Returns list of specific union matches with metadata."""
        results = []
        if self.specific_union_regex:
            for m in self.specific_union_regex.finditer(text):
                term = m.group(0)
                info = self.get_union(term)
                if not info:
                    continue
                region, country, code = info
                results.append(
                    {
                        "term": term,
                        "region": region,
                        "country": country,
                        "code": code,
                        "span": m.span(),
                    }
                )
        return results


def _build_code_to_region_map():
    mapping = {}
    all_regions = [
        NORTH_AMERICA,
        EUROPE,
        ASIA_PACIFIC,
        LATIN_AMERICA,
        MIDDLE_EAST_AFRICA,
        INTERNATIONAL,
    ]
    for r_set in all_regions:
        for nation in r_set:
            if nation.code:
                mapping[nation.code] = nation.region.value
    return mapping


_CODE_TO_REGION = _build_code_to_region_map()
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

def _load_external_weights(csv_filename="gdp_pop_pct.csv", alpha=0.6):
    """
    Loads GDP and Population percentages to calculate a composite weight.
    Formula: Weight = alpha * gdp_pct + (1 - alpha) * population_pct
    Default alpha=0.6 gives slightly more weight to economic output (GDP) 
    as a proxy for formal employment presence.
    """
    # Search for CSV in current or parent directories
    candidates = [
        Path(csv_filename),
        Path("union") / csv_filename,
        Path("..") / csv_filename,
        Path("../..") / csv_filename
    ]
    
    df = None
    for p in candidates:
        if p.exists():
            try:
                df = pd.read_csv(p)
                break
            except Exception:
                continue
    
    if df is None or "code" not in df.columns:
        return {}

    try:
        # Ensure columns exist and fill NaNs
        cols = ["gdp_pct", "population_pct"]
        for c in cols:
            if c not in df.columns:
                df[c] = 0.0
        df = df.fillna(0)
        
        # Calculate composite weight
        # Note: Input percentages are 0-100 based on dataset.py logic
        df["weight"] = (alpha * df["gdp_pct"]) + ((1 - alpha) * df["population_pct"])
        
        # Normalize to avoid extremely small numbers if needed, 
        # but relative weights are what matters for division.
        return df.set_index("code")["weight"].to_dict()
    except Exception:
        return {}

def _build_code_to_weight_map():
    mapping = {}
    external_weights = _load_external_weights()
    
    defined_codes = set()
    
    all_regions = [
        NORTH_AMERICA,
        EUROPE,
        ASIA_PACIFIC,
        LATIN_AMERICA,
        MIDDLE_EAST_AFRICA,
        INTERNATIONAL,
    ]
    for r_set in all_regions:
        for nation in r_set:
            if nation.code:
                defined_codes.add(nation.code)
                # Use external weight if available, else default
                if nation.code in external_weights:
                    mapping[nation.code] = external_weights[nation.code]
                else:
                    mapping[nation.code] = nation.weight
    
    # Log codes present in CSV but not in definitions (Undefined Countries)
    missing_definitions = []
    for code, weight in external_weights.items():
        if code not in defined_codes:
            missing_definitions.append({"code": code, "weight": weight})
            
    if missing_definitions:
        try:
            pd.DataFrame(missing_definitions).to_csv("undefined_countries.csv", index=False)
        except Exception:
            pass
    
    return mapping


_CODE_TO_WEIGHT = _build_code_to_weight_map()

def _build_region_weights_map(country_weights):
    """Aggregates country weights to determine region weights."""
    r_weights = {}
    
    # Map Region Enum to list of country codes
    region_to_codes = {}
    
    # 1. Group codes by Region
    all_regions = [
        NORTH_AMERICA, EUROPE, ASIA_PACIFIC, LATIN_AMERICA, MIDDLE_EAST_AFRICA, INTERNATIONAL
    ]
    
    for r_set in all_regions:
        for nation in r_set:
            if nation.code and nation.code in country_weights:
                r_val = nation.region.value
                if r_val not in region_to_codes:
                    region_to_codes[r_val] = []
                region_to_codes[r_val].append(nation.code)

    # 2. Sum weights
    for r_val, codes in region_to_codes.items():
        total_w = sum(country_weights[c] for c in codes)
        r_weights[r_val] = total_w

    # 3. Map Region Codes (EU, APAC) to the same weight
    # We find the "Container Nation" for each region to get its code
    for r_set in all_regions:
        for nation in r_set:
            # Heuristic: If nation name matches region name or is a known container
            if nation.name in [r.value for r in Region] or nation.code in ["EU", "APAC", "LATAM", "MEA", "NA"]:
                if nation.region.value in r_weights:
                    r_weights[nation.code] = r_weights[nation.region.value]
                    # Also update the country-level map for the region code itself
                    # so "EU" gets the weight of Europe, not 0.005
                    _CODE_TO_WEIGHT[nation.code] = r_weights[nation.region.value]

    return r_weights

REGION_WEIGHTS = _build_region_weights_map(_CODE_TO_WEIGHT)

def group_by_scope(entities: List[Dict[str, Any]], target_count: Optional[int] = None) -> List[List[Dict[str, Any]]]:
    """
    Groups geographic entities into clusters based on scope hierarchy to match a target count.
    Used when the number of counts matches the number of 'scopes' but not the total number of entities.
    
    Example: 
      Entities: [International, Europe, China]
      Target: 1
      Result: [[International, Europe, China]] (International contains others)
      
      Entities: [Domestic, International, Europe, China]
      Target: 2
      Result: [[Domestic], [International, Europe, China]]
    """
    if not entities:
        return []

    # Sort by position in text
    sorted_entities = sorted(entities, key=lambda x: x["span"][0])
    
    groups = []
    
    for entity in sorted_entities:
        if not groups:
            groups.append([entity])
            continue
            
        current_head = groups[-1][0]
        
        # Check containment
        head_region = current_head.get("region_enum")
        child_region = entity.get("region_enum")
        child_key = entity.get("key")
        
        is_child = False
        
        if head_region == Region.GLOBAL:
            is_child = True
        elif head_region == Region.INTERNATIONAL:
            # International contains everything except Domestic and Global
            if child_region not in (Region.DOMESTIC, Region.GLOBAL) and child_key != "DOM":
                is_child = True
        elif head_region in (Region.DOMESTIC, Region.UNKNOWN):
            # Domestic/Unknown usually doesn't contain other regions/countries in this context
            # unless explicitly mapped, but usually they are peers or specific locations
            pass
        elif head_region and current_head.get("key") in REGION_CODES:
            # Specific Region (e.g. EUROPE) contains countries in that region
            # CRITICAL: Only allow grouping if Head is a Region Code (Container), not a Country
            # Check if child is a country in that region
            # We can check if child_region matches head_region (Country's region_enum is set to its region)
            if child_region == head_region:
                # Ensure it's not the same region name (e.g. Europe inside Europe)
                if entity.get("key") != current_head.get("key"):
                    is_child = True

        if is_child:
            groups[-1].append(entity)
        else:
            groups.append([entity])
            
    if target_count is None or len(groups) == target_count:
        return groups
        
    return []
