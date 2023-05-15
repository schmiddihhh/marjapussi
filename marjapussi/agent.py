from marjapussi.game import MarjaPussi
from marjapussi.policy import Policy, RandomPolicy
from marjapussi.utils import Card, CARDS, all_color_cards, all_value_cards, cards_str, high_card, higher_cards, sorted_cards

from tqdm import trange
import logging
logging.basicConfig(format='%(levelname)s: %(message)s')

class Agent:
    """Implements an agent able to play Marjapussi."""
    def __init__(self, name: str, all_players: list[str], policy: Policy, start_cards: list[Card], custom_state_dict={}, log=False) -> None:
        self.name = name
        self.all_players = all_players
        self.policy = policy
        self.state: dict = {
            'player_num': all_players.index(name),
            'cards': start_cards,
            'provoking_history': [],
            'game_value': 115,
            'current_trick': [],
            'all_tricks': [],
            'points': {player: 0 for player in all_players},
            'possible_cards': {player: set() if player == name else set(CARDS[:]).difference(start_cards) for player in all_players},
            'secure_cards': {player: set(start_cards) if player == name else set() for player in all_players},
            'playing_player': '',
        }
        self.custom_state = custom_state_dict

        self.policy.start_hand(self.state['possible_cards'])

        self.logger = logging.getLogger("single_agent_logger")
        self.log = log
        if log:
            self.logger.setLevel(logging.INFO)
        if log == "DEBUG":
            self.logger.setLevel(logging.DEBUG)
        self.logger.info(f"Created Agent: {self}")

    def __str__(self):
        return f"<{self.name} Agent, {type(self.policy).__name__}>"

    def next_action(self, possible_actions):
        self.logger.debug(f"{self} selects action.")
        return self.policy.select_action(self.state, possible_actions)

    def observe_action(self, action):
        player_num, phase, val = action.split(',')
        player_num = int(player_num)
        partner_num = (player_num + 2) % 4
        player_name = self.all_players[player_num]

        if phase == 'TRCK':
            card_played = Card.from_str(val)
            self.state['current_trick'].append((player_name, card_played))
            if len(self.state['current_trick']) == 4:
                self.state['all_tricks'].append(self.state['current_trick'][:])
                if self.log:
                    self.logger.debug(f"AGENT {self} evals trick")
                self.state['possible_cards'] = self._possible_cards_after_trick(self.state['possible_cards'], self.state['current_trick'])
                self.state['current_trick'] = []

        if phase == 'PASS' or phase == "PBCK":
            card_pass = Card.from_str(val)
            self.state['secure_cards'][player_name].discard(card_pass)
            self.state['possible_cards'][player_name].discard(card_pass)
            self.state['secure_cards'][self.all_players[partner_num]].add(card_pass)
            self.state['possible_cards'][self.all_players[partner_num]].add(card_pass)
            self.state['possible_cards'][self.all_players[(partner_num + 1) % 4]].discard(card_pass)
            self.state['possible_cards'][self.all_players[(partner_num + 2) % 4]].discard(card_pass)

        if isinstance(val, Card) and not (phase == 'PASS' or phase == "PBCK"):
            assert val in self.state['possible_cards'][player_name] or val in self.state['secure_cards'][
                player_name], "Card has to be possible if it is played."
            for name in self.all_players:
                self.state['possible_cards'][name].discard(val)
                self.state['secure_cards'][name].discard(val)

            # let the policy observe the action as well
        self.policy.observe_action(self.state, action)

        self.logger.debug(f"{self} observed {action}.")

        if self.log == 'DEBUG':
            self._print_state()

    def _possible_cards_after_trick(self, possible_cards, trick):
        # This function will need to be updated to work with the Card class, but without knowing its implementation, it's hard to provide a correct refactoring.
        pass

        # Add a static method to the Card class for creating a Card instance from a string

    @staticmethod
    def card_from_string(card_str):
        color, value = card_str.split('-')
        return Card(color, value)

    def _print_state(self):
        print(f"State of {str(self)}:")
        print(f"cards: {', '.join(str(card) for card in self.state['cards'])}")
        print(f"points: {self.state['points']}")
        print(f"playing_player: {self.state['playing_player']}")
        print(f"possible cards:")
        for p, cards in self.state['possible_cards'].items():
            print(f"{p}:\t {', '.join(str(card) for card in sorted_cards(cards))}")
        print(f"secure cards:")
        for p, cards in self.state['secure_cards'].items():
            print(f"{p}:\t {', '.join(str(card) for card in sorted_cards(cards))}")
        print(self.state)

    def _possible_cards_after_trick(self, possible: dict, trick: list, sup_col='', first_trick=False) -> dict[str]:
        """Returns which player could have which cards after a trick.
        possible: dict with players and possible cards
        trick: list of tuples with (player, card)
        trump: color of trump [r|s|e|g]
        first_trick: whether the trick is the first trick
        """

        def remove_possibles(set, difflist):
            return set(set).difference(set(difflist))

        # remove played cards from possible cards
        cards_in_trick = set([elem[1] for elem in trick])
        for player in [elem[0] for elem in trick]:
            possible[player] = remove_possibles(possible[player], cards_in_trick)

        trick_col = trick[0][1].color
        trick_till_here = []

        # special rule for first trick
        if first_trick and trick[0][1].value != 'A':  # first trick needs to be an ace or green
            player = trick[0][0]
            possible[player] = remove_possibles(possible[player], all_value_cards('A'))
            if trick[0][1].color != 'g':
                possible[player] = remove_possibles(possible[player], all_color_cards('g'))

        # any trick
        for player, card in trick:
            if card.color != trick_col and card.color != sup_col:  # cant have same color and cant have trump
                possible[player] = remove_possibles(possible[player], all_color_cards(sup_col))
            if card.color != trick_col:  # cant have same color
                possible[player] = remove_possibles(possible[player], all_color_cards(trick_col))
            # cant have any card higher than the highest in the trick
            if trick_till_here and card != high_card(trick_till_here + [card]):
                possible[player] = remove_possibles(possible[player],
                                                    higher_cards(high_card(trick_till_here, up_col=sup_col),
                                                                 sup_col=sup_col,
                                                                 pool=possible[player]))
            trick_till_here.append(card)

        return possible

    def _standing_cards(self, player_name, possible: dict, player_hand: list, trump_suit='') -> list:
        """Returns all cards with which player_name could possibly win a trick."""
        standing_cards = []

        # If there's a trump suit, only the highest trump cards in hand are standing
        if trump_suit:
            trump_cards_in_hand = [card for card in player_hand if card.suit == trump_suit]
            if trump_cards_in_hand:
                highest_trump = max(trump_cards_in_hand, key=lambda card: card.rank)
                standing_cards.append(highest_trump)
            return standing_cards  # return early as no other cards can be standing

        # If no trump, check each suit in hand
        for suit in set(card.suit for card in player_hand):
            # Only consider cards in hand of this suit
            cards_in_hand = [card for card in player_hand if card.suit == suit]
            # Possible cards of this suit in the game
            possible_cards = possible.get(suit, [])

            # The highest card of the suit in hand that hasn't been played yet is standing
            highest_in_hand = max(cards_in_hand, key=lambda card: card.rank)
            if possible_cards:
                highest_possible = max(possible_cards, key=lambda card: card.rank)
                if highest_in_hand.rank >= highest_possible.rank:
                    standing_cards.append(highest_in_hand)

            # If there are fewer possible cards of this suit than in hand, all additional cards in hand are standing
            if len(cards_in_hand) > len(possible_cards):
                additional_cards = sorted(cards_in_hand, key=lambda card: card.rank, reverse=True)[
                                   :len(cards_in_hand) - len(possible_cards)]
                standing_cards.extend(additional_cards)

        return standing_cards


