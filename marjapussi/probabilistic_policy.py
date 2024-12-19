import math
from enum import Enum
from marjapussi.policy import Policy
from marjapussi.gamestate import GameState
from marjapussi.action import Action, Talk
from marjapussi.card import Card, Color, Value, Deck
from marjapussi.gamerules import GameRules
from marjapussi.policy_player import PolicyPlayer
from marjapussi.concept import Concept
from itertools import combinations
import marjapussi.utils as utils
import numpy as np
import random as rnd


class ProvokingInfos(Enum):
    Ass = "Ass"
    BigPair = "BigPair"
    SmallPair = "SmallPair"
    Halves3 = "Halves3"
    Halves2 = "Halves2"


class JonasPolicy(Policy):
    def __init__(self) -> None:
        super().__init__()
        self.game_rules = GameRules()

    def _assess_own_hand(self, state: GameState):
        """
        Analyzes the own hand and adds corresponding concepts to the concept store.
        """

        hand_cards: set[Card] = state.hand_cards
        
        # first check for aces
        aces = [card for card in hand_cards if card.value == Value.Ass]
        if aces:
            # add the secure knowledge about the ace to the concept store
            state.concepts.add(Concept(f"{state.name}_has_ace", {}, value=1.0))
        state.aces_on_hand = aces

        # next, check for pairs
        big_pairs = state.big_pairs_on_hand()
        if big_pairs:
            state.concepts.add(Concept(f"{state.name}_has_big_pair", {}, value=1.0))
        small_pairs = state.small_pairs_on_hand()
        if small_pairs:
            state.concepts.add(Concept(f"{state.name}_has_small_pair", {}, value=1.0))
        
        # check how many standalone halves we have
        standalone_halves = state.standalone_halves_on_hand()
        assert len(standalone_halves) <= 4, "You can't have more than 4 standalone halves"
        if len(standalone_halves) >= 3:
            # we have 3+ halves
            state.concepts.add(Concept(f"{state.name}_has_3+_halves", {}, value=1.0))
        elif len(standalone_halves) == 2:
            # we have 2 halves
            state.concepts.add(Concept(f"{state.name}_has_2_halves", {}, value=1.0))

        # determine what information we want to share in the provoking phase
        if state.aces_on_hand:
            state.to_communicate.append(ProvokingInfos.Ass)
        for _ in big_pairs:
            state.to_communicate.append(ProvokingInfos.BigPair)
        for _ in small_pairs:
            state.to_communicate.append(ProvokingInfos.SmallPair)
        if len(standalone_halves) >= 3:
            state.to_communicate.append(ProvokingInfos.Halves3)
        elif len(standalone_halves) == 2:
            state.to_communicate.append(ProvokingInfos.Halves2)

    def _provoke(self, state: GameState, cur_value: int) -> int:
        """
        Chooses a provoking step based on a very strict provoking logic.
        """
        # get some info from the gamestate
        concepts = state.concepts
        to_communicate = state.to_communicate   # this is initialized in _assess_own_hand (called in game_start)
        next_info = None

        # find the info we want to communicate
        while not next_info:
            if not to_communicate:
                # nothing more to communicate
                print(state.name, ": folding since there is nothing to communicate")
                return 0
            # get the info to be communicated
            next_info = to_communicate.pop(0)
            # if the info is an ace and the partner already called one, skip it and try to get the next info
            if next_info == ProvokingInfos.Ass and concepts.get_by_name(f"{state.partner()}_has_ace"):
                next_info = None
            # if the info is 2 halves and no ace was called in the party, skip it
            elif next_info == ProvokingInfos.Halves2 and not (concepts.get_by_name(f"{state.partner()}_has_ace") or concepts.get_by_name(f"{state.name}_has_ace")):
                next_info = None

        # get the step corresponding to the info
        step = self._standard_provoking_steps(next_info)
        next_value = cur_value + step
        if cur_value < 140 and next_value >= 140:
            next_value += 5
        
        # fold if you get above the game limit
        if next_value > state.game_rules.max_game_value:
            print(state.name, f": folding since I can't exceed the game limit, remaining steps were", [next_info] + to_communicate)
            return 0

        # check if we can do the step safely
        if next_value < 140:
            # we assume that the step is safe and just provoke it
            print(state.name, ": provoking", next_value, "for", next_info, "while staying under 140")
            return next_value
        else:
            # if the value is larger than 140, you need a pair to safely provoke it
            if state.have_secure_pair():
                # for now, we will just do our provoking step, no matter if our pair is big enough
                print(state.name, ": provoking", next_value, "for", next_info, "while being sure that we have a pair;\nconcepts:", state.concepts)
                return next_value
            else:
                # we either don't have a pair or don't know about it
                # to be save, we will fold
                print(state.name, ": folding since I am not sure if we have a pair;\nconcepts:", state.concepts)
                return 0
            
    def _standard_provoking_steps(self, info: ProvokingInfos) -> int:
        """
        Calculates the provoking value corresponding to the information that should be shared.
        """
        match info:
            case ProvokingInfos.Ass | ProvokingInfos.Halves2:
                return 5
            case ProvokingInfos.SmallPair | ProvokingInfos.Halves3:
                return 10
            case ProvokingInfos.BigPair:
                return 15
            case _:
                # should not happen
                raise RuntimeError("Invalid ProvokingInfo")
            
    def _deduct_provoking_infos(self, state: GameState, player_num: int, value: int) -> None:
        """
        We need infos about what the players are trying to communicate!
        For now, we assume they have the same provoking rules as we have :)
        In the Future it might be wise to not rely too much on what the opponents try to communicate
        As this way players could abuse the AI too much by feeding false information
        We will also have to assume more variety when playing with other AI policies together
        Concepts that can be learned:
        f"{player_name}_has_ace"
        f"{player_name}_has_small_pair"
        f"{player_name}_has_big_pair"
        f"{player_name}_has_{color}_pair"
        f"{player_name}_has_3+_halves"
        f"{player_name}_has_2_halves"
        "we_have_pair"

        used provoking rules (always applied top to bottom):
        - never say 140 (we are scared of playing black)
        - only go over 140 if you know that the team has a pair
        - add 5 to the provoking value if 140 is between the old game value (exclusive) and the own provoking value (inclusive)
        - do 5-step if you have an ace and nobody in the party called one yet
        - do 15-step if you have a big pair
        - do 10-step if you have either 3+ halves or a small pair
        - do 5-step if you have exactly 2 halves, didn't call them yet and an ace was already called in the party
        - if you couldn't do a step considering all these rules: fold (do a 0-step)
        """

        # we don't interpret our own steps, the infos from our hand are already in the concepts
        if state.player_num == player_num:
            return

        # if the other party uses another policy, we ignore their provoking steps, since we don't know what they mean
        if player_num != state.partner_num() and state.opponent_policy != type(self):
            return

        player_steps = state.provoking_steps(player_num)
        player_name = state.all_players[player_num]
        partner_num = state.partner_num(player_num)
        partner_steps = state.provoking_steps(partner_num)

        if value == 140:
            # currently, this value has no meaning and should not occur, since this policy always skips 140
            # later, we should introduce an interpretation of a 140 provoke
            pass

        # if 140 is between the old value (exclusive) and the new value (exclusive), we have to divide 5 from the step, since 140 was skipped
        if value > 140 and value - player_steps[-1] < 140:
            player_steps[-1] -= 5

        match player_steps[-1]:
            case 0:
                self._interpret_0_prov(state, player_name, player_steps, partner_steps)
            case 5:
                self._interpret_5_prov(value, state, player_name, player_steps, partner_steps)
            case 10:
                self._interpret_10_prov(value, state, player_name, player_steps)
            case 15:
                self._interpret_15_prov(value, state, player_name, player_steps)
            case _:
                # should not happen when using this policy
                raise RuntimeError(f"Unexpected provoking step by {type(self).__name__}: {player_steps[-1]}")
    
    def _interpret_0_prov(self, state: GameState, player_name: str, player_steps: list[int], partner_steps: list[int]) -> None:
        # we won't interpret anything here for now, we'll only use the safely deducted information from the actually done provoking steps
        pass

    def _interpret_5_prov(self, value: int, state: GameState, player_name: str, player_steps: list[int], partner_steps: list[int]) -> None:
        # first in the party: player has ace
        if (player_steps + partner_steps).count(5) == 1:
            state.concepts.add(Concept(f"{player_name}_has_ace", {}, value=1.0))
        # second in the party OR 
        # third in the party, but the player did at most one 5-step yet: player has 2 halves
        elif (player_steps + partner_steps).count(5) == 2 or \
            ((player_steps + partner_steps).count(5) == 3 and player_steps.count(5) < 3):
            state.concepts.add(Concept(f"{player_name}_has_2_halves", {}, value=1.0))
        else:
            # should not happen when using this policy since it has no specific meaning
            # and this policy only does well-defined provoking steps
            raise RuntimeError(f"{state.name} unexpected provoking step by {type(self).__name__}: {player_steps[-1]} (5 is {(player_steps + partner_steps).count(5)} times in the list)\n \
                               own steps: {player_steps}\n \
                               partner steps: {partner_steps}")

    def _interpret_10_prov(self, value: int, state: GameState, player_name: str, player_steps: list[int]) -> None:
        # first of the player: player has at least three halves OR player has a small pair
        if player_steps.count(10) == 1:
            state.concepts.add(Concept(f"{player_name}_has_3+_halves", {}, value=0.5))
            state.concepts.add(Concept(f"{player_name}_has_small_pair", {}, value=0.5))
        elif player_steps.count(10) <= 2:
            # player could communicate a small pair and additional 3 halves OR two small pairs
            # in both cases, he has a small pair
            state.concepts.add(Concept(f"{player_name}_has_3+_halves", {}, value=0.5))
            state.concepts.add(Concept(f"{player_name}_has_small_pair", {}, value=1.0))
        else:
            # should not happen when using this policy
            raise RuntimeError(f"Unexpected provoking step by {type(self).__name__}: {player_steps[-1]}")
        
    def _interpret_15_prov(self, value: int, state: GameState, player_name: str, player_steps: list[int]) -> None:
        # first of the player: player has a big pair
        if player_steps.count(15) <= 2:
            # the player could do 2 steps to communicate 2 pairs
            state.concepts.add(Concept(f"{player_name}_has_big_pair", {}, value=1.0))
        else:
            # should not happen when using this policy
            raise RuntimeError(f"Unexpected provoking step by {type(self).__name__}: {player_steps[-1]}")
        
    def _select_cards_to_pass(self, state: GameState) -> set[Card]:
        """
        Select the cards to pass, according to fixed passing rules.
        """

        assert len(state.hand_cards) == 9, "selecting cards to pass is only possible if there are exactly 9 cards left on the hand"

        # divide the cards into subsets, one per color
        colors = [color for color in Color]
        color_subsets = {color: [card for card in state.hand_cards if card.color == color] for color in colors}
        sizes = {color: len(color_subsets[color]) for color in colors}

        def get_subsets_by_count(count: int) -> list[list[Card]]:
            """
            Returns a list of all color subsets that have size "count".
            """
            color_sets = []
            for color in colors:
                if sizes[color] == count:
                    color_sets.append(color_subsets[color])
            return color_sets
        
        def get_highest(n: int, card_set: list[Card]) -> list[Card]:
            assert n <= len(card_set), "n is too high for this set"
            return utils.sorted_cards(card_set)[-n:]
        
        subsets = {size: get_subsets_by_count(size) for size in range(0, 10)}

        passing_cards = []

        # 11.74% of hands: passed cards have shape 4
        # if we are already blank in at least one color and have exactly 4 cards of another color: pass these 4 cards
        # also, if we have 9 cards of one color (very rare): pass the 4 highest of them; TODO: we should probably have taken the game in this case...
        if subsets[0]:
            if subsets[4]:
                # return all 4 cards of the first best color -> I am blank in 2 cards
                passing_cards = subsets[4][0]
            if subsets[9]:
                # sort the cards (ascending) and return the 4 highest
                passing_cards = utils.sorted_cards(list(state.hand_cards))[-4:0]
            
        # 45.11% of hands: passed cards have shape 3-1
        # if the colors are distributed 8-1: return (3 out of 8) and 1
        # 6-3: (1 out of 6) and 3
        # 5-3-1: 3 and 1
        # 3-3-3: 3 and (1 out of 3)
        # 4-3-1-1: 3 and 1
        # 3-3-2-1: 3 and 1
        if subsets[8]:
            passing_cards = subsets[1][0] + get_highest(3, subsets[8][0])
        if subsets[6] and subsets[3]:
            passing_cards = subsets[3][0] + get_highest(1, subsets[6][0])
        if subsets[5] and subsets[3]:
            passing_cards = subsets[3][0] + subsets[1][0]
        if len(subsets[3]) == 3:
            passing_cards = subsets[3][0] + get_highest(1, subsets[3][1])
        if subsets[4] and subsets[3] and subsets[1]:
            passing_cards = subsets[3][0] + subsets[1][0]
        if len(subsets[3]) == 2 and subsets[2]:
            passing_cards = subsets[3][0] + subsets[1][0]
        
        # 37.48% of hands: passed cards have shape 2-2
        # 7-2: (2 out of 7) and 2
        # 5-2-2: 2 and 2
        # 4-2-2-1: 2 and 2
        # 3-2-2-2: 2 and 2
        if subsets[7] and subsets[2]:
            passing_cards = subsets[2][0] + get_highest(2, subsets[7][0])
        if subsets[5] and len(subsets[2]) == 2:
            passing_cards = subsets[2][0] + subsets[2][1]
        if subsets[4] and len(subsets[2]) == 2:
            passing_cards = subsets[2][0] + subsets[2][1]
        if subsets[3] and len(subsets[2]) == 3:
            passing_cards = subsets[2][0] + subsets[2][1]
        
        # 5.414% of hands: passed cards have shape 2-1-1
        # 7-1-1: (2 out of 7) and 1 and 1
        # 6-2-1: (1 out of 6) and 2 and 1
        # 5-2-1-1: 2 and 1 and 1
        if subsets[7] and subsets[1]:
            passing_cards = get_highest(2, subsets[7][0]) + subsets[1][0] + subsets[1][1]
        if subsets[6] and subsets[2]:
            passing_cards = get_highest(1, subsets[6][0]) + subsets[2][0] + subsets[1][0]
        if subsets[5] and subsets[2] and subsets[1]:
            passing_cards = subsets[2][0] + subsets[1][0] + subsets[1][1]
        
        # 0.2602% of hands: passed cards have shape 1-1-1-1
        # 6-1-1-1: 1 and 1 and 1
        if len(subsets[1]) == 3:
            passing_cards = subsets[1][0] + subsets[1][1] + subsets[1][2]

        assert len(passing_cards) == 4, f"invalid choice of cards in _select_cards_to_pass: length {len(passing_cards)}"

        state.passed_cards = passing_cards

        # update the concepts
        self._update_concepts_after_passing(state, passing_cards)

        return passing_cards
        
    def _deduct_passing_infos(self, state: GameState) -> None:
        """
        Deduct information about the partner's cards according to the cards he passed.
        """
        passed_cards = state.got_cards_passed
        colors = [color for color in Color]
        color_subsets = {color: [card for card in passed_cards if card.color == color] for color in colors}
        sizes = {color: len(color_subsets[color]) for color in colors}

        def get_subsets_by_count(count: int) -> list[list[Card]]:
            """
            Returns a list of all color subsets that have size "count".
            """
            color_sets = []
            for color in colors:
                if sizes[color] == count:
                    color_sets.append(color_subsets[color])
            return color_sets
        
        def get_colors_by_count(count: int) -> list[Color]:
            """
            Returns a list of all colors with their subset having size "count".
            """
            count_colors = []
            for color in colors:
                if sizes[color] == count:
                    count_colors.append(color)
            return count_colors
        
        subsets = {size: get_subsets_by_count(size) for size in range(0, 5)}

        # 4 identical colored cards: assume that the partner is blank in this color and one other color
        if subsets[4]:
            color = get_colors_by_count(4)[0].name
            state.concepts.add(Concept(f"{state.partner()}_is_blank_in_{color}", {}, value=1.0))
        # 3-1: assume that the partner is blank in both colors
        if subsets[3]:
            for count in [3, 1]:
                color = get_colors_by_count(count)[0]
                state.concepts.add(Concept(f"{state.partner()}_is_blank_in_{color.name}", {}, value=1.0))
        # 2-2: assume that the partner is blank in both colors
        if len(subsets[2]) == 2:
            count_colors = get_colors_by_count(2)
            for color in count_colors:
                state.concepts.add(Concept(f"{state.partner()}_is_blank_in_{color.name}", {}, value=1.0))
        # 2-1-1: assume that the partner is blank in two of the three colors
        if subsets[2] and subsets[1]:
            for count in [2, 1]:
                count_colors = get_colors_by_count(count)
                for color in count_colors:
                    state.concepts.add(Concept(f"{state.partner()}_is_blank_in_{color.name}", {}, value=0.66))
        # 1-1-1-1: assume that the player is blank in three of four colors
        if len(subsets[1]) == 4:
            for color in colors:
                state.concepts.add(Concept(f"{state.partner()}_is_blank_in_{color.name}", {}, value=0.75))

        # now check if the partner passed a pair
        passed_pairs = [pair.pop().color for pair in utils.pairs() if pair.issubset(passed_cards)]
        for pair_color in passed_pairs:
            if pair_color == Color.Rot or pair_color == Color.Schell:
                state.concepts.remove(f"{state.partner()}_has_big_pair")
            else:
                state.concepts.remove(f"{state.partner()}_has_small_pair")

        # next, check for standalone halves
        passed_halves = [card for card in passed_cards if card.value == Value.Ober or card.value == Value.Koenig]
        for half in passed_halves:
            if half.color in passed_pairs:
                passed_halves.remove(half)
        if passed_halves:
            if state.concepts.get_by_name(f"{state.partner()}_has_3+_halves"):
                state.concepts.remove(f"{state.partner()}_has_3+_halves")
                if len(passed_halves) == 1:
                    state.concepts.add(Concept(f"{state.partner()}_has_2_halves", {}, value=1.0))
            elif state.concepts.get_by_name(f"{state.partner()}_has_2_halves"):
                state.concepts.remove(f"{state.partner()}_has_2_halves")

    def _select_cards_to_pass_back(self, state: GameState) -> set[Card]:
        """
        Select cards to pass back while keeping as many standing cards as possible and not slicing pairs.
        """
        # we don't want to pass back colors that out partner is blank in
        partner_blank_colors = []
        if state.concepts.get_by_name(f"{state.partner()}_is_blank_in_Gruen"):
            partner_blank_colors.append(Color.Gruen)
        if state.concepts.get_by_name(f"{state.partner()}_is_blank_in_Eichel"):
            partner_blank_colors.append(Color.Eichel)
        if state.concepts.get_by_name(f"{state.partner()}_is_blank_in_Schell"):
            partner_blank_colors.append(Color.Schell)
        if state.concepts.get_by_name(f"{state.partner()}_is_blank_in_Rot"):
            partner_blank_colors.append(Color.Rot)
        best_pbck_cards = [card for card in state.hand_cards if card.color not in partner_blank_colors]
        if len(best_pbck_cards) < 4:
            # we have to pass one of the gotten colors back since there are not enough differently colored cards
            print("passing back some cards my partner is blank in since I have no other choice")
            cards_to_pbck = best_pbck_cards + utils.sorted_cards(state.hand_cards - set(best_pbck_cards))[0:4-len(best_pbck_cards)]
            # update the concepts
            self._update_concepts_after_passing(state, cards_to_pbck)
            return cards_to_pbck

        # if we have the choice, we don't want to pass back standing cards
        not_standing = set(best_pbck_cards) - state.standing_cards()
        if len(not_standing) < 4:
            # there are less than 4 cards that are not standing which means that all hand cards are standing after passing
            # just pass the 4 lowest cards back
            print("passing 4 cards my partner is (probably) not blank in, while choosing as low cards as possible; all remaining cards are standing")
            cards_to_pbck = list(not_standing) + utils.sorted_cards(state.standing_cards())[0:4-len(not_standing)]
            # update the concepts
            self._update_concepts_after_passing(state, cards_to_pbck)
            return cards_to_pbck

        print("passing 4 cards my partner is (probably) not blank in, while choosing as low cards as possible")
        cards_to_pbck = utils.sorted_cards(not_standing)[0:4]
        # update the concepts
        self._update_concepts_after_passing(state, cards_to_pbck)
        return cards_to_pbck
    
    def _update_concepts_after_passing(self, state: GameState, passed_cards: list[Card]) -> None:
        # check if halves or pairs were passed
        passed_halves = [card for card in passed_cards if card.value == Value.Ober or card.value == Value.Koenig]

        # remove info about pairs from the state
        passed_pairs = [pair.pop().color for pair in utils.pairs() if pair.issubset(passed_halves)]
        for pair_color in passed_pairs:
            print("damn, I just passed a pair (might be not that smart)")
            if pair_color == Color.Rot or pair_color == Color.Schell:
                state.concepts.remove(f"{state.name}_has_big_pair")
            else:
                state.concepts.remove(f"{state.name}_has_small_pair")
        
        passed_standalone_halves = [half for half in passed_halves if half.color not in passed_pairs]
        if len(passed_standalone_halves) >= 2:
            print("I passed at least two single halves, fresh")
            state.concepts.remove(f"{state.name}_has_3+_halves")
            state.concepts.remove(f"{state.name}_has_2_halves")
        elif len(passed_standalone_halves) == 1:
            state.concepts.remove(f"{state.name}_has_2_halves")
            if state.concepts.get_by_name(f"{state.name}_has_3+_halves"):
                value = state.concepts.get_by_name(f"{state.name}_has_3+_halves").value
                state.concepts.remove(f"{state.name}_has_3+_halves")
                state.concepts.add(Concept(f"{state.name}_has_2_halves", {}, value=value))
        
    def _select_card_or_question(self, state: GameState, legal_actions: list[Action]) -> Action:
        """
        When you are at turn, select which card you want to play or, if you start a new trick and it's not the first one, if you want to ask something.
        """
        current_trick = state.current_trick
        standing_cards = state.standing_cards()

        # calculate how many steps it will at most take to announce a pair
        max_attempts_to_pair = math.inf
        min_attempts_to_pair = None
        partner_might_have_pair = False
        next_to_ask = ""
        if state.small_pairs_on_hand() or state.big_pairs_on_hand():
            # I have an unannounced pair
            max_attempts_to_pair = 0
            next_to_ask = "MY"
        elif (concept := state.concepts.get_by_name(f"{state.partner}_has_big_pair")) or (concept := state.concepts.get_by_name(f"{state.partner}_has_small_pair")):
            # if the partner has a big pair, the value in the concept is always 1.0
            # only if he made an ambiguous 10-step, we can't be sure if he has a pair
            if concept.value == 1.0:
                # my partner has a pair for sure
                max_attempts_to_pair = 0
                next_to_ask = "YOURS"
            # else the partner might or might not have a pair, we will have to ask him
            else:
                partner_might_have_pair = True
        if max_attempts_to_pair == math.inf and \
           ( state.concepts.get_by_name(f"{state.partner()}_has_3+_halves") and len(state.standalone_halves_on_hand()) >= 2 or \
             state.concepts.get_by_name(f"{state.partner()}_has_2_halves") and len(state.standalone_halves_on_hand()) >= 3 ):
            # I am not sure that one of us has a pair, but we definitely have a pair together
            possible_colors = [half.color for half in state.standalone_halves_on_hand()]
            assert len(possible_colors) > 0, "sure about shared pair, but no halves remaining on the own hand"
            max_attempts_to_pair = len(possible_colors)
            if partner_might_have_pair:
                # we will first ask for his pair before asking for halves, that adds one asking step
                max_attempts_to_pair += 1
            else:
                # we will directly start asking for halves
                next_to_ask = "OUR"
        if next_to_ask == "":
            # we didn't find any secure pairs
            # in this case, we will ask for a pair and then for all halves that we have, hoping that we will find a pair
            min_attempts_to_pair = 1 + len(state.standalone_halves_on_hand())

        # find out if we start the trick or if we have to follow the suit
        if current_trick.get_status() == 0:
            # we start the trick
            if state.phase == "TRCK":
                # this must be either the first trick or we are right after asking a question
                # just play a standing card if possible, TODO: check if this would destroy a pair
                print("trying to play a standing card")
                return self._select_card_action(state, legal_actions)
            elif state.phase == "QUES":
                # I just won a trick and can either announce a pair, ask a question or play a card
                if next_to_ask == "" and min_attempts_to_pair < len(standing_cards) or max_attempts_to_pair < len(standing_cards):
                    # enough standing cards remaining, just play one of them
                    print(f"playing a standing card since there are enough standing to announce a pair securely ({len(standing_cards)} standing cards)")
                    card_action_to_play = self._select_card_action(state, legal_actions)
                    assert card_action_to_play.content in standing_cards, f"_select_card_action not working properly; chose {card_action_to_play.content} while standing cards are {list(standing_cards)}"
                    return card_action_to_play
                else:
                    # we have to announce a pair as soon as possible before running out of standing cards
                    if next_to_ask != "":
                        # we have found a secure pair beforehand and want to announce it
                        for action in legal_actions:
                            if isinstance(action.content, Talk):
                                print("-------------------------------------------------------", action.content.pronoun)
                                if action.content.pronoun.upper() == next_to_ask:
                                    print(f"announcing a secure pair ({action.content.pronoun.upper()} {action.content.color}) since there are no standing cards left")
                                    return action
                        print("all cards:", state.hand_cards)
                        print("pairs on hand:", state.big_pairs_on_hand() + state.small_pairs_on_hand())
                        print("concepts:", state.concepts)
                        raise RuntimeError(f"didn't find the desired talk {next_to_ask}")
                    else:
                        # there is no secure pair in our view, we just have to try all options
                        # first try to ask for a pair
                        for action in legal_actions:
                            if isinstance(action.content, Talk):
                                if action.content.pronoun.upper() == "YOURS" and not state.concepts.get_by_name(f"{state.partner()}_has_no_pair"):
                                    print("asking for a pair since there is no secure one and we are running out of standing cards")
                                    return action
                        # if this is not possible (already did this and partner had no pair): try to ask for halves
                        for action in legal_actions:
                            if isinstance(action.content, Talk):
                                if action.content.pronoun.upper() == "OUR" and \
                                   action.content.color in map(lambda half: half.color, state.standalone_halves_on_hand()) and \
                                   not action.content.color in state.announced_pairs:
                                    print("asking for a half since there is no secure pair and we are running out of standing cards")
                                    return action
                        # if both is not possible: we cannot announce any pair, just play a card
                        print("we can't have a pair, so I'll just play a card")
                        return self._select_card_action(state, legal_actions)
        else:
            print("not starting the trick, just choosing a card to play")
            return self._select_card_action(state, legal_actions)
        
        print(legal_actions)
        raise RuntimeError("FAK")

    def _select_card_action(self, state: GameState, legal_actions: list[Action]) -> Action:
            """
            Chooses which card the player should play. Does not consider other steps like asking questions, this must be done outside the function.
            """
            # play a standing card if I can take the trick with it
            standing_cards = utils.sorted_cards(state.standing_cards())
            standing_cards.reverse()
            winning_cards = [card for card in standing_cards if state.current_trick.taken_by(card)]

            # look for a winning card that I am allowed to play
            for card in winning_cards:
                for action in legal_actions:
                    if isinstance(action.content, Card) and action.content == card:
                        print(f"playing card {action.content} since it will win the trick (standing cards: {standing_cards}, trump: {state.current_trick.trump_color})")
                        return action

            # if I can't play a standing card: play the lowest card possible
            legal_card_actions = [action for action in legal_actions if isinstance(action.content, Card)]
            legal_cards = [action.content for action in legal_card_actions]
            assert legal_card_actions
            legal_cards_sorted = utils.sorted_cards(legal_cards)
            print(f"playing low card since I can't win the trick safely")
            return legal_card_actions[legal_cards_sorted.index(legal_cards_sorted[0])]

    def observe_action(self, state: GameState, action: Action) -> None:
        """
        Deducts knowledge from the observed action and adds it to the state.
        """
        match state.phase:
            case 'PROV':
                # deduct info from the provoking step
                prov_value = action.content
                self._deduct_provoking_infos(state, action.player_number, prov_value)
            case 'PASS':
                # if I pass the cards to my partner, the info is already in the gamestate
                # if the passing happens in the opponent team, I am not allowed to see the content (info is still visible for me -> framework issue)
                # I will only notice if my partner passes cards to me
                if action.player_number != state.partner_num():
                    # only observe passed cards within the own team
                    return
                state.got_cards_passed.append(action.content)
                if len(state.got_cards_passed) == 4:
                    self._deduct_passing_infos(state)
            case 'ANSW':
                if action.player_number == state.partner_num() and action.content.pronoun.upper() == "NMY":
                    state.concepts.add(Concept(f"{state.partner()}_has_no_pair", {}, value=1.0))
            case 'PRMO':
                print(f"{state.player_num}:")
                print(f"  cards: {[f"{card.color}{card.value}" for card in state.hand_cards]}")
                print(f"  aces: {[f"{card.color}{card.value}" for card in state.aces_on_hand]}")
                print(f"  standing cards: {[f"{card.color}{card.value}" for card in state.standing_cards()]}")
                print(f"  pairs: {[str(color) for color in state.big_pairs_on_hand() + state.small_pairs_on_hand()]}")
                print(f"  standalone_halves: {[str(card.color) + str(card.value) for card in state.standalone_halves_on_hand()]}")
                print(f"  concepts: {[(concept[0], concept[1].value) for concept in state.concepts.dict_by_name.items()]}")

    def select_action(self, state: GameState, legal_actions: list[Action]) -> Action:
        """
        select an action based on the current state and legal actions
        TODO: Use the plan that was formed to carry out actions and estimate the strongest moves of the opponent
        TODO: If the likelihood of a move failing is too high, try to rethink the game and carry on with a new plan
        """
        print()
        if state.phase == "PROV":
            action = None
            prov_value = self._provoke(state, state.game_value)
            for legal_action in legal_actions:
                if legal_action.content == prov_value:
                    action = legal_action
                    break
            if not action:
                # fold since the desired provoking step could not be found in the legal actions (should not happen)
                print("WARNING: could not execute the desired provoking step")
                # first legal action is always a step of 0 in this phase
                return legal_actions[0]
            else:
                return action
        elif state.phase == "PASS":
            if not state.passed_cards:
                state.passed_cards = self._select_cards_to_pass(state)
                assert len(state.passed_cards) == 4, "invalid return of select_cards_to_pass"
            for action in legal_actions:
                if action.content in state.passed_cards:
                    return action
            print(state.passed_cards)
            print([action.content for action in legal_actions])
            raise RuntimeError("couldn't pass the cards I wanted to")
        elif state.phase == "PBCK":
            if not state.passed_cards:
                state.passed_cards = self._select_cards_to_pass_back(state)
                assert len(state.passed_cards) == 4, "invalid return of select_cards_to_pass_back"
            for action in legal_actions:
                if action.content in state.passed_cards:
                    return action
            print(state.passed_cards)
            print([action.content for action in legal_actions])
            raise RuntimeError("couldn't pass back the cards I wanted to")
        elif state.phase == "QUES" or state.phase == "TRCK":
            print("selecting...")
            return self._select_card_or_question(state, legal_actions)
        elif state.phase == "PRMO":
            for action in legal_actions:
                if action.content == 0:
                    return action
            print(legal_actions)
            raise RuntimeError()
        else:
            print(state.phase)
            return rnd.choice(legal_actions)

    def game_start(self, state: GameState):
        """initializes the Policy to be ready for next game"""
        self._assess_own_hand(state)


