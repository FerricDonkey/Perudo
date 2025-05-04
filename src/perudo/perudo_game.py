"""
Core game logic for Perudo (Liar's Dice).

This module implements the main game mechanics for Perudo, a dice game where players
make bids about the total number of dice showing a particular value across all players'
dice. Players can challenge others' bids, with the loser losing one die. The game
continues until only one player has dice remaining.

Key game rules:
- Each player starts with 5 dice
- Players bid on total number of dice showing a value across all players
- Player can challenge previous bid (calling "liar")
- Ones are wild except in "ones" bids
- Loser of each round loses one die
- Last player with dice wins
"""

import argparse
import collections
import dataclasses
import random
import typing as ty

from perudo import common
from perudo import actions
from perudo import players as pl


def dice_to_str(dice_counter: collections.Counter[int]) -> str:
    return ', '.join(f'{face}: {value}' for face, value in sorted(dice_counter.items()))


@dataclasses.dataclass
class PerudoGame:
    """
    Represents a game of Perudo.

    The PerudoGame class manages the game logic, players, rounds, and their respective states in
    the game of Perudo. It provides functionalities for starting new rounds, ending
    rounds, determining valid moves, and keeping track of the game's progress. The game
    operates with a turn-by-turn mechanism involving players, dice, and actions. This
    class encapsulates the core rules and mechanics and serves as the central engine of
    the game.

    The game does not trust the Player objects to validate their actions, or to report accurate
    information about their current state (held dice, number of dice, etc.). Instead, it tracks
    these itself. This makes things a bit more clunky, but it means that extensions of player
    classes are less likely to break the game logic.

    I have no idea what the below syntax means or what system it is for, but it's what the AI did,
    and I'm leaving it until I get around to replacing it with something more compact.

    :ivar STARTING_NUM_DICE: The default starting number of dice each player begins with.
    :type STARTING_NUM_DICE: int

    :ivar players: List of players participating in the game.
    :type players: list[perudo.players.PlayerABC]

    :ivar player_index_to_num_dice: List mapping each player's index to the number of dice they hold.
    :type player_index_to_num_dice: list[int]

    :ivar cur_player_index: The index of the current player whose turn it is.
    :type cur_player_index: int

    :ivar cur_round_single_die: Indicates if the current round is a single-die round.
    :type cur_round_single_die: bool

    :ivar all_rounds_actions: History of actions taken in all rounds, stored as a list of lists.
    :type all_rounds_actions: list[list[actions.Action]]

    :ivar all_rounds_dice: History of dice rolls for all players across all rounds.
    :type all_rounds_dice: list[list[list[int]]]

    :ivar all_rounds_living_players: Tracks the living players for each round.
    :type all_rounds_living_players: list[list[int]]

    :ivar all_rounds_losers: Tracks players who lost dice in each round.
    :type all_rounds_losers: list[list[int]]
    """
    STARTING_NUM_DICE: ty.ClassVar[int] = 5

    players: list[pl.PlayerABC]
    player_index_to_num_dice: list[int]
    cur_player_index: int = -1
    cur_round_single_die: bool = False
    all_rounds_actions: list[list[actions.Action]] = dataclasses.field(default_factory=list[list[actions.Action]])
    all_rounds_dice: list[list[collections.Counter[int]]] = dataclasses.field(default_factory=list[list[collections.Counter[int]]])
    all_rounds_living_players: list[list[int]] = dataclasses.field(default_factory=list[list[int]])
    all_rounds_losers: list[list[int]] = dataclasses.field(default_factory=list[list[int]])
    single_die_round_history: list[bool] = dataclasses.field(default_factory=list[bool])
    print_while_playing: bool = False
    print_non_human_dice: bool = True

    @property
    def current_round_actions(self) -> list[actions.Action]:
        if not self.all_rounds_actions:
            raise RuntimeError('No current round')
        return self.all_rounds_actions[-1]

    @property
    def current_round_dice_by_player(self) -> list[collections.Counter[int]]:
        if not self.all_rounds_actions:
            raise RuntimeError('No current round')
        return self.all_rounds_dice[-1]

    @property
    def previous_living_player_index(self) -> int:
        """
        Raises an error if no player (excluding the current player) has any
        dice
        """
        prev_index = (self.cur_player_index - 1) % len(self.players)
        while self.player_index_to_num_dice[prev_index] == 0:
            if prev_index == self.cur_player_index:
                raise RuntimeError("previous_living_player_index used when there wasn't one")
            prev_index = (prev_index - 1) % len(self.players)
        return prev_index

    @property
    def next_living_player_index(self) -> int:
        """
        Raises an error if no player (excluding the current player) has any
        dice
        """
        next_index = (self.cur_player_index + 1) % len(self.players)
        while self.player_index_to_num_dice[next_index] == 0:
            if next_index == self.cur_player_index:
                raise RuntimeError("next_living_player_index used when there wasn't one")
            next_index = (next_index + 1) % len(self.players)
        return next_index

    def start_new_round(
        self,
        first_player_index: int,
        single_die_round: bool
    ) -> None:
        if not (0 <= first_player_index < len(self.players)):
            raise RuntimeError(f'Invalid first_player_index {first_player_index} (Out of range)')

        if self.player_index_to_num_dice[first_player_index] < 1:
            raise RuntimeError(f'Invalid first_player_index {first_player_index} (does not have dice)')

        self.single_die_round_history.append(single_die_round)
        self.cur_round_single_die = single_die_round
        self.all_rounds_actions.append([])
        self.all_rounds_dice.append([])
        living_players = [
            index % len(self.players)
            for index in range(first_player_index, first_player_index + len(self.players))
            if self.player_index_to_num_dice[index % len(self.players)] > 0
        ]
        self.all_rounds_living_players.append(living_players)
        self.cur_player_index = first_player_index

        for player, num_dice in zip(self.players, self.player_index_to_num_dice):
            dice = collections.Counter(random.choices(  # sorted makes display nicer
                range(common.MIN_FACE_VAL, common.MAX_FACE_VAL),
                k=num_dice
            ))
            player.set_dice(dice)
            self.current_round_dice_by_player.append(dice)

        if self.print_while_playing:
            print(f"\nStarting new round ({single_die_round=} num_die={sum(self.player_index_to_num_dice)}):\n====================")
            for player_index in self.all_rounds_living_players[-1]:
                if not (self.print_non_human_dice or isinstance(self.players[player_index], pl.HumanPlayer)):
                    continue
                dice_counter = self.current_round_dice_by_player[player_index]
                print(
                    "{name} ({dice_count} dice): {dice_string}".format(
                        name=self.players[player_index].name,
                        dice_count=self.player_index_to_num_dice[player_index],
                        dice_string=dice_to_str(dice_counter),
                    )
                )
            print("-------------------")


    def end_round(
        self,
        loser_indexes: ty.Collection[int],
    ) -> bool:
        """
        End this round, start a new one IF anyone survived.

        :param loser_indexes: The players who lose a die at the end of this round
        :return: Whether there's a next round
        """
        self.all_rounds_losers.append(sorted(loser_indexes))
        for index in loser_indexes:
            self.player_index_to_num_dice[index] = max(0, self.player_index_to_num_dice[index] - 1)

        # Start a new round if multiple people are still alive
        if sum(num > 0 for num in self.player_index_to_num_dice) > 1:
            losers_with_dice = [
                index for index in loser_indexes
                if self.player_index_to_num_dice[index] > 0
            ]
            # TODO: Is this right?
            if losers_with_dice:
                next_player = random.choice(losers_with_dice)
            else:
                next_player = self.next_living_player_index
            if any(
                self.player_index_to_num_dice[index] == 1
                for index in losers_with_dice
            ):
                single_die_round = True
            else:
                single_die_round = False

            round_summary = RoundSummary.from_game_losers(
                game=self,
                losers=[self.players[index] for index in loser_indexes],
            )
            for player in self.players:
                player.react_to_round_summary(round_summary)

            self.start_new_round(
                first_player_index=next_player,
                single_die_round=single_die_round,
            )
            return True  # game is continuing

        # Game is not continuing
        round_summary = RoundSummary.from_game_losers(
            game=self,
            losers=[self.players[index] for index in loser_indexes],
        )
        for player in self.players:
            player.react_to_round_summary(round_summary)
        return False

    def take_turn(self,) -> bool:
        """
        returns True if the game continues, False if not
        """
        # Get action from player
        if len(self.current_round_actions) > 20:
            raise
        action = self.players[self.cur_player_index].get_action(
            round_actions=self.current_round_actions,
            is_single_die_round=self.cur_round_single_die,
            num_dice_in_play=sum(self.player_index_to_num_dice),
            num_players_alive=sum(count > 0 for count in self.player_index_to_num_dice),
        )
        if not self.current_round_actions:
            prev_action = None
        else:
            prev_action = self.current_round_actions[-1]

        # Check if the action was valid. Will be an InvalidAction object if not
        action = action.validate(
            previous=prev_action,
            is_single_die_round=self.cur_round_single_die,
        )
        if self.print_while_playing:
            print(f"    {self.players[self.cur_player_index].typed_name}: {action}")
        self.current_round_actions.append(action)

        # Handle round ending actions (including InvalidActions)
        if isinstance(action, actions.EndAction):
            all_dice = [
                die
                for player_dice in self.current_round_dice_by_player
                for die in player_dice
            ]
            other_living_players = [
                player_index
                for player_index, num_dice in enumerate(self.player_index_to_num_dice)
                if player_index != self.cur_player_index and num_dice > 0
            ]
            losers = action.get_losers(
                previous_action=prev_action,
                all_dice=all_dice,
                is_single_die_round=self.cur_round_single_die,
                caller=self.cur_player_index,
                previous_player=self.previous_living_player_index,
                other_players=other_living_players,
            )
            if self.print_while_playing:
                print(f'Loser(s): {", ".join(self.players[loser].typed_name for loser in losers)}')

            return self.end_round(loser_indexes=losers,)

        self.cur_player_index = self.next_living_player_index
        return True

    @classmethod
    def from_player_list(
        cls,
        players: list[pl.PlayerABC],
        print_while_playing: bool=True,
        print_non_human_dice: bool=True,
    ) -> ty.Self:
        return cls(
            players=players,
            player_index_to_num_dice=[cls.STARTING_NUM_DICE for _ in players],
            print_while_playing=print_while_playing,
            print_non_human_dice=print_non_human_dice,
        )

    def print_summary(self) -> None:
        """
        Print a summary of the game. DO NOT CALL DURING A ROUND

        This is kind of redundant to use locally now that verbose is added, but
        I'm leaving it for now for testing purposes - network play will send
        the objects it creates to client players, who will use them to see
        what happened, since they don't have access to the game itself.
        """
        game_summary = GameSummary.from_game(self, self.cur_player_index)
        game_summary.print()

    def main_loop(
        self,
        game_end_callback: ty.Callable[[pl.PlayerABC], None] | None = None,
    ) -> int:
        """
        Suitable for running the game purely locally

        :param game_end_callback: Function called at game end with winning player
        :return: winning player index
        """
        first_player_index = random.randrange(len(self.players))
        self.start_new_round(
            first_player_index=first_player_index,
            single_die_round=False,  # Assuming we're not being weird.
        )
        while self.take_turn():
            pass

        # self.cur_player_index is the winner
        if game_end_callback is not None:
            game_end_callback(self.players[self.cur_player_index])

        return self.cur_player_index


