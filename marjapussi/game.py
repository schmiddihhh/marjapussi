from random import shuffle
import marjapussi.utils as utils
from marjapussi.player import Player
from marjapussi.card import Card, Deck, Color
from marjapussi.action import Action, Talk
from marjapussi.trick import Trick

import logging
logging.basicConfig(format='%(levelname)s: %(message)s')


class MarjaPussi():
    """Implements a single game of MarjaPussi."""

    DEFAULT_RULES = {
        "start_game_value": 115,
        "max_game_value": 420,
        "points": {symb: val for symb, val in zip("rsegAZKOU9876L", [100, 80, 60, 40, 11, 10, 4, 3, 2, 0, 0, 0, 0, 20])},
        "start_phase": "PROV",
    } # TODO swap this for a centralised GameRules class

    def __init__(self, player_names: list[str], override_rules =None, log= True, fancy=True, language=1) -> None:
        # init logger
        self.logger = logging.getLogger("single_game_logger")
        if log:
            self.logger.setLevel(logging.INFO)
        if log == "DEBUG":
            self.logger.setLevel(logging.DEBUG)
        self.fancy = fancy
        self.language = language
        # init rules
        if not override_rules:
            override_rules = {}
        self.rules = MarjaPussi.DEFAULT_RULES | override_rules
        self.logger.debug(f"Ruleset: {override_rules}")
        # init players and cards
        assert len(player_names) == 4, "There have to be 4 names!"
        deck = Deck()
        shuffle(deck.cards)
        self.players = [Player(name, num, self.rules["points"])
                        for num, name in enumerate(player_names)]
        # only used for logging
        self.players_dict = {player.number: player for player in self.players}
        while deck.cards:
            for p in self.players:
                p.give_card(deck.cards.pop())
        for player in self.players:
            self.logger.debug(
                f"{player.name}: {utils.cards_str(player.cards, fancy=self.fancy)}")
        self.logger.info(MarjaPussi.INFO_MSG["got_their_cards"][self.language])

        for i in range(4):
            self.players[i].set_partner(self.players[(i+2) % 4])
            self.players[i].set_next_player(self.players[(i+1) % 4])

        self.original_cards = {p.name: [card for card in p.cards] for p in self.players}  # Change this line
        self.player_at_turn: Player = self.players[0]
        self.playing_player: Player | None = None
        self.game_value = self.rules["start_game_value"]
        self.no_one_plays = True
        self.phase = self.rules["start_phase"]
        self.passed_cards = {"forth": [], "back": []}
        self.all_actions: list[Action] = []
        self.trump: Color | None = None
        self.all_trump: list[Color] = []
        self.tricks: list[Trick] = [Trick()]
        self.card_pool = Deck()

    def legal_actions(self) -> list[Action]:
        """
        phases:
        PROV - provoking
        PASS - Passing 4 cards forward
        PBCK - Pushing 4 cards back
        PRMO - Increasing to game value
        FTRI - UNKNOWN, NOT USED?!
        QUES - Asking for pairs or halves
        ANSW - Answering for pairs and halves
        ANSS - Answering if questioning player too has a half
        TRCK - Playing cards into the Trick
        DONE - After the game is done
        """
        legal_in_phase = {
            "PROV": self.legal_prov,
            "PASS": self.legal_pass,
            "PBCK": self.legal_passing_back,
            "PRMO": self.legal_prmo,
            "QUES": self.legal_ques,  # also includes act_trck
            "ANSW": self.legal_answer,
            "ANSA": self.legal_anssagen,
            "TRCK": self.legal_trck,
            "DONE": lambda: []
        }[self.phase]
        return legal_in_phase()

    def act_action(self, action: Action) -> bool:
        """Phases: PROV, PASS, PBCK, PRMO, FTRI, QUES, ANSW, TRCK"""
        # ? there is not a real reason why they are 4 letters long but it looks neat
        if action not in self.legal_actions():
            self.logger.warning("Not a legal action! This is not supposed to happen!")
            return False

        self.all_actions.append(action)

        self.logger.debug(f"{self.player_at_turn.name}: {utils.cards_str(self.player_at_turn.cards, fancy=self.fancy)}")
        self.logger.debug(
            f"Action player={self.players_dict[action.player_number].name}, phase={action.phase}, content={action.content}")

        act_in_phase = {
            "PROV": self.act_prov,
            "PASS": self.act_pass,
            "PBCK": self.act_pbck,
            "PRMO": self.act_prmo,
            "QUES": self.act_ques,
            "ANSW": self.act_answ,
            "ANSA": self.act_ansagen,
            "TRCK": self.act_trck,
        }[action.phase]
        assert action.player_number == self.player_at_turn.number, \
            "mismanaged players, the wrong person might be at turn"
        act_in_phase(action.content)
        return True

    def legal_prov(self) -> list[Action]:
        actions = [Action(self.player_at_turn.number, "PROV", 000)]
        for poss_val in range(self.game_value + 5, self.rules["max_game_value"] + 1, 5):
            actions.append(Action(self.player_at_turn.number, "PROV", poss_val))
        return actions

    def act_prov(self, value: int) -> None:
        if value > self.game_value:
            self.game_value = value
            self.logger.info(
                f"{self.player_at_turn.name} {MarjaPussi.INFO_MSG['player_says'][self.language]} {value}.")
        else:
            self.player_at_turn.still_prov = False
            self.logger.info(
                f"{self.player_at_turn.name} {MarjaPussi.INFO_MSG['is_gone'][self.language]}")
        players_still_prov = sum([1 for p in self.players if p.still_prov])
        # more than one player or last player still able to provoke
        if players_still_prov > 1 or (players_still_prov == 1 and self.game_value == self.rules["start_game_value"]):
            self.player_at_turn = self.player_at_turn.next_player
            while not self.player_at_turn.still_prov:
                self.player_at_turn = self.player_at_turn.next_player
        else:
            if self.game_value == self.rules["start_game_value"]:
                # noone took the game
                self.player_at_turn = self.players[0]
                self.logger.info(
                    f"{MarjaPussi.INFO_MSG['noon_plays'][self.language]}. {self.player_at_turn.name} "
                    f"{MarjaPussi.INFO_MSG['plays'][self.language]}")
                self.phase = "TRCK"
            else:
                # last prov player takes the game
                self.no_one_plays = False
                self.player_at_turn = [
                    p for p in self.players if p.still_prov][0]
                self.playing_player = self.player_at_turn
                self.player_at_turn = self.playing_player.partner
                self.logger.info(
                    f"{self.player_at_turn.name} {MarjaPussi.INFO_MSG['takes_the_game'][self.language]} {self.game_value}.")
                self.phase = "PASS"

    def legal_pass(self) -> list[Action]:
        actions = []
        for card in self.playing_player.partner.cards:
            if card in self.passed_cards["forth"]:
                continue
            actions.append(Action(self.playing_player.partner.number, "PASS", card))
        return actions

    def act_pass(self, card: Card) -> None:
        if len(self.passed_cards["forth"]) < 4:
            self.passed_cards["forth"].append(card)
        if len(self.passed_cards["forth"]) == 4:
            self.logger.debug(
                f"{self.player_at_turn.name} {MarjaPussi.INFO_MSG['gives'][self.language]} {utils.cards_str(self.passed_cards['forth'], fancy=self.fancy)} "
                f"{MarjaPussi.INFO_MSG['forth'][self.language]}.")
            for c in self.passed_cards["forth"]:
                self.playing_player.give_card(c)
                self.playing_player.partner.take_card(c)
            self.player_at_turn = self.player_at_turn.partner
            self.phase = "PBCK"

    def legal_passing_back(self) -> list[Action]:
        actions = []
        for card in self.playing_player.cards:
            if card in self.passed_cards["back"]:
                continue
            actions.append(Action(self.playing_player.number, "PBCK", card))
        return actions

    def act_pbck(self, card: Card) -> None:
        if len(self.passed_cards["back"]) < 4:
            self.passed_cards["back"].append(card)
        if len(self.passed_cards["back"]) == 4:
            self.logger.debug(
                f"{self.player_at_turn.name} {MarjaPussi.INFO_MSG['gives'][self.language]} "
                f"{utils.cards_str(self.passed_cards['back'], fancy=self.fancy)} "
                f"{MarjaPussi.INFO_MSG['back'][self.language]}.")
            for c in self.passed_cards["back"]:
                self.playing_player.take_card(c)
                self.playing_player.partner.give_card(c)
            self.player_at_turn = self.playing_player
            self.logger.info(
                f"{self.player_at_turn.name} {MarjaPussi.INFO_MSG['and'][self.language]} "
                f"{self.player_at_turn.partner.name} {MarjaPussi.INFO_MSG['passed_cards'][self.language]}")
            self.phase = "PRMO"

    def legal_prmo(self) -> list[Action]:
        actions = [Action(self.player_at_turn.number, "PRMO", 0)]
        for poss_val in range(self.game_value + 5, self.rules["max_game_value"] + 1, 5):
            actions.append(Action(self.player_at_turn.number, "PRMO", poss_val))
        return actions

    def act_prmo(self, value: int) -> None:
        value = int(value)
        if value > self.game_value:
            self.game_value = value
            self.logger.info(
                f"{self.playing_player.name} {MarjaPussi.INFO_MSG['raises_to'][self.language]} {value}.")
        else:
            self.logger.info(
                f"{self.playing_player.name} {MarjaPussi.INFO_MSG['plays_for'][self.language]} {self.game_value}.")
        self.phase = "TRCK"

    def legal_trck(self) -> list[Action]:
        return [Action(self.player_at_turn.number, "TRCK", card) for card in
                utils.allowed_general(self.player_at_turn.cards, self.tricks[-1],
                                      first=(self.tricks[0].get_status() != 4))]

    def act_trck(self, card: Card) -> None:
        self.logger.info(
            f"{self.players_dict[self.player_at_turn.number].name} {MarjaPussi.INFO_MSG['plays'][self.language]} "
            f"{str(card)}.")
        self.phase = 'TRCK'
        self.player_at_turn.take_card(card)
        # first not over
        self.tricks[-1].play_card(card)
        self.player_at_turn = self.player_at_turn.next_player
        # trick over
        if self.tricks[-1].get_status() == 4:
            # find the player who won the trick
            for c in self.tricks[-1].cards:
                if c == self.tricks[-1].high_card:
                    break
                self.player_at_turn = self.player_at_turn.next_player
            self.logger.info(
                f"{MarjaPussi.INFO_MSG['trick'][self.language]} {len(self.tricks)}: "
                f"{utils.cards_str(self.tricks[-1].cards, fancy=self.fancy)} "
                f"{MarjaPussi.INFO_MSG['goes_to'][self.language]} {self.player_at_turn.name}."
            )
            self.player_at_turn.take_trick(
                self.tricks[-1], last=len(self.tricks) == len(self.card_pool.cards) / 4)
            self.phase = "QUES"
            if len(self.tricks) == len(self.card_pool.cards) / 4:
                self.phase = "DONE"
                self.eval_game()
            else:
                self.tricks.append(Trick(self.trump))

    def legal_ques(self) -> list[Action]:
        """ou->ours,yo->yours,my->my"""
        lvl = self.player_at_turn.asking
        quests = []
        if lvl <= 2:
            quests += [Action(self.player_at_turn.number, "QUES", Talk("our", col)) for col in Color]
        if lvl <= 1:
            quests += [Action(self.player_at_turn.number, "QUES", Talk("yours", None))]
        if lvl == 0:
            quests += [Action(self.player_at_turn.number, "QUES", Talk("my", col)) for col in Color
                   if (utils.contains_col_pair(self.player_at_turn.cards, col) and col not in self.all_trump)]
        return quests + self.legal_trck()

    def act_ques(self, ques: Talk) -> None:
        if ques.pronoun == "my":
            self.trump = col = ques.color
            self.tricks[-1].trump_color = self.trump
            self.logger.info(
                f"{self.player_at_turn.name} {MarjaPussi.INFO_MSG['has'][self.language]} "
                f"{utils.color_str(col, fancy=self.fancy)} {MarjaPussi.INFO_MSG['pair'][self.language]}")
            self.logger.info(
                f"{col.fancy_name().capitalize()} {MarjaPussi.INFO_MSG['is_trump'][self.language]}")
            self.player_at_turn.call_trump(col)
            self.all_trump.append(col)
            self.phase = "TRCK"
        if ques.pronoun == "yours":
            self.logger.info(
                f"{self.player_at_turn.name} {MarjaPussi.INFO_MSG['asks_for'][self.language]} "
                f"{MarjaPussi.INFO_MSG['pair'][self.language]}")
            self.player_at_turn.asking = 1
            self.player_at_turn = self.player_at_turn.partner
            self.phase = "ANSW"
        if ques.pronoun == "our":
            self.logger.info(f"{self.player_at_turn.name} {MarjaPussi.INFO_MSG['asks_for'][self.language]} "
                             f"{utils.color_str(ques.color, fancy=self.fancy)} "
                             f"{MarjaPussi.INFO_MSG['half'][self.language]}")
            self.player_at_turn.asking = 2
            self.player_at_turn = self.player_at_turn.partner
            self.phase = "ANSW"

    def legal_answer(self) -> list[Action]:
        quest = self.all_actions[-1].content
        if quest.pronoun == "yours":
            answ = [Action(self.player_at_turn.number, "ANSW", Talk("my", col)) for col in Color
                    if (utils.contains_col_pair(self.player_at_turn.cards, col) and col not in self.all_trump)]
            if not answ:
                return [Action(self.player_at_turn.number, "ANSW", Talk("nmy", None))]
            return answ
        else:
            col = quest.color
            return [Action(self.player_at_turn.number, "ANSW",
                           Talk("ou", col) if utils.contains_col_half(self.player_at_turn.cards, col)
                           else Talk("no", col))]

    def act_answ(self, answ: Talk) -> None:
        # partner has no pair
        match answ.pronoun:
            case "nmy":
                self.logger.info(
                    f"{self.player_at_turn.name} {MarjaPussi.INFO_MSG['no_pair'][self.language]}")
            # partner has a pair
            case "my":
                self.trump = answ.color
                self.tricks[-1].trump_color = self.trump
                self.logger.info(
                    f"{self.player_at_turn.name} {MarjaPussi.INFO_MSG['has'][self.language]} "
                    f"{utils.color_str(self.trump, fancy=self.fancy)} {MarjaPussi.INFO_MSG['pair'][self.language]}")
                self.player_at_turn.call_trump(self.trump)
            # partner has a half
            case "ou":
                pot_trump = answ.color
                self.logger.info(
                    f"{self.player_at_turn.name} {MarjaPussi.INFO_MSG['has'][self.language]} "
                    f"{utils.color_str(pot_trump, fancy=self.fancy)} {MarjaPussi.INFO_MSG['half'][self.language]}")
                self.player_at_turn = self.player_at_turn.partner
                self.phase = "ANSA"
                return
            # partner doesn't have a half
            case "no":
                self.logger.info(
                    f"{self.player_at_turn.name} {MarjaPussi.INFO_MSG['doesnt_have'][self.language]} "
                    f"{utils.color_str(answ.color, fancy=self.fancy)} {MarjaPussi.INFO_MSG['half'][self.language]}")

        # check if new color is trump
        if self.trump and self.trump not in self.all_trump:
            self.all_trump.append(self.trump)
            self.logger.info(
                f"{utils.color_str(self.trump, fancy=self.fancy).capitalize()} "
                f"{MarjaPussi.INFO_MSG['is_trump'][self.language]}")
        self.player_at_turn = self.player_at_turn.partner
        self.phase = "TRCK"


    def legal_anssagen(self) -> list[Action]:
        answ = self.all_actions[-1].content
        col = answ.color
        return [Action(self.player_at_turn.number, 'ANSA',
                       Talk('we', col) if utils.contains_col_half(self.player_at_turn.cards, col) else Talk('nwe',
                                                                                                            col))]

    def act_ansagen(self, answ: Talk) -> None:
        pot_trump = answ.color
        if answ.pronoun == 'we':
            self.trump = pot_trump
            self.tricks[-1].trump_color = self.trump
            self.player_at_turn.call_trump(pot_trump)
            self.logger.info(
                f"{self.player_at_turn.name} {MarjaPussi.INFO_MSG['has_also'][self.language]} "
                f"{utils.color_str(pot_trump, fancy=self.fancy)} {MarjaPussi.INFO_MSG['half'][self.language]}")
            # check if new color is trump
        if answ.pronoun == 'nwe':
            self.logger.info(
                f"{self.player_at_turn.name} {MarjaPussi.INFO_MSG['doesnt_have'][self.language]} "
                f"{utils.color_str(pot_trump, fancy=self.fancy)} {MarjaPussi.INFO_MSG['half'][self.language]}")
        if self.trump and self.trump not in self.all_trump:
            self.all_trump.append(self.trump)
            self.logger.info(
                f"{utils.color_str(self.trump, fancy=self.fancy).capitalize()} "
                f"{MarjaPussi.INFO_MSG['is_trump'][self.language]}")
        self.phase = "TRCK"

    def eval_game(self) -> None:
        self.logger.info(MarjaPussi.INFO_MSG["game_done"][self.language])
        if self.no_one_plays:
            return
        playing, partner = self.playing_player, self.playing_player.partner
        self.logger.info(
            f"{playing.name} {MarjaPussi.INFO_MSG['and'][self.language]} {partner.name}: {playing.points_made}+"
            f"{partner.points_made}={(pl := playing.points_made + partner.points_made)}")
        notplay, noplaypart = self.playing_player.next_player, self.playing_player.next_player.partner
        self.logger.info(
            f"{notplay.name} {MarjaPussi.INFO_MSG['and'][self.language]} {noplaypart.name}: {notplay.points_made}+"
            f"{noplaypart.points_made}={(npl := notplay.points_made + noplaypart.points_made)}")

        if not self.no_one_plays:
            self.logger.info(
                f"{MarjaPussi.INFO_MSG['playing_party'][self.language]}: {pl}/{self.game_value}")
            if pl >= self.game_value:
                self.logger.info(utils.bold_str(
                    MarjaPussi.INFO_MSG['win'][self.language], fancy=self.fancy))
            else:
                self.logger.info(utils.bold_str(
                    MarjaPussi.INFO_MSG['loose'][self.language], fancy=self.fancy))
        else:
            self.logger.info("There are only losers this round.")

    def players_cards(self):
        return {player.name: [str(card) for card in player.cards] for player in self.players}

    def state_dict(self):
        return {
            "players_names": [player.name for player in self.players],
            "players_cards": {player.name: [str(card) for card in player.cards] for player in self.players},
            "game_value": self.game_value,
            "trump_color": self.trump,
            "player_at_turn": self.player_at_turn.name,
            "game_phase": self.phase,
            "trick_num": len(self.tricks),
            "current_trick": self.tricks[-1].cards,
            "legal_actions": self.legal_actions(),
            "points_playing_party": None if not self.playing_player else
            self.playing_player.points_made + self.playing_player.partner.points_made,
            "points_not_playing_party": None if not self.playing_player else
            self.playing_player.next_player.points_made + self.playing_player.next_player.partner.points_made,
            "won": None if not self.playing_player else
            self.playing_player.points_made + self.playing_player.partner.points_made > self.game_value,
            "noone_plays": None if not self.playing_player else self.no_one_plays,
        }

    def end_info(self):
        """Return dict with all relevant info."""
        return {
            "players": [p.name for p in self.players],
            "cards": [str(card) for card in self.original_cards],
            "passed_cards": {name: [str(card) for card in cards] for name, cards in self.passed_cards.items()},
            "tricks": [[c for c in trick.cards] for trick in self.tricks],
            "actions": self.all_actions,
            "playing_player": self.playing_player.name if not self.no_one_plays else None,
            "game_value": self.game_value,
            "players_points": {p.name: p.points_made for p in self.players},
            "players_sup": {p.name: p.trump_calls for p in self.players},
            "schwarz_game": (len(self.players[0].tricks) + len(self.players[2].tricks) == 9
                             or len(self.players[1].tricks) + len(self.players[3].tricks) == 9),
        }

    INFO_MSG = {
        "got_their_cards": ["All players got their cards.", "Alle Spieler erhalten ihre Karten."],
        "player_says": ["says", "sagt"],
        "is_gone": ["is gone.", "ist weg."],
        "noon_plays": ["No one takes the game.", "Niemand spielt das Spiel."],
        "starts": ["starts.", "beginnt."],
        "takes_the_game": ["takes the game for", "nimmt das Spiel für"],
        "and": ["and", "und"],
        "passed_cards": ["passed cards.", "haben geschoben."],
        "raises_to": ["raises to", "erhöht auf"],
        "plays_for": ["plays for", "spielt für"],
        "plays": ["plays", "legt"],
        "trick": ["Trick", "Stich"],
        "goes_to": ["goes to", "geht an"],
        "has": ["has", "hat"],
        "gives": ["passes", "schiebt"],
        "back": ["back", "zurück"],
        "forth": ["forth", "hin"],
        "is_trump": ["is now superior.", "ist jetzt Trumpf"],
        "asks_for": ["asks for", "fragt nach"],
        "pair": ["pair.", "Paar."],
        "half": ["half.", "Hälfte."],
        "no_pair": ["doesn't have a pair.", "hat kein Paar."],
        "has_also": ["also has", "hat auch"],
        "doesnt_have": ["doesn't have", "hat keine"],
        "game_done": ["Game is finished.", "Spiel vorbei."],
        "win": ["Playing party WINS.", "Spielende Partei hat gewonnen!"],
        "loose": [f"Playing party WINS.", "Spielende Partei hat verloren."],
        "noonewins": ["No one played, no one wins...", "Niemand hat gespielt, Niemand gewinnt..."],
        "playing_party": ["Playing Party", "Spielende Partei"]
    }
