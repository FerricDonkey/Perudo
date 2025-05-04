"""
Package for Perudo game. Intended to support bots and network play.

Exposes some classes directly. For others, import the relevant module.
"""

__version__ = "0.0.0"

# Convenience imports - also need to tell pyright not to be angry about it
# pyright: reportUnusedImport=false
from perudo.actions import Bid, Challenge, Exact
from perudo.players import PlayerABC, RandomLegalPlayer, ProbalisticPlayer, HumanPlayer
from perudo.perudo_game import PerudoGame
from perudo.network_stuff.client import ClientPlayer
