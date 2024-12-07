from marjapussi.game import MarjaPussi
from marjapussi.policy import Policy
from marjapussi.utils import Card, sorted_cards
from marjapussi.action import Action, Talk
from marjapussi.gamestate import GameState

from tqdm import trange
import logging

logging.basicConfig(format='%(levelname)s: %(message)s')


class Agent:
    """Implements an agent able to play Marjapussi."""
    def __init__(self, name: str, all_players: list[str], policy: Policy, start_cards: list[Card], log=False) -> None:
        self.name = name
        self.all_players = all_players
        self.state = GameState(name, all_players, start_cards)
        self.policy = policy
        self.policy.game_start(self.state)
        self.logger = logging.getLogger("single_agent_logger")
        self.log = log
        if log:
            self.logger.setLevel(logging.INFO)
        if log == "DEBUG":
            self.logger.setLevel(logging.DEBUG)
        self.logger.info(f"Created Agent: {self}")

    def __str__(self):
        return f"<{self.name} Agent, {type(self.policy).__name__}>"

    def next_action(self, possible_actions: list[Action]):
        self.logger.debug(f"{self} selects action.")
        return self.policy.select_action(self.state, possible_actions)

    def observe_action(self, action: Action) -> None:
        """
        Updates the players knowledge about possible and secure cards solely based on the game rules
        This is done after any Action is called out
        """
        # simplify variable names for current context
        player_num = action.player_number
        partner_num = (player_num + 2) % 4
        player_name = self.all_players[player_num]
        self.state.phase = action.phase
        match action.phase:
            case 'TRCK':  # do the action on the agents representation of the trick
                card_played: Card = action.content
                self.state.play_card(card_played, player_num)

            case 'PASS' | 'PBCK':
                card_pass = action.content
                if action.phase == 'PASS':
                    self.state.playing_party = [player_num, partner_num]
                if self.state.player_num in self.state.playing_party:
                    self.state.pass_card(card_pass, player_name, player_num, partner_num)

            case 'QUES':
                question: Talk = action.content
                self.state.ask_question(question.pronoun, player_name)

            case 'ANSW':
                answer: Talk = action.content
                self.state.answer_question(answer, player_name)

            case 'ANSA':
                ansage: Talk = action.content
                self.state.announce_ansage(ansage, player_name)

            case 'PROV':
                self.state.provoke(action)

        # let the policy observe the action as well
        self.policy.observe_action(self.state, action)

        self.state.actions.append(action)

        self.logger.debug(f"{self} observed {action}.")

        if self.log == 'DEBUG':
            self._print_state()

    def _print_state(self):
        print(f"State of {str(self)}:")
        print(f"cards: {', '.join(str(card) for card in self.state.secure_cards)}")
        print(f"points: {self.state.points}")
        print(f"playing_player: {self.state.playing_player}")
        print(f"possible cards:")
        for p, cards in self.state.possible_cards.items():
            print(f"{p}:\t {', '.join(str(card) for card in sorted_cards(cards))}")
        print(f"secure cards:")
        for p, cards in self.state.secure_cards.items():
            print(f"{p}:\t {', '.join(str(card) for card in sorted_cards(cards))}")
        print(self.state)


def test_agents(policy_a: Policy, policy_b: Policy, log_agent=False, log_game=False,
                rounds: int = 100, custom_rules: dict = None) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """
    Plays specified number of rounds and returns wins and losses of policy_A and policy_B.
    """
    print(f"Testing {type(policy_a).__name__} vs {type(policy_b).__name__} in {rounds} games.")
    players = ['0', '1', '2', '3']  # 0,2 play with policy_A and 1,3 with policy_B
    results = [[0, 0], [0, 0]]
    if not custom_rules:
        custom_rules = {}

    for _ in trange(rounds, leave=False):
        test_game = MarjaPussi(players, log=log_game, fancy=True, override_rules=custom_rules)
        agents = {player.name: Agent(player.name, [p.name for p in test_game.players],
                                     policy_a if int(player.name) % 2 == 0 else policy_b, player.cards, log=log_agent)
                  for player in test_game.players}

        while test_game.phase != "DONE":
            current_player, legal = test_game.player_at_turn.name, test_game.legal_actions()
            chosen_action = agents[current_player].next_action(legal)
            test_game.act_action(chosen_action)
            for agent in agents.values():
                agent.observe_action(chosen_action)
        res = test_game.end_info()
        playing_player = res['playing_player']
        players: list = res['players']
        if playing_player:
            playing_partner = players[(players.index(playing_player) + 2) % 4]
            points_pl = res['players_points'][playing_player] + res['players_points'][playing_partner]
            won = points_pl >= res['game_value']
            results[int(playing_player) % 2][0 if won else 1] += 1
        # reorder players for next round
        players = players[1:] + [players[0]]

    party_a_played, party_a_won = sum(results[0]), results[0][0]
    party_b_played, party_b_won = sum(results[1]), results[1][0]
    try:
        print(
            f"{type(policy_a).__name__} took {party_a_played}/{rounds}={party_a_played * 100.0 / rounds:.2f}% games " +
            f"and won {party_a_won}/{party_a_played}={party_a_won * 100.0 / party_a_played:.2f}%.")
        print(
            f"{type(policy_b).__name__} took {party_b_played}/{rounds}={party_b_played * 100.0 / rounds:.2f}% games " +
            f"and won {party_b_won}/{party_b_played}={party_b_won * 100.0 / party_b_played:.2f}%.")
    except:
        print("!!! Not enough games for sensical evaluation!")
    return tuple(results[0]), tuple(results[1])
