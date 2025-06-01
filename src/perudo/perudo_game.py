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

import dataclasses
import random
import typing as ty

from perudo import common
from perudo import actions
from perudo import players as pl


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
    """
    players: list[pl.PlayerABC]
    num_dice_by_player_history: list[list[int]] = dataclasses.field(default_factory=list[list[int]])
    cur_player_index: int = -1
    cur_round_single_die: bool = False
    all_rounds_actions: list[list[actions.Action]] = dataclasses.field(default_factory=list[list[actions.Action]])
    all_rounds_dice_counts: list[list[common.DiceCounts]] = dataclasses.field(default_factory=list[list[common.DiceCounts]])
    all_rounds_losers: list[list[int]] = dataclasses.field(default_factory=list[list[int]])
    single_die_round_history: list[bool] = dataclasses.field(default_factory=list[bool])
    print_while_playing: bool = False
    print_non_human_dice: bool = True
    hide_noops: bool = False

    @property
    def current_round_actions(self) -> list[actions.Action]:
        if not self.all_rounds_actions:
            raise RuntimeError('No current round')
        return self.all_rounds_actions[-1]

    @property
    def current_round_dice_by_player(self) -> list[common.DiceCounts]:
        if not self.all_rounds_actions:
            raise RuntimeError('No current round')
        return self.all_rounds_dice_counts[-1]

    def get_previous_living_player_index(self) -> int:
        """
        Raises an error if no player (excluding the current player) has any
        dice
        """
        prev_index = (self.cur_player_index - 1) % len(self.players)
        while self.num_dice_by_player_history[-1][prev_index] == 0:
            if prev_index == self.cur_player_index:
                raise RuntimeError("previous_living_player_index used when there wasn't one")
            prev_index = (prev_index - 1) % len(self.players)
        return prev_index

    def get_next_living_player_index(self) -> int:
        """
        Raises an error if no player (excluding the current player) has any
        dice
        """
        next_index = (self.cur_player_index + 1) % len(self.players)
        while self.num_dice_by_player_history[-1][next_index] == 0:
            if next_index == self.cur_player_index:
                raise RuntimeError("get_next_living_player_index used when there wasn't one")
            next_index = (next_index + 1) % len(self.players)
        return next_index

    def get_most_recent_non_noop_action(self) -> actions.Bid | None:
        for prev_action in reversed(self.current_round_actions):
            if not isinstance(prev_action, actions.NoOp):
                break
        else:
            return None
        assert isinstance(prev_action, actions.Bid), (
            "Last action was not a bid. This should never happen. "
            f"{prev_action=}, {self.current_round_actions=}, {self.all_rounds_actions=}"
        )
        return prev_action

    def start_new_round(
        self,
        first_player_index: int,
        single_die_round: bool
    ) -> None:
        if not (0 <= first_player_index < len(self.players)):
            raise RuntimeError(f'Invalid first_player_index {first_player_index} (Out of range)')

        if self.num_dice_by_player_history[-1][first_player_index] < 1:
            raise RuntimeError(f'Invalid first_player_index {first_player_index} (does not have dice)')

        self.single_die_round_history.append(single_die_round)
        self.cur_round_single_die = single_die_round
        self.all_rounds_actions.append([actions.NoOpFirstTurnSkip() for _ in range(first_player_index)])
        self.cur_player_index = first_player_index

        self.all_rounds_dice_counts.append([])
        for player, num_dice in zip(self.players, self.num_dice_by_player_history[-1]):
            dice_counts=common.DiceCounts.from_random(num_dice=num_dice)
            player.set_dice(dice_counts)
            self.current_round_dice_by_player.append(dice_counts)

        if self.print_while_playing:
            print(f"\nStarting new round ({single_die_round=} num_dice_in_play={sum(self.num_dice_by_player_history[-1])}):\n====================")
            for player_index, (
                player,
                player_dice,
                player_num_dice,
            ) in enumerate(zip(
                self.players,
                self.current_round_dice_by_player,
                self.num_dice_by_player_history[-1]
            )):
                if not self.print_non_human_dice and not isinstance(player, pl.HumanPlayer):
                    dice_str = "MASKED"
                else:
                    dice_str = player_dice.to_str()

                if player_index == first_player_index:
                    first_indicator = " <-------- First"
                else:
                    first_indicator = ""

                index_pwidth = len(str(len(self.players) - 1))
                print(
                    f'{player_index:>{index_pwidth}} - {player.name} '
                    f'({player_num_dice} dice): {dice_str}{first_indicator}'
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
        self.num_dice_by_player_history.append(self.num_dice_by_player_history[-1].copy())
        for index in loser_indexes:
            self.num_dice_by_player_history[-1][index] = max(0, self.num_dice_by_player_history[-1][index] - 1)

        # Start a new round if multiple people are still alive
        if sum(num > 0 for num in self.num_dice_by_player_history[-1]) > 1:
            losers_with_dice = [
                index for index in loser_indexes
                if self.num_dice_by_player_history[-1][index] > 0
            ]
            # TODO: Is this right?
            if losers_with_dice:
                next_player = random.choice(losers_with_dice)
            else:
                next_player = self.get_next_living_player_index()
            if any(
                self.num_dice_by_player_history[-1][index] == 1
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
        if self.num_dice_by_player_history[-1][self.cur_player_index] == 0:
            raise RuntimeError(f"Player index {self.cur_player_index} has no dice left")
        previous_action = self.get_most_recent_non_noop_action()
        num_living_players = sum(
            num_dice != 0
            for num_dice in self.num_dice_by_player_history[-1]
        )
        observation = pl.ActionObservation(
            previous_action=previous_action,
            is_single_die_round=self.cur_round_single_die,
            num_players=len(self.players),
            num_living_players=num_living_players,
            num_dice_in_play=sum(self.num_dice_by_player_history[-1]),
            num_dice_by_player_history=self.num_dice_by_player_history,
            all_rounds_actions=self.all_rounds_actions,
            dice_reveal_history=self.all_rounds_dice_counts[:-1],
        )
        action = self.players[self.cur_player_index].get_action(observation=observation)

        # Check if the action was valid. Will be an InvalidAction object if not
        action = action.validate(
            previous_action=previous_action,
            is_single_die_round=self.cur_round_single_die,
        )
        self.current_round_actions.append(action)
        if self.print_while_playing:
            print(f"    {self.players[self.cur_player_index].typed_name}: {action}")

        # Handle round ending actions (including InvalidActions)
        if isinstance(action, actions.EndAction):
            all_dice = common.DiceCounts.from_multi_counts(self.current_round_dice_by_player)
            other_living_players = [
                player_index
                for player_index, num_dice in enumerate(self.num_dice_by_player_history[-1])
                if player_index != self.cur_player_index and num_dice > 0
            ]
            losers = action.get_losers(
                previous_action=previous_action,
                all_dice_counts=all_dice,
                is_single_die_round=self.cur_round_single_die,
                caller=self.cur_player_index,
                previous_player=self.get_previous_living_player_index(),
                other_players=other_living_players,
            )
            if self.print_while_playing:
                print(f'Loser(s): {", ".join(self.players[loser].typed_name for loser in losers)}')

            return self.end_round(loser_indexes=losers,)

        next_player_index = self.get_next_living_player_index()
        noop_index = (self.cur_player_index + 1) % len(self.players)
        while noop_index != next_player_index:
            self.current_round_actions.append(actions.NoOpDead())
            if self.print_while_playing and not self.hide_noops:
                print(f"       (  {self.players[noop_index].typed_name}: {actions.NoOpDead()}  )")
            noop_index = (noop_index + 1) % len(self.players)

        self.cur_player_index = next_player_index
        return True

    @classmethod
    def from_player_list(
        cls,
        players: list[pl.PlayerABC],
        print_while_playing: bool=True,
        print_non_human_dice: bool=True,
        shuffle_players: bool=True,
    ) -> ty.Self:
        if shuffle_players:
            players = random.sample(players, len(players))
        else:
            players = players.copy()

        return cls(
            players=players,
            num_dice_by_player_history=[[common.STARTING_NUM_DICE for _ in players]],
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
        randomize_starting_player: bool = True,
    ) -> int:
        """
        Run the game until it ends.

        :param randomize_starting_player: If True, the starting player will be chosen randomly. Else, 0 goes first
        :param game_end_callback: Function called at game end with winning player
        :return: winning player index
        """
        for player_index, player in enumerate(self.players):
            player.initialize(
                index=player_index,
                num_players=len(self.players),
            )
        if randomize_starting_player:
            first_player_index = random.randrange(len(self.players))
        else:
            first_player_index = 0

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
    players: list[str]
    all_player_dice: list[common.DiceCounts]
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
            players=[player.name for player in game.players],
            all_player_dice=game.all_rounds_dice_counts[-1],
            all_actions=game.all_rounds_actions[-1],
            single_die_round=game.single_die_round_history[-1],
            losers=[player.name for player in losers],
        )

    def print(self, hide_noop:bool=False) -> None:
        print('===================')
        for player, dice_counts in zip(self.players, self.all_player_dice):
            num_dice = dice_counts.get_num_dice()
            if num_dice:
                print(f'  {player} ({num_dice}): {dice_counts.to_str()}')
            else:
                print(f'  {player} (0): Dead')
        print('  -----------------')
        action_print_width = len(str(len(self.all_actions)))
        player_print_width = max(len(player) for player in self.players)
        print(self.all_actions)
        for action_index, action in enumerate(self.all_actions):
            if isinstance(action, actions.NoOp):
                if hide_noop:
                    continue
                prefix = "    (  "
                suffix = "  )"
            else:
                prefix = ""
                suffix = ""

            player = self.players[action_index % len(self.players)]
            print(
                f'  {prefix}{action_index:>{action_print_width}} - '
                f'{player+':':<{player_print_width+1}} {action}{suffix}'
            )
        print('  -----------------')
        print(f'  Round Loser(s): {", ".join(self.losers)}\n')

@dataclasses.dataclass(frozen=True)
class GameSummary(common.BaseFrozen):
    """
    Note that this class primarily exists so that it can be sent over the
    network via standard send_obj methods.
    """
    all_rounds_actions: list[list[actions.Action]]
    all_rounds_dice: list[list[common.DiceCounts]]
    players: list[str]
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
            all_rounds_dice=game.all_rounds_dice_counts,
            players=[player.name for player in game.players],
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

    def print(self, hide_noop:bool=False) -> None:
        print("Game Summary:\n==============")
        for round_index, (
                round_actions,
                round_dice,
                round_losers,
                single_die_round,
        ) in enumerate(
            zip(
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
                players=self.players,
                all_player_dice=round_dice,
                all_actions=round_actions,
                single_die_round=single_die_round,
                losers=round_losers,
            )
            round_summary.print(hide_noop=hide_noop)
        print(f"==============\nWinner: {self.winner}\n")
