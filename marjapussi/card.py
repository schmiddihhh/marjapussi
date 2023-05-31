from enum import Enum
from marjapussi.gamerules import CardPoints


class Color(Enum):
    """Card Colors"""
    Rot = "r"
    Schell = "s"
    Eichel = "e"
    Gruen = "g"

    def __str__(self):
        return self.value

    def __lt__(self, other):
        # Custom less-than comparison logic
        order = ["g", "e", "s", "r"]
        return order.index(self.value) < order.index(other.value)

    def fancy_name(self) -> str:
        match self.value:
            case("r"): return "Rot"
            case("s"): return "Schell"
            case("e"): return "Eichel"
            case("g"): return "Grün"

    @property
    def points(self):
        return CardPoints[self.name].value


class Value(Enum):
    """Card Values"""
    Ass = "A"
    Zehn = "Z"
    Koenig = "K"
    Ober = "O"
    Unter = "U"
    Neun = "9"
    Acht = "8"
    Sieben = "7"
    Sechs = "6"

    def __str__(self):
        return self.value

    def __lt__(self, other):
        # Custom less-than comparison logic
        order = ["6", "7", "8", "9", "U", "O", "K", "Z", "A"]
        return order.index(self.value) < order.index(other.value)

    @property
    def points(self):
        return CardPoints[self.name].value


class Card:
    """A generalized Card class"""
    def __init__(self, color: Color | str, value: Value | str):
        self.color: Color = self._validate_and_convert(color, Color, "color")
        self.value: Value = self._validate_and_convert(value, Value, "value")

    @staticmethod
    def _validate_and_convert(value, enum_class, attribute_name):
        if isinstance(value, str):
            try:
                return enum_class(value)
            except ValueError:
                raise ValueError(f"Invalid {attribute_name} value.")
        elif isinstance(value, enum_class):
            return value
        else:
            raise TypeError(f"Invalid {attribute_name} "
                            f"type. Expected an instance of {enum_class.__name__} or a string.")

    def __str__(self) -> str:
        return f"{self.color}-{self.value}"

    def __eq__(self, other) -> bool:
        return self.color == other.color and self.value == other.value

    def __hash__(self):
        return hash((self.color, self.value))


class Deck:
    """A Deck, that by being populated consists of all possible cards there is"""
    def __init__(self):
        self.cards = [Card(color, value) for color in Color for value in Value]

    def __str__(self):
        return ", ".join(str(card) for card in self.cards)