# class ProbabilisticPolicy2(Policy):
#     def __init__(self) -> None:
#         super().__init__()

#     def game_start(self, state: GameState, scores: list[int] = None, total_rounds: int = 8):
#         super().game_start(state)
#         """initializes the Policy to be ready for next game"""

#         # already begin reasoning...
#         self._assess_own_hand(state)
#         self._to_communicate(state)

#     def _deduct_provoking_infos(self, state: GameState, player_num: int, value: int) -> None:
#         """
#         We need infos about what the players are trying to communicate!
#         For now, we assume they have the same provoking rules as we have :)
#         In the Future it might be wise to not rely too much on what the opponents try to communicate
#         As this way players could abuse the AI too much by feeding false information
#         We will also have to assume more variety when playing with other AI policies together
#         Concepts that can be learned:
#         f"{player_name}_has_ace"
#         f"{player_name}_has_small_pair"
#         f"{player_name}_has_big_pair"
#         f"{player_name}_has_{color}_pair"
#         f"{player_name}_has_3+_halves"
#         f"{player_name}_has_2_halves"
#         "we_have_pair"

#         used provoking rules (always applied top to bottom):
#         - never say 140 (we are scared of playing black)
#         - only go over 140 if you know that the team has a pair
#         - add 5 to the provoking value if 140 is between the old game value (exclusive) and the own provoking value (inclusive)
#         - do 5-step if you have an ace and nobody in the party called one yet
#         - do 15-step if you have a big pair
#         - do 10-step if you have either 3+ halves or a small pair
#         - do 5-step if you have exactly 2 halves, didn't call them yet and an ace was already called in the party
#         - if you couldn't do a step considering all these rules: fold (do a 0-step)
#         """

