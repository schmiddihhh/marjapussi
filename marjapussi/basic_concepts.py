from marjapussi.concept import Concept
from marjapussi.gamestate import GameState

# All Basic Concepts are in this file, this is used primarily for the probabilistic Policy
def provoking_concepts(state: GameState):
    for player_name in state.all_players:
        state.concepts.add(Concept(f"{player_name}_provoke_first_gone",{"player": player_name}))
        state.concepts.add(Concept(f"{player_name}_provoke_first_5",{"player": player_name}))