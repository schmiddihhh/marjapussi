from marjapussi.card import Card, Deck, Color, Value
from marjapussi.trick import Trick
from itertools import combinations
import math

text_format = {"r": "\033[91m", "s": "\033[93m", "e": "\033[96m", "g": "\033[92m",
               "end": "\033[0m", "bold": "\033[1m", "uline": "\033[4m"}


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


def _calc_sets_possibilities(x: list[int], v: list[int]) -> int:
    """
    x: list of set sizes
    v: list of restriction set sizes
    """
    n = sum(x)
    v_fact_multi = math.prod([math.factorial(vx) for vx in v])
    binomial_sum = 0
    for i in range(v[0]):
        for j in range(v[1]):
            binomial_sum += math.comb(x[1] + x[2], v[0]) * \
                         math.comb(x[0] + x[2] - j, v[1]) * \
                         math.comb(x[0] + x[1] - v[0] + j - i, v[2])
    return math.factorial(n - sum(v)) * v_fact_multi * binomial_sum


def calculate_set_in_3set_probability(possible_sets: list[set[Card]], set_sizes: list[int],
                                      test_set: set[Card], target_set: int) -> float:
    """
    we calculate the probability, that the test_set is in the possible_sets with index target_set
    with the given set_sizes, thanks Andreas for helping out with this!
    maybe we could also make this function work for an arbitrary amount of sets other than 3 later if necessary
    """
    union_set = set()
    total_card_amount = len(union_set)
    assert total_card_amount == sum(set_sizes), "the total amount of possible cards needs to exactly fit in the sets"
    assert len(possible_sets) == 3, "this function only works for 3 sets at a time"
    assert len(set_sizes) == 3, "this functions inputs need to match length, which is the amount of sets that is 3"
    assert target_set in range(3), "the target set needs to be an index within range of the provided sets! 0, 1 or 2"

    for poss_set in possible_sets:
        union_set |= poss_set
    diff_sets = [union_set.difference(poss_set) for poss_set in possible_sets]

    # Let's first rule out the problem cases:
    if not test_set.issubset(possible_sets[target_set]):
        return 0.
    if len(test_set) > set_sizes[target_set]:
        return 0.

    # first we calculate the possible configurations for the restrictions each set has
    v = [len(diff_set) for diff_set in diff_sets]
    x = set_sizes
    set_possibilities = _calc_sets_possibilities(x, v)

    # Now we calculate the possibilities, if we already distributed the test_set
    test_set_possible_distribs = math.comb(x[target_set], len(test_set))
    new_union_set = union_set.difference(test_set)
    x[target_set] -= len(test_set)
    new_poss_sets = [poss_set.difference(test_set) for poss_set in possible_sets]
    new_diff_sets = [new_union_set.difference(poss_set) for poss_set in new_poss_sets]
    v = [len(diff_set) for diff_set in new_diff_sets]
    set_possibilities_restrict = test_set_possible_distribs * _calc_sets_possibilities(x, v)

    return set_possibilities_restrict / set_possibilities


def standing_in_suite(leftover_cards: set[Card], color: Color, possible_cards: set[Card]) -> set[Card]:
    """returns all cards of color that are standing in the possible_cards belonging to the player with player_num"""
    # first, we need to sort the cards of the color we want to check
    col_cards = sorted_cards([card for card in possible_cards if card.color == color])
    col_cards.reverse()
    all_col_cards_left = sorted_cards([card for card in leftover_cards if card.color == color])
    all_col_cards_left.reverse()
    majority = len(col_cards) >= len(all_col_cards_left)/2
    standing = []
    for card in col_cards:
        stand_nr = len(standing)
        if not majority:
            if card == all_col_cards_left[stand_nr]:
                standing.append(card)
            else:
                break
        else:
            no_higher_zone = all_col_cards_left[stand_nr:(2*stand_nr+1)]
            if card in no_higher_zone:
                standing.append(card)
            else:
                break

    return set(standing)


def gruen_pair() -> set[Card]:
    return {Card(Color.Gruen, Value.Koenig), Card(Color.Gruen, Value.Ober)}


def eichel_pair() -> set[Card]:
    return {Card(Color.Gruen, Value.Koenig), Card(Color.Gruen, Value.Ober)}


def schell_pair() -> set[Card]:
    return {Card(Color.Schell, Value.Koenig), Card(Color.Schell, Value.Ober)}


def rot_pair() -> set[Card]:
    return {Card(Color.Schell, Value.Koenig), Card(Color.Schell, Value.Ober)}


def small_pair() -> set[Card]:
    return gruen_pair() | eichel_pair()


def big_pair() -> set[Card]:
    return schell_pair() | rot_pair()


def pair() -> set[Card]:
    return small_pair() | big_pair()


def generate_subsets(set_elements: set, subset_size: int) -> list[set]:
    subsets = []
    for subset in combinations(set_elements, subset_size):
        subsets.add(set(subset))
    return subsets


def small_halves() -> list[set[Card]]:
    return [subset for subset in generate_subsets(small_pair(), 2) if subset not in [gruen_pair(), eichel_pair()]]


def big_halves() -> list[set[Card]]:
    return [subset for subset in generate_subsets(big_pair(), 2) if subset not in [schell_pair(), rot_pair()]]


def three_halves() -> list[set[Card]]:
    all_3_halves = generate_subsets(pair(), 3)
    pairs = [gruen_pair(), eichel_pair(), schell_pair(), rot_pair()]
    return [subset for subset in all_3_halves if not any(p.issubset(subset) for p in pairs)]