#         # we don't interpret our own steps, the infos from our hand are already in the concepts
#         if state.player_num == player_num:
#             return

#         # if the other party uses another policy, we ignore their provoking steps, since we don't know what they mean
#         if player_num != state.partner_num() and state.opponent_policy != type(self):
#             return

#         player_steps = state.provoking_steps(player_num)
#         player_name = state.all_players[player_num]
#         partner_num = state.partner_num(player_num)
#         partner_steps = state.provoking_steps(partner_num)

#         assert player_steps != [5, 5] or partner_steps != [5, 5]

#         if value == 140:
#             # currently, this value has no meaning and should not occur, since this policy always skips 140
#             # later, we should introduce an interpretation of a 140 provoke
#             pass

#         # if 140 is between the old value (exclusive) and the new value (exclusive), we have to divide 5 from the step, since 140 was skipped
#         if value > 140 and value - player_steps[-1] < 140:
#             player_steps[-1] -= 5

#         match player_steps[-1]:
#             case 0:
#                 self._interpret_0_prov(state, player_name, player_steps, partner_steps)
#             case 5:
#                 self._interpret_5_prov(value, state, player_name, player_steps, partner_steps)
#             case 10:
#                 self._interpret_10_prov(value, state, player_name, player_steps)
#             case 15:
#                 self._interpret_15_prov(value, state, player_name, player_steps)
#             case _:
#                 # should not happen when using this policy
#                 raise RuntimeError(f"Unexpected provoking step by {type(self).__name__}: {player_steps[-1]}")
    
#     def _interpret_0_prov(self, state: GameState, player_name: str, player_steps: list[int], partner_steps: list[int]) -> None:
#         # we won't interpret anything here for now, we'll only use the safely deducted information from the actually done provoking steps
#         pass

#     def _interpret_5_prov(self, value: int, state: GameState, player_name: str, player_steps: list[int], partner_steps: list[int]) -> None:
#         # first in the party: player has ace
#         if (player_steps + partner_steps).count(5) == 1:
#             state.concepts.add(Concept(f"{player_name}_has_ace", {}, value=1.0))
#         # second in the party OR 
#         # third in the party, but the player did at most one 5-step yet: player has 2 halves
#         elif (player_steps + partner_steps).count(5) == 2 or \
#             ((player_steps + partner_steps).count(5) == 3 and player_steps.count(5) < 3):
#             # second in the party: 2 halves
#             # third in the party, but not all by the same person: 2 halves
#             state.concepts.add(Concept(f"{player_name}_has_2_halves", {}, value=1.0))
#         else:
#             # should not happen when using this policy since it has no specific meaning
#             # and this policy only does well-defined provoking steps
#             raise RuntimeError(f"{state.name} unexpected provoking step by {type(self).__name__}: {player_steps[-1]} (5 is {(player_steps + partner_steps).count(5)} times in the list)\n \
#                                own steps: {player_steps}\n \
#                                partner steps: {partner_steps}")

#     def _interpret_10_prov(self, value: int, state: GameState, player_name: str, player_steps: list[int]) -> None:
#         # first of the player: player has at least three halves OR player has a small pair
#         if player_steps.count(10) == 1:
#             state.concepts.add(Concept(f"{player_name}_has_3+_halves", {}, value=0.5))
#             state.concepts.add(Concept(f"{player_name}_has_small_pair", {}, value=0.5))
#         elif player_steps.count(10) <= 2:
#             # player could communicate a small pair and additional 3 halves OR two small pairs
#             # in both cases, he has a small pair
#             state.concepts.add(Concept(f"{player_name}_has_3+_halves", {}, value=0.5))
#             state.concepts.add(Concept(f"{player_name}_has_small_pair", {}, value=1.0))
#         else:
#             # should not happen when using this policy
#             raise RuntimeError(f"Unexpected provoking step by {type(self).__name__}: {player_steps[-1]}")
        
#     def _interpret_15_prov(self, value: int, state: GameState, player_name: str, player_steps: list[int]) -> None:
#         # first of the player: player has a big pair
#         if player_steps.count(15) <= 2:
#             # the player could do 2 steps to communicate 2 pairs
#             state.concepts.add(Concept(f"{player_name}_has_big_pair", {}, value=1.0))
#         else:
#             # should not happen when using this policy
#             raise RuntimeError(f"Unexpected provoking step by {type(self).__name__}: {player_steps[-1]}")
        
#     def _deduct_passing_infos(self, state: GameState) -> None:
#         """
#         Deduct information about the partner's cards according to the cards he passed.
#         """
#         passed_cards = state.customs['passed_cards']
#         colors = [color for color in Color]
#         color_subsets = {color: [card for card in passed_cards if card.color == color] for color in colors}
#         sizes = {color: len(color_subsets[color]) for color in colors}

#         def get_subsets_by_count(count: int) -> list[list[Card]]:
#             """
#             Returns a list of all color subsets that have size "count".
#             """
#             color_sets = []
#             for color in colors:
#                 if sizes[color] == count:
#                     color_sets.append(color_subsets[color])
#             return color_sets
        
#         def get_colors_by_count(count: int) -> list[Color]:
#             """
#             Returns a list of all colors with their subset having size "count".
#             """
#             count_colors = []
#             for color in colors:
#                 if sizes[color] == count:
#                     count_colors.append(color)
#             return count_colors
        
#         subsets = {size: get_subsets_by_count(size) for size in range(0, 5)}

#         # 4 identical colored cards: assume that the partner is blank in this color and one other color
#         if subsets[4]:
#             color = get_colors_by_count(4)[0].name
#             state.concepts.add(Concept(f"{state.partner()}_is_blank_in_{color}", {}, value=1.0))
#         # 3-1: assume that the partner is blank in both colors
#         if subsets[3]:
#             for count in [3, 1]:
#                 color = get_colors_by_count(count)[0]
#                 state.concepts.add(Concept(f"{state.partner()}_is_blank_in_{color.name}", {}, value=1.0))
#         # 2-2: assume that the partner is blank in both colors
#         if len(subsets[2]) == 2:
#             count_colors = get_colors_by_count(2)
#             for color in count_colors:
#                 state.concepts.add(Concept(f"{state.partner()}_is_blank_in_{color.name}", {}, value=1.0))
#         # 2-1-1: assume that the partner is blank in two of the three colors
#         if subsets[2] and subsets[1]:
#             for count in [2, 1]:
#                 count_colors = get_colors_by_count(count)
#                 for color in count_colors:
#                     state.concepts.add(Concept(f"{state.partner()}_is_blank_in_{color.name}", {}, value=0.66))
#         # 1-1-1-1: assume that the player is blank in three of four colors
#         if len(subsets[1]) == 4:
#             for color in colors:
#                 state.concepts.add(Concept(f"{state.partner()}_is_blank_in_{color.name}", {}, value=0.75))

