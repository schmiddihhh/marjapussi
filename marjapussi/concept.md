# Concept

## Plan
The idea is to use concepts as stores for
probabilities of possible states in a game.
For this, the agent holds all information
he has about his own cards and fellow players.
For this, he stores the information's origin
(called source) and the "correctness
likelihood". 

Concepts may have dependencies, whose 
weighted sum becomes its value. Therefore,
there are dependent (as just described) and
basic concepts (such that are directly 
influenced by the agent's code).

## List of all concepts

| Concept String                             | Source                | Encodes the likelihood of ...          |
|--------------------------------------------|-----------------------|----------------------------------------|
| f"{player_name}_has_ace"                   | provoking             | having an ace                          |
| f"{player_name}_has_3+_halves"             | provoking             | having 3+ halves                       |
| f"{player_name}_has_halves"                | provoking             | having 2+ halves                       |
| f"{player_name}_has_small_pair"            | provoking             | having small pair                      |
| f"{player_name}_has_big_pair"              | provoking             | having big pair                        |
| "getting_played_black"                     | provoking             | getting played black                   |
| "playing_black"                            | provoking             | playing the opponents "Schwarz"        |
| f"{player_name}_has_{str(color)}_big_pair" | assessment / question | having specific pair                    |
| f"{player_name}_has_{str(p_col)}_half"     | question              | having specific half                   |
| "good_hand_cards"                          | assessment            | having very good cards on starting hand |
