from dataclasses import dataclass
from enum import Enum

class Region(Enum):
    NORTH_AMERICA = "North America"
    LATIN_AMERICA = "Latin America"
    EUROPE = "Europe"
    MIDDLE_EAST_AFRICA = "Middle East & Africa"
    ASIA_PACIFIC = "Asia Pacific"


@dataclass
class Nation:
    name: str
    phrases: list[str]
    region: Region
    
    def __hash__(self):
        return hash(self.name)
    
    def __eq__(self, other):
        return self.name == other.name

NORTH_AMERICA = {
    Nation("United States", ["us", "u.s.", "usa", "united states", "american"], Region.NORTH_AMERICA),
    Nation("Canada", ["canada", "canadian"], Region.NORTH_AMERICA),
}

EUROPE = {
    Nation("Europe", ["europe", "eurozone", "eu", "european"], Region.EUROPE),
    Nation("United Kingdom", ["uk", "u.k.", "britain", "united kingdom"], Region.EUROPE),
    Nation("Norway", ["norway", "norwegian"], Region.EUROPE),
    Nation("Sweden", ["sweden", "swedish"], Region.EUROPE),
    Nation("Denmark", ["denmark", "danish"], Region.EUROPE),
    Nation("Poland", ["poland", "polish"], Region.EUROPE),
    Nation("Hungary", ["hungary", "hungarian"], Region.EUROPE),
    Nation("Czech Republic", ["czech republic", "czechia", "czech"], Region.EUROPE),
    Nation("Turkey", ["turkey", "turkish"], Region.EUROPE),
    Nation("Russia", ["russia", "russian"], Region.EUROPE),
    Nation("Bulgaria", ["bulgaria", "bulgarian"], Region.EUROPE),
    Nation("Romania", ["romania", "romanian"], Region.EUROPE),
    Nation("Germany", ["germany", "german", "deutschland"], Region.EUROPE),
    Nation("France", ["france", "french"], Region.EUROPE),
    Nation("Italy", ["italy", "italian"], Region.EUROPE),
    Nation("Spain", ["spain", "spanish"], Region.EUROPE),
    Nation("Netherlands", ["netherlands", "dutch", "holland"], Region.EUROPE),
    Nation("Switzerland", ["switzerland", "swiss"], Region.EUROPE),
    Nation("Belgium", ["belgium", "belgian"], Region.EUROPE),
    Nation("Austria", ["austria", "austrian"], Region.EUROPE),
    Nation("Ireland", ["ireland", "irish"], Region.EUROPE),
    Nation("Portugal", ["portugal", "portuguese"], Region.EUROPE),
    Nation("Greece", ["greece", "greek"], Region.EUROPE),
    Nation("Finland", ["finland", "finnish"], Region.EUROPE),
    Nation("Ukraine", ["ukraine", "ukrainian"], Region.EUROPE),
}

ASIA_PACIFIC = {
    Nation("Japan", ["japan", "japanese"], Region.ASIA_PACIFIC),
    Nation("South Korea", ["south korea", "korea", "korean"], Region.ASIA_PACIFIC),
    Nation("Singapore", ["singapore", "singaporean"], Region.ASIA_PACIFIC),
    Nation("Hong Kong", ["hong kong", "hk"], Region.ASIA_PACIFIC),
    Nation("Taiwan", ["taiwan", "taiwanese"], Region.ASIA_PACIFIC),
    Nation("China", ["china", "chinese", "prc", "p.r.c."], Region.ASIA_PACIFIC),
    Nation("Thailand", ["thailand", "thai"], Region.ASIA_PACIFIC),
    Nation("Malaysia", ["malaysia", "malaysian"], Region.ASIA_PACIFIC),
    Nation("Philippines", ["philippines", "philippine", "filipino"], Region.ASIA_PACIFIC),
    Nation("Vietnam", ["vietnam", "vietnamese"], Region.ASIA_PACIFIC),
    Nation("Indonesia", ["indonesia", "indonesian"], Region.ASIA_PACIFIC),
    Nation("India", ["india", "indian"], Region.ASIA_PACIFIC),
    Nation("Pakistan", ["pakistan", "pakistani"], Region.ASIA_PACIFIC),
    Nation("Australia", ["australia", "australian"], Region.ASIA_PACIFIC),
    Nation("New Zealand", ["new zealand", "nz"], Region.ASIA_PACIFIC),
    Nation("Fiji", ["fiji", "fijian"], Region.ASIA_PACIFIC),
    Nation("Bangladesh", ["bangladesh", "bangladeshi"], Region.ASIA_PACIFIC),
}

LATIN_AMERICA = {
    Nation("Mexico", ["mexico", "mexican"], Region.LATIN_AMERICA),
    Nation("Brazil", ["brazil", "brazilian"], Region.LATIN_AMERICA),
    Nation("Argentina", ["argentina", "argentine"], Region.LATIN_AMERICA),
    Nation("Chile", ["chile", "chilean"], Region.LATIN_AMERICA),
    Nation("Colombia", ["colombia", "colombian"], Region.LATIN_AMERICA),
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
    Nation("United Arab Emirates", ["uae", "u.a.e.", "emirates"], Region.MIDDLE_EAST_AFRICA),
    Nation("Saudi Arabia", ["saudi arabia", "saudi"], Region.MIDDLE_EAST_AFRICA),
    Nation("Israel", ["israel", "israeli"], Region.MIDDLE_EAST_AFRICA),
    Nation("Kuwait", ["kuwait", "kuwaiti"], Region.MIDDLE_EAST_AFRICA),
    Nation("South Africa", ["south africa", "south african"], Region.MIDDLE_EAST_AFRICA),
    Nation("Nigeria", ["nigeria", "nigerian"], Region.MIDDLE_EAST_AFRICA),
    Nation("Kenya", ["kenya", "kenyan"], Region.MIDDLE_EAST_AFRICA),
    Nation("Tanzania", ["tanzania", "tanzanian"], Region.MIDDLE_EAST_AFRICA),
    Nation("Egypt", ["egypt", "egyptian"], Region.MIDDLE_EAST_AFRICA),
    Nation("Ethiopia", ["ethiopia", "ethiopian"], Region.MIDDLE_EAST_AFRICA),
    Nation("Ghana", ["ghana", "ghanaian"], Region.MIDDLE_EAST_AFRICA),
    Nation("Morocco", ["morocco", "moroccan"], Region.MIDDLE_EAST_AFRICA),
    Nation("Tunisia", ["tunisia", "tunisian"], Region.MIDDLE_EAST_AFRICA),
    Nation("Algeria", ["algeria", "algerian"], Region.MIDDLE_EAST_AFRICA),
    Nation("Qatar", ["qatar", "qatari"], Region.MIDDLE_EAST_AFRICA),
}