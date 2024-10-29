from math import ceil
import random as rnd
from marjapussi.gamestate import GameState
from marjapussi.action import Action
from marjapussi.gamerules import GameRules


class Policy(object):
    def __init__(self) -> None:
        super().__init__()
        self.game_rules = GameRules()

    def observe_action(self, state: GameState, action: Action) -> None:
        """
        This method is called when the agent observes an action taken by any player.
        The agent shall update their knowledge about the game.
        """
        pass

    def select_action(self, state: GameState, legal_actions: list[Action]) -> Action:
        """
        This method is called when the agent
        is at its turn. It responds with an action
        """
        pass

    def game_start(self, state: GameState):
        """initializes the Policy to be ready for next game"""
        pass


class RandomPolicy(Policy):
    def __init__(self, prom=True) -> None:
        super().__init__()

    def observe_action(self, state: GameState, action: Action) -> None:
        pass
    
    def select_action(self, state: GameState, legal_actions: list[Action]) -> Action:
        return rnd.choice(legal_actions)


class LittleSmartPolicy(Policy):
    def __init__(self) -> None:
        super().__init__()

    def observe_action(self, state: GameState, action: Action) -> None:
        pass

    def select_action(self, state: GameState, legal_actions: list[Action]) -> Action:
        if legal_actions[0].phase == 'PROV':
            return rnd.choice(legal_actions)
        return rnd.choice(legal_actions[:int(ceil(len(legal_actions)/2))])
