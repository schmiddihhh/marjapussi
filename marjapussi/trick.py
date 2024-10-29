from marjapussi.card import Card, Color


class Trick:
    """
    Holds information about a trick in the game
    If the trick hasn't been started yet, high card, and player number are -1 and the base color is set to None
    """
    def __init__(self, trump_color: Color = None):
        self.cards: list[Card] = []
        self.trump_color = trump_color
        self.base_color: Color | None = None
        self.starting_player_num: int = -1
        self.high_card: Card | None = None
        self.high_card_idx: int = -1

    def play_card(self, card: Card, player_num: int = -1):
        """
        Adds a card to the trick and updates information about the trick like the highest card or the base color
        """
        if self._is_valid_play():
            self.cards.append(card)
            self.high_card = self._high_card()
            self.high_card_idx = self._high_card_idx()
            if self.get_status() == 1:
                self.base_color = self.cards[0].color
                self.starting_player_num = player_num
        else:
            raise ValueError("Too many cards for one trick")

    def _is_valid_play(self):
        return self.get_status() < 4

    def get_status(self) -> int:
        """
        returns how many cards have been played so far
        0 - the trick is initilized
        1-3 - the trick is ongoing
        4 - the trick is finished
        """
        return len(self.cards)

    def _high_card(self) -> Card | None:
        """returns the current winning card of the trick counting from first card played"""
        num_cards = len(self.cards)
        if num_cards == 0:
            return None
        trump_cards = [card for card in self.cards if card.color == self.trump_color]
        if trump_cards:
            return max(trump_cards, key=lambda card: card.value)
        else:
            return max(self.cards, key=lambda card: (card.color == self.base_color, card.value))

    def _high_card_idx(self) -> int:
        high_card = self.high_card
        if self.high_card:
            return self.cards.index(high_card)
        else:
            return -1