def test_agents(policy_A: Policy, policy_B: Policy, log_agent=False, log_game=False,
                rounds: int = 100, custom_rules: dict = {}) -> tuple[tuple[int, int], tuple[int, int]]:
    """
    Plays specified number of rounds and returns wins and losses of policy_A and policy_B.
    """
    print(f"Testing {type(policy_A).__name__} vs {type(policy_B).__name__} in {rounds} games.")
    player_numbers = [1, 2, 3, 4]  # 2,4 play with policy_A and 1,3 with policy_B
    results = [[0, 0], [0, 0]]

    for _ in trange(rounds, leave=False):
        testgame = MarjaPussi(
            player_numbers, log=log_game, fancy=True, override_rules=custom_rules)
        agents = {player.name:
                      Agent(player.name, [p.name for p in testgame.players],
                            policy_A if player.name % 2 == 0 else policy_B, player.cards, log=log_agent)
                  for player in testgame.players}

        while testgame.phase != "DONE":
            current_player, legal = testgame.player_at_turn.name, testgame.legal_actions()
            chosen_action = agents[current_player].next_action(legal)
            testgame.act_action(chosen_action)
            for agent in agents.values():
                agent.observe_action(chosen_action)
        res = testgame.end_info()
        playing_player = res['playing_player']
        players: list = res['players']
        if playing_player:
            playing_partner = players[(players.index(playing_player) + 2) % 4]
            points_pl = res['players_points'][playing_player] + res['players_points'][playing_partner]
            won = points_pl >= res['game_value']
            results[playing_player % 2][0 if won else 1] += 1
        # reorder players for next round
        players = players[1:] + [players[0]]

    party_A_played, party_A_won = sum(results[0]), results[0][0]
    party_B_played, party_B_won = sum(results[1]), results[1][0]
    try:
        print(
            f"{type(policy_A).__name__} took {party_A_played}/{rounds}={party_A_played * 100.0 / rounds:.2f}% games " +
            f"and won {party_A_won}/{party_A_played}={party_A_won * 100.0 / party_A_played:.2f}%.")
        print(
            f"{type(policy_B).__name__} took {party_B_played}/{rounds}={party_B_played * 100.0 / rounds:.2f}% games " +
            f"and won {party_B_won}/{party_B_played}={party_B_won * 100.0 / party_B_played:.2f}%.")
    except:
        print("!!! Not enough games for sensical evaluation!")
    return (tuple(results[0]), tuple(results[1]))


