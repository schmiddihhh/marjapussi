import math

from marjapussi.policy import Policy
from marjapussi.gamestate import GameState
from marjapussi.action import Action
from marjapussi.card import Card, Deck, Color, Value
from marjapussi.gamerules import GameRules
from marjapussi.policy_player import PolicyPlayer
from marjapussi.concept import Concept
import marjapussi.utils as utils
import numpy as np


class ProbabilisticPolicy(Policy):
    def __init__(self) -> None:
        super().__init__()
        # initialize some values that we always need and update by observing actions
        self.players: list[PolicyPlayer] = []

        self.game_rules = GameRules()
        self.prov_base = 115

        self.max_reach_value = 0
        self.max_opponent_reach_value = 420

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

    @staticmethod
    def _interpret_first_gone_provoke(state: GameState, partner_steps: list[int], player_name: str, value: int) -> None:
        """
        Information is saved inside the GameState object that the function adds concepts and information on to
        TODO put this logic in dependencies
        """
        if value < 140:
            if (not partner_steps) or partner_steps[0] == 0:
                # this means kinda bad cards!
                state.concepts.add(Concept(f"{player_name}_has_ace",
                                           {"player": player_name, "info_type": "ace"}, value=0.))
                state.concepts.add(Concept(f"{player_name}_has_3+_halves",
                                           {"player": player_name, "info_type": "halves"}, value=0.))
                state.concepts.add(Concept(f"{player_name}_has_small_pair",
                                           {"player": player_name, "info_type": "pair"}, value=0.))
                state.concepts.add(Concept(f"{player_name}_has_big_pair",
                                           {"player": player_name, "info_type": "pair"}, value=0.))
            else:
                # this means less, but still bad cards!
                state.concepts.add(Concept(f"{player_name}_has_ace",
                                           {"player": player_name, "info_type": "ace"}, value=0.))
                state.concepts.add(Concept(f"{player_name}_has_3+_halves",
                                           {"player": player_name, "info_type": "halves"}, value=0.))
                state.concepts.add(Concept(f"{player_name}_has_small_pair",
                                           {"player": player_name, "info_type": "pair"}, value=0.))
                state.concepts.add(Concept(f"{player_name}_has_big_pair",
                                           {"player": player_name, "info_type": "pair"}, value=0.))
                pass

    @staticmethod
    def _interpret_first_5_provoke(state: GameState, partner_steps: list[int], player_name: str, value: int) -> None:
        """
        Information is saved inside the GameState object that the function adds concepts and information on to
        TODO put this logic in dependencies
        """
        if value < 140:
            if (partner_steps and partner_steps[0] != 5) or not partner_steps:
                # we are dealing likely with an ace
                # TODO lookup the probabilities instead of just the possibilities
                if any(card.value == Value.Ass for card in state.possible_cards.get(player_name, set())):
                    state.concepts.add(Concept(f"{player_name}_has_ace",
                                               {"player": player_name, "info_type": "ace"}, value=1.))
                    # TODO add probabilities to the Ace cards that we don't know about yet for that player
                else:
                    state.concepts.add(Concept(f"{player_name}_is_faking_ace",
                                               {"player": player_name, "info_type": "ace"}, value=1.))
            elif partner_steps and partner_steps[0] == 5:
                # the partner already announced an ace, so we assume it must be something else
                # right now we ignore the small likelihood that he has just another ace
                state.concepts.add(Concept(f"{player_name}_has_halves",
                                           {"player": player_name, "info_type": "halves"}, value=1.))
        else:
            # value 140 might mean anything, especially if its just a 5, but we could add some probability
            # if the partner indicated a pair, it might just be the ace
            # TODO add case for values above 140, for now its all the same
            if partner_steps and partner_steps[0] == 10 or partner_steps[0] == 15 or partner_steps[0] == 20:
                if any(card.value == Value.Ass for card in state.possible_cards.get(player_name, set())):
                    state.concepts.add(Concept(f"{player_name}_has_ace",
                                               {"player": player_name, "info_type": "ace"}, value=1.))
            # we need to differentiate at this point if its our partner:
            if player_name == state.partner:
                # we might want to hit a black game, our partner needs aces and standing cards
                # if they win with this call, other than that we can't really guess anything
                pass
            else:
                # if we are predicting that we might get played black and we have no pair indication, this might
                # ring alarm bells even more
                skunked_concept = state.concepts.get_by_name("getting_played_black")
                if skunked_concept and skunked_concept.evaluate() > 0.5:
                    state.concepts.get_by_name("getting_played_black").value = \
                        min(skunked_concept.value + 0.3, 1)
                    # TODO make this more of a dependant property!
                pass

    @staticmethod
    def _interpret_first_10_provoke(state: GameState, partner_steps: list[int], player_name: str, value: int) -> None:
        """
        Information is saved inside the GameState object that the function adds concepts and information on to
        TODO put this logic in dependencies
        """
        # Probability for small pair or three halves can be calculated, based on the probability
        # we can more accurately tell, which one it might be, given that the player already announced
        # that he has either one
        small_pair_prob = utils.player_has_set_probability(state, player_name, utils.small_pairs())
        three_halves_prob = utils.player_has_set_probability(state, player_name, utils.three_halves())

        if value < 140:
            # we can tell for sure, the player has something:
            state.concepts.add(Concept(f"{player_name}_has_halves",
                                       {"player": player_name, "info_type": "halves"}, value=1.))
            if (partner_steps and partner_steps[0] != 5) or not partner_steps:
                # we are dealing somewhat likely with no ace
                state.concepts.add(Concept(f"{player_name}_has_ace",
                                           {"player": player_name, "info_type": "ace"}, value=0.1))
            state.concepts.add(Concept(f"{player_name}_has_small_pair",
                                       {"player": player_name, "info_type": "pair"}, value=math.sqrt(small_pair_prob)))
            state.concepts.add(Concept(f"{player_name}_has_3+_halves",
                                       {"player": player_name, "info_type": "pair"},
                                       value=math.sqrt(three_halves_prob)))
        elif value == 140:
            # In this case, the information is unclear. We'd assume they wanna just play black, unless this is
            # our own partner, then we might try to hit a black game
            if player_name == state.partner(state.name):
                state.concepts.add(Concept(f"playing_black", {}, value=0.3))
            elif state.concepts.get_by_name(f"getting_played_black"):
                state.concepts.add(Concept(f"getting_played_black", {},
                                           value=math.sqrt(state.concepts.get_by_name(f"getting_played_black").value)))
            else:
                # TODO calculate actual probability of getting played black via dependencies instead of flat values
                state.concepts.add(Concept(f"getting_player_black", {}, value=0.3))
        else:
            # we can tell for sure, the player has something:
            state.concepts.add(Concept(f"{player_name}_has_halves",
                                       {"player": player_name, "info_type": "halves"}, value=1.))
            # first check if we skipped 140
            if state.concepts.get_by_name(f"{state.partner(player_name)}_has_3+_halves"):
                # if the partner indicated haves, it might just be a guessed step for a guessed pair
                state.concepts.add(Concept(f"{player_name}_has_3+_halves",
                                           {"player": player_name, "info_type": "pair"},
                                           value=math.sqrt(three_halves_prob)))
                state.concepts.add(Concept(f"{player_name}_has_small_pair",
                                           {"player": player_name, "info_type": "pair"},
                                           value=small_pair_prob))
            else:
                # otherwise this is likely a small pair, as otherwise the player wouldn't go over 140.
                state.concepts.add(Concept(f"{player_name}_has_3+_halves",
                                           {"player": player_name, "info_type": "pair"},
                                           value=three_halves_prob))
                state.concepts.add(Concept(f"{player_name}_has_small_pair",
                                           {"player": player_name, "info_type": "pair"},
                                           value=math.sqrt(small_pair_prob)))

    @staticmethod
    def _interpret_first_15_provoke(state: GameState, partner_steps: list[int], player_name: str,
                                    value: int) -> None:
        """
        Information is saved inside the GameState object that the function adds concepts and information on to
        TODO put this logic in dependencies
        """
        # Probability for a small pair if the step has skipped 140,
        # if the player has gone directly with +15, they might have a big pair

        big_pair_prob = utils.player_has_set_probability(state, player_name, utils.big_pairs())
        small_pair_prob = utils.player_has_set_probability(state, player_name, utils.small_pairs())
        three_halves_prob = utils.player_has_set_probability(state, player_name, utils.three_halves())

        if value < 140:
            # we can tell for sure, the player has something:
            state.concepts.add(Concept(f"{player_name}_has_halves",
                                       {"player": player_name, "info_type": "halves"}, value=1.))
            # very likely its a big pair
            state.concepts.add(Concept(f"{player_name}_has_big_pair",
                                       {"player": player_name, "info_type": "pair"}, value=math.sqrt(big_pair_prob)))
        elif value == 140:
            # In this case, the information is unclear. We'd assume they wanna just play black, unless this is
            # our own partner, then we might try to hit a black game
            if player_name == state.partner(state.name):
                state.concepts.add(Concept(f"playing_black", {}, value=0.3))
            elif state.concepts.get_by_name(f"getting_played_black"):
                state.concepts.add(Concept(f"getting_played_black", {},
                                           value=math.sqrt(state.concepts.get_by_name(f"getting_played_black").value)))
            else:
                # TODO calculate actual probability of getting played black via dependencies instead of flat values
                state.concepts.add(Concept(f"getting_player_black", {}, value=0.3))
        else:
            # we can tell for sure, the player has something:
            state.concepts.add(Concept(f"{player_name}_has_halves",
                                       {"player": player_name, "info_type": "halves"}, value=1.))
            # first check if we skipped 140
            if state.concepts.get_by_name(f"{state.partner(player_name)}_has_3+_halves"):
                # if the partner indicated haves, it might just be a guessed step for a guessed pair
                state.concepts.add(Concept(f"{player_name}_has_3+_halves",
                                           {"player": player_name, "info_type": "pair"},
                                           value=math.sqrt(three_halves_prob)))
                state.concepts.add(Concept(f"{player_name}_has_small_pair",
                                           {"player": player_name, "info_type": "pair"},
                                           value=small_pair_prob))
            else:
                # otherwise this is likely a small pair, as otherwise the player wouldn't go over 140.
                state.concepts.add(Concept(f"{player_name}_has_3+_halves",
                                           {"player": player_name, "info_type": "pair"},
                                           value=three_halves_prob))
                state.concepts.add(Concept(f"{player_name}_has_small_pair",
                                           {"player": player_name, "info_type": "pair"},
                                           value=math.sqrt(small_pair_prob)))

    def _deduct_provoking_infos(self, state: GameState, player_num: int, value: int) -> None:
        """
        We need infos about what the players are trying to communicate!
        For now we assume they have the same provoking rules as we have :)
        In the Future it might be wise to not rely too much on what the opponents try to communicate
        As this way players could abuse the AI too much by feeding false information
        We will also have to assume more variety when playing with other AI policies together
        Concepts that can be learned:
        f"{player_name}_has_small_pair", info_type: pair
        f"{player_name}_has_big_pair", info_type: pair
        f"{player_name}_has_{color}_pair", info_type: pair
        f"{player_name}_has_3+_halves"
        """
        player_steps = self.players[player_num].provoking_history_steps
        partner_num = self.players[player_num].partner_number
        partner_steps = self.players[partner_num].provoking_history_steps
        player_name = self.players[player_num].name

        # we don't interpret our own steps, the infos from our hand are already in the concepts
        if state.player_num == player_num:
            return

        # interpreting first steps:
        if len(self.players[player_num].provoking_history_steps) == 1:
            # interpreting if the first step was a 5 increase
            match player_steps[0]:
                case 5:
                    self._interpret_first_5_provoke(state, partner_steps, player_name, value)
                case 10:
                    self._interpret_first_10_provoke(state, partner_steps, player_name, value)
                case 15:
                    self._interpret_first_15_provoke(state, partner_steps, player_name, value)
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
        We yield a rough estimate for the game value we could reach with this hand alone
        And we also yield what the opponents party could reach maximum!
        We also give an estimation if they would play a black game on us, depending on our way to get into the
        different suites. If we can't ensure that we could get a trick in a suite if they don't
        TODO put this logic in dependencies
        """
        hand_cards: set[Card] = state.secure_cards[state.name]
        # arbitrary hand score, for our own sake ^^ we will keep track of how good we stand

        # TODO make dependant concepts out of these scores
        self.max_reach_value = 140
        hand_score = 0
        opp_estimate_max = 420

        # first we need to check for aces, add arbitrary points to our score based on that
        aces = [card for card in hand_cards if card.value == Value.Ass]
        if aces:
            hand_score += 5 * math.pow(2, len(aces) - 1)
            opp_estimate_max -= 11 * len(aces)

        # Tens are impactful, as usually if you have another card with them, they can stop trump games
        # However they can also ruin your chances if they are single on your hand!
        # They also are a lot of points and likely land in your tricks if you end up taking the game!
        hand_cards_by_suite = {}
        tens = [card for card in hand_cards if card.value == Value.Zehn]
        for color in Color:
            hand_cards_by_suite[color] = [card for card in hand_cards if card.color == color]
            if Card(color, Value.Zehn) in tens:
                if len(hand_cards_by_suite[color]) > 1:
                    hand_score += 10
                else:
                    hand_score -= 10

        # Let's calculate which pairs we or the opponents might have
        pair_value = 0
        for color in Color:
            if utils.contains_col_pair(list(hand_cards), color):
                state.concepts.add(Concept(f"{state.name}_has_{str(color)}_pair",
                                           {"player": state.name, "info_type": "pair", "color": color},
                                           value=1.))
                hand_score += color.points
                # blank pairs are not that good, additional trump however is even better!:
                if len(hand_cards_by_suite[color]) == 2:
                    hand_score += color.points * 3 / 4
                elif len(hand_cards_by_suite[color]) == 3:
                    hand_score += color.points
                else:
                    hand_score += color.points * 5 / 4
                # trump aces and tens are all the more valuable!
                if Card(color, Value.Ass) in aces:
                    hand_score += 10
                    if Card(color, Value.Zehn) in tens:
                        hand_score += 10
                else:
                    if Card(color, Value.Zehn) in tens:
                        hand_score += 5

                self.max_reach_value += color.points
                pair_value += color.points
                opp_estimate_max -= color.points

            elif utils.contains_col_half(list(hand_cards), color):
                # add some arbitrary amount for the colors for evaluation
                hand_score += color.points / 5
                opp_estimate_max -= color.points
            else:
                # TODO estimate if there is anything we can deduct from having nothing?!
                pass

        # Now let's calculate roughly the value of our standing cards
        standing_cards = state.standing_cards()
        hand_score += sum([card.value.points for card in standing_cards])

        # we fear getting played black under different circumstances
        black_chance = (1 - hand_score / opp_estimate_max) / (len(aces) + 1)
        if len(aces) == 4:
            black_chance = 0

        # TODO calculate pseudo standing cards like a Koenig and a Zehn together where one will likely stand

        # TODO make these all depending concepts based on more basic values!
        state.concepts.add(Concept(f"getting_played_black", {}, value=black_chance))
        state.concepts.add(Concept(f"my_hand_value", {}, value=hand_score))
        self.max_opponent_reach_value = opp_estimate_max

    def _calculate_possible_card_probabilities(self, state: GameState):
        """
        Based on combinatorics (binomials mainly for choice) we calculate how like it is for players
        to have a specific card on their hand, based on the information we got in our class variables like the state
        values for possible cards each player has and which cards we know securely (for those the probability is 1)
        """
        # TODO

    def _estimate_provoking_max(self, state) -> int:
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

    def _guess_plan(self, state):
        """
        This method is only for the playing teams secondary player, who tries to guess the plan of the planning player!
        This way he can react with the information given at any point in the game to carry out the plan.
        This is based on the information given and the concepts formed, swapping trump, taking tricks,
        and not giving any opportunity for the opponent to intervene with the plan.
        """
        # TODO
        pass

    def select_action(self, state: GameState, legal_actions: list[Action]) -> Action:
        """
        select an action based on the current state and legal actions
        TODO: Use the plan that was formed to carry out actions and estimate the strongest moves of the opponent
        TODO: If the likelihood of a move failing is too high, try to rethink the game and carry on with a new plan
        """
        # currently a random action is played
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
        if self._calculate_concept_probabilities(state, 'getting_played_black'):
            if max_value < 140:
                return 140
            elif max_value < 180:
                return 180
            elif max_value < 200:
                return 200
        elif cur_value < estimated_max:
            # Check if we have a very good hand
            if self._calculate_concept_probabilities(state, 'hand_card_value'):
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