#     def observe_action(self, state: GameState, action: Action) -> None:
#         """
#         adds Knowledge that is based on the observed cards, that helps to decide for the pest action
#         This should update some values like the phase or trump that is currently present,
#         but it should call for calculating probabilities when the possible cards and secure cards
#         in the self.game_state get updated

#         Example: cards that are played get removed from self.cards_left, then the information will be used
#         to deduct what cards players have based on the possible cards they could have and some simpel math

#         In summary, the function will take the game state and update the classes values according to the circumstances
#         """
#         match state.phase:
#             case 'PROV':
#                 prov_value = action.content
#                 self._deduct_provoking_infos(state, action.player_number, prov_value)
#             case 'PASS':
#                 if action.player_number == state.partner_num():
#                     # only observe passed cards within the own team
#                     if not 'passed_cards' in state.customs:
#                         state.customs['passed_cards'] = [action.content]
#                     else:
#                         state.customs['passed_cards'].append(action.content)
#                     if len(state.customs['passed_cards']) == 4:
#                         self._deduct_passing_infos(state)
#             case 'PRMO':
#                 print(f"{state.player_num}:")
#                 print(f"  cards: {[f"{card.color}{card.value}" for card in state.hand_cards]}")
#                 print(f"  aces: {[f"{card.color}{card.value}" for card in state.customs['aces']]}")
#                 print(f"  standing cards: {[f"{card.color}{card.value}" for card in state.customs['standing_cards']]}")
#                 print(f"  pairs: {[str(color) for color in state.customs['pairs']]}")
#                 print(f"  standalone_halves: {[str(card.color) + str(card.value) for card in state.customs['standalone_halves']]}")
#                 print(f"  concepts: {[(concept[0], concept[1].value) for concept in state.concepts.dict_by_name.items()]}")

#     def _assess_own_hand(self, state: GameState):
#         """
#         Analyze the own hand and add corresponding concepts to the concept store.
#         """

#         hand_cards: set[Card] = state.hand_cards
        
#         # first check for aces
#         aces = [card for card in hand_cards if card.value == Value.Ass]
#         if aces:
#             # add the secure knowledge about the ace to the concept store
#             state.concepts.add(Concept(f"{state.name}_has_ace", {}, value=1.0))
#         state.customs['aces'] = aces

#         # next, check for pairs
#         big_pairs = []
#         if utils.contains_col_pair(hand_cards, Color.Rot):
#             big_pairs.append(Color.Rot)
#         if utils.contains_col_pair(hand_cards, Color.Schell):
#             big_pairs.append(Color.Schell)
#         if big_pairs:
#             # we have a big pair
#             state.concepts.add(Concept(f"{state.name}_has_big_pair", {}, value=1.0))
#         state.customs['big_pairs'] = big_pairs
#         small_pairs = []
#         if utils.contains_col_pair(hand_cards, Color.Eichel):
#             small_pairs.append(Color.Eichel)
#         if utils.contains_col_pair(hand_cards, Color.Gruen):
#             small_pairs.append(Color.Gruen)
#         if small_pairs:
#             # we have a small pair
#             state.concepts.add(Concept(f"{state.name}_has_small_pair", {}, value=1.0))
#         state.customs['small_pairs'] = small_pairs
#         pairs = small_pairs + big_pairs
#         state.customs['pairs'] = pairs
        
#         # check how many standalone halves we have
#         standalone_halves = [card for card in hand_cards if card.value == Value.Ober or card.value == Value.Koenig]
#         for pair_color in small_pairs + big_pairs:
#             standalone_halves.remove(Card(pair_color, Value.Koenig))
#             standalone_halves.remove(Card(pair_color, Value.Ober))
#         assert len(standalone_halves) <= 4, "You can't have more than 4 standalone halves"
#         if len(standalone_halves) >= 3:
#             # we have 3+ halves
#             state.concepts.add(Concept(f"{state.name}_has_3+_halves", {}, value=1.0))
#         elif len(standalone_halves) == 2:
#             # we have 2 halves
#             state.concepts.add(Concept(f"{state.name}_has_2_halves", {}, value=1.0))
#         state.customs['standalone_halves'] = standalone_halves

#         # check for standing cards
#         standing_cards = utils.standing_cards(hand_cards, Deck().cards)
#         state.customs['standing_cards'] = standing_cards

#     def select_card_or_question(self, state: GameState, legal_actions: list[Action]) -> Action:
#         """
#         When you are at turn, select which card you want to play or, if you start a new trick and it's not the first one, if you want to ask something.
#         """
#         current_trick = state.current_trick
#         standing_cards = state.standing_cards()

#         # calculate how many steps it will at most take to announce a pair
#         max_attempts_to_pair = math.inf
#         min_attempts_to_pair = None
#         partner_might_have_pair = False
#         next_to_ask = ""
#         if state.customs['pairs']:
#             # I have an unannounced pair
#             max_attempts_to_pair = 0
#             next_to_ask = "MY"
#         elif (concept := state.concepts.get_by_name(f"{state.partner}_has_big_pair")) or (concept := state.concepts.get_by_name(f"{state.partner}_has_small_pair")):
#             # if the partner has a big pair, the value in the concept is always 1.0
#             # only if he made an ambiguous 10-step, we can't be sure if he has a pair
#             if concept.value == 1.0 and not state.customs['partner_pair_announced']:
#                 # my partner has a pair for sure
#                 max_attempts_to_pair = 0
#                 next_to_ask = "YOURS"
#             # else the partner might or might not have a pair, we will have to ask him
#             else:
#                 partner_might_have_pair = True
#         if max_attempts_to_pair == math.inf and \
#            ( state.concepts.get_by_name(f"{state.partner()}_has_3+_halves") and len(state.customs['standalone_halves']) >= 2 or \
#              state.concepts.get_by_name(f"{state.partner()}_has_2_halves") and len(state.customs['standalone_halves']) >= 3 ):
#             # I am not sure that one of us has a pair, but we definitely have a pair together
#             possible_colors = [half.color for half in state.customs['standalone_halves']]
#             assert len(possible_colors) > 0, "sure about shared pair, but no halves remaining on the own hand"
#             max_attempts_to_pair = len(possible_colors)
#             if partner_might_have_pair:
#                 # we will first ask for his pair before asking for halves, that adds one asking step
#                 max_attempts_to_pair += 1
#             else:
#                 # we will directly start asking for halves
#                 next_to_ask = "OUR"
#         if next_to_ask == "":
#             # we didn't find any secure pairs
#             # in this case, we will ask for a pair and then for all halves that we have, hoping that we will find a pair
#             min_attempts_to_pair = 1 + len(state.customs['standalone_halves'])

#         # find out if we start the trick or if we have to follow the suit
#         if current_trick.get_status() == 0:
#             # we start the trick
#             if state.phase == "TRCK":
#                 # this must be either the first trick or we are right after asking a question
#                 # just play a standing card if possible, TODO: check if this would destroy a pair
#                 print("playing a standing card")
#                 return self.select_card_action(state, legal_actions)
#             elif state.phase == "QUES":
#                 # I just won a trick and can either announce a pair, ask a question or play a card
#                 if next_to_ask == "" and min_attempts_to_pair < len(standing_cards) or max_attempts_to_pair < len(standing_cards):
#                     # enough standing cards remaining, just play one of them
#                     card_action_to_play = self.select_card_action(state, legal_actions)
#                     assert card_action_to_play.content in standing_cards, f"select_card_action not working properly; chose {card_action_to_play.content} while standing cards are {list(standing_cards)}"
#                     print("playing a standing card since there are enough standing to announce a pair securely")
#                     return card_action_to_play
#                 else:
#                     # we have to announce a pair as soon as possible before running out of standing cards
#                     if next_to_ask != "":
#                         # we have found a secure pair beforehand and want to announce it
#                         for action in legal_actions:
#                             if isinstance(action.content, Talk):
#                                 print("-------------------------------------------------------", action.content.pronoun)
#                                 if action.content.pronoun.upper() == next_to_ask:
#                                     print("announcing a secure pair since there are no standing cards left")
#                                     if action.content.pronoun.upper() == "MY":
#                                         state.customs['pairs'].remove(action.content.color)
#                                     elif action.content.pronoun.upper() == "YOURS":
#                                         state.customs['partner_pair_announced'] = True
#                                     else:
#                                         state.customs['asked_for_halves'] 
#                                     return action
#                         raise RuntimeError(f"didn't find the desired talk {next_to_ask}")
#                     else:
#                         # there is no secure pair in our view, we just have to try all options
#                         # first try to ask for a pair
#                         for action in legal_actions:
#                             if isinstance(action.content, Talk):
#                                 if action.content.pronoun.upper() == "YOURS":
#                                     print("asking for a pair since there is no secure one and we are running out of standing cards")
#                                     return action
#                         # if this is not possible (already did this and partner had no pair): try to ask for halves
#                         for action in legal_actions:
#                             if isinstance(action.content, Talk):
#                                 if action.content.pronoun.upper() == "OUR":
#                                     print("asking for a half since there is no secure pair and we are running out of standing cards")
#                                     return action
#                         # if both is not possible: we cannot announce any pair, just play a card
#                         print("we have no pair, so I just play a card")
#                         return self.select_card_action(state, legal_actions)
#         else:
#             print("not starting the trick, just playing a standing card to get the trick if possible")
#             return self.select_card_action(state, legal_actions)
        
#         print(legal_actions)
#         raise RuntimeError("FAK")

#     def select_action(self, state: GameState, legal_actions: list[Action]) -> Action:
#         """
#         select an action based on the current state and legal actions
#         TODO: Use the plan that was formed to carry out actions and estimate the strongest moves of the opponent
#         TODO: If the likelihood of a move failing is too high, try to rethink the game and carry on with a new plan
#         """
#         print()
#         if state.phase == "PROV":
#             action = None
#             prov_value = self.provoking(state, state.game_value)
#             for legal_action in legal_actions:
#                 if legal_action.content == prov_value:
#                     action = legal_action
#                     break
#             if not action:
#                 # fold since the desired provoking step could not be found in the legal actions (should not happen)
#                 print("WARNING: could not execute the desired provoking step")
#                 # first legal action is always a step of 0 in this phase
#                 return legal_actions[0]
#             else:
#                 return action
#         elif state.phase == "PASS":
#             if not 'cards_to_pass' in state.customs:
#                 state.customs['cards_to_pass'] = self.select_cards_to_pass(state)
#                 assert len(state.customs['cards_to_pass']) == 4, "invalid return of select_cards_to_pass"
#             for action in legal_actions:
#                 if action.content in state.customs['cards_to_pass']:
#                     return action
#             print(state.customs['cards_to_pass'])
#             print([action.content for action in legal_actions])
#             raise RuntimeError("couldn't pass the cards I wanted to")
#         elif state.phase == "PBCK":
#             if not 'cards_to_pass_back' in state.customs:
#                 state.customs['cards_to_pass_back'] = self.select_cards_to_pass_back(state)
#                 assert len(state.customs['cards_to_pass_back']) == 4, "invalid return of select_cards_to_pass_back"
#             for action in legal_actions:
#                 if action.content in state.customs['cards_to_pass_back']:
#                     return action
#             print(state.customs['cards_to_pass_back'])
#             print([action.content for action in legal_actions])
#             raise RuntimeError("couldn't pass back the cards I wanted to")
#         elif state.phase == "QUES" or state.phase == "TRCK":
#             print("selecting...")
#             return self.select_card_or_question(state, legal_actions)
#         elif state.phase == "PRMO":
#             for action in legal_actions:
#                 if action.content == 0:
#                     return action
#             print(legal_actions)
#             raise RuntimeError()
#         else:
#             print(state.phase)
#             return rnd.choice(legal_actions)

#     def _to_communicate(self, state: GameState) -> None:
#         """
#         generates a list of things that need to be communicated from my hand
#         This could include, based on the game state
#         - I have an Ace
#         - I have a big pair
#         - I have a small pair
#         - I have 3+ halves
#         """
#         state.customs['to_be_communicated'] = []

#         # need to call out my ace:
#         # first provoke, no ace called by partner, not over 140 unless we are somewhat sure that we have a pair
#         if state.customs['aces']:
#             state.customs['to_be_communicated'].append(ProvokingInfos.Ass)

#         for _ in state.customs['big_pairs']:
#             state.customs['to_be_communicated'].append(ProvokingInfos.BigPair)

#         for _ in state.customs['small_pairs']:
#             state.customs['to_be_communicated'].append(ProvokingInfos.SmallPair)

#         if len(state.customs['standalone_halves']) >= 3:
#             state.customs['to_be_communicated'].append(ProvokingInfos.Halves3)
#         elif len(state.customs['standalone_halves']) == 2:
#             state.customs['to_be_communicated'].append(ProvokingInfos.Halves2)

