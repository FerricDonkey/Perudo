"""
Silly Example of using a custom player class
"""

import dataclasses

import perudo

@perudo.PlayerABC.register_constructor
@dataclasses.dataclass
class DumbPlayer(perudo.PlayerABC):
    # Use this decorater if you want to operate on local indexes.
    # @perudo.PlayerABC.rotate_get_action_args_decorator
    def get_action(self, observation: perudo.ActionObservation) -> perudo.Action:
        # Note that this is not always legal. This is on purpose, to demonstrate
        # that the game tolerates custom classes that make illegal moves.
        return perudo.Bid(face=3, count=3)

if __name__ == '__main__':
    perudo.main()
