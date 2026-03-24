from dataclasses import dataclass, field
from enum import Enum
import re
from typing import Dict, List, Optional, Tuple, Any, Set
from defs.regex_lib import (
    add_restrictions,
    build_compound,
    build_regex,
    to_build_alternation,
)
import pandas as pd
from pathlib import Path


class Region(Enum):
    NORTH_AMERICA = "North America"
    LATIN_AMERICA = "Latin America"
    EUROPE = "Europe"
    MIDDLE_EAST_AFRICA = "Middle East/Africa"
    ASIA_PACIFIC = "Asia/Pacific"
    INTERNATIONAL = "International"
    UNKNOWN = "Unknown"
    DOMESTIC = "Domestic"
    GLOBAL = "Global"
    AGGREGATE = "Aggregate"


class GeoCode(Enum):
    AGGREGATE = "AGG"
    DOMESTIC = "DOM"
    INTERNATIONAL = "INT"
    GLOBAL = "GLO"
    UNKNOWN = "UNK"
    NORTH_AMERICA = "NA"
    EUROPE = "EUR"
    ASIA_PACIFIC = "APAC"
    LATIN_AMERICA = "LATAM"
    MIDDLE_EAST_AFRICA = "MEA"
    INT_LANG = "INT_"

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
    weight: float = 0.005  # 0.5%

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
            to_build_alternation(
                add_restrictions(
                    r"american?", lookbehinds=[r"central", r"latin", r"south"]
                )
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
            "AFL-CIO",
            "SEIU",
            "Service Employees International Union",
            "UFCW",
            "United Food and Commercial Workers",
            "USW",
            "USWA",
            "United Steelworkers",
            "PAFCA",
            "Professional Airline Flight Control Association",
            "IFPTE",
            "International Federation of Professional and Technical Engineers",
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
            "AFA",
            "Association of Flight Attendants",
            "AFMA",
            "Aircraft Mechanics Fraternal Association",
            "UMWA",
            "United Mine Workers",
            "IATSE",
            "International Alliance of Theatrical Stage Employees",
            "IUOE",
            "International Union of Operating Engineers",
            "ILA",
            "International Longshoremen's Association",
            "ILWU",
            r"International Longshore(?:mans'|men)? and Warehouse(?:mans'|men)? Union",
            r"International Association of Heat and Frost Insulators and Asbestos Workers",
            r"Association of Professional Flight Attendants",
            r"AFPA",
            "BCTGM",
            "Bakery, Confectionery, Tobacco Workers and Grain Millers",
            "AFSCME",
            "American Federation of State, County and Municipal Employees",
            "LIUNA",
            "Laborers' International Union of North America",
            "BLET",
            "Brotherhood of Locomotive Engineers and Trainmen",
            "SMART",
            "UTU",
            "SMWIA",
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
            "International Bricklayers of America",
            r"American Federation of State, County and Municipal Employees",
            r"AFSCME"
        ],
        [r"Railway Labor Act", r"RLA", r"National Mediation Board"],
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
            "National Automobile, Aerospace, Transportation and General Workers",
            "Canadian Auto Workers",
            "CAW",
        ],
        code="CA",
    ),
    Nation(
        "North America",
        ["north america", "north american"],
        Region.NORTH_AMERICA,
        [],
        [
            "Teamsters",
            "IBT",
            "International Brotherhood of Teamsters",
            "IBEW",
            "International Brotherhood of Electrical Workers",
            "ALPA",
            "Air Line Pilots Association",
            "IAM",
            "International Association of Machinists",
            "International Union of Bricklayers and Allied Craftworkers",
            "AFL-CIO-CLC",
        ],
        code=GeoCode.NORTH_AMERICA.value,
    ),
}