#     @staticmethod
#     def _standard_provoking_steps(info: ProvokingInfos) -> int:
#         """calculates next value based on standard provoking rules"""
#         match info:
#             case ProvokingInfos.Ass | ProvokingInfos.Halves2:
#                 return 5
#             case ProvokingInfos.SmallPair | ProvokingInfos.Halves3:
#                 return 10
#             case ProvokingInfos.BigPair:
#                 return 15
#             case _:
#                 # should not happen
#                 raise RuntimeError("Invalid ProvokingInfo")

#     def provoking(self, state: GameState, cur_value: int) -> int:
#         """
#         implement provoking logic:
#         - try to go high and not let other provoke if you have a very good hand, that means big pairs and aces
#         - avoid getting skunked, sometimes this means going to specific values like 140, 180 or 200 first, so the
#             enemies can't take the game like that
#         - otherwise only go over 140 if you are sure (check concept) that our party has a pair of enough value
#         Default to these for normal games, to let your partner know what you have:
#         - provoke 5 for an ace (unless your partner has indicated he has one already)
#         - provoke 10 for 3 halves (Koenig, or Ober) or a small pair
#         - provoke 15 for a big pair
#         - provoking 0 means folding, which we do by default if we don't want to communicate nor take the game
#         """

#         concepts = state.concepts
#         customs = state.customs
#         to_be_communicated = None

#         # find the info we want to communicate
#         while not to_be_communicated:
#             if not customs['to_be_communicated']:
#                 # nothing more to communicate
#                 print(state.name, ": folding since there is nothing to communicate")
#                 return 0
#             # get the info to be communicated
#             to_be_communicated = customs['to_be_communicated'].pop(0)
#             # if the info is an ace and the partner already called one, skip it and try to get the next info
#             if to_be_communicated == ProvokingInfos.Ass and concepts.get_by_name(f"{state.partner()}_has_ace"):
#                 to_be_communicated = None
#             # if the info is 2 halves and no ace was called in the party, skip it and try to get the next info
#             elif to_be_communicated == ProvokingInfos.Halves2 and not (concepts.get_by_name(f"{state.partner()}_has_ace") or concepts.get_by_name(f"{state.name}_has_ace")):
#                 to_be_communicated = None

#         # get the step corresponding to the info
#         step = self._standard_provoking_steps(to_be_communicated)
#         next_value = cur_value + step
#         if cur_value < 140 and next_value >= 140:
#             next_value += 5
        
#         # fold if you get above the game limit
#         if next_value > state.game_rules.max_game_value:
#             print(state.name, f": folding since I can't exceed the game limit, remaining steps were", [to_be_communicated] + customs['to_be_communicated'])
#             return 0

#         # check if we can do the step safely
#         if next_value < 140:
#             # we assume that the step is safe and just provoke it
#             print(state.name, ": provoking", next_value, "for", to_be_communicated, "while staying under 140")
#             return next_value
#         else:
#             # if the value is larger than 140, you need a pair to safely provoke it
#             partner_has_pair = concepts.get_by_name(f"{state.partner()}_has_big_pair")
#             if not partner_has_pair:
#                 partner_has_pair = concepts.get_by_name(f"{state.partner()}_has_small_pair")
            
#             if customs['pairs'] or \
#                partner_has_pair and partner_has_pair.value == 1.0 or \
#                len(customs['standalone_halves']) >= 3 and (concepts.get_by_name(f"{state.partner()}_has_3+_halves") or concepts.get_by_name(f"{state.partner()}_has_2_halves")) or \
#                len(customs['standalone_halves']) == 2 and concepts.get_by_name(f"{state.partner()}_has_3+_halves"):
#                 # under these conditions, we have a pair for sure
#                 # for now, we will just do our provoking step, no matter if our pair is big enough
#                 print(state.name, ": provoking", next_value, "for", to_be_communicated, "while being sure that we have a pair;\nconcepts:", state.concepts)
#                 return next_value
#             else:
#                 # we either don't have a pair or don't know about it
#                 # to be save, we will fold
#                 print(state.name, ": folding since I am not sure if we have a pair;\nconcepts:", state.concepts)
#                 return 0

#     def select_cards_to_pass(self, state: GameState) -> set[Card]:
#         """
#         Select the cards to pass, according to fixed passing rules.
#         """

#         assert len(state.hand_cards) == 9, "selecting cards to pass is only possible if there are exactly 9 cards left on the hand"

#         # divide the cards into subsets, one per color
#         colors = [color for color in Color]
#         color_subsets = {color: [card for card in state.hand_cards if card.color == color] for color in colors}
#         sizes = {color: len(color_subsets[color]) for color in colors}

#         def get_subsets_by_count(count: int) -> list[list[Card]]:
#             """
#             Returns a list of all color subsets that have size "count".
#             """
#             color_sets = []
#             for color in colors:
#                 if sizes[color] == count:
#                     color_sets.append(color_subsets[color])
#             return color_sets
        
#         def get_highest(n: int, card_set: list[Card]) -> list[Card]:
#             assert n <= len(card_set), "n is too high for this set"
#             return utils.sorted_cards(card_set)[-n:]
        
#         subsets = {size: get_subsets_by_count(size) for size in range(0, 10)}

#         passing_cards = []

#         # 11.74% of hands: passed cards have shape 4
#         # if we are already blank in at least one color and have exactly 4 cards of another color: pass these 4 cards
#         # also, if we have 9 cards of one color (very rare): pass the 4 highest of them; TODO: we should probably have taken the game in this case...
#         if subsets[0]:
#             if subsets[4]:
#                 # return all 4 cards of the first best color -> I am blank in 2 cards
#                 return subsets[4][0]
#             if subsets[9]:
#                 # sort the cards (ascending) and return the 4 highest
#                 return utils.sorted_cards(list(state.hand_cards))[-4:0]
            
#         # 45.11% of hands: passed cards have shape 3-1
#         # if the colors are distributed 8-1: return (3 out of 8) and 1
#         # 6-3: (1 out of 6) and 3
#         # 5-3-1: 3 and 1
#         # 3-3-3: 3 and (1 out of 3)
#         # 4-3-1-1: 3 and 1
#         # 3-3-2-1: 3 and 1
#         if subsets[8]:
#             return subsets[1][0] + get_highest(3, subsets[8][0])
#         if subsets[6] and subsets[3]:
#             return subsets[3][0] + get_highest(1, subsets[6][0])
#         if subsets[5] and subsets[3]:
#             return subsets[3][0] + subsets[1][0]
#         if len(subsets[3]) == 3:
#             return subsets[3][0] + get_highest(1, subsets[3][1])
#         if subsets[4] and subsets[3] and subsets[1]:
#             return subsets[3][0] + subsets[1][0]
#         if len(subsets[3]) == 2 and subsets[2]:
#             return subsets[3][0] + subsets[1][0]
        
#         # 37.48% of hands: passed cards have shape 2-2
#         # 7-2: (2 out of 7) and 2
#         # 5-2-2: 2 and 2
#         # 4-2-2-1: 2 and 2
#         # 3-2-2-2: 2 and 2
#         if subsets[7] and subsets[2]:
#             return subsets[2][0] + get_highest(2, subsets[7][0])
#         if subsets[5] and len(subsets[2]) == 2:
#             return subsets[2][0] + subsets[2][1]
#         if subsets[4] and len(subsets[2]) == 2:
#             return subsets[2][0] + subsets[2][1]
#         if subsets[3] and len(subsets[2]) == 3:
#             return subsets[2][0] + subsets[2][1]
        
#         # 5.414% of hands: passed cards have shape 2-1-1
#         # 7-1-1: (2 out of 7) and 1 and 1
#         # 6-2-1: (1 out of 6) and 2 and 1
#         # 5-2-1-1: 2 and 1 and 1
#         if subsets[7] and subsets[1]:
#             return get_highest(2, subsets[7][0]) + subsets[1][0] + subsets[1][1]
#         if subsets[6] and subsets[2]:
#             return get_highest(1, subsets[6][0]) + subsets[2][0] + subsets[1][0]
#         if subsets[5] and subsets[2] and subsets[1]:
#             return subsets[2][0] + subsets[1][0] + subsets[1][1]
        
#         # 0.2602% of hands: passed cards have shape 1-1-1-1
#         # 6-1-1-1: 1 and 1 and 1
#         if len(subsets[1]) == 3:
#             return subsets[1][0] + subsets[1][1] + subsets[1][2]

#         raise RuntimeError("this state should not be reached")
    
#     def select_cards_to_pass_back(self, state: GameState) -> set[Card]:
#         """
#         Select cards to pass back while keeping as many standing cards as possible and not slicing pairs
#         for now: random choice (no time :/)
#         """
#         return list(state.hand_cards)[0:4]
    
#     def select_card_action(self, state: GameState, legal_actions: list[Action]) -> Action:
#             """
#             Chooses which card the player should play. Does not consider other steps like asking questions, this must be done outside the function.
#             """
#             # play a standing card if possible
#             standing_cards = state.standing_cards()
#             for action in legal_actions:
#                 if isinstance(action.content, Card) and action.content in standing_cards:
#                     print("FOUND STANDING")
#                     return action
                
#             # if I can't play a standing card: play the lowest card possible
#             legal_card_actions = [action for action in legal_actions if isinstance(action.content, Card)]
#             legal_cards = [action.content for action in legal_card_actions]
#             assert legal_card_actions
#             legal_cards_sorted = utils.sorted_cards(legal_cards)
#             return legal_card_actions[legal_cards_sorted.index(legal_cards_sorted[0])]

#     def select_card_or_question(self, state: GameState, legal_actions: list[Action]) -> Action:
#         """
#         When you are at turn, select which card you want to play or, if you start a new trick and it's not the first one, if you want to ask something.
#         """
#         current_trick = state.current_trick
#         standing_cards = state.standing_cards()

#         # calculate how many steps it will at most take to announce a pair
#         max_attempts_to_pair = math.inf
#         min_attempts_to_pair = None
#         partner_might_have_pair = False
#         next_to_ask = ""
#         if state.customs['pairs']:
#             # I have an unannounced pair
#             max_attempts_to_pair = 0
#             next_to_ask = "MY"
#         elif (concept := state.concepts.get_by_name(f"{state.partner}_has_big_pair")) or (concept := state.concepts.get_by_name(f"{state.partner}_has_small_pair")):
#             # if the partner has a big pair, the value in the concept is always 1.0
#             # only if he made an ambiguous 10-step, we can't be sure if he has a pair
#             if concept.value == 1.0 and not state.customs['partner_pair_announced']:
#                 # my partner has a pair for sure
#                 max_attempts_to_pair = 0
#                 next_to_ask = "YOURS"
#             # else the partner might or might not have a pair, we will have to ask him
#             else:
#                 partner_might_have_pair = True
#         if max_attempts_to_pair == math.inf and \
#            ( state.concepts.get_by_name(f"{state.partner()}_has_3+_halves") and len(state.customs['standalone_halves']) >= 2 or \
#              state.concepts.get_by_name(f"{state.partner()}_has_2_halves") and len(state.customs['standalone_halves']) >= 3 ):
#             # I am not sure that one of us has a pair, but we definitely have a pair together
#             possible_colors = [half.color for half in state.customs['standalone_halves']]
#             assert len(possible_colors) > 0, "sure about shared pair, but no halves remaining on the own hand"
#             max_attempts_to_pair = len(possible_colors)
#             if partner_might_have_pair:
#                 # we will first ask for his pair before asking for halves, that adds one asking step
#                 max_attempts_to_pair += 1
#             else:
#                 # we will directly start asking for halves
#                 next_to_ask = "OUR"
#         if next_to_ask == "":
#             # we didn't find any secure pairs
#             # in this case, we will ask for a pair and then for all halves that we have, hoping that we will find a pair
#             min_attempts_to_pair = 1 + len(state.customs['standalone_halves'])

#         # find out if we start the trick or if we have to follow the suit
#         if current_trick.get_status() == 0:
#             # we start the trick
#             if state.phase == "TRCK":
#                 # this must be either the first trick or we are right after asking a question
#                 # just play a standing card if possible, TODO: check if this would destroy a pair
#                 print("playing a standing card")
#                 return self.select_card_action(state, legal_actions)
#             elif state.phase == "QUES":
#                 # I just won a trick and can either announce a pair, ask a question or play a card
#                 if next_to_ask == "" and min_attempts_to_pair < len(standing_cards) or max_attempts_to_pair < len(standing_cards):
#                     # enough standing cards remaining, just play one of them
#                     card_action_to_play = self.select_card_action(state, legal_actions)
#                     assert card_action_to_play.content in standing_cards, f"select_card_action not working properly; chose {card_action_to_play.content} while standing cards are {list(standing_cards)}"
#                     print("playing a standing card since there are enough standing to announce a pair securely")
#                     return card_action_to_play
#                 else:
#                     # we have to announce a pair as soon as possible before running out of standing cards
#                     if next_to_ask != "":
#                         # we have found a secure pair beforehand and want to announce it
#                         for action in legal_actions:
#                             if isinstance(action.content, Talk):
#                                 print("-------------------------------------------------------", action.content.pronoun)
#                                 if action.content.pronoun.upper() == next_to_ask:
#                                     print("announcing a secure pair since there are no standing cards left")
#                                     if action.content.pronoun.upper() == "MY":
#                                         state.customs['pairs'].remove(action.content.color)
#                                     elif action.content.pronoun.upper() == "YOURS":
#                                         state.customs['partner_pair_announced'] = True
#                                     else:
#                                         state.customs['asked_for_halves'] 
#                                     return action
#                         raise RuntimeError(f"didn't find the desired talk {next_to_ask}")
#                     else:
#                         # there is no secure pair in our view, we just have to try all options
#                         # first try to ask for a pair
#                         for action in legal_actions:
#                             if isinstance(action.content, Talk):
#                                 if action.content.pronoun.upper() == "YOURS":
#                                     print("asking for a pair since there is no secure one and we are running out of standing cards")
#                                     return action
#                         # if this is not possible (already did this and partner had no pair): try to ask for halves
#                         for action in legal_actions:
#                             if isinstance(action.content, Talk):
#                                 if action.content.pronoun.upper() == "OUR":
#                                     print("asking for a half since there is no secure pair and we are running out of standing cards")
#                                     return action
#                         # if both is not possible: we cannot announce any pair, just play a card
#                         print("we have no pair, so I just play a card")
#                         return self.select_card_action(state, legal_actions)
#         else:
#             print("not starting the trick, just playing a standing card to get the trick if possible")
#             return self.select_card_action(state, legal_actions)
        
