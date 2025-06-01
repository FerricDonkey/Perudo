"""
Package for Perudo game. Intended to support bots and network play.

Exposes some functionality directly. For others, import the relevant modules.
"""

__version__ = "0.0.0"

# Convenience imports to make import perudo actually useful.

# If this looks stupid, it's because it is. This "import x as x" syntax makes
# the type checkers aware that these things are imported for the sake of exporting.
#
# You'd think I could just do a single pragma style comment to tell the type
# checkers that exporting these things is the entire freaking point of this
# whole stupid __init__.py file. But no, I can't. Because the type checkers
# don't have that functionality for some stupid reason. And even though this is
# an __init__.py file, they have to guard against heretics who might try to do
# actual processing here, like the gross monsters that they are, and so import
# things that they don't want to re-export. Freaking morons.
#
# So because of the sins of the many, I have to make my file look stupid. Or I
# could make an __all__, of course, but that's even worse, and would cause both
# my past and future selves to invent time machines for the sole purpose of
# coming here and stabbing me. And I'd deserve it.
#
# So anyway, this is what we're left with.
from perudo.actions import (
    Bid as Bid,
    Challenge as Challenge,
    Exact as Exact,
    Action as Action,
    InvalidAction as InvalidAction,
    NoOp as NoOp,
    NoOpFirstTurnSkip as NoOpFirstTurnSkip,
    NoOpDead as NoOpDead,
    EndAction as EndAction,
)
from perudo.players import (
    ActionObservation as ActionObservation,
    PlayerABC as PlayerABC,
    RandomLegalPlayer as RandomLegalPlayer,
    ProbabilisticPlayer as ProbabilisticPlayer,
    HumanPlayer as HumanPlayer,
)
from perudo.perudo_game import (
    PerudoGame as PerudoGame,
)
from perudo.network_stuff.client import (
    ClientPlayer as ClientPlayer,
)
from perudo.cli.cli_main import (
    main as main,
)
from perudo.common import (
    WILD_FACE_VAL as WILD_FACE_VAL,
    MAX_FACE_VAL as MAX_FACE_VAL,
    MIN_FACE_VAL as MIN_FACE_VAL,
    NUM_FACES as NUM_FACES,
    STARTING_NUM_DICE as STARTING_NUM_DICE,
    DiceCounts as DiceCounts,
)
