from marjapussi.policy import Policy
from marjapussi.gamestate import GameState
from marjapussi.action import Action
from marjapussi.card import Card, Deck, Color, Value
from marjapussi.gamerules import GameRules
from marjapussi.policy_player import PolicyPlayer
from marjapussi.concept import Concept
from marjapussi.utils import contains_col_pair, contains_col_half
import numpy as np


class ProbabilisticPolicy(Policy):
    def __init__(self) -> None:
        super().__init__()
        # initialize some values that we always need and update by observing actions
        self.players: list[PolicyPlayer] = []

        self.game_rules = GameRules()
        self.prov_base = 115

        self.our_score = 0
        self.their_score = 0
        self.round = 1

    def game_start(self, state: GameState, scores: [int, int] = None, total_rounds: int = 8):
        super().game_start(state)
        """initializes the Policy to be ready for next game"""
        if not scores:
            scores = [0, 0]
        self.players = [PolicyPlayer(i, state.all_players[i], scores[i % 2]) for i in range(0, 4)]

        self.game_rules.total_rounds = total_rounds
        self.prov_base = self.game_rules.start_game_value

        self.round += 1
        if self.round > self.game_rules.total_rounds:
            self.round = 1

        # already begin reasoning...
        self._calculate_possible_card_probabilities(state)
        self._assess_own_hand(state)

    def _deduct_provoking_infos(self, state: GameState, player_num: int, value: int) -> None:
        """
        We need infos about what the players are trying to communicate!
        For now we assume they have the same provoking rules as we have :)
        In the Future it might be wise to not rely too much on what the opponents try to communicate
        As this way players could abuse the AI too much by feeding false information
        We will also have to assume more variety when playing with other AI policies together
        """
        player_steps = self.players[player_num].provoking_history_steps
        partner_num = self.players[player_num].partner_number
        partner_steps = self.players[partner_num].provoking_history_steps
        player_name = self.players[player_num].name
        # interpreting first steps:
        if len(self.players[player_num].provoking_history_steps) == 1:
            # interpreting if the first step was a 5 increase
            match player_steps[0]:
                case 5:
                    if value < 140:
                        if (partner_steps and partner_steps[0] != 5) or not partner_steps:
                            # we are dealing likely with an ace
                            # TODO lookup the probabilities instead of just the possibilities
                            if any(card.value == Value.Ass for card in state.possible_cards.get(player_name, set())):
                                state.concepts.add(Concept(f"{player_name}_has_ace",
                                                           {"player": player_name, "info_type": "ace"}, value = 1))
                                # TODO add probabilities to the Ace cards that we don't know about yet for that player
                            else:
                                state.concepts.add(Concept(f"{player_name}_is_faking_ace",
                                                           {"player": player_name, "info_type": "ace"}, value=1))
                        elif partner_steps and partner_steps[0] == 5:
                            # the partner already announced an ace, so we assume it must be something else
                            state.concepts.add(Concept(f"{player_name}_has_halves",
                                                       {"player": player_name, "info_type": "halves"}, value=1))
                    elif value == 140:
                        # value 140 might mean anything, especially if its just a 5, but we could add some probability

                        pass
                    else:
                        pass
                case 10:
                    pass
                case 15:
                    pass
                case 20:
                    pass
                case _:
                    pass

        # interpreting consecutive steps:
        else:
            pass

    def observe_action(self, state: GameState, action: Action) -> None:
        """
        adds Knowledge that is based on the observed cards, that helps to decide for the pest action
        This should update some values like the phase or trump that is currently present,
        but it should call for calculating probabilities when the possible cards and secure cards
        in the self.game_state get updated

        Example: cards that are played get removed from self.cards_left, then the information will be used
        to deduct what cards players have based on the possible cards they could have and some simpel math

        In summary, the function will take the game state and update the classes values according to the circumstances
        """
        match state.phase:
            case 'PROV':
                prov_value = action.content
                step = max(0, prov_value - self.prov_base)
                self.players[action.player_number].provoking_history_steps.append(step)
                if prov_value > self.game_rules.start_game_value:
                    self.prov_base = prov_value
                self._deduct_provoking_infos(state, action.player_number, prov_value)

    def _assess_own_hand(self, state: GameState):
        """
        check for pairs, halves, and any cards that might be worth something
        For now we ll just focus on aces, tens and pairs and halves as well as the number of cards for each suite
        """
        # TODO
        hand_cards = state.secure_cards
        # arbitrary hand score, for our own sake ^^ we will keep track of how good we stand
        hand_score = 0

        # first we need to check for aces
        standing_cards_count = len()


    def _calculate_possible_card_probabilities(self, state: GameState):
        """
        Based on combinatorics (binomials mainly for choice) we calculate how like it is for players
        to have a specific card on their hand, based on the information we got in our class variables like the state
        values for possible cards each player has and which cards we know securely (for those the probability is 1)
        """
        # TODO

    def _estimate_provoking_max(self, state):
        """
        We can estimate that the maximum we can reach is somewhere below the combination of
        - standing cards we have as a team
        - pairs each of us has
        - pairs we can combine
        """
        # TODO
        pass

    def _plan_game(self, state):
        """
        This method is only for the playing player!
        Planning the moves ahead to not loose the game to the opponents team.
        We need to watch out for getting as many tricks as possible but also to destroy their abilities
        to swap the trump color
        """
        # TODO
        pass

    def select_action(self, state: GameState, legal_actions: list[Action]) -> Action:
        # select an action based on the current state and legal actions
        probabilities = self.calculate_best_action(state, legal_actions)
        action = np.random.choice(legal_actions, p=probabilities)
        return action

    def calculate_best_action(self, state: GameState, legal_actions: list[Action]):
        game_phase = legal_actions[0].phase
        match game_phase:
            case 'PROV':
                cur_value = legal_actions[-1].content
                self.provoking(state, cur_value)
            case _:
                # calculates evaluation values for each action
                action_evaluations = []
                for action in legal_actions:
                    eval = self.evaluate_action(state, action)
                    action_evaluations.append(eval)
                    # normalize the probabilities so they sum to 1
                normal_eval = [p / sum(action_evaluations) for p in action_evaluations]
                return normal_eval

    def provoking(self, state: GameState, cur_value: int):
        """
        implement provoking logic:
        - try to go high and not let other provoke if you have a very good hand, that means big pairs and aces
        - avoid getting skunked, sometimes this means going to specific values like 140, 180 or 200 first, so the
            enemies can't take the game like that
        - otherwise only go over 140 if you are sure (check concept) that our party has a pair of enough value
        Default to these for normal games, to let your partner know what you have:
        - provoke 5 for an ace (unless your partner has indicated he has one already)
        - provoke 10 for 3 halves (Koenig, or Ober) or a small pair
        - provoke 15 for a big pair
        """
        provoking_history = state.provoking_history
        # we want an optimistic estimate of what we could reach
        estimated_max = self._estimate_provoking_max(state)


        # Check if we are at risk of getting skunked
        if self._calculate_concept_probabilities(state, 'we are getting skunked'):
            if max_value < 140:
                return 140
            elif max_value < 180:
                return 180
            elif max_value < 200:
                return 200
        elif cur_value < estimated_max:
            # Check if we have a very good hand
            if self._calculate_concept_probabilities(state, 'i have very good cards'):
                if cur_value < 120:  # if we move first, let them not exchange information
                    return 140

            # Check if we have a pair of enough value
            if self.has_valuable_pair():
                if max_value < 140:
                    return max_value + 5

            # Default provoking values
            if self.has_ace() and not self.partner_has_indicated_ace(provoking_history):
                return 5
            elif self.has_three_halves_or_small_pair():
                return 10
            elif self.has_big_pair():
                return 15

            # If none of the above conditions are met, provoke with the current max_value
            return max_value

    def evaluate_action(self, state: GameState, action: Action):
        # evaluate the probable success of an action, this is where the knowledge of the game should be used
        # for now, it's a placeholder and always returns 1
        return 1