#         print(legal_actions)
#         raise RuntimeError("FAK")

                

# class ProbabilisticPolicy(Policy):
#     def __init__(self) -> None:
#         super().__init__()
#         # initialize some values that we always need and update by observing actions
#         self.players: list[PolicyPlayer] = []

#         self.game_rules = GameRules()
#         self.prov_base = 115
#         self.to_be_communicated = []
#         self.communicated = []

#         self.max_reach_value = 0
#         self.max_opponent_reach_value = self.game_rules.max_game_value

#         self.our_score = 0
#         self.their_score = 0
#         self.round = 1

#     def game_start(self, state: GameState, scores: list[int] = None, total_rounds: int = 8):
#         super().game_start(state)
#         """initializes the Policy to be ready for next game"""
#         if not scores:
#             scores = [0, 0]
#         self.players = [PolicyPlayer(i, state.all_players[i], scores[i % 2]) for i in range(0, 4)]

#         self.game_rules.total_rounds = total_rounds
#         self.prov_base = self.game_rules.start_game_value

#         self.round += 1
#         if self.round > self.game_rules.total_rounds:
#             self.round = 1

#         # already begin reasoning...
#         self._initialize_concepts(state)
#         self._calculate_possible_card_probabilities(state)
#         self._assess_own_hand(state)
#         self._to_communicate(state)

#     @staticmethod
#     def _interpret_first_gone_provoke(state: GameState, partner_steps: list[int], player_name: str, value: int) -> None:
#         """
#         Information is saved inside the GameState object that the function adds concepts and information on to
#         TODO put this logic in dependencies
#         """
#         if value < 140:
#             if (not partner_steps) or partner_steps[0] == 0:
#                 # this means kinda bad cards!
#                 state.concepts.add(Concept(f"{player_name}_has_ace",
#                                            {"player": player_name, "source": "provoking"}, value=0.))
#                 state.concepts.add(Concept(f"{player_name}_has_3+_halves",
#                                            {"player": player_name, "source": "provoking"}, value=0.))
#                 state.concepts.add(Concept(f"{player_name}_has_small_pair",
#                                            {"player": player_name, "source": "provoking"}, value=0.))
#                 state.concepts.add(Concept(f"{player_name}_has_big_pair",
#                                            {"player": player_name, "source": "provoking"}, value=0.))
#             else:
#                 # this means less, but still bad cards!
#                 state.concepts.add(Concept(f"{player_name}_has_ace",
#                                            {"player": player_name, "source": "provoking"}, value=0.))
#                 state.concepts.add(Concept(f"{player_name}_has_3+_halves",
#                                            {"player": player_name, "source": "provoking"}, value=0.))
#                 state.concepts.add(Concept(f"{player_name}_has_small_pair",
#                                            {"player": player_name, "source": "provoking"}, value=0.))
#                 state.concepts.add(Concept(f"{player_name}_has_big_pair",
#                                            {"player": player_name, "source": "provoking"}, value=0.))
#                 pass

#     @staticmethod
#     def _interpret_first_5_provoke(state: GameState, partner_steps: list[int], player_name: str, value: int) -> None:
#         """
#         Information is saved inside the GameState object that the function adds concepts and information on to
#         TODO put this logic in dependencies
#         """
#         if value < 140:
#             if (partner_steps and partner_steps[0] != 5) or not partner_steps:
#                 # we are dealing likely with an ace
#                 # TODO lookup the probabilities instead of just the possibilities
#                 if any(card.value == Value.Ass for card in state.possible_cards.get(player_name, set())):
#                     state.concepts.add(Concept(f"{player_name}_has_ace",
#                                                {"player": player_name, "source": "provoking"}, value=1.))
#                     # TODO add probabilities to the Ace cards that we don't know about yet for that player
#                 else:
#                     state.concepts.add(Concept(f"{player_name}_is_faking_ace",
#                                                {"player": player_name, "source": "provoking"}, value=1.))
#             elif partner_steps and partner_steps[0] == 5:
#                 # the partner already announced an ace, so we assume it must be something else
#                 # right now we ignore the small likelihood that he has just another ace
#                 state.concepts.add(Concept(f"{player_name}_has_halves",
#                                            {"player": player_name, "source": "provoking"}, value=1.))
#         else:
#             # value 140 might mean anything, especially if its just a 5, but we could add some probability
#             # if the partner indicated a pair, it might just be the ace
#             # TODO add case for values above 140, for now its all the same
#             if partner_steps and partner_steps[0] == 10 or partner_steps[0] == 15 or partner_steps[0] == 20:
#                 if any(card.value == Value.Ass for card in state.possible_cards.get(player_name, set())):
#                     state.concepts.add(Concept(f"{player_name}_has_ace",
#                                                {"player": player_name, "source": "provoking"}, value=1.))
#             # we need to differentiate at this point if its our partner:
#             if player_name == state.partner:
#                 # we might want to hit a black game, our partner needs aces and standing cards
#                 # if they win with this call, other than that we can't really guess anything
#                 pass
#             else:
#                 # if we are predicting that we might get played black and we have no pair indication, this might
#                 # ring alarm bells even more
#                 skunked_concept = state.concepts.get_by_name("getting_played_black")
#                 if skunked_concept and skunked_concept.evaluate() > 0.5:
#                     state.concepts.get_by_name("getting_played_black").value = \
#                         min(skunked_concept.value + 0.3, 1)
#                     # TODO make this more of a dependant property!
#                 pass

#     @staticmethod
#     def _interpret_first_10_provoke(state: GameState, partner_steps: list[int], player_name: str, value: int) -> None:
#         """
#         Information is saved inside the GameState object that the function adds concepts and information on to
#         TODO put this logic in dependencies
#         """
#         # Probability for small pair or three halves can be calculated, based on the probability
#         # we can more accurately tell, which one it might be, given that the player already announced
#         # that he has either one
#         small_pair_prob = state.player_has_set_probability(player_name, utils.small_pairs())
#         three_halves_prob = state.player_has_set_probability(player_name, utils.three_halves())

#         if value < 140:
#             # we can tell for sure, the player has something:
#             state.concepts.add(Concept(f"{player_name}_has_halves",
#                                        {"player": player_name, "source": "provoking"}, value=1.))
#             if (partner_steps and partner_steps[0] != 5) or not partner_steps:
#                 # we are dealing somewhat likely with no ace
#                 state.concepts.add(Concept(f"{player_name}_has_ace",
#                                            {"player": player_name, "source": "provoking"}, value=0.1))
#             state.concepts.add(Concept(f"{player_name}_has_small_pair",
#                                        {"player": player_name, "source": "provoking"},
#                                        value=utils.is_probable(small_pair_prob)))
#             state.concepts.add(Concept(f"{player_name}_has_3+_halves",
#                                        {"player": player_name, "source": "provoking"},
#                                        value=utils.is_probable(three_halves_prob)))
#         elif value == 140:
#             # In this case, the information is unclear. We'd assume they wanna just play black, unless this is
#             # our own partner, then we might try to hit a black game
#             if player_name == state.partner(state.name):
#                 state.concepts.add(Concept(f"playing_black", {}, value=0.3))
#             elif state.concepts.get_by_name(f"getting_played_black"):
#                 state.concepts.add(Concept(f"getting_played_black", {},
#                                            value=utils.is_probable(
#                                                state.concepts.get_by_name(f"getting_played_black").value)))
#             else:
#                 # TODO calculate actual probability of getting played black via dependencies instead of flat values
#                 state.concepts.add(Concept(f"getting_played_black", {}, value=0.3))
#         else:
#             # we can tell for sure, the player has something:
#             state.concepts.add(Concept(f"{player_name}_has_halves",
#                                        {"player": player_name, "source": "provoking"}, value=1.))
#             # first check if we skipped 140
#             if state.concepts.get_by_name(f"{state.partner(player_name)}_has_3+_halves"):
#                 # if the partner indicated haves, it might just be a guessed step for a guessed pair
#                 state.concepts.add(Concept(f"{player_name}_has_3+_halves",
#                                            {"player": player_name, "source": "provoking"},
#                                            value=utils.is_probable(three_halves_prob)))
#                 state.concepts.add(Concept(f"{player_name}_has_small_pair",
#                                            {"player": player_name, "source": "provoking"},
#                                            value=small_pair_prob))
#             else:
#                 # otherwise this is likely a small pair, as otherwise the player wouldn't go over 140.
#                 state.concepts.add(Concept(f"{player_name}_has_3+_halves",
#                                            {"player": player_name, "source": "provoking"},
#                                            value=three_halves_prob))
#                 state.concepts.add(Concept(f"{player_name}_has_small_pair",
#                                            {"player": player_name, "source": "provoking"},
#                                            value=utils.is_probable(small_pair_prob)))

#     @staticmethod
#     def _interpret_first_15_provoke(state: GameState, partner_steps: list[int], player_name: str,
#                                     value: int) -> None:
#         """
#         Information is saved inside the GameState object that the function adds concepts and information on to
#         TODO put this logic in dependencies
#         """
#         # Probability for a small pair if the step has skipped 140,
#         # if the player has gone directly with +15, they might have a big pair

#         big_pair_prob = state.player_has_set_probability(player_name, utils.big_pairs())
#         small_pair_prob = state.player_has_set_probability(player_name, utils.small_pairs())
#         three_halves_prob = state.player_has_set_probability(player_name, utils.three_halves())

#         if value < 140:
#             if (partner_steps and partner_steps[0] != 5) or not partner_steps:
#                 # we are dealing somewhat likely with no ace
#                 state.concepts.add(Concept(f"{player_name}_has_ace",
#                                            {"player": player_name, "source": "provoking"}, value=0.2))
#             # we can tell for sure, the player has something:
#             state.concepts.add(Concept(f"{player_name}_has_halves",
#                                        {"player": player_name, "source": "provoking"}, value=1.))
#             # very likely it's a big pair
#             state.concepts.add(Concept(f"{player_name}_has_big_pair",
#                                        {"player": player_name, "source": "provoking"},
#                                        value=utils.is_probable(big_pair_prob)))
#         elif value == 140:
#             # In this case, the information is unclear. We'd assume they wanna just play black, unless this is
#             # our own partner, then we might try to hit a black game
#             if player_name == state.partner(state.name):
#                 state.concepts.add(Concept(f"playing_black", {}, value=0.4))
#             elif state.concepts.get_by_name(f"getting_played_black"):
#                 state.concepts.add(Concept(f"getting_played_black", {},
#                                            value=utils.is_probable(
#                                                state.concepts.get_by_name(f"getting_played_black").value)))
#             else:
#                 # TODO calculate actual probability of getting played black via dependencies instead of flat values
#                 state.concepts.add(Concept(f"getting_player_black", {}, value=0.4))
#         else:
#             # we can tell for sure, the player has something:
#             state.concepts.add(Concept(f"{player_name}_has_halves",
#                                        {"player": player_name, "source": "provoking"}, value=1.))
#             # first check if we skipped 140
#             if value == 145 or value == 150:
#                 # this might ust be a small pair after all
#                 if state.concepts.get_by_name(f"{state.partner(player_name)}_has_3+_halves"):
#                     # if the partner indicated haves, it might just be a guessed step for a guessed pair
#                     state.concepts.add(Concept(f"{player_name}_has_3+_halves",
#                                                {"player": player_name, "source": "provoking"},
#                                                value=utils.is_probable(three_halves_prob)))
#                     state.concepts.add(Concept(f"{player_name}_has_small_pair",
#                                                {"player": player_name, "source": "provoking"},
#                                                value=small_pair_prob))
#                 else:
#                     # otherwise this is likely a small pair, as otherwise the player wouldn't go over 140.
#                     state.concepts.add(Concept(f"{player_name}_has_3+_halves",
#                                                {"player": player_name, "source": "provoking"},
#                                                value=three_halves_prob))
#                     state.concepts.add(Concept(f"{player_name}_has_small_pair",
#                                                {"player": player_name, "source": "provoking"},
#                                                value=utils.is_probable(small_pair_prob)))
#             else:
#                 # this is just straight up a big pair!
#                 if big_pair_prob > 0:
#                     state.concepts.add(Concept(f"{player_name}_has_big_pair",
#                                                {"player": player_name, "source": "provoking"},
#                                                value=utils.is_probable(big_pair_prob)))
#                 else:
#                     # TODO add something for enemy trying to snipe away our black in certain cases
#                     pass

