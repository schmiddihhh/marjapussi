from enum import Enum


class GamePhase(Enum):
    """
    phases:
    PROV - provoking
    PASS - Passing 4 cards forward
    PBCK - Pushing 4 cards back
    PRMO - Increasing to game value
    QUES - Asking for pairs or halves
    ANSW - Answering for pairs and halves
    ANSS - Answering if questioning player too has a half
    TRCK - Playing cards into the Trick
    DONE - After the game is done
    """
    PROV = 'PROV'
    PASS = 'PASS'
    PBCK = 'PBCK'
    PRMO = 'PRMO'
    QUES = 'QUES'
    ANSW = 'ANSW'
    ANSA = 'ANSA'
    TRCK = 'TRCK'
    DONE = 'DONE'

    def __str__(self):
        return self.value