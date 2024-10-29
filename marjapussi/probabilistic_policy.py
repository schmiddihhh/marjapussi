import math
from enum import Enum
from marjapussi.policy import Policy
from marjapussi.gamestate import GameState
from marjapussi.action import Action
from marjapussi.card import Card, Color, Value, Deck
from marjapussi.gamerules import GameRules
from marjapussi.policy_player import PolicyPlayer
from marjapussi.concept import Concept
from itertools import combinations
import marjapussi.utils as utils
import numpy as np


class ProvokingInfos(Enum):
    Ass = "Ass"
    BigPair = "BigPair"
    SmallPair = "SmallPair"
    Halves3 = "Halves3"
    Halves2 = "Halves2"


class ProbabilisticPolicy(Policy):
    def __init__(self) -> None:
        super().__init__()
        # initialize some values that we always need and update by observing actions
        self.players: list[PolicyPlayer] = []

        self.game_rules = GameRules()
        self.prov_base = 115
        self.to_be_communicated = []
        self.communicated = []

        self.max_reach_value = 0
        self.max_opponent_reach_value = self.game_rules.max_game_value

        self.our_score = 0
        self.their_score = 0
        self.round = 1

    def game_start(self, state: GameState, scores: list[int] = None, total_rounds: int = 8):
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
        self._initialize_concepts(state)
        self._calculate_possible_card_probabilities(state)
        self._assess_own_hand(state)
        self._to_communicate(state)

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
                                           {"player": player_name, "source": "provoking"}, value=0.))
                state.concepts.add(Concept(f"{player_name}_has_3+_halves",
                                           {"player": player_name, "source": "provoking"}, value=0.))
                state.concepts.add(Concept(f"{player_name}_has_small_pair",
                                           {"player": player_name, "source": "provoking"}, value=0.))
                state.concepts.add(Concept(f"{player_name}_has_big_pair",
                                           {"player": player_name, "source": "provoking"}, value=0.))
            else:
                # this means less, but still bad cards!
                state.concepts.add(Concept(f"{player_name}_has_ace",
                                           {"player": player_name, "source": "provoking"}, value=0.))
                state.concepts.add(Concept(f"{player_name}_has_3+_halves",
                                           {"player": player_name, "source": "provoking"}, value=0.))
                state.concepts.add(Concept(f"{player_name}_has_small_pair",
                                           {"player": player_name, "source": "provoking"}, value=0.))
                state.concepts.add(Concept(f"{player_name}_has_big_pair",
                                           {"player": player_name, "source": "provoking"}, value=0.))
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
                                               {"player": player_name, "source": "provoking"}, value=1.))
                    # TODO add probabilities to the Ace cards that we don't know about yet for that player
                else:
                    state.concepts.add(Concept(f"{player_name}_is_faking_ace",
                                               {"player": player_name, "source": "provoking"}, value=1.))
            elif partner_steps and partner_steps[0] == 5:
                # the partner already announced an ace, so we assume it must be something else
                # right now we ignore the small likelihood that he has just another ace
                state.concepts.add(Concept(f"{player_name}_has_halves",
                                           {"player": player_name, "source": "provoking"}, value=1.))
        else:
            # value 140 might mean anything, especially if its just a 5, but we could add some probability
            # if the partner indicated a pair, it might just be the ace
            # TODO add case for values above 140, for now its all the same
            if partner_steps and partner_steps[0] == 10 or partner_steps[0] == 15 or partner_steps[0] == 20:
                if any(card.value == Value.Ass for card in state.possible_cards.get(player_name, set())):
                    state.concepts.add(Concept(f"{player_name}_has_ace",
                                               {"player": player_name, "source": "provoking"}, value=1.))
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
        small_pair_prob = state.player_has_set_probability(player_name, utils.small_pairs())
        three_halves_prob = state.player_has_set_probability(player_name, utils.three_halves())

        if value < 140:
            # we can tell for sure, the player has something:
            state.concepts.add(Concept(f"{player_name}_has_halves",
                                       {"player": player_name, "source": "provoking"}, value=1.))
            if (partner_steps and partner_steps[0] != 5) or not partner_steps:
                # we are dealing somewhat likely with no ace
                state.concepts.add(Concept(f"{player_name}_has_ace",
                                           {"player": player_name, "source": "provoking"}, value=0.1))
            state.concepts.add(Concept(f"{player_name}_has_small_pair",
                                       {"player": player_name, "source": "provoking"},
                                       value=utils.is_probable(small_pair_prob)))
            state.concepts.add(Concept(f"{player_name}_has_3+_halves",
                                       {"player": player_name, "source": "provoking"},
                                       value=utils.is_probable(three_halves_prob)))
        elif value == 140:
            # In this case, the information is unclear. We'd assume they wanna just play black, unless this is
            # our own partner, then we might try to hit a black game
            if player_name == state.partner(state.name):
                state.concepts.add(Concept(f"playing_black", {}, value=0.3))
            elif state.concepts.get_by_name(f"getting_played_black"):
                state.concepts.add(Concept(f"getting_played_black", {},
                                           value=utils.is_probable(
                                               state.concepts.get_by_name(f"getting_played_black").value)))
            else:
                # TODO calculate actual probability of getting played black via dependencies instead of flat values
                state.concepts.add(Concept(f"getting_player_black", {}, value=0.3))
        else:
            # we can tell for sure, the player has something:
            state.concepts.add(Concept(f"{player_name}_has_halves",
                                       {"player": player_name, "source": "provoking"}, value=1.))
            # first check if we skipped 140
            if state.concepts.get_by_name(f"{state.partner(player_name)}_has_3+_halves"):
                # if the partner indicated haves, it might just be a guessed step for a guessed pair
                state.concepts.add(Concept(f"{player_name}_has_3+_halves",
                                           {"player": player_name, "source": "provoking"},
                                           value=utils.is_probable(three_halves_prob)))
                state.concepts.add(Concept(f"{player_name}_has_small_pair",
                                           {"player": player_name, "source": "provoking"},
                                           value=small_pair_prob))
            else:
                # otherwise this is likely a small pair, as otherwise the player wouldn't go over 140.
                state.concepts.add(Concept(f"{player_name}_has_3+_halves",
                                           {"player": player_name, "source": "provoking"},
                                           value=three_halves_prob))
                state.concepts.add(Concept(f"{player_name}_has_small_pair",
                                           {"player": player_name, "source": "provoking"},
                                           value=utils.is_probable(small_pair_prob)))

    @staticmethod
    def _interpret_first_15_provoke(state: GameState, partner_steps: list[int], player_name: str,
                                    value: int) -> None:
        """
        Information is saved inside the GameState object that the function adds concepts and information on to
        TODO put this logic in dependencies
        """
        # Probability for a small pair if the step has skipped 140,
        # if the player has gone directly with +15, they might have a big pair

        big_pair_prob = state.player_has_set_probability(player_name, utils.big_pairs())
        small_pair_prob = state.player_has_set_probability(player_name, utils.small_pairs())
        three_halves_prob = state.player_has_set_probability(player_name, utils.three_halves())

        if value < 140:
            if (partner_steps and partner_steps[0] != 5) or not partner_steps:
                # we are dealing somewhat likely with no ace
                state.concepts.add(Concept(f"{player_name}_has_ace",
                                           {"player": player_name, "source": "provoking"}, value=0.2))
            # we can tell for sure, the player has something:
            state.concepts.add(Concept(f"{player_name}_has_halves",
                                       {"player": player_name, "source": "provoking"}, value=1.))
            # very likely it's a big pair
            state.concepts.add(Concept(f"{player_name}_has_big_pair",
                                       {"player": player_name, "source": "provoking"},
                                       value=utils.is_probable(big_pair_prob)))
        elif value == 140:
            # In this case, the information is unclear. We'd assume they wanna just play black, unless this is
            # our own partner, then we might try to hit a black game
            if player_name == state.partner(state.name):
                state.concepts.add(Concept(f"playing_black", {}, value=0.4))
            elif state.concepts.get_by_name(f"getting_played_black"):
                state.concepts.add(Concept(f"getting_played_black", {},
                                           value=utils.is_probable(
                                               state.concepts.get_by_name(f"getting_played_black").value)))
            else:
                # TODO calculate actual probability of getting played black via dependencies instead of flat values
                state.concepts.add(Concept(f"getting_player_black", {}, value=0.4))
        else:
            # we can tell for sure, the player has something:
            state.concepts.add(Concept(f"{player_name}_has_halves",
                                       {"player": player_name, "source": "provoking"}, value=1.))
            # first check if we skipped 140
            if value == 145 or value == 150:
                # this might ust be a small pair after all
                if state.concepts.get_by_name(f"{state.partner(player_name)}_has_3+_halves"):
                    # if the partner indicated haves, it might just be a guessed step for a guessed pair
                    state.concepts.add(Concept(f"{player_name}_has_3+_halves",
                                               {"player": player_name, "source": "provoking"},
                                               value=utils.is_probable(three_halves_prob)))
                    state.concepts.add(Concept(f"{player_name}_has_small_pair",
                                               {"player": player_name, "source": "provoking"},
                                               value=small_pair_prob))
                else:
                    # otherwise this is likely a small pair, as otherwise the player wouldn't go over 140.
                    state.concepts.add(Concept(f"{player_name}_has_3+_halves",
                                               {"player": player_name, "source": "provoking"},
                                               value=three_halves_prob))
                    state.concepts.add(Concept(f"{player_name}_has_small_pair",
                                               {"player": player_name, "source": "provoking"},
                                               value=utils.is_probable(small_pair_prob)))
            else:
                # this is just straight up a big pair!
                if big_pair_prob > 0:
                    state.concepts.add(Concept(f"{player_name}_has_big_pair",
                                               {"player": player_name, "source": "provoking"},
                                               value=utils.is_probable(big_pair_prob)))
                else:
                    # TODO add something for enemy trying to snipe away our black in certain cases
                    pass

    @staticmethod
    def _interpret_first_20_provoke(state: GameState, partner_steps: list[int], player_name: str,
                                    value: int) -> None:
        """
        Information is saved inside the GameState object that the function adds concepts and information on to
        TODO put this logic in dependencies and add on to it
        """
        # We'll just interpret anything that is a 20 step and not straight 140 as a big pair.

        big_pair_prob = state.player_has_set_probability(player_name, utils.big_pairs())

        if value == 140:
            # In this case, the information is unclear. We'd assume they wanna just play black, unless this is
            # our own partner, then we might try to hit a black game
            if player_name == state.partner(state.name):
                state.concepts.add(Concept(f"playing_black", {}, value=0.5))
            elif state.concepts.get_by_name(f"getting_played_black"):
                state.concepts.add(Concept(f"getting_played_black", {},
                                           value=utils.is_probable(
                                               state.concepts.get_by_name(f"getting_played_black").value)))
            else:
                # TODO calculate actual probability of getting played black via dependencies instead of flat values
                state.concepts.add(Concept(f"getting_player_black", {}, value=0.5))
            # we can tell for sure, the player has something:
            state.concepts.add(Concept(f"{player_name}_has_halves",
                                       {"player": player_name, "source": "provoking"}, value=1.))
            # very likely it's a big pair
            state.concepts.add(Concept(f"{player_name}_has_big_pair",
                                       {"player": player_name, "source": "provoking"},
                                       value=utils.is_probable(big_pair_prob)))
        else:
            if (partner_steps and partner_steps[0] != 5) or not partner_steps:
                # we are dealing somewhat likely with no ace
                state.concepts.add(Concept(f"{player_name}_has_ace",
                                           {"player": player_name, "source": "provoking"}, value=0.1))
            # we can tell for sure, the player has something:
            state.concepts.add(Concept(f"{player_name}_has_halves",
                                       {"player": player_name, "source": "provoking"}, value=1.))
            # this is just straight up a big pair!
            if big_pair_prob > 0:
                state.concepts.add(Concept(f"{player_name}_has_big_pair",
                                           {"player": player_name, "source": "provoking"},
                                           value=utils.is_probable(big_pair_prob)))
            else:
                # TODO add something for enemy trying to snipe away our black in certain cases
                pass

    def _deduct_provoking_infos(self, state: GameState, player_num: int, value: int) -> None:
        """
        We need infos about what the players are trying to communicate!
        For now, we assume they have the same provoking rules as we have :)
        In the Future it might be wise to not rely too much on what the opponents try to communicate
        As this way players could abuse the AI too much by feeding false information
        We will also have to assume more variety when playing with other AI policies together
        Concepts that can be learned:
        f"{player_name}_has_small_pair"
        f"{player_name}_has_big_pair"
        f"{player_name}_has_{color}_pair"
        f"{player_name}_has_3+_halves"
        """
        player_steps = state.provoking_steps(player_num)
        player_name = state.all_players[player_num]
        partner_num = state.partner_num(player_num)
        partner_steps = state.provoking_steps(partner_num)

        # we don't interpret our own steps, the infos from our hand are already in the concepts
        if state.player_num == player_num:
            return

        # interpreting first steps:
        if len(state.provoking_steps(player_num)) == 1:
            # interpreting if the first step was a 5 increase
            match player_steps[0]:
                case 5:
                    self._interpret_first_5_provoke(state, partner_steps, player_name, value)
                case 10:
                    self._interpret_first_10_provoke(state, partner_steps, player_name, value)
                case 15:
                    self._interpret_first_15_provoke(state, partner_steps, player_name, value)
                case 20:
                    self._interpret_first_20_provoke(state, partner_steps, player_name, value)
                case 0:
                    self._interpret_first_gone_provoke(state, partner_steps, player_name, value)
                case _:
                    pass

        # TODO interpreting consecutive steps:
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
        hand_cards: set[Card] = state.hand_cards
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
                                           {"player": state.name, "source": "assessment", "color": color},
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
                state.concepts.add(Concept(f"{state.name}_has_{str(color)}_half",
                                           {"player": state.name, "source": "assessment", "color": color},
                                           value=1.))
            else:
                # TODO estimate if there is anything we can deduct from having nothing?! (Risking enemy trump)
                pass

        # Now let's calculate roughly the value of our standing cards
        standing_cards = state.standing_cards()
        hand_score += sum([card.value.points for card in standing_cards])

        # we fear getting played black under different circumstances
        black_chance = (1 - hand_score / opp_estimate_max) / (len(aces) + 1)
        if len(aces) == 4:
            black_chance = 0

        # TODO calculate pseudo standing cards like a Koenig and a Zehn together where one will likely stand

        # TODO we could make getting played black a possibility mainly based on possibly standing cards of opponents

        # TODO make these all depending concepts based on more basic values!
        state.concepts.add(Concept(f"getting_played_black", {}, value=black_chance))
        state.concepts.add(Concept(f"good_hand_cards", {}, value=min(hand_score / 210, 1)))
        self.max_opponent_reach_value = opp_estimate_max

    def _calculate_possible_card_probabilities(self, state: GameState):
        """
        Based on combinatorics (binomials mainly for choice) we calculate how like it is for players
        to have a specific card on their hand, based on the information we got in our class variables like the state
        values for possible cards each player has and which cards we know securely (for those the probability is 1)
        """
        # TODO

    def _estimate_game_value(self, state) -> tuple[int, int]:
        """
        We can estimate that the maximum we can reach is somewhere below the combination of
        - standing cards we have as a team
        - pairs each of us has
        - pairs we can combine
        We can estimate the maximum as well as the reasonable value of the game that we could make as points
        """
        estimated_value = 0
        estimated_max = 140
        unknown_pairs = utils.pairs()
        team_cards = state.hand_cards

        # consider all pair points we can get
        # my pairs
        if utils.gruen_pair() in state.hand_cards:
            estimated_value += 40
            unknown_pairs.remove(utils.gruen_pair())
        if utils.eichel_pair() in state.hand_cards:
            estimated_value += 60
            unknown_pairs.remove(utils.eichel_pair())
        if utils.schell_pair() in state.hand_cards:
            estimated_value += 80
            unknown_pairs.remove(utils.schell_pair())
        if utils.rot_pair() in state.hand_cards:
            estimated_value += 100
            unknown_pairs.remove(utils.rot_pair())
        estimated_max += estimated_value

        # partners pairs
        # TODO add the logic to know which pairs we have exactly
        # TODO put this logic in dependencies of concepts
        if (state.concepts.get_by_name(f"{state.partner()}_has_big_pair") and
                state.concepts.get_by_name(f"{state.partner()}_has_big_pair").value > 0.8):
            if (Card(Color.Schell, Value.Ober) in state.hand_cards or
                    Card(Color.Schell, Value.Koenig) in state.hand_cards):
                estimated_value += 100
                unknown_pairs.remove(utils.rot_pair())
                team_cards |= utils.rot_pair()
            else:
                estimated_value += 80
                unknown_pairs.remove(utils.schell_pair())
                if (Card(Color.Rot, Value.Ober) in state.hand_cards or
                        Card(Color.Rot, Value.Koenig) in state.hand_cards):
                    team_cards |= utils.schell_pair()
        if (state.concepts.get_by_name(f"{state.partner()}_has_small_pair") and
                state.concepts.get_by_name(f"{state.partner()}_has_small_pair").value > 0.8):
            if (Card(Color.Gruen, Value.Ober) in state.hand_cards or
                    Card(Color.Gruen, Value.Koenig) in state.hand_cards):
                estimated_value += 60
                unknown_pairs.remove(utils.eichel_pair())
                team_cards |= utils.eichel_pair()
            else:
                estimated_value += 40
                unknown_pairs.remove(utils.gruen_pair())
                if (Card(Color.Eichel, Value.Ober) in state.hand_cards or
                        Card(Color.Eichel, Value.Koenig) in state.hand_cards):
                    team_cards |= utils.rot_pair()

        # our pairs
        if (state.concepts.get_by_name(f"{state.partner()}_has_3+_halves") and
                state.concepts.get_by_name(f"{state.partner()}_has_3+_halves").value > 0.8):
            if len(unknown_pairs) == 4:
                halves = utils.pair_cards()
                hand_halves = [card for card in halves if card in state.hand_cards]
                estimated_value += sum([card.color.points for card in utils.smallest_x(set(hand_halves),
                                                                                       len(hand_halves) - 1)])
            elif len(unknown_pairs) <= 3:
                unknown_pair_cards = []
                for pair in unknown_pairs:
                    unknown_pair_cards += [card for card in pair]
                hand_halves = [card for card in unknown_pair_cards if card in state.hand_cards]
                estimated_value += sum([card.color.points for card in utils.smallest_x(set(hand_halves),
                                                                                       len(hand_halves))])

        # estimate the standing cards we could have as a team
        min_standing = 13
        min_standing_cards = {}
        if (state.concepts.get_by_name(f"{state.partner()}_has_ace")):
            for ace in utils.ace_cards():
                if not(ace in state.hand_cards):
                    team_cards_ace = team_cards | ace
                    standing = utils.standing_cards(set(Deck().cards), team_cards_ace)
                    min_standing = min(len(standing), min_standing)

        standing_points = 120
        if min_standing >= 7:
            standing_points = 140
        else:
            standing_points = sum([card.value.points for card in standing])
        # estimate obstacles by enemy team
        for pair in unknown_pairs:
            pass
            # need to check if we can destroy those pairs if we need to
            # TODO

        # estimate last trick security
        # TODO

        return estimated_value, estimated_max

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
                    evaluation = self.evaluate_action(state, action)
                    action_evaluations.append(evaluation)
                    # normalize the probabilities so they sum to 1
                normal_eval = [p / sum(action_evaluations) for p in action_evaluations]
                return normal_eval

    def _update_to_be_communicated(self, state: GameState, cur_value: int):
        """
        Updates things that we shouldn't communicate anymore, because we missed the chance!
        """
        hand_cards: set[Card] = state.hand_cards
        partner = state.partner()

        # remove ace to be communicated when:
        # - our partner told us about his ace
        # - we reached a value too high to make a provoke of an ace alone viable without proper support
        # - we provoked our first step already, in which case we also don't tell abt halves anymore
        if state.concepts.get_by_name(f"{partner}_has_ace"):
            self.to_be_communicated.remove(ProvokingInfos.Ass)

        elif cur_value >= 140 and (not (state.concepts.get_by_name(f"{partner}_has_big_pair").value > 0.8  # CONCEPT
                                        or (state.concepts.get_by_name(f"{partner}_has_small_pair").value >
                                            state.concepts.get_by_name(f"{partner}_has_3+_halves").value)
                                        or utils.contains_pair(hand_cards))):
            self.to_be_communicated.remove(ProvokingInfos.Ass)
            self.communicated.append(ProvokingInfos.Ass)

        elif len(state.provoking_history) >= 4:
            self.to_be_communicated.remove(ProvokingInfos.Ass)
            self.to_be_communicated.remove(ProvokingInfos.Halves2)
            self.to_be_communicated.remove(ProvokingInfos.Halves3)

        # TODO also remove stuff about pairs we don't need to communicate anymore, is there any?

    def _to_communicate(self, state: GameState) -> None:
        """
        generates a list of things that need to be communicated from my hand
        This could include, based on the game state
        - I have an Ace
        - I have a big pair
        - I have a small pair
        - I have 3+ halves
        """
        hand_cards: set[Card] = state.hand_cards
        self.to_be_communicated = []

        # need to call out my ace:
        # first provoke, no ace called by partner, not over 140 unless we are somewhat sure that we have a pair
        if utils.contains_ace(hand_cards):
            self.to_be_communicated.append(ProvokingInfos.Ass)

        for pair in [pair for pair in utils.big_pairs() if pair.issubset(hand_cards)]:
            self.to_be_communicated.append(ProvokingInfos.BigPair)

        for pair in [pair for pair in utils.small_pairs() if pair.issubset(hand_cards)]:
            self.to_be_communicated.append(ProvokingInfos.SmallPair)

        if any([halves for halves in utils.three_halves() if halves.issubset(hand_cards)]):
            self.to_be_communicated.append(ProvokingInfos.Halves3)
        else:
            self.to_be_communicated.append(ProvokingInfos.Halves2)

    @staticmethod
    def _standard_provoking(info: ProvokingInfos, cur_value) -> int:
        """calculates next value based on standard provoking rules"""
        match info:
            case ProvokingInfos.Ass | ProvokingInfos.Halves2:
                cur_value = cur_value + 5
            case ProvokingInfos.SmallPair | ProvokingInfos.Halves3:
                cur_value = cur_value + 10
                if cur_value == 140:
                    cur_value = 145
            case ProvokingInfos.BigPair:
                cur_value = cur_value + 15
                if cur_value == 140:
                    cur_value = 145
        return cur_value

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
        - provoking 0 means folding, which we do by default if we don't want to communicate nor take the game
        """
        # we want an optimistic estimate of what we could reach
        estimated_value, estimated_max = self._estimate_game_value(state)

        next_value = cur_value
        regular_provoking_value = None
        communication = None
        if len(self.to_be_communicated) > 0:
            communication = self.to_be_communicated.pop(0)
            next_value = self._standard_provoking(communication, cur_value)
            regular_provoking_value = next_value

        # Check if we are at risk of getting skunked
        elif next_value == cur_value and state.concepts.get_by_name("getting_played_black").evaluate() > 0.7:  # CONCEPT
            if cur_value < 140:
                next_value = 140
            elif cur_value < 180:
                next_value = 180
            elif cur_value < 200:
                next_value = 200
            elif cur_value < 220:
                next_value = 220
            elif cur_value < 240:
                next_value = 240
            elif cur_value < estimated_max:
                next_value = estimated_max
            else:
                next_value = cur_value

        # Do we want to take the game? We should if we can reach and can't properly pass cards
        elif estimated_value > cur_value:
            if state.provoking_steps(state.partner_num()) and state.provoking_steps(state.partner_num())[-1] == 0:
                next_value = cur_value + 5
            elif self.eval_passing(state, self.passing_best(state)) < 5:
                next_value = cur_value + 5

        # If none of the above conditions are met, provoke with the current max_value
        prov_value = max(cur_value, min(next_value, estimated_max))

        # update communications
        if regular_provoking_value and regular_provoking_value == prov_value:
            self.communicated.append(communication)

        return prov_value

    def eval_passing(self, state: GameState, passed_cards: set[Card]) -> float:
        """
        Evaluating passed cards based on the GameState, before passing them.
        Factors that play a role:
        - getting rid of 2 colors
        - passing necessary cards (not knowing they got an ace? Pass it!)
        - ambiguous information
        -> low card in a non blank color
        -> giving halves of pairs signaled (splitting pairs)
        ->
        - getting rid of blank 10s or pairs
        - not passing stuff you already signaled
        - passing cards to clear up information (didn't call the ace? Pass it!)
        - passing valuable cards if possible
        """
        total = 0
        hand_without_passed = [card for card in state.hand_cards if not card in passed_cards]
        hand_wop_sorted = [[card for card in hand_without_passed if card.color == color] for color in Color]
        color_amounts = [len(cards) for cards in hand_wop_sorted]

        # check being blank in two colors
        if sum([min(amount, 1) for amount in color_amounts]) <= 2:
            total += 5

        # check passing necessary cards
        # check fo ace
        # TODO check for specific pair
        # TODO make sure this value is most definitely set if used for actual passing, need to know the ace probability
        if (state.concepts.get_by_name(f"{state.partner()}_has_ace") and
                state.concepts.get_by_name(f"{state.partner()}_has_ace").value < 0.5 and
                utils.contains_ace(passed_cards)):
            total += 8

        # check ambiguities
        passed_sorted = [[card for card in passed_cards if card.color == color] for color in Color]
        for i, amount in enumerate(color_amounts):
            # having cards but still passing a low card of that color
            if amount > 0 and utils.contains_low_card(set(passed_sorted[i])):
                total -= 3
            if amount == 0 and utils.contains_low_card(set(hand_wop_sorted[i])):
                total -= 2

        # check blank high cards
        total -= 3 * len([cards for cards in hand_wop_sorted if len(cards) == 1 and cards[0].value > Value.Unter])

        # check given information
        if ProvokingInfos.Halves3 in self.communicated or ProvokingInfos.Halves2 in self.communicated:
            if len([card for card in passed_cards if card.value == Value.Koenig or card.value == Value.Ober]) >= 2:
                total += 1

        # keep pairs that are communicated, pass pairs that aren't, depending on value
        # TODO care for case, when two small or two big pairs were communicated
        if ProvokingInfos.SmallPair in self.communicated:
            if utils.contains_col_pair(list(hand_without_passed), Color.Gruen) and len(hand_wop_sorted[1]) == 0:
                total += 2
            if utils.contains_col_pair(list(hand_without_passed), Color.Eichel) and len(hand_wop_sorted[0]) == 0:
                total += 2
        else:
            if (utils.contains_col_pair(list(state.hand_cards), Color.Gruen) and
                    not utils.contains_col_pair(list(passed_cards), Color.Gruen)):
                total -= 1
            if (utils.contains_col_pair(list(state.hand_cards), Color.Eichel) and
                    not utils.contains_col_pair(list(passed_cards), Color.Eichel)):
                total -= 2

        if ProvokingInfos.BigPair in self.communicated:
            if utils.contains_col_pair(list(hand_without_passed), Color.Schell) and len(hand_wop_sorted[3]) == 0:
                total += 2
            if utils.contains_col_pair(list(hand_without_passed), Color.Rot) and len(hand_wop_sorted[2]) == 0:
                total += 2
        else:
            if (utils.contains_col_pair(list(state.hand_cards), Color.Schell) and
                    not utils.contains_col_pair(list(passed_cards), Color.Schell)):
                total -= 3
            if (utils.contains_col_pair(list(state.hand_cards), Color.Rot) and
                    not utils.contains_col_pair(list(passed_cards), Color.Rot)):
                total -= 4

        # we would like to plan ourselves if possible, if we have 5 or more halves!
        hand_halves = set([card for card in state.hand_cards if card in utils.pair_cards()])
        if len(hand_halves) > 4:
            total -= 3
        if len(hand_halves) > 5:
            total -= 3
        if len(hand_halves) > 6:
            total -= 3
        if len(hand_halves) > 7:
            total -= 3

        # check overall value of hand cards given
        for card in passed_cards:
            if card.value > Value.Unter:
                total += 0.5

        for card in hand_without_passed:
            if card.value > Value.Unter:
                total -= 1

        # try not to pass green if unnecessary
        for card in passed_cards:
            if card.color == Color.Gruen: total -= 0.5

        return total

    def passing_best(self, state: GameState) -> set[Card]:
        """
        calculate the best passing cards, based on the evaluations of all possible card combinations
        for the 9 original hand cards it is (9 over 4) = 126 combinations to test
        TODO add methods to reduce the combinations drastically beforehand
        """
        best_eval = -1000
        best_set = None
        for subset in combinations(state.hand_cards, 4):
            eval_s = self.eval_passing(subset)
            if best_eval < eval_s:
                best_eval = eval_s
                best_set = subset
        return best_set

    def evaluate_action(self, state: GameState, action: Action):
        # evaluate the probable success of an action, this is where the knowledge of the game should be used
        # for now, it's a placeholder and always returns 1
        return 1

    def _initialize_concepts(self, state: GameState):
        """
        Add every concept that we could need for decisions in our probabilistic policy
        """
        # First add basic concepts that just record actions of players