@dataclasses.dataclass(frozen=True)
class RoundSummary(common.BaseFrozen):
    """
    This class is also a message that will be sent over the network to client
    players in a network game - but players can react to it as well, if they
    so desire.
    """
    ordered_players: list[str]
    all_player_dice: list[collections.Counter[int]]
    all_actions: list[actions.Action]
    single_die_round: bool
    losers: list[str]

    @classmethod
    def from_game_losers(
        cls,
        game: PerudoGame,
        losers: list[pl.PlayerABC],
    ) -> ty.Self:
        return cls(
            ordered_players=[game.players[index].name for index in game.all_rounds_living_players[-1]],
            all_player_dice=game.all_rounds_dice[-1],
            all_actions=game.all_rounds_actions[-1],
            single_die_round=game.single_die_round_history[-1],
            losers=[player.name for player in losers],
        )

    def print(self) -> None:
        print('===================')
        for player, dice in zip(self.ordered_players, self.all_player_dice):
            print(f'  {player}: {dice_to_str(dice)}')
        print('  -----------------')
        action_print_width = len(str(len(self.all_actions)))
        player_print_width = max(len(player) for player in self.ordered_players)
        for action_index, action in enumerate(self.all_actions):
            player = self.ordered_players[action_index % len(self.ordered_players)]
            print(f'  {action_index:>{action_print_width}} - {player+':':<{player_print_width+1}} {action}')
        print('  -----------------')
        print(f'  Round Loser(s): {", ".join(self.losers)}\n')

