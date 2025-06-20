"""
Some tests, mostly ai generated because I'm lazy (but I did read them). A few
modified or added.
"""

import pytest

from perudo import actions
from perudo import common
from perudo import perudo_game as pg
from perudo import players as pl


@pytest.fixture
def simple_bid() -> actions.Bid:
    return actions.Bid(face=2, count=2)

@pytest.fixture
def simple_game() -> pg.PerudoGame:
    players: list[pl.PlayerABC] = [pl.RandomLegalPlayer(name=f"Bot-{i}") for i in range(2)]
    game = pg.PerudoGame.from_player_list(players)
    return game

def test_bid_validation_first_move_valid(simple_bid: actions.Bid) -> None:
    action = simple_bid.validate(previous_action=None, is_single_die_round=False)
    assert isinstance(action, actions.Bid)

def test_bid_validation_invalid_face() -> None:
    bid = actions.Bid(face=7, count=2)
    result = bid.validate(previous_action=None, is_single_die_round=False)
    assert isinstance(result, actions.InvalidAction)

def test_bid_min_next_count() -> None:
    bid = actions.Bid(face=3, count=3)
    assert bid.min_next_count(3) == 4  # Same face -> count + 1
    assert bid.min_next_count(4) == 3  # Higher face -> same count
    assert bid.min_next_count(1) == 2  # Wild -> ceil(count/2)
    assert bid.min_next_count(2) == 5  # Lower -> wrap around ceil(count/2)*2 + 1

def test_bid_min_next_count_wild_base() -> None:
    bid = actions.Bid(face=common.WILD_FACE_VAL, count=3)
    assert bid.min_next_count(common.WILD_FACE_VAL) == 4  # Same face -> count + 1
    assert bid.min_next_count(common.WILD_FACE_VAL + 1) == 7  # Higher face -> same count
    assert bid.min_next_count(common.WILD_FACE_VAL + 2) == 7  # Lower -> wrap around ceil(count/2)*2 + 1

def test_challenge_success() -> None:
    previous = actions.Bid(face=3, count=2)
    dice_counts = common.DiceCounts.from_dictionary({3:2, 2:1, 6:1})
    challenge = actions.Challenge()
    losers = challenge.get_losers(
        previous_action=previous,
        all_dice_counts=dice_counts,
        is_single_die_round=False,
        caller=0,
        previous_player=1,
        other_players=[1]
    )
    assert losers == [0]  # Caller loses because bid was valid

def test_challenge_failure() -> None:
    previous = actions.Bid(face=3, count=3)
    dice_counts = common.DiceCounts.from_dictionary({3:1, 2:2, 6:1})
    challenge = actions.Challenge()
    losers = challenge.get_losers(
        previous_action=previous,
        all_dice_counts=dice_counts,
        is_single_die_round=False,
        caller=0,
        previous_player=1,
        other_players=[1]
    )
    assert losers == [1]  # Previous player loses because bid was invalid

def test_exact_success_no_wild() -> None:
    previous = actions.Bid(face=2, count=2)
    dice_counts = common.DiceCounts.from_dictionary({3:1, 2:2, 6:1})
    exact = actions.Exact()
    losers = exact.get_losers(
        previous_action=previous,
        all_dice_counts=dice_counts,
        is_single_die_round=False,
        caller=0,
        previous_player=4,
        other_players=[1, 2, 3, 4]
    )
    assert losers == [1, 2, 3, 4]  # All non caller players lose because bid was exact

def test_exact_success_with_wild() -> None:
    previous = actions.Bid(face=2, count=2)
    dice_counts = common.DiceCounts.from_dictionary({3:1, 2:1, 1:1, 6:1})
    exact = actions.Exact()
    losers = exact.get_losers(
        previous_action=previous,
        all_dice_counts=dice_counts,
        is_single_die_round=False,
        caller=0,
        previous_player=4,
        other_players=[1, 2, 3, 4]
    )
    assert losers == [1, 2, 3, 4]  # All non caller players lose because bid was exact

def test_exact_success_disabled_wild() -> None:
    previous = actions.Bid(face=2, count=2)
    dice_counts = common.DiceCounts.from_dictionary({1:1, 2:2, 6:1})
    exact = actions.Exact()
    losers = exact.get_losers(
        previous_action=previous,
        all_dice_counts=dice_counts,
        is_single_die_round=True,
        caller=0,
        previous_player=4,
        other_players=[1, 2, 3, 4]
    )
    assert losers == [1, 2, 3, 4]  # All non caller players lose because bid was exact

def test_exact_failure_no_wild() -> None:
    previous = actions.Bid(face=3, count=2)
    dice_counts = common.DiceCounts.from_dictionary({3:1, 2:2, 6:1})
    exact = actions.Exact()
    losers = exact.get_losers(
        previous_action=previous,
        all_dice_counts=dice_counts,
        is_single_die_round=False,
        caller=0,
        previous_player=4,
        other_players=[1, 2, 3, 4]
    )
    assert losers == [0]  # Caller loses because exact call failed

def test_exact_failure_with_wild() -> None:
    previous = actions.Bid(face=3, count=2)
    dice_counts = common.DiceCounts.from_dictionary({3:2, 1:1, 6:1})
    exact = actions.Exact()
    losers = exact.get_losers(
        previous_action=previous,
        all_dice_counts=dice_counts,
        is_single_die_round=False,
        caller=0,
        previous_player=4,
        other_players=[1, 2, 3, 4]
    )
    assert losers == [0]  # Caller loses because exact call failed

def test_exact_failure_disabled_wild() -> None:
    previous = actions.Bid(face=3, count=2)
    dice_counts = common.DiceCounts.from_dictionary({3:1, 2:1, 1:1, 6:1})
    exact = actions.Exact()
    losers = exact.get_losers(
        previous_action=previous,
        all_dice_counts=dice_counts,
        is_single_die_round=True,
        caller=0,
        previous_player=4,
        other_players=[1, 2, 3, 4]
    )
    assert losers == [0]  # Caller loses because exact call failed

def test_perudogame_start_new_round(simple_game: pg.PerudoGame) -> None:
    simple_game.start_new_round(first_player_index=0, single_die_round=False)
    assert simple_game.cur_player_index == 0
    assert simple_game.current_round_dice_by_player  # Players should have dice
    assert simple_game.all_rounds_actions[-1] == []

def test_perudogame_take_turn(simple_game: pg.PerudoGame) -> None:
    simple_game.start_new_round(first_player_index=0, single_die_round=False)
    still_going = simple_game.take_turn()
    assert isinstance(still_going, bool)
    assert simple_game.current_round_actions  # Some action should have been taken
