from marjapussi.card import Card, Deck, Color, Value
from marjapussi.trick import Trick

text_format = {"r": "\033[91m", "s": "\033[93m", "e": "\033[96m", "g": "\033[92m",
               "end": "\033[0m", "bold": "\033[1m", "uline": "\033[4m"}

faculties

def allowed_first(cards: list[Card]) -> list[Card]:
    """Filters cards by allowed first: First player has to play an ace, green or any card."""
    allowed = [c for c in cards if c.value == Value.Ass]
    if not allowed:
        allowed = [c for c in cards if c.color == Color.Gruen]
    if not allowed:
        allowed = cards[:]
    return allowed


def allowed_general(hand: list[Card], trick: Trick, first=False) -> list[Card]:
    """Sorts which cards are allowed to be played from the hand right now"""
    if trick.get_status() == 0 and first:
        return allowed_first(hand)
    if trick.get_status() == 0:
        return hand

    if first:
        # check for ace
        ace = next((card for card in hand if card.color == trick.base_color and card.value == Value.Ass), None)
        if ace:
            return [ace]

    # need to play base_color first, then trump and then any. Needs to go also higher than previous trick cards
    allowed = [card for card in hand if card.color == trick.base_color]
    if not allowed and trick.trump_color:
        allowed = [card for card in hand if card.color == trick.trump_color]
    high_cards = higher_cards(trick, allowed)
    if high_cards:
        allowed = high_cards

    return allowed if allowed else hand


def higher_cards(trick: Trick, card_pool: list[Card] | set[Card] = None) -> list[Card]:
    """Returns all cards out of the pool that would win the given trick."""
    # default: Check all cards for higher cards
    if card_pool is None:
        card_pool = Deck().cards
    if trick.get_status():
        # trick is trump color trick
        if trick.trump_color == trick.base_color:
            return [c for c in card_pool if trick.base_color == c.color and c.value > trick.high_card.value]
        # trick has been taken over by trump, but with different base color, can only be beaten by trump
        elif trick.trump_color == trick.high_card.color:
            return [c for c in card_pool if (c.color == trick.trump_color and c.value > trick.high_card.value)]
        # a true base color trick
        else:
            return [c for c in card_pool if (trick.base_color == c.color and c.value > trick.high_card.value)
                    or c.color == trick.trump_color]
    else:
        return card_pool


def contains_col_pair(cards: list[Card], col: Color) -> bool:
    """Checks cards for the pair of specified Color"""
    return any(c.color == col and c.value == Value.Koenig for c in cards) and any(
        c.color == col and c.value == Value.Ober for c in cards)


def contains_col_half(cards: list[Card], col: Color) -> bool:
    """Checks cards for one half of pair of specified Color"""
    return any(card.color == col and (card.value == Value.Koenig or card.value == Value.Ober) for card in cards)


def sorted_cards(cards: list[Card]) -> list[Card]:
    return sorted(cards, key=lambda card: (card.color, card.value))


def all_color_cards(col: Color) -> list[Card]:
    """Returns all cards with given color."""
    return [Card(col, v) for v in Value]


def all_value_cards(value: Value) -> list[Card]:
    """Returns all cards with given type."""
    return [Card(c, value) for c in Color]


def card_str(card: Card, fancy=True) -> str:
    return text_format[str(card.color)] + str(card) + text_format["end"] if fancy else str(card)


def cards_str(cards: list[Card], fancy=True) -> str:
    return " ".join([card_str(card, fancy=fancy) for card in cards])


def color_str(col: Color, fancy=True) -> str:
    return text_format[str(col)] + col.fancy_name() + text_format["end"] if fancy else col.fancy_name


def bold_str(s: str, fancy=True) -> str:
    return text_format["bold"] + s + text_format["end"] if fancy else s


def _calculate_set_probability(possible_sets: list[set[Card]], set_sizes: list[int],
                               test_set: set[Card], target_set: int) -> float:
    # TODO: insert set calculations (thanks for helping with this part Andreas Berger aka Wurzelfreak)
    pass


def standing_in_suite(leftover_cards: set[Card], color: Color, possible_cards: set[Card]) -> set[Card]:
    """returns all cards of color that are standing in the possible_cards belonging to the player with player_num"""
    # first, we need to sort the cards of the color we want to check
    col_cards = sorted_cards([card for card in possible_cards if card.color == color])
    col_cards.reverse()
    all_col_cards_left = sorted_cards([card for card in leftover_cards if card.color == color])
    all_col_cards_left.reverse()
    standing = []
    for card in col_cards:
        stand_nr = len(standing)
        no_higher_zone = all_col_cards_left[stand_nr:(2*stand_nr+1)]
        if card in no_higher_zone:
            standing.append(card)
        else:
            break

    return set(standing)
