from marjapussi.card import Card, Deck, Color, Value
from marjapussi.trick import Trick
from marjapussi.action import Talk, Action
from marjapussi.utils import higher_cards, all_color_cards, all_value_cards, standing_in_suite
from marjapussi.concept import Concept, ConceptStore


class GameState:
    def __init__(self, name: str, all_players: list[str], start_cards: list[Card]):
        self.name = name
        self.player_num = all_players.index(name)  # the player with index 0 is always first
        self.provoking_history: list[Action] = []
        self.game_value = 115
        self.current_trick = Trick()
        self.playing_party = None
        self.all_tricks = []
        self.concepts: ConceptStore = ConceptStore()
        self.points = {player: 0 for player in all_players}
        self.possible_cards = {player: set() if player == name else set(Deck().cards).difference(start_cards)
                               for player in all_players}
        self.possible_cards_probabilities = {player: set() if player == name else
                                             set(Deck().cards).difference(start_cards) for player in all_players}
        self.secure_cards = {player: set(start_cards) if player == name else set() for player in all_players}
        self.playing_player = ''
        self.asking_status = {player: 0 for player in all_players}
        self.all_players = all_players
        self.actions: list[Action] = []
        self.phase = 'PROV'
        self.cards_left = set(Deck().cards)
        self.player_cards_left: list[int] = [int(len(self.cards_left) / len(self.all_players)) for i in
                                             range(len(self.all_players))]

    def _set_secure_card(self, card: Card, player_name: str) -> None:
        self.secure_cards[player_name].add(card)
        for player in self.all_players:
            self.possible_cards[player].discard(card)

    def play_card(self, card_played: Card, player_num: int):
        # do the action on the agents representation of the trick
        player_name = self.all_players[player_num]
        assert card_played in self.possible_cards[player_name] | self.secure_cards[player_name], \
            "Card has to be possible if it is played."
        self.current_trick.play_card(card_played, player_num)

        # remove the card played from all players, it is no longer in the game
        self.cards_left.discard(card_played)
        self.player_cards_left[player_num] -= 1
        for player in self.all_players:
            self.possible_cards[player].discard(card_played)
            self.secure_cards[player].discard(card_played)

        # apply game logic to deduct what is still possible for that player
        self._possible_player_cards(player_name, self.current_trick)

        # apply game logic to deduct information from players pairs and halves in combination with the played card
        self._pair_concepts_check(player_name, card_played)

        # apply set logic, to deduct if there are only those combinations left that leave nothing to the imagination
        self._set_logic_check()

        # update to new trick for next Phase after 4th card was played
        if self.current_trick.get_status() == 4:
            self.all_tricks.append(self.current_trick)
            self.current_trick = Trick(self.current_trick.trump_color)
        else:
            self.current_trick = self.current_trick

    def provoke(self, action: Action):
        if action.content > 0:
            self.game_value = action.content
        self.provoking_history.append(action)

    def pass_card(self, card_pass: Card, player_name: str, player_num: int, partner_num: int):
        self.secure_cards[player_name].discard(card_pass)
        self.possible_cards[player_name].discard(card_pass)
        self._set_secure_card(card_pass, self.all_players[partner_num])
        self.possible_cards[self.all_players[(player_num + 1) % 4]].discard(card_pass)
        self.possible_cards[self.all_players[(partner_num + 1) % 4]].discard(card_pass)

    def ask_question(self, pronoun: str, player_name: str):
        match pronoun:
            case "our":
                self.asking_status[player_name] = 2
            case "yours":
                self.asking_status[player_name] = 1

    def remove_possibles(self, player_name, diff_list: list[Card] | set[Card]) -> None:
        self.possible_cards[player_name] = self.possible_cards[player_name].difference(set(diff_list))

    def answer_question(self, answer: Talk, player_name: str):
        match answer.pronoun:
            case "nmy":
                self.concepts.add(Concept(f"{player_name}_has_no_pair",
                                          {"player": player_name, "info_type": "no_pair"}))
            case "no":
                pair = {Card(answer.color, Value.Koenig), Card(answer.color, Value.Ober)}
                self.remove_possibles(player_name, pair)
            case "my":
                # we know now exactly where these two cards are!
                self._set_secure_card(Card(answer.color, Value.Koenig), player_name)
                self._set_secure_card(Card(answer.color, Value.Ober), player_name)
                self.current_trick.trump_color = answer.color
                self.concepts.add(Concept(f"{player_name}_has_{answer.color}_pair",
                                          {"color": answer.color, "player": player_name, "info_type": "no_pair"}))
            case "ou":
                pair = {Card(answer.color, Value.Koenig), Card(answer.color, Value.Ober)}
                poss_update = self.possible_cards[player_name].intersection(pair)
                if len(poss_update) == 1:
                    self._set_secure_card(poss_update.pop(), player_name)
                else:
                    self.concepts.add(Concept(f"{player_name}_has_{str(answer.color)}_half",
                                              {"color": answer.color, "player": player_name, "info_type": "half"}))
        self._set_logic_check()

    def announce_ansage(self, ansage: Talk, player_name: str):
        pair = {Card(ansage.color, Value.Koenig), Card(ansage.color, Value.Ober)}
        match ansage.pronoun:
            case 'we':
                poss_update = (self.possible_cards[player_name] | self.secure_cards[player_name]).intersection(pair)
                if len(poss_update) == 1:
                    self.remove_possibles(player_name, pair)
                    self.secure_cards[player_name].add(poss_update.pop())
                self.current_trick.trump_color = ansage.color
            case 'nwe':
                self.remove_possibles(player_name, pair)
        self._set_logic_check()

    def _possible_player_cards(self, player_name, trick: Trick) -> None:
        """
        player_name: The player who is investigated and updated depending their possible cards they still have
        trick: The trick he just played a card on, the last card is the players card
        """

        trick_col = trick.base_color
        trump = trick.trump_color
        card = trick.cards[-1]

        # first card of first trick needs to be an ace or green, else the player has neither
        if not self.all_tricks and trick.get_status() == 1:
            if card.value != Value.Ass:
                self.remove_possibles(player_name, all_value_cards(Value.Ass))
                if card.color != Color.Gruen:
                    self.remove_possibles(player_name, all_color_cards(Color.Gruen))

        # need to always go higher if possible, matching base color first, else the player has no higher cards
        if card.color == trick_col:
            # if it's a trump color trick or there is no trump, played cards needs to be high
            if card != trick.high_card and (trump and (trick_col == trump or trick.high_card.color != trump)):
                self.remove_possibles(player_name, higher_cards(trick, card_pool=all_color_cards(trick_col)))

        else:  # player can't have same color
            self.remove_possibles(player_name, all_color_cards(trick_col))
            if trump:
                if card.color == trump:
                    if card != trick.high_card:  # card needs to be high
                        self.remove_possibles(player_name, higher_cards(trick, card_pool=all_color_cards(trump)))
                else:  # also doesn't have trump
                    self.remove_possibles(player_name, all_color_cards(trump))

    def _pair_concepts_check(self, player_name: str, played_card: Card) -> None:
        """
        We check all possible cards and secure cards to see if we can combine information with what we know
        from calls about pairs and halves to deduct further implications
        """
        p_val = played_card.value
        p_col = played_card.color
        if (p_val == Value.Ober) | (p_val == Value.Koenig):
            other_val = Value.Koenig if p_val == Value.Ober else Value.Ober
            other_card = Card(p_col, other_val)
            for player in self.all_players:
                # check for half calls
                for concept in self.concepts.get_all_by_properties({"color": p_col,
                                                                    "player": player, "info_type": "half"}):
                    # we could either have the concept that the player has or doesn't have a half
                    if concept.name == f"{player}_has_{str(p_col)}_half":
                        # if it's the one who played we remove that, else we now know the specific card!
                        if player_name == player:
                            self.concepts.remove(concept.name)
                        else:
                            if not (other_card in self.possible_cards[player] | self.secure_cards[player]):
                                raise ValueError(f"{player} announced a card {str(other_card)} but doesn't posses one.")
                            self._set_secure_card(Card(p_col, other_val), player)
            # check for no pair calls
            if self.concepts.get_by_name(f"{player_name}_has_no_pair"):
                if not self.concepts.get_by_name(f"{player_name}_has_{played_card.color}_pair"):
                    self.remove_possibles(player_name, [other_card])
            # after this, the pair can't be in one hand anymore!
            self.concepts.remove(f"{player_name}_has_{played_card.color}_pair")

    def _set_logic_check(self):
        """ruling out possible cards by simple set logic:"""
        player_count = len(self.all_players)
        updated = False
        while True:
            poss_card_counts = [self.player_cards_left[player_num] -
                                len(self.secure_cards[self.all_players[player_num]])
                                for player_num in range(player_count)]
            possible_cards = [self.possible_cards[player] for player in self.all_players]

            for i in range(player_count):
                # check for cards that are only possible for one player:
                only_for_i = possible_cards[i] - possible_cards[(i + 1) % 4] - \
                             possible_cards[(i + 2) % 4] - possible_cards[(i + 3) % 4]
                if only_for_i:
                    updated = True
                    for card in only_for_i:
                        self._set_secure_card(card, self.all_players[i])

                # check if there is a possible card set, that is equal in size to the amount of cards the player has
                if poss_card_counts[i] != 0 and len(possible_cards[i]) == poss_card_counts[i]:
                    updated = True
                    while possible_cards[i]:
                        self._set_secure_card(possible_cards[i].pop(), self.all_players[i])
            if not updated:
                break
            else:
                updated = False

    def standing_cards(self, player_name: str = None, trump: Color = '') -> set[Card]:
        """Returns all cards for the player_name (by default state owner) which can or could win the trick."""
        standing_cards = set()
        if player_name is None:
            player_name = self.name

        potential_player_hand = self.secure_cards[player_name] | self.possible_cards[player_name]
        # If there's a trump suit, only the highest trump cards in hand are standing
        if trump:
            trump_cards_in_hand = [card for card in potential_player_hand if card.suit == trump]
            return standing_in_suite(self.cards_left, trump, potential_player_hand)

        # If no trump, check each suit in hand
        for suit in set(card.suit for card in potential_player_hand):
            # Only consider cards in hand of this suit
            suit_hand_cards = set([card for card in potential_player_hand if card.color == suit])
            standing_cards |= standing_in_suite(self.cards_left, suit, suit_hand_cards)

        return standing_cards

    def partner(self, player_name: str = None) -> str:
        """Returns the partners name for a given player. Without input returns the partner of the gamestate owner"""
        if not player_name:
            player_name = self.name
        p_index = self.all_players.index(player_name)
        return self.all_players[(p_index + 2) % 4]