@dataclasses.dataclass(frozen=True)
class GameSummary(common.BaseFrozen):
    """
    Note that this class primarily exists so that it can be sent over the
    network via standard send_obj methods.
    """
    all_rounds_actions: list[list[actions.Action]]
    all_rounds_dice: list[list[collections.Counter[int]]]
    all_rounds_living_players: list[list[str]]
    all_rounds_losers: list[list[str]]
    single_die_round_history: list[bool]
    winner: str

    @classmethod
    def from_game(
        cls,
        game: PerudoGame,
        winner_index: int,
    ) -> ty.Self:
        return cls(
            all_rounds_actions=game.all_rounds_actions,
            all_rounds_dice=game.all_rounds_dice,
            all_rounds_living_players=[
                [
                    game.players[player_index].name
                    for player_index in player_indices
                ]
                for player_indices in game.all_rounds_living_players
            ],
            all_rounds_losers=[
                [
                    game.players[player_index].name
                    for player_index in player_indices
                ]
                for player_indices in game.all_rounds_losers
            ],
            single_die_round_history=game.single_die_round_history,
            winner=game.players[winner_index].name,
        )

    def print(self) -> None:
        print("Game Summary:\n==============")
        for round_index, (
                ordered_players,
                round_actions,
                round_dice,
                round_losers,
                single_die_round,
        ) in enumerate(
            zip(
                self.all_rounds_living_players,
                self.all_rounds_actions,
                self.all_rounds_dice,
                self.all_rounds_losers,
                self.single_die_round_history,
                strict=True
            ), start=1
        ):
            header = f"Round {round_index} ({single_die_round=})"
            print(f'{"-" * len(header)}\n{header}')
            round_summary = RoundSummary(
                ordered_players=ordered_players,
                all_player_dice=round_dice,
                all_actions=round_actions,
                single_die_round=single_die_round,
                losers=round_losers,
            )
            round_summary.print()
        print(f"==============\nWinner: {self.winner}\n")
