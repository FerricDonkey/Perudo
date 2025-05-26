"""
Package for Perudo game. Intended to support bots and network play.

Exposes some classes directly. For others, import the relevant module.
"""

__version__ = "0.0.0"

# Convenience imports - also need to tell pyright not to be angry about it
# pyright: reportUnusedImport=false
from perudo.actions import Bid, Challenge, Exact, Action, InvalidAction, NoOp, NoOpFirstTurnSkip, NoOpDead, EndAction
from perudo.players import PlayerABC, RandomLegalPlayer, ProbabilisticPlayer, HumanPlayer
from perudo.perudo_game import PerudoGame
from perudo.network_stuff.client import ClientPlayer
from perudo.cli.cli_main import  main
from perudo.common import WILD_FACE_VAL, MAX_FACE_VAL, MIN_FACE_VAL, NUM_FACES, STARTING_NUM_DICE
