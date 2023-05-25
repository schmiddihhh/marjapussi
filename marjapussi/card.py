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

    def points(self):
        return CardPoints[self.name].value


class Card:
    """A generalized Card class"""
    def __init__(self, color: Color | str, value: Value | str):
        if isinstance(color, str):
            try:
                color = Color(color)
            except ValueError:
                raise ValueError("Invalid color value.")
        elif isinstance(color, Color):
            pass
        else:
            raise TypeError("Invalid color type. Expected an instance of Color or a string.")

        if isinstance(value, str):
            try:
                value = Value(value)
            except ValueError:
                raise ValueError("Invalid value.")
        elif isinstance(value, Value):
            pass
        else:
            print(f"Type of value: {type(value)} which is {value}")
            raise TypeError("Invalid value type. Expected an instance of Value or a string.")

        self.color: Color = color
        self.value: Value = value

    def __str__(self) -> str:
        return f"{self.color}-{self.value}"

    def __eq__(self, other) -> bool:
        return self.color == other.color and self.value == other.value

    def __hash__(self):
        return hash((self.color, self.value))


class Deck:
    """A Deck, that by being populated consists of all possible cards there is"""
    def __init__(self):
        self.cards = []
        self.populate()

    def populate(self):
        for color in Color:
            for value in Value:
                card = Card(color, value)
                self.cards.append(card)

    def __str__(self):
        return ", ".join(str(card) for card in self.cards)
