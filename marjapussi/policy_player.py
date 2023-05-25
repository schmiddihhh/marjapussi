class PolicyPlayer:
    def __init__(self, player_number, name, score):
        # for our policy we don't care about the player names, use the player_num as ids
        # this is mainly because our decision making is highly based on the position we are playing in
        # and this makes it easier to bind the information we deduct directly to the position we are playing from
        self.player_number = player_number
        self.name = name
        self.partner_number = (player_number + 2) % 4
        self.card_probabilities = {}
        self.concept_probabilities = {}
        self.provoking_history_steps = []
        self.score = score