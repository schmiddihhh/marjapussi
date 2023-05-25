from marjapussi.card import Card, Deck, Color, Value
from marjapussi.trick import Trick
from marjapussi.action import Talk, Action
from marjapussi.utils import higher_cards, all_color_cards, all_value_cards


class GameState:
    def __init__(self, name: str, all_players: list[str], start_cards: list[Card]):
        self.name = name
        self.player_num = all_players.index(name)  # the player with index 0 is always first
        self.provoking_history: list[Action] = []
        self.game_value = 115
        self.current_trick = Trick()
        self.playing_party = None
        self.all_tricks = []
        self.points = {player: 0 for player in all_players}
        self.possible_cards = {player: set() if player == name else set(Deck().cards).difference(start_cards)
                               for player in all_players}
        self.secure_cards = {player: set(start_cards) if player == name else set() for player in all_players}
        self.playing_player = ''
        self.asking_status = {player: 0 for player in all_players}
        self.all_players = all_players
        self.actions: list[Action] = []
        self.phase = 'PROV'
        self.cards_left = set(Deck().cards)

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
        for player in self.all_players:
            self.possible_cards[player].discard(card_played)
            self.secure_cards[player].discard(card_played)

        copy = self.possible_cards[player_name].copy()
        copy2 = self.secure_cards[player_name].copy()
        # apply game logic to deduct what is still possible
        self.possible_cards[player_name] = self._possible_player_cards_after_card_played(
            self.possible_cards[player_name], self.current_trick)

        assert len(self.possible_cards[player_name] | self.secure_cards[player_name]) >= 8 - len(self.all_tricks), \
            f"{[str(card) for card in self.possible_cards[player_name]]} and " \
            f"{[str(card) for card in self.secure_cards[player_name]]} \n" \
            f"{[str(card) for card in copy]} and " \
            f"{[str(card) for card in copy2]}"

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
        self.secure_cards[self.all_players[partner_num]].add(card_pass)
        self.possible_cards[self.all_players[partner_num]].add(card_pass)
        self.possible_cards[self.all_players[(player_num + 1) % 4]].discard(card_pass)
        self.possible_cards[self.all_players[(partner_num + 1) % 4]].discard(card_pass)

    def ask_question(self, pronoun: str, player_name: str):
        match pronoun:
            case "our": self.asking_status[player_name] = 2
            case "yours": self.asking_status[player_name] = 1

    def answer_question(self, answer: Talk, player_name: str):
        match answer.pronoun:
            case "nmy":
                pass
                # TODO add concept of having no pair for deducting cards!
            case "no":
                pair = {Card(answer.color, Value.Koenig), Card(answer.color, Value.Ober)}
                self.possible_cards[player_name] = self.possible_cards[player_name].difference(pair)
            case "my":
                # we know now exactly where these two cards are!
                self._set_secure_card(Card(answer.color, Value.Koenig), player_name)
                self._set_secure_card(Card(answer.color, Value.Ober), player_name)
                self.current_trick.trump_color = answer.color
            case "ou":
                pair = {Card(answer.color, Value.Koenig), Card(answer.color, Value.Ober)}
                poss_update = self.possible_cards[player_name].intersection(pair)
                if len(poss_update) == 1:
                    self._set_secure_card(poss_update.pop(), player_name)

    def announce_ansage(self, ansage: Talk, player_name: str):
        pair = {Card(ansage.color, Value.Koenig), Card(ansage.color, Value.Ober)}
        match ansage.pronoun:
            case 'we':
                poss_update = (self.possible_cards[player_name] | self.secure_cards[player_name]).intersection(pair)
                if len(poss_update) == 1:
                    self.possible_cards[player_name] = self.possible_cards[player_name].difference(pair)
                    self.secure_cards[player_name].add(poss_update.pop())
                self.current_trick.trump_color = ansage.color
            case 'nwe':
                self.possible_cards[player_name] = self.possible_cards[player_name].difference(pair)

    def _possible_player_cards_after_card_played(self, poss: set[Card], trick: Trick) -> set[Card]:
        """
        possible_before: the possible cards the player who played the last could have had before he played that card
        trick: The trick he just played a card on, the last card is the players card
        """
        def remove_possibles(in_set: set[Card], diff_list: list[Card]) -> set[Card]:
            return in_set.difference(set(diff_list))

        trick_col = trick.base_color
        trump = trick.trump_color
        card = trick.cards[-1]

        # first card of first trick needs to be an ace or green, else the player has neither
        if not self.all_tricks and trick.get_status() == 1:
            if card.value != Value.Ass:
                poss = remove_possibles(poss, all_value_cards(Value.Ass))
                if card.color != Color.Gruen:
                    poss = remove_possibles(poss, all_color_cards(Color.Gruen))

        # need to always go higher if possible, matching base color first, else the player has no higher cards
        if card.color == trick_col:
            # if it's a trump color trick or there is no trump, played cards needs to be high
            # trumpfstich
            # farbstich ohne trumpf gespielt
            if card != trick.high_card and (trump and (trick_col == trump or trick.high_card.color != trump)):
                poss = remove_possibles(poss, higher_cards(trick, card_pool=all_color_cards(trick_col)))

        else:  # player can't have same color
            poss = remove_possibles(poss, all_color_cards(trick_col))
            if trump:
                if card.color == trump:
                    if card != trick.high_card:  # card needs to be high
                        poss = remove_possibles(poss, higher_cards(trick, card_pool=all_color_cards(trump)))
                else:  # also doesn't have trump
                    poss = remove_possibles(poss, all_color_cards(trump))
        return poss