#     @staticmethod
#     def _interpret_first_20_provoke(state: GameState, partner_steps: list[int], player_name: str,
#                                     value: int) -> None:
#         """
#         Information is saved inside the GameState object that the function adds concepts and information on to
#         TODO put this logic in dependencies and add on to it
#         """
#         # We'll just interpret anything that is a 20 step and not straight 140 as a big pair.

#         big_pair_prob = state.player_has_set_probability(player_name, utils.big_pairs())

#         if value == 140:
#             # In this case, the information is unclear. We'd assume they wanna just play black, unless this is
#             # our own partner, then we might try to hit a black game
#             if player_name == state.partner(state.name):
#                 state.concepts.add(Concept(f"playing_black", {}, value=0.5))
#             elif state.concepts.get_by_name(f"getting_played_black"):
#                 state.concepts.add(Concept(f"getting_played_black", {},
#                                            value=utils.is_probable(
#                                                state.concepts.get_by_name(f"getting_played_black").value)))
#             else:
#                 # TODO calculate actual probability of getting played black via dependencies instead of flat values
#                 state.concepts.add(Concept(f"getting_player_black", {}, value=0.5))
#             # we can tell for sure, the player has something:
#             state.concepts.add(Concept(f"{player_name}_has_halves",
#                                        {"player": player_name, "source": "provoking"}, value=1.))
#             # very likely it's a big pair
#             state.concepts.add(Concept(f"{player_name}_has_big_pair",
#                                        {"player": player_name, "source": "provoking"},
#                                        value=utils.is_probable(big_pair_prob)))
#         else:
#             if (partner_steps and partner_steps[0] != 5) or not partner_steps:
#                 # we are dealing somewhat likely with no ace
#                 state.concepts.add(Concept(f"{player_name}_has_ace",
#                                            {"player": player_name, "source": "provoking"}, value=0.1))
#             # we can tell for sure, the player has something:
#             state.concepts.add(Concept(f"{player_name}_has_halves",
#                                        {"player": player_name, "source": "provoking"}, value=1.))
#             # this is just straight up a big pair!
#             if big_pair_prob > 0:
#                 state.concepts.add(Concept(f"{player_name}_has_big_pair",
#                                            {"player": player_name, "source": "provoking"},
#                                            value=utils.is_probable(big_pair_prob)))
#             else:
#                 # TODO add something for enemy trying to snipe away our black in certain cases
#                 pass

#     def _deduct_provoking_infos(self, state: GameState, player_num: int, value: int) -> None:
#         """
#         We need infos about what the players are trying to communicate!
#         For now, we assume they have the same provoking rules as we have :)
#         In the Future it might be wise to not rely too much on what the opponents try to communicate
#         As this way players could abuse the AI too much by feeding false information
#         We will also have to assume more variety when playing with other AI policies together
#         Concepts that can be learned:
#         f"{player_name}_has_small_pair"
#         f"{player_name}_has_big_pair"
#         f"{player_name}_has_{color}_pair"
#         f"{player_name}_has_3+_halves"
#         """
#         player_steps = state.provoking_steps(player_num)
#         player_name = state.all_players[player_num]
#         partner_num = state.partner_num(player_num)
#         partner_steps = state.provoking_steps(partner_num)

#         # we don't interpret our own steps, the infos from our hand are already in the concepts
#         if state.player_num == player_num:
#             return

#         # interpreting first steps:
#         if len(state.provoking_steps(player_num)) == 1:
#             # interpreting if the first step was a 5 increase
#             match player_steps[0]:
#                 case 5:
#                     self._interpret_first_5_provoke(state, partner_steps, player_name, value)
#                 case 10:
#                     self._interpret_first_10_provoke(state, partner_steps, player_name, value)
#                 case 15:
#                     self._interpret_first_15_provoke(state, partner_steps, player_name, value)
#                 case 20:
#                     self._interpret_first_20_provoke(state, partner_steps, player_name, value)
#                 case 0:
#                     self._interpret_first_gone_provoke(state, partner_steps, player_name, value)
#                 case _:
#                     pass

#         # TODO interpreting consecutive steps:
#         else:
#             pass

#     def observe_action(self, state: GameState, action: Action) -> None:
#         """
#         adds Knowledge that is based on the observed cards, that helps to decide for the pest action
#         This should update some values like the phase or trump that is currently present,
#         but it should call for calculating probabilities when the possible cards and secure cards
#         in the self.game_state get updated

#         Example: cards that are played get removed from self.cards_left, then the information will be used
#         to deduct what cards players have based on the possible cards they could have and some simpel math

#         In summary, the function will take the game state and update the classes values according to the circumstances
#         """
#         match state.phase:
#             case 'PROV':
#                 prov_value = action.content
#                 self._deduct_provoking_infos(state, action.player_number, prov_value)

#     def _assess_own_hand(self, state: GameState):
#         """
#         check for pairs, halves, and any cards that might be worth something
#         For now we ll just focus on aces, tens and pairs and halves as well as the number of cards for each suite
#         We yield a rough estimate for the game value we could reach with this hand alone
#         And we also yield what the opponents party could reach maximum!
#         We also give an estimation if they would play a black game on us, depending on our way to get into the
#         different suites. If we can't ensure that we could get a trick in a suite if they don't
#         TODO put this logic in dependencies
#         """
#         hand_cards: set[Card] = state.hand_cards
#         # arbitrary hand score, for our own sake ^^ we will keep track of how good we stand

#         # TODO make dependant concepts out of these scores
#         self.max_reach_value = 140
#         hand_score = 0
#         opp_estimate_max = 420

#         # first we need to check for aces, add arbitrary points to our score based on that
#         aces = [card for card in hand_cards if card.value == Value.Ass]
#         if aces:
#             hand_score += 5 * math.pow(2, len(aces) - 1)
#             opp_estimate_max -= 11 * len(aces)

#         # Tens are impactful, as usually if you have another card with them, they can stop trump games
#         # However they can also ruin your chances if they are single on your hand!
#         # They also are a lot of points and likely land in your tricks if you end up taking the game!
#         hand_cards_by_suite = {}
#         tens = [card for card in hand_cards if card.value == Value.Zehn]
#         for color in Color:
#             hand_cards_by_suite[color] = [card for card in hand_cards if card.color == color]
#             if Card(color, Value.Zehn) in tens:
#                 if len(hand_cards_by_suite[color]) > 1:
#                     hand_score += 10
#                 else:
#                     hand_score -= 10

#         # Let's calculate which pairs we or the opponents might have
#         pair_value = 0
#         for color in Color:
#             if utils.contains_col_pair(list(hand_cards), color):
#                 state.concepts.add(Concept(f"{state.name}_has_{str(color)}_pair",
#                                            {"player": state.name, "source": "assessment", "color": color},
#                                            value=1.))
#                 hand_score += color.points
#                 # blank pairs are not that good, additional trump however is even better!:
#                 if len(hand_cards_by_suite[color]) == 2:
#                     hand_score += color.points * 3 / 4
#                 elif len(hand_cards_by_suite[color]) == 3:
#                     hand_score += color.points
#                 else:
#                     hand_score += color.points * 5 / 4
#                 # trump aces and tens are all the more valuable!
#                 if Card(color, Value.Ass) in aces:
#                     hand_score += 10
#                     if Card(color, Value.Zehn) in tens:
#                         hand_score += 10
#                 else:
#                     if Card(color, Value.Zehn) in tens:
#                         hand_score += 5

#                 self.max_reach_value += color.points
#                 pair_value += color.points
#                 opp_estimate_max -= color.points

#             elif utils.contains_col_half(list(hand_cards), color):
#                 # add some arbitrary amount for the colors for evaluation
#                 hand_score += color.points / 5
#                 opp_estimate_max -= color.points
#                 state.concepts.add(Concept(f"{state.name}_has_{str(color)}_half",
#                                            {"player": state.name, "source": "assessment", "color": color},
#                                            value=1.))
#             else:
#                 # TODO estimate if there is anything we can deduct from having nothing?! (Risking enemy trump)
#                 pass

#         # Now let's calculate roughly the value of our standing cards
#         standing_cards = state.standing_cards()
#         hand_score += sum([card.value.points for card in standing_cards])

#         # we fear getting played black under different circumstances
#         black_chance = (1 - hand_score / opp_estimate_max) / (len(aces) + 1)
#         if len(aces) == 4:
#             black_chance = 0

#         # TODO calculate pseudo standing cards like a Koenig and a Zehn together where one will likely stand

#         # TODO we could make getting played black a possibility mainly based on possibly standing cards of opponents

#         # TODO make these all depending concepts based on more basic values!
#         state.concepts.add(Concept(f"getting_played_black", {}, value=black_chance))
#         state.concepts.add(Concept(f"good_hand_cards", {}, value=min(hand_score / 210, 1)))
#         self.max_opponent_reach_value = opp_estimate_max

#     def _calculate_possible_card_probabilities(self, state: GameState):
#         """
#         Based on combinatorics (binomials mainly for choice) we calculate how like it is for players
#         to have a specific card on their hand, based on the information we got in our class variables like the state
#         values for possible cards each player has and which cards we know securely (for those the probability is 1)
#         """
#         # TODO

#     def _estimate_game_value(self, state) -> tuple[int, int]:
#         """
#         We can estimate that the maximum we can reach is somewhere below the combination of
#         - standing cards we have as a team
#         - pairs each of us has
#         - pairs we can combine
#         We can estimate the maximum as well as the reasonable value of the game that we could make as points
#         """
#         estimated_value = 0
#         estimated_max = 140
#         unknown_pairs = utils.pairs()
#         team_cards = state.hand_cards

#         # consider all pair points we can get
#         # my pairs
#         if utils.gruen_pair() in state.hand_cards:
#             estimated_value += 40
#             unknown_pairs.remove(utils.gruen_pair())
#         if utils.eichel_pair() in state.hand_cards:
#             estimated_value += 60
#             unknown_pairs.remove(utils.eichel_pair())
#         if utils.schell_pair() in state.hand_cards:
#             estimated_value += 80
#             unknown_pairs.remove(utils.schell_pair())
#         if utils.rot_pair() in state.hand_cards:
#             estimated_value += 100
#             unknown_pairs.remove(utils.rot_pair())
#         estimated_max += estimated_value

#         # partners pairs
#         # TODO add the logic to know which pairs we have exactly
#         # TODO put this logic in dependencies of concepts
#         if (state.concepts.get_by_name(f"{state.partner()}_has_big_pair") and
#                 state.concepts.get_by_name(f"{state.partner()}_has_big_pair").value > 0.8):
#             if (Card(Color.Schell, Value.Ober) in state.hand_cards or
#                     Card(Color.Schell, Value.Koenig) in state.hand_cards):
#                 estimated_value += 100
#                 unknown_pairs.remove(utils.rot_pair())
#                 team_cards |= utils.rot_pair()
#             else:
#                 estimated_value += 80
#                 unknown_pairs.remove(utils.schell_pair())
#                 if (Card(Color.Rot, Value.Ober) in state.hand_cards or
#                         Card(Color.Rot, Value.Koenig) in state.hand_cards):
#                     team_cards |= utils.schell_pair()
#         if (state.concepts.get_by_name(f"{state.partner()}_has_small_pair") and
#                 state.concepts.get_by_name(f"{state.partner()}_has_small_pair").value > 0.8):
#             if (Card(Color.Gruen, Value.Ober) in state.hand_cards or
#                     Card(Color.Gruen, Value.Koenig) in state.hand_cards):
#                 estimated_value += 60
#                 unknown_pairs.remove(utils.eichel_pair())
#                 team_cards |= utils.eichel_pair()
#             else:
#                 estimated_value += 40
#                 unknown_pairs.remove(utils.gruen_pair())
#                 if (Card(Color.Eichel, Value.Ober) in state.hand_cards or
#                         Card(Color.Eichel, Value.Koenig) in state.hand_cards):
#                     team_cards |= utils.rot_pair()

#         # our pairs
#         if (state.concepts.get_by_name(f"{state.partner()}_has_3+_halves") and
#                 state.concepts.get_by_name(f"{state.partner()}_has_3+_halves").value > 0.8):
#             if len(unknown_pairs) == 4:
#                 halves = utils.pair_cards()
#                 hand_halves = [card for card in halves if card in state.hand_cards]
#                 estimated_value += sum([card.color.points for card in utils.smallest_x(set(hand_halves),
#                                                                                        len(hand_halves) - 1)])
#             elif len(unknown_pairs) <= 3:
#                 unknown_pair_cards = []
#                 for pair in unknown_pairs:
#                     unknown_pair_cards += [card for card in pair]
#                 hand_halves = [card for card in unknown_pair_cards if card in state.hand_cards]
#                 estimated_value += sum([card.color.points for card in utils.smallest_x(set(hand_halves),
#                                                                                        len(hand_halves))])

#         # estimate the standing cards we could have as a team
#         min_standing = 13
#         min_standing_cards = {}
#         if (state.concepts.get_by_name(f"{state.partner()}_has_ace")):
#             for ace in utils.ace_cards():
#                 if not(ace in state.hand_cards):
#                     team_cards_ace = team_cards | ace
#                     standing = utils.standing_cards(set(Deck().cards), team_cards_ace)
#                     min_standing = min(len(standing), min_standing)

