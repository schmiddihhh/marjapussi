class PolicyPlayer:
    def __init__(self, player_number: int, name: str, score: int):
        # The name is the main and unique identifier for players across multiple rounds
        self.name = name
        # For some policies though the player number might be more important
        self.player_number = player_number
        self.partner_number = (player_number + 2) % 4
        self.provoking_history_steps = []
        self.score = score