EUROPE = {
    Nation(
        "Europe",
        ["europe(?:an)?"],
        Region.EUROPE,
        [],
        [],
        [],
        code=GeoCode.EUROPE.value,
    ),
    Nation(
        "European Union",
        [
            "european u",
            "european union",
            "eurozone",
            "eur",
            "euro",
        ],
        Region.EUROPE,
        [],
        [],
        [r"ewc"],
        code="EU",
    ),
    Nation(
        "Nordics",
        ["nordics", "nordic", "scandinavia", "scandinavian"],
        Region.EUROPE,
        code="NORD",
    ),
    Nation(
        "Benelux",
        ["benelux"],
        Region.EUROPE,
        code="BNLX",
    ),
    Nation(
        "Iberia",
        ["iberia", "iberian"],
        Region.EUROPE,
        code="IBE",
    ),
    Nation(
        "DACH",
        ["dach"],
        Region.EUROPE,
        code="DACH",
    ),
    Nation(
        "Eastern Europe",
        ["east(?:ern)? europe(?:an)?", "cee", "central europe(?:an)?"],
        Region.EUROPE,
        code="CEE",
    ),
    Nation(
        "Western Europe",
        ["west(?:ern)? europe(?:an)?"],
        Region.EUROPE,
        code="WEU",
    ),
    Nation(
        "United Kingdom",
        [
            "uk",
            "britain",
            "united kingdom",
            add_restrictions("england", lookbehinds=[r"new"]),
            "sterling",
            "gbp",
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
            Location("English Channel", ["english channel"]),
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
        ["norway", "norwegian", "norge"],
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
        ["sweden", "swedish", "sverige"],
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
        [
            "Unionen",
            "IF Metall",
            "Sveriges Ingenjörer",
            "Ledarna",
            "LO",
            "Landsorganisationen",
        ],
        [
            "Saltsjöbadsavtalet",
            "Kollektivavtal",
            "Arbete",
            "Fackförening",
            "Förening",
            "Förbund",
            "Fack",
        ],
        code="SE",
    ),
    Nation("Denmark", ["denmark", "danish", "danmark"], Region.EUROPE, code="DK"),
    Nation(
        "Denmark",
        ["denmark", "danish", "danmark"],
        Region.EUROPE,
        [],
        [],
        ["Arbejde", "Fagforening", "Forening", "Forbund"],
        code="DK",
    ),
    Nation(
        "Poland",
        ["poland", "polish", "polska"],
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
        [
            "Zwiazek",
            "Zawodowy",
            "Pracownikow",
            "Praca",
            "Stowarzyszenie",
            "Zjednoczone",
            "Federacja",
            "Konfederacja",
        ],
        code="PL",
    ),
    Nation(
        "Hungary",
        ["hungary", "hungarian", "magyarország", "magyarorszag"],
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
        ["czech republic", "czechia", "czech", "česká republika", "ceska republika", "česko", "cesko"],
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
        ["turkey", "turkish", "lira", "türkiye", "turkiye"],
        Region.EUROPE,
        [
            Location("Istanbul", ["istanbul"]),
            Location("Ankara", ["ankara"]),
            Location("Izmir", ["izmir"]),
            Location("Bursa", ["bursa"]),  # Major automotive hub
            Location("Kocaeli", ["kocaeli", "izmit"]),  # Industrial hub
        ],
        ["Türk Metal", "Türk Metal Sendikasi", "DISK", "HAK-IS", "TURK-IS"],
        [],
        code="TR",
    ),
    Nation(
        "Russia",
        ["russia", "russian", "ruble", "rub"],
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
        [
            "Trud",
            "Rabota",
            "Soyuz",
            "Profsoyuz",
            "Assotsiatsiya",
            "Federatsiya",
            "Rabochiy",
        ],
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
    Nation("Romania", ["romania", "romanian", "românia"], Region.EUROPE, code="RO"),
    Nation(
        "Romania",
        ["romania", "romanian", "românia"],
        Region.EUROPE,
        [],
        [],
        ["Muncă", "Sindicat", "Asociația", "Uniunea", "Federația", "Lucrătorilor"],
        code="RO",
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
        ["italy", "italian", "italia"],
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
        ["spain", "spanish", "España"],
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
        ["netherlands", "dutch", "holland", "nederland"],
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
        ["switzerland", "swiss", "chf", "schweiz", "suisse", "svizzera"],
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
        ["belgium", "belgian", "belgique", "belgië", "belgie"],
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
        ["austria", "austrian", "österreich", "oesterreich"],
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
        ["greece", "greek", "hellas", "ellada"],
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
        ["finland", "finnish", "suomi"],
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
        [
            "Työehtosopimus",
            "TES",
            "Ammattiliitto",
            "Työ",
            "Liitto",
            "Yhdistys",
        ],  # CBA/Union terms
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
        ["luxembourg", "luxembourgish", "lëtzebuerg", "letzebuerg"],
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
        ["estonia", "estonian", "eesti"],
        Region.EUROPE,
        [Location("Tallinn", ["tallinn"])],
        [
            "IMTAL",
            "Estonian Industrial and Metalworkers' Union",
            "Eesti Industriaal-ja Metallitöötajate Ametiühingute Liit",
        ],
        ["Ametiühingute", "Liit", "Töötajate"],
        code="EE",
    ),
    Nation(
        "Latvia",
        ["latvia", "latvian", "latvija"],
        Region.EUROPE,
        [Location("Riga", ["riga"])],
        code="LV",
    ),
    Nation(
        "Lithuania",
        ["lithuania", "lithuanian", "lietuva"],
        Region.EUROPE,
        [Location("Vilnius", ["vilnius"]), Location("Kaunas", ["kaunas"])],
        code="LT",
    ),
    Nation(
        "Baltic States",
        ["baltic states", "baltics", "baltic region"],
        Region.EUROPE,
        code="BALT",
    ),
    Nation(
        "Balkans",
        ["balkans", "balkan", "balkan peninsula"],
        Region.EUROPE,
        code="BALK",
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
    Nation("Kosovo", ["kosovo"], Region.EUROPE, code="XK"),
    Nation(
        "Republic of Georgia",
        ["republic of georgia"],
        Region.EUROPE,
        [Location("Tbilisi", ["tbilisi"])],
        code="GE",
    ),
    Nation(
        "Commonwealth of Independent States",
        ["cis", "commonwealth of independent states", "ussr", "soviet union", "soviet"],
        Region.EUROPE,
        code="CIS",
    ),
    Nation("Albania", ["albania", "albanian"], Region.EUROPE, code="AL"),
    Nation("Andorra", ["andorra", "andorran"], Region.EUROPE, code="AD"),
    Nation(
        "Bosnia and Herzegovina",
        ["bosnia", "herzegovina", "bosnian"],
        Region.EUROPE,
        code="BA",
    ),
    Nation("Croatia", ["croatia", "croatian", "hrvatska"], Region.EUROPE, code="HR"),
    Nation("Faroe Islands", ["faroe islands", "faroese"], Region.EUROPE, code="FO"),
    Nation("Gibraltar", ["gibraltar"], Region.EUROPE, code="GI"),
    Nation("Greenland", ["greenland", "greenlandic"], Region.EUROPE, code="GL"),
    Nation("Iceland", ["iceland", "icelandic", "ísland"], Region.EUROPE, code="IS"),
    Nation("Montenegro", ["montenegro", "montenegrin"], Region.EUROPE, code="ME"),
    Nation(
        "North Macedonia",
        ["north macedonia", "macedonia", "macedonian"],
        Region.EUROPE,
        code="MK",
    ),
    Nation("San Marino", ["san marino", "sammarinese"], Region.EUROPE, code="SM"),
    Nation("Serbia", ["serbia", "serbian", "srbija"], Region.EUROPE, code="RS"),
    Nation("Slovakia", ["slovakia", "slovak", "slovensko"], Region.EUROPE, code="SK"),
    Nation("Slovenia", ["slovenia", "slovenian", "slovenija"], Region.EUROPE, code="SI"),
}
ASIA_PACIFIC = {
    Nation(
        "Asia",
        ["asia", "asian", "asia[- ]?pacific", "apac"],
        Region.ASIA_PACIFIC,
        code=GeoCode.ASIA_PACIFIC.value,
    ),
    Nation(
        "Oceania",
        ["oceanian?"],
        Region.ASIA_PACIFIC,
        code="OCN",
    ),
    Nation(
        "Southeast Asia",
        ["southeast asia", "s.e. asia", "asean"],
        Region.ASIA_PACIFIC,
        code="ASEAN",
    ),
    Nation(
        "South Asia",
        ["south(?:ern) asian?", "indian subcontinent"],
        Region.ASIA_PACIFIC,
        code="SASIA",
    ),
    Nation(
        "East Asia",
        ["east(?:ern) asian?"],
        Region.ASIA_PACIFIC,
        code="EASIA",
    ),
    Nation(
        "Japan",
        ["japan", "japanese", "yen", "jpy", "nihon", "nippon"],
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
            "Rodo Kumiai",  # common alt spelling
            "Rodo Kumia",  # variant
            "Zenroren",  # National Confederation of Trade Unions
            "Zenrokyo",  # National Trade Union Council
            "Domei",  # historical but still appears in filings
            "Shokugyo Kumiai",  # occupational union
            "Sangyo Kumiai",  # industrial union
            "Jigyousho Kumiai",  # workplace union
            "Roso",  # labor union (abbrev)
            "Roso Domei",  # labor union federation
            "Kigyōbetsu Kumiai",  # enterprise union
            "Kigyō Roso",  # enterprise labor union
            "Roren",  # federation of labor unions
            "Rengo Roren",  # appears in some filings
            "Kumiai Iin",  # union ,committee
            "Kumiai Soshiki",  # union organization
        ],
        [
            "Shunto",  # spring wage offensive
            "Karoshi",  # death from overwork
            "Roudou",
            "Rodo",  # variant
            "Roudousha",  # worker
            "Rodosha",  # variant
            "Roudou Kijun",  # labor standards
            "Rodo Kijun",  # variant
            "Roudou Jikan",  # working hours
            "Rodo Jikan",  # variant
            "Koyo",  # employment
            "Koyo Keiyaku",  # employment contract
            "Hiseiki",  # non‑regular worker
            "Seiki",  # regular worker
            "Haken",  # dispatched labor
            "Haken Rodosha",  # dispatched worker
            "Kumiai",  # generic “association/union” but NOT specific enough to imply an organization
        ],
        code="JP",
    ),
    Nation(
        "South Korea",
        ["south korea", "krw", add_restrictions(
            to_build_alternation(["korea", "korean"]), lookbehinds=[r"north"])
        ],
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
            "Nodongjo",
            "Rodongjo",
            "Nodongjohap",
            "Nojo",
            "Johap",
            "Chohap",
            "Danche gyoseop",
            "Nosa",
            "Geurroja",
            "Bijeonggyujik",
            "Jeonggyujik",
            "Pagaen geullo",
        ],
        [
            "Chaebol",
            "Jaebeol",
            "Nodong",
            "Rodong",
            "Gieop",
            "Giup",
            "Kiup",
            "Daegieop",
            "Junggyeon gieop",
            "Jungso gieop",
            "Gyeyolsa",
            "Jiju hoesa",
            "Saneop danji",
            "Saneop geongyeong",
            "Sannop",
            "Sannop-eop",
            "Jejo",
            "Jejo-eop",
            "Jung-gong-eop",
            "Joseon-eop",
            "Bandochae",
            "Jeonja bubun",
            "Bupumsa",
            "Gongjang",
            "Saengsan line",
            "Saengsan neungnyeok",
            "Goyong Nodongbu",
            "Sanup Tonghaebu",
            "Gongjeong Gyeongjae Wiwonhoe",
            "Guksae Cheong",
        ],
        code="KR",
    ),
    Nation(
        "China",
        [
            "china",
            "chinese",
            "prc",
            "p.r.c.",
            "people's republic of china",
            "yuan",
            "renminbi",
            "rmb",
            "cny",
        ],
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
        [
            "All-China Federation of Trade Unions",
            "ACFTU",
        ],
        [
            "Laodong",  # labor
            "Laogong",  # worker
            "Laodongzhe",  # laborer
            "Laodongli",  # labor force
            "Laodong Hetong",  # labor contract
            "Laowu",  # labor service
            "Laowu Hetong",  # service contract
            "Waidiren",  # migrant worker
            "Gongren",  # worker
            "Zhigong",  # staff/employee
            "Gonghui",  # 工会 — generic "union", but used in union context
            "Zonggonghui",  # 总工会 — general union / federation
            "Gonghui Lianhehui",  # 工会联合会 — union federation (appears occasionally)
        ],
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
            "Hind Mazdoor Sabha",
            "UTUC",  # United Trade Union Congress
            "UTUC-LS",  # Lenin Sarani faction
            "LPF",  # Labour Progressive Federation
            "SEWA",  # Self-Employed Women's Association
            "AICCTU",  # All India Central Council of Trade Unions
            "AIUTUC",  # All India United Trade Union Centre
            "TUCI",  # Trade Union Centre of India
            "Mazdoor Union",  # generic but union-specific
            "Mazdoor Sabha",  # labor union
            "Kamgar Union",  # common in Maharashtra
            "Kamgar Sangh",  # labor association
            "Karmachari Union",  # employee union
            "Karmachari Sangh",  # employee association
        ],
        [
            "Standing Orders",
            "Industrial Disputes Act",
            "Trade Unions Act",
            "Mazdoor",  # worker
            "Kamgar",  # worker
            "Karmachari",  # employee
            "Shramik",  # laborer
            "Samvida",  # contract/temporary
            "Theka Mazdoor",  # contract labor
            "Prabandhan",  # management
            "Sangathan",  # organization (generic)
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
        ["vietnam", "vietnamese", "việt nam"],
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
        [],
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
        ["philippines", "philippine", "filipino", "pilipinas"],
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
        [],
        code="ID",
    ),
    Nation(
        "New Zealand",
        ["new zealand", "nz", "aotearoa"],
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
    Nation("Afghanistan", ["afghanistan", "afghan"], Region.ASIA_PACIFIC, code="AF"),
    Nation("American Samoa", ["american samoa"], Region.ASIA_PACIFIC, code="AS"),
    Nation("Bhutan", ["bhutan", "bhutanese"], Region.ASIA_PACIFIC, code="BT"),
    Nation("Brunei", ["brunei", "bruneian"], Region.ASIA_PACIFIC, code="BN"),
    Nation("Cambodia", ["cambodia", "cambodian"], Region.ASIA_PACIFIC, code="KH"),
    Nation("French Polynesia", ["french polynesia"], Region.ASIA_PACIFIC, code="PF"),
    Nation("Guam", ["guam"], Region.ASIA_PACIFIC, code="GU"),
    Nation("Kiribati", ["kiribati"], Region.ASIA_PACIFIC, code="KI"),
    Nation("Laos", ["laos", "laotian"], Region.ASIA_PACIFIC, code="LA"),
    Nation("Macau", ["macau", "macanese"], Region.ASIA_PACIFIC, code="MO"),
    Nation("Maldives", ["maldives", "maldivian"], Region.ASIA_PACIFIC, code="MV"),
    Nation("Marshall Islands", ["marshall islands"], Region.ASIA_PACIFIC, code="MH"),
    Nation("Micronesia", ["micronesia"], Region.ASIA_PACIFIC, code="FM"),
    Nation("Mongolia", ["mongolia", "mongolian"], Region.ASIA_PACIFIC, code="MN"),
    Nation("Myanmar", ["myanmar", "burma", "burmese"], Region.ASIA_PACIFIC, code="MM"),
    Nation("Nauru", ["nauru", "nauruan"], Region.ASIA_PACIFIC, code="NR"),
    Nation("Nepal", ["nepal", "nepalese"], Region.ASIA_PACIFIC, code="NP"),
    Nation("New Caledonia", ["new caledonia"], Region.ASIA_PACIFIC, code="NC"),
    Nation("North Korea", ["north korean?", "dprk"], Region.ASIA_PACIFIC, code="KP"),
    Nation(
        "Northern Mariana Islands",
        ["northern mariana islands"],
        Region.ASIA_PACIFIC,
        code="MP",
    ),
    Nation("Palau", ["palau", "palauan"], Region.ASIA_PACIFIC, code="PW"),
    Nation(
        "Papua New Guinea", ["papua new guinea", "png"], Region.ASIA_PACIFIC, code="PG"
    ),
    Nation("Samoa", ["samoa", "samoan"], Region.ASIA_PACIFIC, code="WS"),
    Nation("Solomon Islands", ["solomon islands"], Region.ASIA_PACIFIC, code="SB"),
    Nation("Sri Lanka", ["sri lanka", "sri lankan"], Region.ASIA_PACIFIC, code="LK"),
    Nation(
        "Timor-Leste", ["timor-leste", "east timor"], Region.ASIA_PACIFIC, code="TL"
    ),
    Nation("Tonga", ["tonga", "tongan"], Region.ASIA_PACIFIC, code="TO"),
    Nation("Tuvalu", ["tuvalu", "tuvaluan"], Region.ASIA_PACIFIC, code="TV"),
    Nation("Vanuatu", ["vanuatu", "vanuatuan"], Region.ASIA_PACIFIC, code="VU"),
}

LATIN_AMERICA = {
    Nation(
        "Latin America",
        [
            "latin america",
            "latin american",
            "latam",
        ],
        Region.LATIN_AMERICA,
        [],
        code=GeoCode.LATIN_AMERICA.value,
    ),
    Nation(
        "South America",
        ["south america", "south american"],
        Region.LATIN_AMERICA,
        code="SAM",
    ),
    Nation(
        "Central America",
        ["central america", "central american"],
        Region.LATIN_AMERICA,
        code="CAM",
    ),
    Nation(
        "Caribbean",
        ["caribbean", "west indies"],
        Region.LATIN_AMERICA,
        code="CARIB",
    ),
    Nation(
        "Mexico",
        ["mexico", "mexican", "méxico"],
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
        ["brazil", "bra(?:z|s)ilian", "reais", "brl", "Brasil"],
        Region.LATIN_AMERICA,
        [
            Location("Sao Paulo", ["sao paulo"]),
            Location("Rio de Janeiro", ["rio de janeiro"]),
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
        ["peru", "peruvian", "perú"],
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
        ["dominican republic", "dominican", "república dominicana", "republica dominicana"],
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
    Nation("Panama", ["panama", "panamanian", "panamá"], Region.LATIN_AMERICA, code="PA"),
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
    Nation(
        "Antigua and Barbuda", ["antigua", "barbuda"], Region.LATIN_AMERICA, code="AG"
    ),
    Nation("Aruba", ["aruba", "aruban"], Region.LATIN_AMERICA, code="AW"),
    Nation("Belize", ["belize", "belizean"], Region.LATIN_AMERICA, code="BZ"),
    Nation("Cuba", ["cuba", "cuban"], Region.LATIN_AMERICA, code="CU"),
    Nation("Dominica", ["dominica"], Region.LATIN_AMERICA, code="DM"),
    Nation(
        "El Salvador", ["el salvador", "salvadoran"], Region.LATIN_AMERICA, code="SV"
    ),
    Nation("Grenada", ["grenada", "grenadian"], Region.LATIN_AMERICA, code="GD"),
    Nation("Guyana", ["guyana", "guyanese"], Region.LATIN_AMERICA, code="GY"),
    Nation("Haiti", ["haiti", "haitian"], Region.LATIN_AMERICA, code="HT"),
    Nation("Honduras", ["honduras", "honduran"], Region.LATIN_AMERICA, code="HN"),
    Nation("Jamaica", ["jamaica", "jamaican"], Region.LATIN_AMERICA, code="JM"),
    Nation("Nicaragua", ["nicaragua", "nicaraguan"], Region.LATIN_AMERICA, code="NI"),
    Nation(
        "Saint Kitts and Nevis",
        ["saint kitts", "nevis"],
        Region.LATIN_AMERICA,
        code="KN",
    ),
    Nation("Saint Lucia", ["saint lucia"], Region.LATIN_AMERICA, code="LC"),
    Nation("Saint Martin", ["saint martin"], Region.LATIN_AMERICA, code="MF"),
    Nation(
        "Saint Vincent and the Grenadines",
        ["saint vincent", "grenadines"],
        Region.LATIN_AMERICA,
        code="VC",
    ),
    Nation("Sint Maarten", ["sint maarten"], Region.LATIN_AMERICA, code="SX"),
    Nation("Suriname", ["suriname", "surinamese"], Region.LATIN_AMERICA, code="SR"),
    Nation(
        "Trinidad and Tobago", ["trinidad", "tobago"], Region.LATIN_AMERICA, code="TT"
    ),
    Nation(
        "Turks and Caicos Islands",
        ["turks and caicos"],
        Region.LATIN_AMERICA,
        code="TC",
    ),
    Nation(
        "U.S. Virgin Islands",
        ["us virgin islands", "usvi"],
        Region.LATIN_AMERICA,
        code="VI",
    ),
}
MIDDLE_EAST_AFRICA = {
    Nation(
        "Middle East",
        ["middle east", "middle eastern"],
        Region.MIDDLE_EAST_AFRICA,
        code="ME",
    ),
    Nation(
        "Middle East & Africa",
        ["middle east and africa", "middle east & africa", "mena"],
        Region.MIDDLE_EAST_AFRICA,
        code=GeoCode.MIDDLE_EAST_AFRICA.value,
    ),
    Nation(
        "Gulf States",
        ["gulf states", "gcc", "gulf cooperation council", "arabian gulf"],
        Region.MIDDLE_EAST_AFRICA,
        code="GCC",
    ),
    Nation(
        "Sub-Saharan Africa",
        ["sub[- ]?saharan african?", "sub[- ]?saharan?"],
        Region.MIDDLE_EAST_AFRICA,
        code="SSA",
    ),
    Nation(
        "Africa",
        [
            "africa",
            to_build_alternation(add_restrictions("african", lookaheads=[r"american"])),
        ],
        Region.MIDDLE_EAST_AFRICA,
        code="AFR",
    ),
    Nation(
        "North Africa",
        ["north(?:ern)? african?"],
        Region.MIDDLE_EAST_AFRICA,
        code="NAFR",
    ),
    Nation(
        "Southern Africa",
        ["southern african?"],
        Region.MIDDLE_EAST_AFRICA,
        code="SAFR",
    ),
    Nation(
        "West Africa",
        ["west(?:ern)? african?"],
        Region.MIDDLE_EAST_AFRICA,
        code="WAFR",
    ),
    Nation(
        "East Africa",
        ["East(?:ern)? african?"],
        Region.MIDDLE_EAST_AFRICA,
        code="EAFR",
    ),
    Nation(
        "Central Africa",
        ["Central african?"],
        Region.MIDDLE_EAST_AFRICA,
        code="CAFR",
    ),
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
        ["Nigeria Labour Congress", "TUC Nigeria"],
        code="NG",
    ),
    Nation(
        "Morocco",
        ["morocco", "moroccan", "maroc"],
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
        ["tunisia", "tunisian", "tunisie"],
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
        ["algeria", "algerian", "algérie", "algerie"],
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
        [
            Location("Kinshasa", ["kinshasa"]),
            Location("Lubumbashi", ["lubumbashi"]),
            Location("Kolwezi", ["kolwezi"]),
        ],
        code="CD",
    ),
    Nation("Angola", ["angola", "angolan"], Region.MIDDLE_EAST_AFRICA, code="AO"),
    Nation("Bahrain", ["bahrain", "bahraini"], Region.MIDDLE_EAST_AFRICA, code="BH"),
    Nation("Benin", ["benin", "beninese"], Region.MIDDLE_EAST_AFRICA, code="BJ"),
    Nation("Botswana", ["botswana"], Region.MIDDLE_EAST_AFRICA, code="BW"),
    Nation(
        "Burkina Faso",
        ["burkina faso", "burkinabe"],
        Region.MIDDLE_EAST_AFRICA,
        code="BF",
    ),
    Nation("Burundi", ["burundi", "burundian"], Region.MIDDLE_EAST_AFRICA, code="BI"),
    Nation(
        "Cabo Verde", ["cabo verde", "cape verde"], Region.MIDDLE_EAST_AFRICA, code="CV"
    ),
    Nation(
        "Cameroon", ["cameroon", "cameroonian"], Region.MIDDLE_EAST_AFRICA, code="CM"
    ),
    Nation(
        "Central African Republic",
        ["central african republic", "car"],
        Region.MIDDLE_EAST_AFRICA,
        code="CF",
    ),
    Nation("Chad", ["chad", "chadian"], Region.MIDDLE_EAST_AFRICA, code="TD"),
    Nation("Comoros", ["comoros", "comorian"], Region.MIDDLE_EAST_AFRICA, code="KM"),
    Nation(
        "Congo",
        ["republic of the congo", "congo-brazzaville"],
        Region.MIDDLE_EAST_AFRICA,
        code="CG",
    ),
    Nation(
        "Côte d'Ivoire",
        ["côte d'ivoire", "ivory coast"],
        Region.MIDDLE_EAST_AFRICA,
        code="CI",
    ),
    Nation(
        "Djibouti", ["djibouti", "djiboutian"], Region.MIDDLE_EAST_AFRICA, code="DJ"
    ),
    Nation(
        "Equatorial Guinea", ["equatorial guinea"], Region.MIDDLE_EAST_AFRICA, code="GQ"
    ),
    Nation("Eritrea", ["eritrea", "eritrean"], Region.MIDDLE_EAST_AFRICA, code="ER"),
    Nation("Eswatini", ["eswatini", "swaziland"], Region.MIDDLE_EAST_AFRICA, code="SZ"),
    Nation("Gabon", ["gabon", "gabonese"], Region.MIDDLE_EAST_AFRICA, code="GA"),
    Nation("Gambia", ["gambia", "gambian"], Region.MIDDLE_EAST_AFRICA, code="GM"),
    Nation("Guinea", ["guinea", "guinean"], Region.MIDDLE_EAST_AFRICA, code="GN"),
    Nation("Guinea-Bissau", ["guinea-bissau"], Region.MIDDLE_EAST_AFRICA, code="GW"),
    Nation("Iran", ["iran", "iranian"], Region.MIDDLE_EAST_AFRICA, code="IR"),
    Nation("Lesotho", ["lesotho"], Region.MIDDLE_EAST_AFRICA, code="LS"),
    Nation("Liberia", ["liberia", "liberian"], Region.MIDDLE_EAST_AFRICA, code="LR"),
    Nation("Libya", ["libya", "libyan"], Region.MIDDLE_EAST_AFRICA, code="LY"),
    Nation(
        "Madagascar", ["madagascar", "malagasy"], Region.MIDDLE_EAST_AFRICA, code="MG"
    ),
    Nation("Malawi", ["malawi", "malawian"], Region.MIDDLE_EAST_AFRICA, code="MW"),
    Nation("Mali", ["mali", "malian"], Region.MIDDLE_EAST_AFRICA, code="ML"),
    Nation(
        "Mauritania",
        ["mauritania", "mauritanian"],
        Region.MIDDLE_EAST_AFRICA,
        code="MR",
    ),
    Nation(
        "Mozambique", ["mozambique", "mozambican"], Region.MIDDLE_EAST_AFRICA, code="MZ"
    ),
    Nation("Niger", ["niger", "nigerien"], Region.MIDDLE_EAST_AFRICA, code="NE"),
    Nation(
        "Palestine", ["palestine", "palestinian"], Region.MIDDLE_EAST_AFRICA, code="PS"
    ),
    Nation("Rwanda", ["rwanda", "rwandan"], Region.MIDDLE_EAST_AFRICA, code="RW"),
    Nation(
        "São Tomé and Príncipe",
        ["são tomé", "principe"],
        Region.MIDDLE_EAST_AFRICA,
        code="ST",
    ),
    Nation("Senegal", ["senegal", "senegalese"], Region.MIDDLE_EAST_AFRICA, code="SN"),
    Nation(
        "Seychelles",
        ["seychelles", "seychellois"],
        Region.MIDDLE_EAST_AFRICA,
        code="SC",
    ),
    Nation(
        "Sierra Leone",
        ["sierra leone", "sierra leonean"],
        Region.MIDDLE_EAST_AFRICA,
        code="SL",
    ),
    Nation("Somalia", ["somalia", "somali"], Region.MIDDLE_EAST_AFRICA, code="SO"),
    Nation(
        "South Sudan",
        ["south sudan", "south sudanese"],
        Region.MIDDLE_EAST_AFRICA,
        code="SS",
    ),
    Nation("Sudan", ["sudan", "sudanese"], Region.MIDDLE_EAST_AFRICA, code="SD"),
    Nation("Syria", ["syria", "syrian"], Region.MIDDLE_EAST_AFRICA, code="SY"),
    Nation("Togo", ["togo", "togolese"], Region.MIDDLE_EAST_AFRICA, code="TG"),
    Nation("Uganda", ["uganda", "ugandan"], Region.MIDDLE_EAST_AFRICA, code="UG"),
    Nation("Yemen", ["yemen", "yemeni"], Region.MIDDLE_EAST_AFRICA, code="YE"),
    Nation(
        "Zimbabwe", ["zimbabwe", "zimbabwean"], Region.MIDDLE_EAST_AFRICA, code="ZW"
    ),
}

INTERNATIONAL = {
    Nation(
        "International",
        ["international", "foreign", "overseas", "internationally", "other countries", "other regions"],
        Region.INTERNATIONAL,
        [],
        [r"CGT"],
        code=GeoCode.INTERNATIONAL.value,
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
        code=GeoCode.GLOBAL.value,
    ),
    Nation(
        "Iberian (Ambiguous)",
        [],
        Region.INTERNATIONAL,
        [],
        unions=[],
        keywords=[
            "Delegados",
            "Aéreo",
            "Metalúrgica",
            "Metalúrgicos",
            "Química",
            "Transporte",
            "Sindicato",
        ],
        code="INT_IBE",
    ),
    Nation(
        "Spanish (Generic)",
        [],
        Region.INTERNATIONAL,
        [],
        unions=[
            "Contrato Colectivo",
            "Convenio Colectivo",
            "Negociación colectiva",
        ],
        keywords=[
            "Minería",
            "Automóvil",
            "Automotriz",
            "Construcción",
            "Ferrocarril",
            "Ferroviarios",
            "Trabajo",
            "Gremios",
            "Huelga",
            "Comisiones Obereras",
        ],
        code="INT_ES",
    ),
    Nation(
        "Portuguese (Generic)",
        [],
        Region.INTERNATIONAL,
        [],
        unions=[
            "Convenção Coletiva",
            "Negociação coletiva",
        ],
        keywords=[
            "Mineração",
            "Automotivo",
            "Construção",
            "Bancários",
            "Petroleiros",
            "Ferroviários",
            "Trabalho",
            "Greve",
        ],
        code="INT_PT",
    ),
    Nation(
        "French (Generic)",
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
        "Italian (Generic)",
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
        "German (Generic)",
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
        "Dutch (Generic)",
        [],
        Region.INTERNATIONAL,
        [],
        [],
        [
            "Arbeid",
            "Staking",
            "Vakbonden",
            "CAO",
            "Ondernemingsraad",
            "Medezeggenschap",
            "Metaal",
            "Bouw",
            "Zorg",
        ],
        code="INT_NL",
    ),
    Nation(
        "Muslim (Generic)",
        [],
        Region.INTERNATIONAL,
        [],
        [],
        [
            "Serikat",
            "Kesatuan",
            "Sendikasi",
            "Sendika",
            "Ittihad",
            "Niqabat",
            "Federasyonu",
            "Konfederasyonu",
            "Persatuan",
            "Sekerja",
            "Birliği",
            "Persekutuan",
            "Asosiasi",
            "Federasi",
            "Konfederasi",
            "Dernek",
            "Buruh",
            "Pekerja",
            "Kerja",
            "Işçileri",
            "Çalışma",
            "Emek",
            "Ummal",
        ],
        code="INT_MUSLIM",
    ),
    Nation(
        Region.DOMESTIC.value,
        ["domestic", "domestically"],
        Region.DOMESTIC,
        [],
        [],
        [],
        code=GeoCode.DOMESTIC.value,
    ),
}

INT_LANGUAGE_MAP = {
    "INT_IBERIA": {
        "BR",
        "PT",
        "ES",
        "MX",
        "AR",
        "CL",
        "CO",
        "PE",
        "VE",
        "EC",
        "GT",
        "DO",
        "CR",
        "PA",
        "UY",
        "BO",
        "PY",
    },
    "INT_ES": {"ES", "MX", "AR", "CL", "CO", "PE", "VE", "EC", "GT", "DO", "CR", "PA", "UY", "BO", "PY"},
    "INT_PT": {"BR", "PT"},
    "INT_FR": {"FR", "BE", "CH", "CA"},
    "INT_IT": {"IT", "CH", "SM", "VA"},
    "INT_DE": {"DE", "AT", "CH", "LI", "LU"},
    "INT_NL": {"NL", "BE", "SR"},
    "INT_MUSLIM": {
        "ID",
        "PK",
        "BD",
        "TR",
        "EG",
        "IR",
        "SA",
        "MY",
        "IQ",
        "AF",
        "DZ",
        "MA",
        "SD",
        "YE",
        "SY",
        "TN",
        "JO",
        "LB",
        "KW",
        "OM",
        "QA",
        "BH",
        "AE",
    },
    "INT_PL": {"PL"},
    "INT_RU": {"RU", "UA", "BY", "KZ", "KG", "TJ", "UZ", "TM", "AZ", "AM", "MD"},
    "INT_NORD": {"SE", "NO", "DK", "FI", "IS"},
}

UNK_SET = {
    Region.UNKNOWN,
    Region.UNKNOWN.value,
    GeoCode.UNKNOWN.value
}

DOMESTIC_SET = {
    Region.DOMESTIC,
    Region.DOMESTIC.value,
    GeoCode.DOMESTIC.value
}

INT_SET = {
    Region.INTERNATIONAL,
    Region.INTERNATIONAL.value,
    GeoCode.INTERNATIONAL.value
}

GLOBAL_SET = {
    Region.GLOBAL,
    Region.GLOBAL.value,
    GeoCode.GLOBAL.value
}
AGG_SET = {
    Region.AGGREGATE,
    Region.AGGREGATE.value,
    GeoCode.AGGREGATE.value
}
IGNORED_REGIONS = GLOBAL_SET | DOMESTIC_SET | INT_SET | AGG_SET | UNK_SET

G20_CODES =  [
        "AR",
        "AU",
        "BR",
        "CA",
        "CN",
        "FR",
        "DE",
        "IN",
        "ID",
        "IT",
        "JP",
        "KR",
        "MX",
        "RU",
        "SA",
        "ZA",
        "TR",
        "GB",
        "US",
        "ES", # Guest member
]
COMPOSITE_REGION_MAP = {
    "BALT": ["EE", "LV", "LT"],
    "BALK": ["AL", "BA", "BG", "HR", "GR", "ME", "MK", "RO", "RS", "SI", "XK"],
    "CIS": ["RU", "BY", "KZ", "KG", "TJ", "UZ", "TM", "AZ", "AM", "MD", "UA"],
    "AFR": [
        "ZA",
        "NG",
        "EG",
        "DZ",
        "MA",
        "KE",
        "ET",
        "GH",
        "CI",
        "TZ",
        "AO",
        "CM",
        "TN",
        "CD",
        "UG",
        "SD",
        "LY",
        "SN",
        "ZM",
        "ZW",
        "BF",
        "ML",
        "BW",
        "MZ",
        "GA",
        "GN",
        "TD",
        "MG",
        "BJ",
        "RW",
        "CG",
        "NE",
        "MW",
        "MR",
        "TG",
        "SL",
        "SO",
        "SS",
        "ER",
        "SZ",
        "BI",
        "DJ",
        "LR",
        "CF",
        "CV",
        "LS",
        "GM",
        "GW",
        "SC",
        "KM",
        "ST",
        "GQ",
    ],
    "GCC": ["SA", "AE", "KW", "QA", "BH", "OM"],
    "ASEAN": ["ID", "TH", "MY", "SG", "PH", "VN", "BN", "KH", "LA", "MM"],
    "SASIA": ["IN", "PK", "BD", "LK", "NP", "BT", "MV", "AF"],
    "EASIA": ["CN", "JP", "KR", "KP", "TW", "MN", "HK", "MO"],
    "ME": [
        "SA",
        "AE",
        "IL",
        "IR",
        "IQ",
        "JO",
        "LB",
        "KW",
        "OM",
        "QA",
        "YE",
        "SY",
        "BH",
        "TR",
    ],
    "NAFR": ["EG", "DZ", "MA", "TN", "LY", "SD"],
    "WAFR": ["BJ", "BF", "CV", "CI", "GM", "GH", "GN", "GW", "LR", "ML", "MR", "NE", "NG", "SN", "SL", "TG"],
    "EAFR": ["BI", "KM", "DJ", "ER", "ET", "KE", "MG", "MW", "MZ", "RW", "SC", "SO", "SS", "UG", "TZ", "ZM", "ZW"],
    "CAFR": ["AO", "CM", "CF", "TD", "CG", "CD", "GQ", "GA", "ST"],
    "SAFR": ["BW", "LS", "ZA", "SZ"],
    "SAM": [
        "AR",
        "BO",
        "BR",
        "CL",
        "CO",
        "EC",
        "GY",
        "PY",
        "PE",
        "SR",
        "UY",
        "VE",
    ],
    "CAM": ["BZ", "CR", "SV", "GT", "HN", "NI", "PA"],
    "CARIB": [
        "AG",
        "AW",
        "BS",
        "BB",
        "BM",
        "VG",
        "KY",
        "CU",
        "CW",
        "DM",
        "DO",
        "GD",
        "HT",
        "JM",
        "KN",
        "LC",
        "MF",
        "PR",
        "VC",
        "SX",
        "TT",
        "TC",
        "VI",
    ],
    "NORD": ["DK", "FI", "IS", "NO", "SE"],
    "BNLX": ["BE", "NL", "LU"],
    "DACH": ["DE", "AT", "CH"],
    "USMCA": ["US", "CA", "MX"],
    "CEE": [
        "PL",
        "CZ",
        "SK",
        "HU",
        "RO",
        "BG",
        "RU",
        "UA",
        "BY",
        "MD",
        "EE",
        "LV",
        "LT",
        "SI",
        "HR",
        "BA",
        "RS",
        "ME",
        "MK",
        "AL",
        "XK",
    ],
    "WEU": ["GB", "IE", "FR", "BE", "NL", "LU", "DE", "AT", "CH"],
    "OCN": [
        "AU",
        "NZ",
        "FJ",
        "PG",
        "SB",
        "VU",
        "WS",
        "TO",
        "TV",
        "KI",
        "NR",
        "FM",
        "MH",
        "PW",
    ],
    "IBE": ["PT", "ES"],
    "EU": ["AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE", "GB"],
}
COMPOSITE_REGION_MAP["SSA"] = [
    c
    for c in COMPOSITE_REGION_MAP["AFR"]
    if c not in COMPOSITE_REGION_MAP["NAFR"]
]

# MEA is ME + AFRICA
COMPOSITE_REGION_MAP[GeoCode.MIDDLE_EAST_AFRICA.value] = list(
    set(COMPOSITE_REGION_MAP["ME"] + COMPOSITE_REGION_MAP["AFR"])
)

# # LATAM is CAM + SAM + MX
# COMPOSITE_REGION_MAP["LATAM"] = list(
#     set(COMPOSITE_REGION_MAP["CAM"] + COMPOSITE_REGION_MAP["SAM"] + ["MX"])
# )

ECONOMIC_CODES = ["G20", "USMCA"]
# All keys that is not G20
COMPOSITE_COUNTRIES = {key for key in COMPOSITE_REGION_MAP if key not in ECONOMIC_CODES}
# Worker terms, Union terms, gap
INT_UNION_MAP = {
    "INT_IBE": (
        [
            "Metalúrgicos",
            "Siderúrgicos",
            "Químicos",
            "Transportes",
            "Transporte",
            "Siderurgia",
            "Petróleo",
            "Minas",
        ],
        [
            "Sindicato",
            "Central",
        ],
        r"(?:\s+(?:de|para|&|Sindical|Nacional|[A-Z][\w-]*)){0,3}\s+",
    ),
    "INT_ES": (
        [
            "Trabajadores",
            "Obrer(?:o|a)s?",
            "Empleados",
            "Funcionarios",
            "Personal",
            "Metalúrgicos",
            "Siderúrgicos",
            "Petroleros",
            "Químicos",
            "Bancarios",
            "Ferroviarios",
            "Portuarios",
            "Rurales",
            "Textiles",
            "Mineros",
            "Automotrices",
            "Construcción",
            "Comercio",
            "Transportes?",
            "Correos",
            "Siderurgia",
            "Petróleo",
            "Carbón",
            "Minas",
            "Automóvil",
            "Energía",
        ],
        [
            "Sindicato",
            "Federaci(?:ó|o)n",
            "Confederaci(?:ó|o)n",
            "Uni(?:ó|o)n",
            "Central",
            "Asociaci(?:ó|o)n",
            "Comisi(?:ó|o)nes",
        ],
        r"(?:\s+(?:del?|de|y|para|los?|las?|el|&|Sindical|Nacional|[A-Z][\w-]*)){0,3}\s+",
    ),
    "INT_PT": (
        [
            "Trabalhadores",
            "Operários",
            "Empregados",
            "Funcionários",
            "Metalúrgicos",
            "Siderúrgicos",
            "Petroleiros",
            "Químicos",
            "Bancários",
            "Ferroviários",
            "Portuários",
            "Rurais",
            "Têxteis",
            "Mineiros",
            "Automotivos",
            "Construção",
            "Comércio",
            "Transportes",
            "Transporte",
            "Correios",
            "Siderurgia",
            "Petróleo",
            "Gás",
            "Carvão",
            "Minas",
            "Automóvel",
            "Energia",
        ],
        [
            "Sindicato",
            "Federação",
            "Confederação",
            "União",
            "Central",
            "Associação",
        ],
        r"(?:\s+(?:dos?|das?|des?|de|e|para|os|as|&|Sindical|Nacional|[A-Z][\w-]*)){0,3}\s+",
    ),
    "INT_FR": (
        [
            "Travailleurs",
            "Salariés",
            "Employés",
            "Ouvriers",
            "Métallurgistes",
            "Sidérurgistes",
            "Pétroliers",
            "Chimistes",
            "Bancaires",
            "Cheminots",
            "Portuaires",
            "Agricoles",
            "Mineurs",
            "Transports",
            "Postes",
            "Métallurgie",
            "Sidérurgie",
            "Pétrole",
            "Gaz",
            "Charbon",
            "Bâtiment",
            "Énergie",
        ],
        ["Syndicat", "Fédération", "Confédération", "Union", "Centrale", "Association"],
        r"(?:\s+(?:du|des?|et|pour|les?|la|&|[A-Z][\w-]*)){0,3}\s+",
    ),
    "INT_IT": (
        [
            "Lavoratori",
            "Dipendenti",
            "Operai",
            "Impiegati",
            "Personale",
            "Addetti",
            "Metalmeccanici",
            "Chimici",
            "Edili",
            "Tessili",
            "Bancari",
            "Ferrovieri",
            "Portuali",
            "Agricoli",
            "Minatori",
            "Automobilistici",
            "Costruzioni",
            "Commercio",
            "Trasporti",
            "Poste",
            "Metallo",
            "Petrolio",
            "Carbone",
            "Miniere",
        ],
        [
            "Sindacato",
            "Federazione",
            "Confederazione",
            "Unione",
            "Associazione",
            "Lega",
            "Camera",
            "Organizzazione",
        ],
        r"(?:\s+(?:dei|degli|delle|di|del|della|e|per|il|lo|la|i|gli|le|&|[A-Z][\w-]*)){0,3}\s+",
    ),
    "INT_DE": (
        [
            "Arbeitnehmer",
            "Arbeiter",
            "Angestellte",
            "Beschäftigte",
            "Personal",
            "Mitarbeiter",
            "Metall",
            "Chemie",
            "Bergbau",
            "Energie",
            "Bau",
            "Dienstleistung",
            "Eisenbahn",
            "Nahrung",
            "Genuss",
            "Gaststätten",
            "Erziehung",
            "Wissenschaft",
            "Polizei",
            "Post",
            "Logistik",
            "Verkehr",
            "Banken",
            "Versicherung",
            "Textil",
            "Bekleidung",
            "Holz",
            "Kunststoff",
        ],
        [
            "Gewerkschaft",
            "Bund",
            "Verband",
            "Vereinigung",
            "Industriegewerkschaft",
            "IG",
        ],
        r"(?:\s+(?:der|des|dem|den|für|im|in|und|&|[A-Z][\w-]*)){0,3}\s+",
    ),
    "INT_NL": (
        [
            "Werknemers",
            "Arbeiders",
            "Personeel",
            "Medewerkers",
            "Bedienden",
            "Metaal",
            "Bouw",
            "Vervoer",
            "Spoorwegen",
            "Havens",
            "Chemie",
            "Onderwijs",
            "Zorg",
            "Politie",
            "Banken",
            "Verzekeringen",
            "Textiel",
            "Voeding",
            "Landbouw",
        ],
        [
            "Vakbond",
            "Bond",
            "Unie",
            "Federatie",
            "Vereniging",
            "Centrale",
            "Vakcentrale",
            "Vakbeweging",
        ],
        r"(?:\s+(?:van|de|het|en|voor|in|op|&|[A-Z][\w-]*)){0,3}\s+",
    ),
    "INT_MUSLIM": (
        [
            "Buruh",
            "Pekerja",
            "Kerja",
            "Işçileri",
            "Çalışma",
            "Emek",
            "Ummal",
        ],
        [
            "Serikat",
            "Kesatuan",
            "Sendikasi",
            "Sendika",
            "Ittihad",
            "Niqabat",
            "Federasyonu",
            "Konfederasyonu",
            "Persatuan",
            "Sekerja",
            "Birliği",
            "Persekutuan",
            "Asosiasi",
            "Federasi",
            "Konfederasi",
            "Dernek",
        ],
        r"(?:\s+(?:al|el|ul|dan|ve|wa|&|[A-Z][\w-]*)){0,3}\s+",
    ),
    "INT_PL": (
        [
            "Pracowników",
            "Robotników",
            "Górników",
            "Hutników",
            "Kolejarzy",
            "Nauczycieli",
            "Budowlanych",
            "Metalowców",
            "Stoczniowców",
            "Portowców",
        ],
        [
            "Związek",
            "Zawodowy",
            "Federacja",
            "Konfederacja",
            "Solidarność",
            "Porozumienie",
            "Zrzeszenie",
        ],
        r"(?:\s+(?:i|ds\.|z|w|dla|&|[A-Z][\w-]*)){0,3}\s+",
    ),
    "INT_RU": (
        [
            "Rabotnikov",
            "Sluzhashchikh",
            "Shakhterov",
            "Metallurgov",
            "Zheleznodorozhnikov",
            "Stroiteley",
            "Neftyanikov",
            "Khimikov",
            "Energetikov",
            "Moryakov",
        ],
        [
            "Profsoyuz",
            "Soyuz",
            "Federatsiya",
            "Konfederatsiya",
            "Ob'yedineniye",
            "Assotsiatsiya",
        ],
        r"(?:\s+(?:i|v|dlya|&|[A-Z][\w-]*)){0,3}\s+",
    ),
    "INT_NORD": (
        [
            "Arbeidere",
            "Arbetare",
            "Ansatte",
            "Anställda",
            "Funktionärer",
            "Ingenjörer",
            "Ingeniører",
            "Lærere",
            "Lärare",
            "Sykepleiere",
            "Sjuksköterskor",
        ],
        [
            "Fagforening",
            "Fackförening",
            "Forbund",
            "Förbund",
            "Unionen",
            "Landsorganisasjonen",
            "Landsorganisationen",
            "Centralorganisationen",
        ],
        r"(?:\s+(?:for|för|och|og|i|&|[A-Z][\w-]*)){0,3}\s+",
    ),
}
REGION_CODES = {
    GeoCode.NORTH_AMERICA.value,
    GeoCode.EUROPE.value,
    GeoCode.ASIA_PACIFIC.value,
    GeoCode.LATIN_AMERICA.value,
    GeoCode.MIDDLE_EAST_AFRICA.value,
    GeoCode.DOMESTIC.value,
    GeoCode.INTERNATIONAL.value,
}


def add_region_values():
    region_values = {r.value for r in Region if r not in IGNORED_REGIONS}
    regions = [
        NORTH_AMERICA,
        EUROPE,
        ASIA_PACIFIC,
        LATIN_AMERICA,
        MIDDLE_EAST_AFRICA,
        INTERNATIONAL,
    ]
    # Iterate to see if any of the region has a code that is a composite key
    for region in regions:
        for nation in region:
            if nation.code in COMPOSITE_REGION_MAP:
                if nation.code in COMPOSITE_COUNTRIES:
                    continue
                # add the value to region values
                region_values.add(nation.name)
    return region_values

REGION_VALUES = add_region_values()

COMPOSITE_REGION_MAP["G20"] =  list(G20_CODES + ["CEE", "WEU", "CIS", "DACH", "IBE", "EASIA", "SASIA"] + [x for x in list(REGION_CODES | REGION_VALUES) if x not in IGNORED_REGIONS])

REGION_CODES.update(set(COMPOSITE_REGION_MAP.keys()) - COMPOSITE_COUNTRIES)
REGION_CODES.update(INT_LANGUAGE_MAP.keys())


def is_region(key: Optional[str] = None) -> bool:
    if not key:
        return False
    reg = key.split("::")[0]
    return reg in REGION_VALUES | REGION_CODES

def get_composite_constituents(code: str) -> List[str]:
    """Returns the list of constituent country codes for a composite region/country."""
    return COMPOSITE_REGION_MAP.get(code, [])

TAX_HAVEN_CODES = {
    "KY",  # Cayman Islands
    "BM",  # Bermuda
    "VG",  # British Virgin Islands
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
}
TAX_HAVEN_PENALTY = 0.05  # Reduce weight by 80% for tax havens
# Additional locations to penalize in weight calculations (but not treat as tax havens for home country detection)
EXTRA_WEIGHT_PENALTY_CODES = {
    "LU": 0.25,  # Luxembourg
    "IE": 0.40,  # Ireland
    "NL": 0.70,  # Netherlands
    "CH": 0.70,  # Switzerland
    "HK": TAX_HAVEN_PENALTY,  # Hong Kong
    "SG": 0.40,  # Singapore
}


BUSINESS_BOOSTER = {
    "TW": 1.5,  # Taiwan – real manufacturing + tech hub
    "IL": 1.5,  # Israel – high complexity, real tech footprint
    "KR": 1.5,  # South Korea – real corporate presence to boost it vs Japan
    "JP": 1.2,  # Japan to extend its dominance
    "AE": 1.10,  # UAE – real corporate hub, not a tax haven
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
    def get_location(
        cls, text: str
    ) -> Optional[Tuple[Region, str, Optional[str], str]]:
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
            pattern_str = r"\b(?:" + "|".join(safe_escape(union_phrases)) + r")\b"
            cls.specific_union_regex = re.compile(pattern_str, re.IGNORECASE)

        cls._compiled = True

    def parse_unions(self, text: str) -> List[Dict[str, Any]]:
        """Returns list of specific union matches with metadata."""
        results = []
        if self.specific_union_regex:
            for m in self.specific_union_regex.finditer(text):
                term = m.group(0)
                if not self.is_valid_specific_union_match(term):
                    continue
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

    @staticmethod
    def is_valid_specific_union_match(term: str) -> bool:
        # Require at least one uppercase letter in the matched text to avoid
        # matching common lowercase words like "cut".
        return any(ch.isupper() for ch in term)

REGION_NAME_MAP = {
    Region.EUROPE.value: GeoCode.EUROPE.value,
    Region.NORTH_AMERICA.value: GeoCode.NORTH_AMERICA.value,
    Region.ASIA_PACIFIC.value: GeoCode.ASIA_PACIFIC.value,
    Region.LATIN_AMERICA.value: GeoCode.LATIN_AMERICA.value,
    Region.MIDDLE_EAST_AFRICA.value: GeoCode.MIDDLE_EAST_AFRICA.value,
    Region.INTERNATIONAL.value: GeoCode.INTERNATIONAL.value,
}

def _build_code_to_region_map():
    mapping = {}
    code_mapping = {}
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
                code_mapping[nation.code] = REGION_NAME_MAP.get(nation.region.value, nation.region.value)
    return mapping, code_mapping


_CODE_TO_REGION, _CODE_TO_REGION_CODE = _build_code_to_region_map()

def is_contained(
    container_key: Optional[str] = None,
    item_key: Optional[str] = None,
    domestic_country_code: str = "US",
    excluded_keys: Optional[Set[str]] = None,
) -> bool:
    """
    Checks if item_key is geographically contained within container_key.
    """
    if not container_key or not item_key:
        return False
    if excluded_keys and item_key in excluded_keys:
        return False
    if container_key == item_key:
        return True

    # Normalize item_key if it's a segment
    check_key = item_key.split("::")[0]

    # Special case: Treat UK as distinct from EU to prevent removal of EU when UK is present
    if container_key == "EU" and check_key == "GB":
        return False

    # Special case: Treat Mexico as part of NA when both are explicitly mentioned.
    # LATAM -> MX is already covered by the default region logic.
    if container_key == GeoCode.NORTH_AMERICA.value and check_key == "MX":
        return True

    # Check for Composite Countries (e.g. CIS containing RU)
    if container_key in COMPOSITE_COUNTRIES:
        constituents = get_composite_constituents(container_key)
        if check_key in constituents:
            return True

    # Global/International contains everything except Domestic
    if container_key in GLOBAL_SET | INT_SET:
        if check_key in {domestic_country_code} | DOMESTIC_SET:
            return False
        if check_key in GLOBAL_SET:
            return False
        return True

    # Region contains its countries
    item_region = _CODE_TO_REGION.get(check_key, check_key)
    container_region = _CODE_TO_REGION.get(container_key, container_key)

    if container_region == item_region:
        # Only if container is actually a Region entity
        is_container_region = is_region(container_key)
        if is_container_region:
            is_item_region = is_region(check_key)
            return not is_item_region
    return False

MAJOR_CURRENCIES = {
    "USD": {
        "symbols": ["$"],
        "names": ["dollar", "dollars"],
        "prefix": True,
        "adj": "american",
    },
    "EUR": {
        "symbols": ["€"],
        "names": ["euro", "euros"],
        "prefix": True,
        "adj": None,
    },
    "GBP": {
        "symbols": ["£"],
        "names": ["pound", "pounds", "sterling"],
        "prefix": True,
        "amb_names": ["pound", "pounds"],
        "adj": "british",
    },
    "JPY": {
        "symbols": ["¥"],
        "names": ["yen"],
        "prefix": True,
        "amb_names": ["yen"],
        "adj": "japanese",
    },
    "CNY": {
        "symbols": ["¥"],
        "names": ["yuan", "renminbi"],
        "prefix": True,
        "amb_names": ["yuan", "renminbi"],
        "adj": "chinese",
    },
    "INR": {
        "symbols": ["₹"],
        "names": ["rupee", "rupees"],
        "suffix": True,
        "amb_names": ["rupee", "rupees"],
        "adj": "indian",
    },
    "CAD": {
        "symbols": ["C$", "CAD"],
        "names": ["canadian dollar"],
        "prefix": True,
        "adj": "canadian",
    },
    "AUD": {
        "symbols": ["A$", "AUD"],
        "names": ["australian dollar"],
        "prefix": True,
        "adj": "australian",
    },
    "CHF": {
        "symbols": ["CHF"],
        "names": ["swiss franc"],
        "prefix": True,
        "adj": "swiss",
    },
    "SEK": {
        "symbols": ["kr"],
        "names": ["krona", "kronor"],
        "suffix": True,
        "amb_names": ["krona", "kronor"],
        "adj": "swedish",
    },
    "NOK": {
        "symbols": ["kr"],
        "names": ["krone", "kroner"],
        "suffix": True,
        "amb_names": ["krone", "kroner"],
        "adj": "norwegian",
    },
    "DKK": {
        "symbols": ["kr"],
        "names": ["krone"],
        "suffix": True,
        "amb_names": ["krone"],
        "adj": "danish",
    },
    "MXN": {
        "symbols": ["Mex$"],
        "names": ["mexican peso"],
        "prefix": True,
        "adj": "mexican",
    },
    "BRL": {
        "symbols": ["R$", "BRL"],
        "names": ["brazilian real"],
        "prefix": True,
        "adj": "brazilian",
    },
    "ARS": {
        "symbols": ["$"],
        "names": ["peso", "pesos"],
        "prefix": True,
        "amb_names": ["peso", "pesos"],
        "adj": "argentine",
    },
    "IDR": {
        "symbols": ["Rp"],
        "names": ["rupiah"],
        "prefix": True,
        "adj": "indonesian",
    },
    "KRW": {
        "symbols": ["₩"],
        "names": ["won"],
        "prefix": True,
        "amb_names": ["won"],
        "adj": "korean",
    },
    "RUB": {
        "symbols": ["₽"],
        "names": ["ruble", "rubles", "rouble", "roubles"],
        "prefix": True,
        "adj": "russian",
    },
    "SAR": {
        "symbols": ["﷼", "SR"],
        "names": ["riyal", "riyals"],
        "prefix": True,
        "amb_names": ["riyal", "riyals"],
        "adj": "saudi",
    },
    "TRY": {
        "symbols": ["₺"],
        "names": ["lira"],
        "prefix": True,
        "amb_names": ["lira"],
        "adj": "turkish",
    },
    "NZD": {
        "symbols": ["NZ$"],
        "names": ["new zealand dollar"],
        "prefix": True,
        "adj": "new zealand",
    },
    "HKD": {
        "symbols": ["HK$"],
        "names": ["hong kong dollar"],
        "prefix": True,
        "adj": "hong kong",
    },
    "SGD": {
        "symbols": ["S$"],
        "names": ["singapore dollar"],
        "prefix": True,
        "adj": "singaporean",
    },
    "AED": {
        "symbols": ["د.إ", "AED"],
        "names": ["dirham", "dirhams"],
        "prefix": True,
        "amb_names": ["dirham", "dirhams"],
        "adj": "emirati",
    },
    "ILS": {
        "symbols": ["₪"],
        "names": ["shekel", "shekels", "new shekel"],
        "prefix": True,
        "amb_names": ["shekel", "shekels"],
        "adj": "israeli",
    },
    "THB": {"symbols": ["฿"], "names": ["baht"], "prefix": True, "adj": "thai"},
    "PLN": {
        "symbols": ["zł", "zl"],
        "names": ["zloty", "złoty"],
        "suffix": True,
        "adj": "polish",
    },
    "CZK": {
        "symbols": ["Kč"],
        "names": ["koruna", "koruny"],
        "suffix": True,
        "adj": "czech",
    },
    "HUF": {"symbols": ["Ft"], "names": ["forint"], "suffix": True, "adj": "hungarian"},
    "RON": {
        "symbols": ["lei"],
        "names": ["leu", "lei"],
        "suffix": True,
        "adj": "romanian",
    },
}


def _load_external_weights(csv_filename="gdp_pop_pct.csv", alpha=0.55):
    """
    Loads GDP and Population percentages to calculate a composite weight.
    Formula: Weight = alpha * gdp_pct + (1 - alpha) * population_pct

    Now supports manual overrides for missing or corrected country codes.
    """

    # Search for CSV in current or parent directories
    candidates = [
        Path(csv_filename),
        Path("union") / csv_filename,
        Path("..") / csv_filename,
        Path("../..") / csv_filename,
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
        return {}, {}

    # # -------------------------------
    # # 🔥 MANUAL OVERRIDES GO HERE
    # # -------------------------------
    # manual_rows = {
    #     # Example: Taiwan (TW)
    #     # Values are in 0–1 scale (not 0–100)
    #     "TW": {"gdp_pct": 0.0084, "population_pct": 0.0029},
    #     "XK": {"gdp_pct": 0.0001, "population_pct": 0.00022},
    #     "GG": {"gdp_pct": 0.000008, "population_pct": 0.000035},
    #     "JE": {"gdp_pct": 0.000013, "population_pct": 0.000073},
    # }

    # # Ensure required columns exist
    # for c in ["gdp_pct", "population_pct"]:
    #     if c not in df.columns:
    #         df[c] = 0.0

    # df = df.fillna(0)

    # # Apply manual overrides
    # for code, vals in manual_rows.items():
    #     if code in df["code"].values:
    #         # Update existing row
    #         df.loc[df["code"] == code, ["gdp_pct", "population_pct"]] = [
    #             vals["gdp_pct"],
    #             vals["population_pct"],
    #         ]
    #     else:
    #         # Insert new row
    #         df = pd.concat(
    #             [
    #                 df,
    #                 pd.DataFrame(
    #                     [
    #                         {
    #                             "code": code,
    #                             "gdp_pct": vals["gdp_pct"],
    #                             "population_pct": vals["population_pct"],
    #                         }
    #                     ]
    #                 ),
    #             ],
    #             ignore_index=True,
    #         )

    # Compute composite weight
    df["weight"] = alpha * df["gdp_pct"] + (1 - alpha) * df["population_pct"]

    # Apply Business Boosters
    for code, multiplier in BUSINESS_BOOSTER.items():
        if code in df["code"].values:
            df.loc[df["code"] == code, "weight"] *= multiplier

    # Apply Tax Haven Penalty
    for code in TAX_HAVEN_CODES:
        if code in df["code"].values:
            df.loc[df["code"] == code, "weight"] *= TAX_HAVEN_PENALTY

    # Apply Specific Penalties
    for code, penalty in EXTRA_WEIGHT_PENALTY_CODES.items():
        if code in df["code"].values:
            df.loc[df["code"] == code, "weight"] *= penalty

    weights = df.set_index("code")["weight"].to_dict()
    labor_rates = {}
    if "labor_rate" in df.columns:
        labor_rates = df.set_index("code")["labor_rate"].to_dict()

    return weights, labor_rates


_EXTERNAL_WEIGHTS, _CODE_TO_LABOR_RATE = _load_external_weights()


def _build_code_to_weight_map():
    mapping = {}
    external_weights = _EXTERNAL_WEIGHTS

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
            pd.DataFrame(missing_definitions).to_csv(
                "undefined_countries.csv", index=False
            )
        except Exception:
            pass

    # Apply Manual Composites
    for code, constituents in COMPOSITE_REGION_MAP.items():
        # Only calculate if the code is currently using the default weight (or missing)
        if code == "G20":
            constituents = G20_CODES
        current_w = mapping.get(code, 0.005)
        if abs(current_w - 0.005) < 0.000001:
            total_w = 0.0
            for c in constituents:
                # Make sure the composite region doesn't include regional keys
                if is_region(c):
                    continue
                # Use external weight if available, else use mapped weight
                total_w += external_weights.get(c, mapping.get(c, 0.0))
            if total_w > 0:
                mapping[code] = total_w

    # Apply INT_LANGUAGE_MAP (Average weight)
    for code, constituents in INT_LANGUAGE_MAP.items():
        # Only calculate if the code is currently using the default weight (or missing)
        current_w = mapping.get(code, 0.005)
        if abs(current_w - 0.005) < 0.000001:
            total_w = 0.0
            count = 0
            for c in constituents:
                total_w += external_weights.get(c, mapping.get(c, 0.0))
                count += 1
            if count > 0:
                mapping[code] = total_w / count

    # Force containers to 0 to prevent accidental distribution
    for code in [GeoCode.DOMESTIC.value, GeoCode.INTERNATIONAL.value, GeoCode.GLOBAL.value]:
        mapping[code] = 0.0
    return mapping


_CODE_TO_WEIGHT = _build_code_to_weight_map()


def _build_region_weights_map(country_weights):
    """Aggregates country weights to determine region weights."""
    r_weights = {}

    # Map Region Enum to list of country codes
    region_to_codes = {}

    # 1. Group codes by Region
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
            if nation.code and nation.code in country_weights:
                # Skip composite/container codes for standard regions to avoid double counting
                # (e.g. Don't add "DACH" weight to "Europe" if we already added DE, AT, CH)
                # But keep them for INTERNATIONAL since it relies on language composites
                is_composite = (nation.code in COMPOSITE_REGION_MAP) or is_region(nation.code)

                if is_composite and nation.region != Region.INTERNATIONAL:
                    continue

                if nation.code in IGNORED_REGIONS:
                    continue

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
            # Skip INT, DOM, GLO from inheriting region weights
            if nation.code in IGNORED_REGIONS:
                continue
            # Heuristic: If nation name matches region name or is a known container
            if nation.name in REGION_VALUES or nation.code in REGION_CODES:
                if nation.region.value in r_weights:
                    r_weights[nation.code] = r_weights[nation.region.value]
                    # Also update the country-level map for the region code itself
                    # so "EUR" gets the weight of Europe, not 0.005
                    _CODE_TO_WEIGHT[nation.code] = r_weights[nation.region.value]

    return r_weights


REGION_WEIGHTS = _build_region_weights_map(_CODE_TO_WEIGHT)


def _build_region_labor_rates_map(country_rates, country_weights):
    """Aggregates country labor rates to determine region labor rates (weighted average)."""
    r_rates = {}
    region_to_codes = {}

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
            if nation.code and nation.code in country_rates:
                r_val = nation.region.value
                if r_val not in region_to_codes:
                    region_to_codes[r_val] = []
                region_to_codes[r_val].append(nation.code)

    for r_val, codes in region_to_codes.items():
        total_weight = 0.0
        weighted_sum = 0.0
        count = 0

        for c in codes:
            rate = country_rates[c]
            weight = country_weights.get(c, 0.0)

            weighted_sum += rate * weight
            total_weight += weight
            count += 1

        if total_weight > 0:
            r_rates[r_val] = weighted_sum / total_weight
        elif count > 0:
            # Simple average if no weights
            r_rates[r_val] = sum(country_rates[c] for c in codes) / count

    # Map Region Codes
    for r_set in all_regions:
        for nation in r_set:
            if nation.code in IGNORED_REGIONS:
                continue
            if nation.name in REGION_VALUES or nation.code in REGION_CODES:
                if nation.region.value in r_rates:
                    r_rates[nation.code] = r_rates[nation.region.value]
                    # Also update the country-level map for the region code itself
                    country_rates[nation.code] = r_rates[nation.region.value]

    # Calculate rates for Composite Regions
    for code, constituents in COMPOSITE_REGION_MAP.items():
        total_weight = 0.0
        weighted_sum = 0.0
        count = 0

        for c in constituents:
            if is_region(c):
                continue
            if c in country_rates:
                rate = country_rates[c]
                weight = country_weights.get(c, 0.0)

                weighted_sum += rate * weight
                total_weight += weight
                count += 1

        if total_weight > 0:
            avg_rate = weighted_sum / total_weight
            country_rates[code] = avg_rate
            r_rates[code] = avg_rate
        elif count > 0:
            avg_rate = (
                sum(country_rates[c] for c in constituents if c in country_rates)
                / count
            )
            country_rates[code] = avg_rate
            r_rates[code] = avg_rate

    return r_rates


REGION_LABOR_RATES = _build_region_labor_rates_map(_CODE_TO_LABOR_RATE, _CODE_TO_WEIGHT)


def weighted_division(
    val: float,
    entities: List[Dict[str, Any]],
    use_labor_weights: bool = False,
    domestic_country: Optional[str] = None,
    excluded_keys: Optional[Set[str]] = None,
    capacities: Optional[Dict[str, float]] = None,
) -> Tuple[Dict[str, float], str]:
    """
    Distributes a value across entities based on heuristic weights.
    Applies hierarchical clustering:
    1. Groups entities into clusters (based on COMPOSITE_REGION_MAP).
    2. Sums raw weights for clusters vs standalone entities.
    3. Distributes value to groups proportional to total weight.
    4. Distributes within clusters using smoothed weights (sqrt).
    """
    if not entities:
        return {}, ""
    if val <= 0:
        # Nothing to distribute; avoid running weighting/cluster math.
        return {e["key"]: 0.0 for e in entities if e.get("key") is not None}, ""

    # 0. Pre-allocate min headcount
    original_val = val
    pre_allocated = {}
    if val >= len(entities):
        for e in entities:
            pre_allocated[e["key"]] = 1.0
        val -= len(entities)

    # 1. Map keys to raw weights
    key_to_weight = {}
    note = "" if not use_labor_weights else "Labor weights applied. "
    for e in entities:
        key = e["key"]
        w = 0.005  # Default weight (small country)

        # Check if key is a region name
        if key in REGION_WEIGHTS:
            w = REGION_WEIGHTS[key]

            if excluded_keys:
                subtracted_weight = 0.0
                for excl in excluded_keys:
                    is_in_region = False
                    # 1. Key is Region Name (e.g. "Europe")
                    if key in REGION_VALUES:
                        if _CODE_TO_REGION.get(excl) == key:
                            is_in_region = True
                    # 2. Key is Region Code (e.g. "EUR", "CIS")
                    elif key in REGION_CODES:
                        if key in COMPOSITE_REGION_MAP:
                            if excl in COMPOSITE_REGION_MAP[key]:
                                is_in_region = True
                        else:
                            # Standard region code (e.g. "EUR" -> "Europe")
                            if _CODE_TO_REGION_CODE.get(excl) == key:
                                is_in_region = True

                    if is_in_region:
                        excl_w = 0.0005
                        if excl in _CODE_TO_WEIGHT:
                            excl_w = _CODE_TO_WEIGHT[excl]
                        
                        if use_labor_weights:
                            rate = 0.15
                            if excl in REGION_LABOR_RATES:
                                rate = REGION_LABOR_RATES[excl]
                            elif excl in _CODE_TO_LABOR_RATE:
                                rate = _CODE_TO_LABOR_RATE[excl]
                            excl_w *= rate
                        
                        subtracted_weight += excl_w
                
                if subtracted_weight > 0:
                    w = max(0.0, w - subtracted_weight)
                    note += f"Excluded {', '.join(excluded_keys)} from {key}. "

        # Check if key is a country code
        elif key in _CODE_TO_WEIGHT:
            w = _CODE_TO_WEIGHT[key]

        if use_labor_weights:
            rate = 0.15  # Default average rate if unknown
            if key in REGION_LABOR_RATES:
                rate = REGION_LABOR_RATES[key]
            elif key in _CODE_TO_LABOR_RATE:
                rate = _CODE_TO_LABOR_RATE[key]

            w *= rate

        key_to_weight[key] = w

    # Special handling for EU and UK (GB) coexistence
    if "EU" in key_to_weight and "GB" in key_to_weight:
        eu_w = key_to_weight["EU"]
        gb_w = key_to_weight["GB"]
        if eu_w > gb_w:
            key_to_weight["EU"] = eu_w - gb_w
            note += "Excluded UK from EU weight. "

    # Special handling for LATAM and Mexico (MX) coexistence
    # LATAM typically includes MX in company reporting context, so subtract to avoid
    # double counting when both are explicitly present.
    if GeoCode.LATIN_AMERICA.value in key_to_weight and "MX" in key_to_weight:
        latam_w = key_to_weight[GeoCode.LATIN_AMERICA.value]
        mx_w = key_to_weight["MX"]
        if latam_w > mx_w:
            key_to_weight[GeoCode.LATIN_AMERICA.value] = latam_w - mx_w
            note += "Excluded MX from LATAM weight. "

    # NA (North America) in this schema is US/CA, so no NA-MX subtraction here.

    # 1.5 Handle Excluded Domestic Country (Ambiguity Penalty)
    # If domestic is excluded, and we only have 1 entity, don't give it 100% of the rest.
    # Inject a phantom "Rest of World" entity to absorb weight.
    is_domestic_excluded = False
    if domestic_country and excluded_keys:
        for k in excluded_keys:
            if k == domestic_country or is_contained(k, domestic_country):
                is_domestic_excluded = True
                break

    if is_domestic_excluded and len(entities) == 1:
        single_key = entities[0]["key"]
        # Only apply if the single entity is specific (not a generic container like INT/GLO)
        if single_key not in IGNORED_REGIONS:
            
            scope_weight = 0.0
            note_suffix = ""
            
            # Determine Domestic Region
            dom_region_val = None
            if domestic_country:
                dom_region_val = _CODE_TO_REGION.get(domestic_country)
            
            # Strategy: Use G20 members as the "significant" scope
            # 1. Try Regional G20 (G20 members in the domestic region)
            g20_in_region = []
            if dom_region_val:
                g20_in_region = [c for c in G20_CODES if _CODE_TO_REGION.get(c) == dom_region_val]
            
            # Check if there are relevant G20 members in region (excluding domestic)
            relevant_regional_g20 = [c for c in g20_in_region if c != domestic_country]
            
            if relevant_regional_g20:
                # Use Regional G20 Scope
                scope_weight = sum(_CODE_TO_WEIGHT.get(c, 0.0) for c in g20_in_region)
                dom_weight = _CODE_TO_WEIGHT.get(domestic_country, 0.0)
                scope_weight = max(0.0, scope_weight - dom_weight)
                note_suffix = f"(G20 in {dom_region_val} - {domestic_country})"
            else:
                # Fallback to Global G20 Scope
                scope_weight = sum(_CODE_TO_WEIGHT.get(c, 0.0) for c in G20_CODES)
                dom_weight = _CODE_TO_WEIGHT.get(domestic_country, 0.0)
                scope_weight = max(0.0, scope_weight - dom_weight)
                note_suffix = "(G20 World - Domestic)"
            
            entity_weight = key_to_weight.get(single_key, 0.0)
            
            # Determine if entity is inside the scope
            entity_in_scope = False
            if relevant_regional_g20:
                # If using Regional G20 scope, check if entity is in that region
                ent_region = _CODE_TO_REGION.get(single_key)
                if ent_region == dom_region_val:
                    entity_in_scope = True
            else:
                # Global G20 scope includes everything conceptually
                entity_in_scope = True
            
            # Calculate Phantom Weight
            if entity_in_scope:
                phantom_weight = max(0.0, scope_weight - entity_weight)
            else:
                phantom_weight = scope_weight
            
            # Only apply if phantom is significant (e.g. > 10% of entity)
            if phantom_weight > entity_weight * 0.1:
                key_to_weight["__PHANTOM__"] = phantom_weight
                note += f"Applied ambiguity penalty {note_suffix}. "

    # 2. Apply Dynamic Domestic Booster
    if not is_domestic_excluded and domestic_country and domestic_country not in IGNORED_REGIONS and domestic_country in key_to_weight and len(entities) > 1:
        raw_dom_w = key_to_weight[domestic_country]
        raw_total_w = sum(key_to_weight.values())

        if raw_total_w > 0:
            raw_share = raw_dom_w / raw_total_w

            # Parameters for dynamic boosting
            MAX_BOOST = 6.0  # Max multiplier
            POP_PIVOT = 5000.0  # Population where boost strength halves
            CLUSTER_MAX = 8.0  # Cluster size where boost fades to 0

            # Incorporate BUSINESS_BOOSTER to extend dominance
            biz_boost = BUSINESS_BOOSTER.get(domestic_country, 1.0)

            # Additive Boost (Ensure baseline share for tiny populations)
            additive_boost = 0.20
            additive_limit = 2500.0
            
            if biz_boost > 1.0:
                additive_limit *= biz_boost * 10
                additive_boost *= biz_boost * 10
                note += f"Extended Bias (x{round(additive_boost, 4)}). "

            if original_val < additive_limit:
                additive_boost *= (1.0 - (original_val / additive_limit))

            # Also boost G20 members slightly to reflect economic gravity
            if domestic_country in COMPOSITE_REGION_MAP.get("G20", []):
                biz_boost *= 1.5 if original_val > additive_limit else 3.0
                note += f"(G20 membership) " if domestic_country in G20_CODES else f"(G20 region) "

            if biz_boost > 1.0:
                MAX_BOOST *= biz_boost * 1.5
                POP_PIVOT *= biz_boost * 3
                CLUSTER_MAX *= biz_boost
                note += f"Extended Booster (x{round(biz_boost, 2)}). "


            # Factor 1: Population (Small pop -> High boost)
            pop_factor = 1.0 / (1.0 + (original_val / POP_PIVOT))

            # Factor 2: Cluster Size (Small cluster -> High boost)
            # Calculate effective cluster size (regions count as multiple entities, up to 3)
            cluster_size = 0

            for e in entities:
                k = e["key"]
                if k in COMPOSITE_REGION_MAP:
                    cluster_size += min(len(COMPOSITE_REGION_MAP[k]), 3)
                elif is_region(k):
                    cluster_size += 3
                else:
                    cluster_size += 1

            cluster_factor = max(0.0, 1.0 - (cluster_size - 2) / (CLUSTER_MAX - 2))

            # Factor 3: Share Risk (Low share -> High boost)
            share_factor = 1.0 - raw_share

            # Calculate Booster
            booster = (
                1.0 + (MAX_BOOST - 1.0) * pop_factor * cluster_factor * share_factor
            )

            if booster > 1.05 or additive_boost > 0:
                key_to_weight[domestic_country] = (
                    key_to_weight[domestic_country] * booster
                ) + additive_boost
                note += f"Domestic {domestic_country} boosted x{booster:.2f} +{additive_boost:.3f} (Pop:{int(original_val)}, N:{cluster_size}, Share:{raw_share:.1%}). "

    # 2.5 G20 Pre-smoothing (Redistribute weight among G20 peers to prevent large-cluster dominance)
    g20_members = set(COMPOSITE_REGION_MAP.get("G20", []))
    # Filter for entities present in this division, excluding domestic (already boosted)
    present_g20 = [
        k for k in key_to_weight 
        if k in g20_members and k != domestic_country
    ]
    
    if len(present_g20) >= 2:
        g20_total_raw = sum(key_to_weight[k] for k in present_g20)
        if g20_total_raw > 0:
            # Apply minor smoothing
            smoothing_power = 0.75
            smoothed_weights = {k: key_to_weight[k] ** smoothing_power for k in present_g20}
            smoothed_total = sum(smoothed_weights.values())
            
            # Renormalize to preserve total G20 weight (so they don't gain/lose against non-G20)
            if smoothed_total > 0:
                scale_factor = g20_total_raw / smoothed_total
                for k in present_g20:
                    key_to_weight[k] = smoothed_weights[k] * scale_factor
                note += f"G20 Pre-smooth (x^{smoothing_power}). "

    # 3. Identify Clusters
    remaining_keys = set(key_to_weight.keys())
    groups = []  # List of dicts: {keys: [], weight: float, is_cluster: bool}
    used_clusters = []

    # Check if all entities are G20 members
    g20_members = set(COMPOSITE_REGION_MAP.get("G20", []))
    all_g20 = remaining_keys.issubset(g20_members)

    # Sort composite regions by size (specificity) - smallest first
    sorted_composites = sorted(COMPOSITE_REGION_MAP.items(), key=lambda x: len(x[1]))

    for region_code, members in sorted_composites:
        # If all entities are G20 members, skip sub-clusters to treat them as a single G20 group
        if all_g20 and region_code != "G20":
            continue

        member_set = set(members)
        # Find intersection with remaining keys
        intersection = remaining_keys.intersection(member_set)
        if len(intersection) >= 2:
            # Found a cluster
            cluster_keys = sorted(list(intersection))
            # Calculate raw weight sum of the cluster
            w_sum = sum(key_to_weight[k] for k in cluster_keys)
            groups.append({"keys": cluster_keys, "weight": w_sum, "is_cluster": True})
            used_clusters.append(f"{region_code}: {', '.join(cluster_keys)}")
            # Remove from remaining
            remaining_keys -= intersection

    # Add remaining as individual groups
    for k in sorted(list(remaining_keys)):
        groups.append({"keys": [k], "weight": key_to_weight[k], "is_cluster": False})

    # 3. Distribute val among groups based on group weights
    total_group_weight = sum(g["weight"] for g in groups)

    final_distribution: Dict[str, float] = {}

    if total_group_weight == 0:
        # Fallback: equal split among all entities
        
        # If all entities were explicitly excluded, do not fallback to equal split.
        # Return empty so the count bubbles up to the parent scope (e.g. Global).
        if excluded_keys:
            if all(e["key"] in excluded_keys for e in entities):
                return {}, note

        split_val = int(val / len(entities))
        # Handle remainder
        remainder = int(val) - (split_val * len(entities))
        for i, e in enumerate(entities):
            final_distribution[e["key"]] = split_val + (1 if i < remainder else 0)

        # Add pre-allocated counts
        for k, v in pre_allocated.items():
            final_distribution[k] = final_distribution.get(k, 0) + v
        return final_distribution, ""

    # Distribute to groups
    val_remaining = int(val)

    for i, group in enumerate(groups):
        # Calculate group share
        if i == len(groups) - 1:
            group_share = val_remaining
        else:
            share = (group["weight"] / total_group_weight) * val
            group_share = int(round(share))
            val_remaining -= group_share

        # 4. Distribute inside group
        if group["is_cluster"]:
            # Smooth weights inside cluster: sqrt(weight)
            member_weights = {k: key_to_weight[k] ** 0.5 for k in group["keys"]}
            total_member_weight = sum(member_weights.values())

            if total_member_weight == 0:
                # Equal split inside cluster
                sub_split = int(group_share / len(group["keys"]))
                sub_rem = int(group_share) - (sub_split * len(group["keys"]))
                for j, k in enumerate(group["keys"]):
                    final_distribution[k] = sub_split + (1 if j < sub_rem else 0)
            else:
                sub_remaining = group_share
                for j, k in enumerate(group["keys"]):
                    if j == len(group["keys"]) - 1:
                        final_distribution[k] = sub_remaining
                    else:
                        sub_share = (
                            member_weights[k] / total_member_weight
                        ) * group_share
                        sub_share_int = int(round(sub_share))
                        final_distribution[k] = sub_share_int
                        sub_remaining -= sub_share_int
        else:
            # Single entity
            k = group["keys"][0]
            final_distribution[k] = group_share

    # 5. Add pre-allocated counts
    for k, v in pre_allocated.items():
        final_distribution[k] = final_distribution.get(k, 0) + v

    # Remove phantom entity if present
    if "__PHANTOM__" in final_distribution:
        del final_distribution["__PHANTOM__"]

    if used_clusters:
        note += f"Smoothed Clusters: {', '.join(used_clusters)}"

    # Post-processing: Enforce capacities (Iterative Redistribution)
    if capacities:
        # Filter capacities relevant to current entities
        relevant_caps = {}
        for k in final_distribution:
            if k in capacities and capacities[k] is not None:
                relevant_caps[k] = capacities[k]
        
        if relevant_caps:
            remaining_dist = {k: float(v) for k, v in final_distribution.items()}
            final_capped_dist = {}
            
            # Iterate to redistribute overflow (Max iterations = len(entities) + safety)
            for _ in range(len(entities) + 2):
                overflow = 0.0
                open_keys = []
                
                # Check constraints
                for k, assigned in remaining_dist.items():
                    if k in final_capped_dist:
                        continue # Already finalized
                        
                    cap = relevant_caps.get(k)
                    if cap is not None and assigned > cap:
                        overflow += (assigned - cap)
                        final_capped_dist[k] = cap
                    else:
                        open_keys.append(k)
                
                if overflow < 0.001:
                    # No new overflow, everything else fits
                    for k in open_keys:
                        final_capped_dist[k] = remaining_dist[k]
                    break
                
                if not open_keys:
                    note += f" (Capped, dropped {int(overflow)})"
                    break
                
                # Distribute overflow proportional to current assignment
                total_open_val = sum(remaining_dist[k] for k in open_keys)
                for k in open_keys:
                    share = (remaining_dist[k] / total_open_val) if total_open_val > 0 else (1.0 / len(open_keys))
                    remaining_dist[k] += (overflow * share)
            
            final_distribution = {k: int(round(v)) for k, v in final_capped_dist.items()}
            note += " (Capacity constrained)"

    return final_distribution, note


def group_by_scope(
    entities: List[Dict[str, Any]], target_count: Optional[int] = None
) -> List[List[Dict[str, Any]]]:
    """
    Groups geographic entities into clusters based on scope hierarchy to match a target count.
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
            if (
                child_region not in (Region.DOMESTIC, Region.GLOBAL)
                and child_key != GeoCode.DOMESTIC.value
            ):
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
            # Override: treat MX as grouped under NA when NA is the explicit parent scope.
            elif (
                current_head.get("key") == GeoCode.NORTH_AMERICA.value
                and child_key == "MX"
            ):
                is_child = True
        
        # Check for Composite Countries acting as containers
        elif current_head.get("key") in COMPOSITE_COUNTRIES:
             constituents = get_composite_constituents(current_head.get("key"))
             if child_key in constituents:
                 is_child = True

        if is_child:
            groups[-1].append(entity)
        else:
            groups.append([entity])

    if target_count is None or len(groups) == target_count:
        return groups

    return []


def resolve_remaining_int(
    mentioned_countries: Set[str],
    domestic_country: Optional[str],
    remaining_int_codes: Set[str],
) -> Dict[str, str]:
    """
    Resolves INT_* matches that are not assigned to a country.
    Returns a mapping of {original_code: resolved_code}.
    """
    mapping = {}
    
    g20_codes = set(G20_CODES)

    # Pre-calculate domestic composites if domestic country exists
    domestic_composites = []
    if domestic_country:
        for name, members in COMPOSITE_REGION_MAP.items():
            if domestic_country in members:
                domestic_composites.append((name, members))
        # Sort by length (specificity): USMCA (3) checked before G20 (20+)
        domestic_composites.sort(key=lambda x: len(x[1]))

    for code in remaining_int_codes:
        if code not in INT_LANGUAGE_MAP:
            mapping[code] = code
            continue

        candidates = INT_LANGUAGE_MAP[code]

        # 1. Domestic
        if domestic_country and domestic_country in candidates:
            mapping[code] = domestic_country
            continue

        # 2. Explicit Country Mention
        explicit = candidates.intersection(mentioned_countries)
        if explicit:
            sorted_explicit = sorted(list(explicit), key=lambda c: _CODE_TO_WEIGHT.get(c, 0.0), reverse=True)
            mapping[code] = sorted_explicit[0]
            continue

        # 3. Explicit Region Mention
        candidate_region_codes = set()
        for c in candidates:
            r_code = _CODE_TO_REGION_CODE.get(c)
            if r_code:
                candidate_region_codes.add(r_code)

        matched_regions = candidate_region_codes.intersection(mentioned_countries)

        if matched_regions:
            target_region_code = sorted(list(matched_regions))[0]
            # Refine: If this INT code only has 1 country in this region, map to country
            region_candidates = [
                c for c in candidates
                if _CODE_TO_REGION_CODE.get(c) == target_region_code
            ]
            if len(region_candidates) == 1:
                mapping[code] = region_candidates[0]
            else:
                # If multiple candidates in region, check G20 in region
                g20_in_region = [c for c in region_candidates if c in g20_codes]
                if g20_in_region:
                     g20_in_region.sort(key=lambda c: _CODE_TO_WEIGHT.get(c, 0.0), reverse=True)
                     mapping[code] = g20_in_region[0]
                else:
                    mapping[code] = target_region_code
            continue
            
        # 4. Domestic Region Preference (Implicit Context)
        if domestic_country:
            dom_region = _CODE_TO_REGION_CODE.get(domestic_country)
            if dom_region:
                region_candidates = [c for c in candidates if _CODE_TO_REGION_CODE.get(c) == dom_region]
                if region_candidates:
                    # If multiple candidates in domestic region, use G20/Weight tiebreaker
                    g20_in_region = [c for c in region_candidates if c in g20_codes]
                    if g20_in_region:
                         g20_in_region.sort(key=lambda c: _CODE_TO_WEIGHT.get(c, 0.0), reverse=True)
                         mapping[code] = g20_in_region[0]
                    else:
                        region_candidates.sort(key=lambda c: _CODE_TO_WEIGHT.get(c, 0.0), reverse=True)
                        mapping[code] = region_candidates[0]
                    continue

        # 4.5 Shared Composite Region Preference (e.g. USMCA)
        # Solves US -> MX (USMCA) for INT_ES, even though MX is LATAM and US is NA
        if domestic_composites:
            found_composite = False
            for comp_name, members in domestic_composites:
                # Check if any candidate is in this composite
                comp_candidates = [c for c in candidates if c in members]
                if comp_candidates:
                    # Sort by weight to pick the most prominent member in that composite
                    comp_candidates.sort(key=lambda c: _CODE_TO_WEIGHT.get(c, 0.0), reverse=True)
                    mapping[code] = comp_candidates[0]
                    found_composite = True
                    break
            if found_composite:
                continue

        # 5. G20 Fallback
        g20_candidates = [c for c in candidates if c in g20_codes]
        if g20_candidates:
            g20_candidates.sort(key=lambda c: _CODE_TO_WEIGHT.get(c, 0.0), reverse=True)
            mapping[code] = g20_candidates[0]
            continue
            
        # 5. Highest Weight Fallback (for INT_NL, etc.)
        sorted_candidates = sorted(list(candidates), key=lambda c: _CODE_TO_WEIGHT.get(c, 0.0), reverse=True)
        if sorted_candidates:
            mapping[code] = sorted_candidates[0]
            continue

        mapping[code] = code

    return mapping
