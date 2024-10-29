from enum import Enum


class CardPoints(Enum):
    Rot = 100
    Schell = 80
    Eichel = 60
    Gruen = 40
    L = 20
    Ass = 11
    Zehn = 10
    Koenig = 4
    Ober = 3
    Unter = 2
    Neun = 0
    Acht = 0
    Sieben = 0
    Sechs = 0


class GameRules:
    def __init__(self):
        self.start_game_value = 115
        self.max_game_value = 420
        self.points = CardPoints
        self.start_phase = "PROV"
        self.bonus = 300
        self.bonus_trigger = 500
        self.total_rounds = 8
