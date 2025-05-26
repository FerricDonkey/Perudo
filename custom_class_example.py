"""
Silly Example of using a custom player class
"""

import collections
import dataclasses

import perudo

@perudo.PlayerABC.register_constructor
@dataclasses.dataclass
class DumbPlayer(perudo.PlayerABC):
    def get_action(
        self,
        previous_action: perudo.Bid | None,
        is_single_die_round: bool,
        num_dice_in_play: int,
        player_dice_count_history: list[list[int]],
        all_rounds_actions: list[list[perudo.Action]],
        dice_reveal_history: list[list[collections.Counter[int]]],
    ) -> perudo.Action:
        # Note that this is not always legal. This is on purpose, to demonstrate
        # that the game tolerates custom classes that make illegal moves.
        return perudo.Bid(face=3, count=3)

if __name__ == '__main__':
    perudo.main()
