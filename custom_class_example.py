"""
Silly Example of using a custom player class
"""

import dataclasses

import perudo
from perudo import actions, PerudoGame


@perudo.PlayerABC.register_constructor
@dataclasses.dataclass
class DumbPlayer(perudo.PlayerABC):
    def get_action(
        self,
        round_actions: list[actions.Action],
        is_single_die_round: bool,
        num_dice_in_play: int,
        num_players_alive: int,
    ) -> actions.Action:
        # Note that this is not always legal. this is on purpose, to demonstrate that the game tolerates custom classes
        # that make illegal moves.
        return perudo.Bid(face=3, count=3)

if __name__ == '__main__':
    perudo.main()
