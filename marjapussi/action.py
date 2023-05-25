from card import Card, Color
from enum import Enum


class Talk:
    """
    adds an interface for questions and answers for the players
    - possible question pronouns: my, yours, our (yours doesn't come with a color)
    - possible answer pronouns: my (i have a pair), nmy (no to your pair), no (to our), ou (yes to ours)
    - possible call pronouns: we (we have a pair together), nwe (we have no pair together)
    """
    def __init__(self, pronoun: str, color: Color | None):
        self.pronoun = pronoun
        self.color = color

    def __str__(self):
        if self.color is None:
            return self.pronoun.capitalize()
        else:
            return f"{self.pronoun.capitalize()} {str(self.color)}"

    def __eq__(self, other):
        return self.pronoun == other.pronoun and self.color == other.color


class Action:
    def __init__(self, player_number: int, phase: str, content: int | Card | Talk):
        self.player_number = player_number
        self.phase = phase
        self.content = content

    def __repr__(self):
        return f"Action(player_number={self.player_number}, phase='{self.phase}', content='{self.content}')"

    def __str__(self):
        return self.__repr__()

    def __eq__(self, other):
        return self.player_number == other.player_number and self.phase == other.phase and self.content == other.content