#         standing_points = 120
#         if min_standing >= 7:
#             standing_points = 140
#         else:
#             standing_points = sum([card.value.points for card in standing])
#         # estimate obstacles by enemy team
#         for pair in unknown_pairs:
#             pass
#             # need to check if we can destroy those pairs if we need to
#             # TODO

#         # estimate last trick security
#         # TODO

#         return estimated_value, estimated_max

#     def _plan_game(self, state):
#         """
#         This method is only for the playing player!
#         Planning the moves ahead to not loose the game to the opponents team.
#         We need to watch out for getting as many tricks as possible but also to destroy their abilities
#         to swap the trump color
#         """
#         # TODO
#         pass

#     def _guess_plan(self, state):
#         """
#         This method is only for the playing teams secondary player, who tries to guess the plan of the planning player!
#         This way he can react with the information given at any point in the game to carry out the plan.
#         This is based on the information given and the concepts formed, swapping trump, taking tricks,
#         and not giving any opportunity for the opponent to intervene with the plan.
#         """
#         # TODO
#         pass

#     def select_action(self, state: GameState, legal_actions: list[Action]) -> Action:
#         """
#         select an action based on the current state and legal actions
#         TODO: Use the plan that was formed to carry out actions and estimate the strongest moves of the opponent
#         TODO: If the likelihood of a move failing is too high, try to rethink the game and carry on with a new plan
#         """
#         # currently a random action is played
#         probabilities = self.calculate_best_action(state, legal_actions)
#         action = np.random.choice(legal_actions, p=probabilities)
#         return action

#     def calculate_best_action(self, state: GameState, legal_actions: list[Action]):
#         game_phase = legal_actions[0].phase
#         match game_phase:
#             case 'PROV':
#                 cur_value = legal_actions[-1].content
#                 self.provoking(state, cur_value)
#             case _:
#                 # calculates evaluation values for each action
#                 action_evaluations = []
#                 for action in legal_actions:
#                     evaluation = self.evaluate_action(state, action)
#                     action_evaluations.append(evaluation)
#                     # normalize the probabilities so they sum to 1
#                 normal_eval = [p / sum(action_evaluations) for p in action_evaluations]
#                 return normal_eval

#     def _update_to_be_communicated(self, state: GameState, cur_value: int):
#         """
#         Updates things that we shouldn't communicate anymore, because we missed the chance!
#         """
#         hand_cards: set[Card] = state.hand_cards
#         partner = state.partner()

#         # remove ace to be communicated when:
#         # - our partner told us about his ace
#         # - we reached a value too high to make a provoke of an ace alone viable without proper support
#         # - we provoked our first step already, in which case we also don't tell abt halves anymore
#         if state.concepts.get_by_name(f"{partner}_has_ace"):
#             self.to_be_communicated.remove(ProvokingInfos.Ass)

#         elif cur_value >= 140 and (not (state.concepts.get_by_name(f"{partner}_has_big_pair").value > 0.8  # CONCEPT
#                                         or (state.concepts.get_by_name(f"{partner}_has_small_pair").value >
#                                             state.concepts.get_by_name(f"{partner}_has_3+_halves").value)
#                                         or utils.contains_pair(hand_cards))):
#             self.to_be_communicated.remove(ProvokingInfos.Ass)
#             self.communicated.append(ProvokingInfos.Ass)

#         elif len(state.provoking_history) >= 4:
#             self.to_be_communicated.remove(ProvokingInfos.Ass)
#             self.to_be_communicated.remove(ProvokingInfos.Halves2)
#             self.to_be_communicated.remove(ProvokingInfos.Halves3)

#         # TODO also remove stuff about pairs we don't need to communicate anymore, is there any?

#     def _to_communicate(self, state: GameState) -> None:
#         """
#         generates a list of things that need to be communicated from my hand
#         This could include, based on the game state
#         - I have an Ace
#         - I have a big pair
#         - I have a small pair
#         - I have 3+ halves
#         """
#         hand_cards: set[Card] = state.hand_cards
#         self.to_be_communicated = []

#         # need to call out my ace:
#         # first provoke, no ace called by partner, not over 140 unless we are somewhat sure that we have a pair
#         if utils.contains_ace(hand_cards):
#             self.to_be_communicated.append(ProvokingInfos.Ass)

#         for pair in [pair for pair in utils.big_pairs() if pair.issubset(hand_cards)]:
#             self.to_be_communicated.append(ProvokingInfos.BigPair)

#         for pair in [pair for pair in utils.small_pairs() if pair.issubset(hand_cards)]:
#             self.to_be_communicated.append(ProvokingInfos.SmallPair)

#         if any([halves for halves in utils.three_halves() if halves.issubset(hand_cards)]):
#             self.to_be_communicated.append(ProvokingInfos.Halves3)
#         else:
#             self.to_be_communicated.append(ProvokingInfos.Halves2)

#     @staticmethod
#     def _standard_provoking(info: ProvokingInfos, cur_value) -> int:
#         """calculates next value based on standard provoking rules"""
#         match info:
#             case ProvokingInfos.Ass | ProvokingInfos.Halves2:
#                 cur_value = cur_value + 5
#             case ProvokingInfos.SmallPair | ProvokingInfos.Halves3:
#                 cur_value = cur_value + 10
#                 if cur_value == 140:
#                     cur_value = 145
#             case ProvokingInfos.BigPair:
#                 cur_value = cur_value + 15
#                 if cur_value == 140:
#                     cur_value = 145
#         return cur_value

#     def provoking(self, state: GameState, cur_value: int):
#         """
#         implement provoking logic:
#         - try to go high and not let other provoke if you have a very good hand, that means big pairs and aces
#         - avoid getting skunked, sometimes this means going to specific values like 140, 180 or 200 first, so the
#             enemies can't take the game like that
#         - otherwise only go over 140 if you are sure (check concept) that our party has a pair of enough value
#         Default to these for normal games, to let your partner know what you have:
#         - provoke 5 for an ace (unless your partner has indicated he has one already)
#         - provoke 10 for 3 halves (Koenig, or Ober) or a small pair
#         - provoke 15 for a big pair
#         - provoking 0 means folding, which we do by default if we don't want to communicate nor take the game
#         """
#         # we want an optimistic estimate of what we could reach
#         estimated_value, estimated_max = self._estimate_game_value(state)

#         next_value = cur_value
#         regular_provoking_value = None
#         communication = None
#         if len(self.to_be_communicated) > 0:
#             communication = self.to_be_communicated.pop(0)
#             next_value = self._standard_provoking(communication, cur_value)
#             regular_provoking_value = next_value

#         # Check if we are at risk of getting skunked
#         elif next_value == cur_value and state.concepts.get_by_name("getting_played_black").evaluate() > 0.7:  # CONCEPT
#             if cur_value < 140:
#                 next_value = 140
#             elif cur_value < 180:
#                 next_value = 180
#             elif cur_value < 200:
#                 next_value = 200
#             elif cur_value < 220:
#                 next_value = 220
#             elif cur_value < 240:
#                 next_value = 240
#             elif cur_value < estimated_max:
#                 next_value = estimated_max
#             else:
#                 next_value = cur_value

#         # Do we want to take the game? We should if we can reach and can't properly pass cards
#         elif estimated_value > cur_value:
#             if state.provoking_steps(state.partner_num()) and state.provoking_steps(state.partner_num())[-1] == 0:
#                 next_value = cur_value + 5
#             elif self.eval_passing(state, self.passing_best(state)) < 5:
#                 next_value = cur_value + 5

#         # If none of the above conditions are met, provoke with the current max_value
#         prov_value = max(cur_value, min(next_value, estimated_max))

#         # update communications
#         if regular_provoking_value and regular_provoking_value == prov_value:
#             self.communicated.append(communication)

#         return prov_value

#     def eval_passing(self, state: GameState, passed_cards: set[Card]) -> float:
#         """
#         Evaluating passed cards based on the GameState, before passing them.
#         Factors that play a role:
#         - getting rid of 2 colors
#         - passing necessary cards (not knowing they got an ace? Pass it!)
#         - ambiguous information
#         -> low card in a non blank color
#         -> giving halves of pairs signaled (splitting pairs)
#         ->
#         - getting rid of blank 10s or pairs
#         - not passing stuff you already signaled
#         - passing cards to clear up information (didn't call the ace? Pass it!)
#         - passing valuable cards if possible
#         """
#         total = 0
#         hand_without_passed = [card for card in state.hand_cards if not card in passed_cards]
#         hand_wop_sorted = [[card for card in hand_without_passed if card.color == color] for color in Color]
#         color_amounts = [len(cards) for cards in hand_wop_sorted]

#         # check being blank in two colors
#         if sum([min(amount, 1) for amount in color_amounts]) <= 2:
#             total += 5

#         # check passing necessary cards
#         # check fo ace
#         # TODO check for specific pair
#         # TODO make sure this value is most definitely set if used for actual passing, need to know the ace probability
#         if (state.concepts.get_by_name(f"{state.partner()}_has_ace") and
#                 state.concepts.get_by_name(f"{state.partner()}_has_ace").value < 0.5 and
#                 utils.contains_ace(passed_cards)):
#             total += 8

#         # check ambiguities
#         passed_sorted = [[card for card in passed_cards if card.color == color] for color in Color]
#         for i, amount in enumerate(color_amounts):
#             # having cards but still passing a low card of that color
#             if amount > 0 and utils.contains_low_card(set(passed_sorted[i])):
#                 total -= 3
#             if amount == 0 and utils.contains_low_card(set(hand_wop_sorted[i])):
#                 total -= 2

#         # check blank high cards
#         total -= 3 * len([cards for cards in hand_wop_sorted if len(cards) == 1 and cards[0].value > Value.Unter])

#         # check given information
#         if ProvokingInfos.Halves3 in self.communicated or ProvokingInfos.Halves2 in self.communicated:
#             if len([card for card in passed_cards if card.value == Value.Koenig or card.value == Value.Ober]) >= 2:
#                 total += 1

#         # keep pairs that are communicated, pass pairs that aren't, depending on value
#         # TODO care for case, when two small or two big pairs were communicated
#         if ProvokingInfos.SmallPair in self.communicated:
#             if utils.contains_col_pair(list(hand_without_passed), Color.Gruen) and len(hand_wop_sorted[1]) == 0:
#                 total += 2
#             if utils.contains_col_pair(list(hand_without_passed), Color.Eichel) and len(hand_wop_sorted[0]) == 0:
#                 total += 2
#         else:
#             if (utils.contains_col_pair(list(state.hand_cards), Color.Gruen) and
#                     not utils.contains_col_pair(list(passed_cards), Color.Gruen)):
#                 total -= 1
#             if (utils.contains_col_pair(list(state.hand_cards), Color.Eichel) and
#                     not utils.contains_col_pair(list(passed_cards), Color.Eichel)):
#                 total -= 2

#         if ProvokingInfos.BigPair in self.communicated:
#             if utils.contains_col_pair(list(hand_without_passed), Color.Schell) and len(hand_wop_sorted[3]) == 0:
#                 total += 2
#             if utils.contains_col_pair(list(hand_without_passed), Color.Rot) and len(hand_wop_sorted[2]) == 0:
#                 total += 2
#         else:
#             if (utils.contains_col_pair(list(state.hand_cards), Color.Schell) and
#                     not utils.contains_col_pair(list(passed_cards), Color.Schell)):
#                 total -= 3
#             if (utils.contains_col_pair(list(state.hand_cards), Color.Rot) and
#                     not utils.contains_col_pair(list(passed_cards), Color.Rot)):
#                 total -= 4

#         # we would like to plan ourselves if possible, if we have 5 or more halves!
#         hand_halves = set([card for card in state.hand_cards if card in utils.pair_cards()])
#         if len(hand_halves) > 4:
#             total -= 3
#         if len(hand_halves) > 5:
#             total -= 3
#         if len(hand_halves) > 6:
#             total -= 3
#         if len(hand_halves) > 7:
#             total -= 3

#         # check overall value of hand cards given
#         for card in passed_cards:
#             if card.value > Value.Unter:
#                 total += 0.5

#         for card in hand_without_passed:
#             if card.value > Value.Unter:
#                 total -= 1

#         # try not to pass green if unnecessary
#         for card in passed_cards:
#             if card.color == Color.Gruen: total -= 0.5

#         return total

#     def passing_best(self, state: GameState) -> set[Card]:
#         """
#         calculate the best passing cards, based on the evaluations of all possible card combinations
#         for the 9 original hand cards it is (9 over 4) = 126 combinations to test
#         TODO add methods to reduce the combinations drastically beforehand
#         """
#         best_eval = -1000
#         best_set = None
#         for subset in combinations(state.hand_cards, 4):
#             eval_s = self.eval_passing(subset)
#             if best_eval < eval_s:
#                 best_eval = eval_s
#                 best_set = subset
#         return best_set

#     def evaluate_action(self, state: GameState, action: Action):
#         # evaluate the probable success of an action, this is where the knowledge of the game should be used
#         # for now, it's a placeholder and always returns 1
#         return 1

#     def _initialize_concepts(self, state: GameState):
#         """
#         Add every concept that we could need for decisions in our probabilistic policy
#         """
#         # First add basic concepts that just record actions of players
