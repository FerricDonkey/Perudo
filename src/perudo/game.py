import argparse
import collections
import dataclasses
import random
import typing as ty

from perudo import common
from perudo import actions
from perudo import players as pl


# DO NOT REGISTER THIS ACTION


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
    all_rounds_actions: list[list[actions.Action]] = dataclasses.field(default_factory=list)
    all_rounds_dice: list[list[collections.Counter[int]]] = dataclasses.field(default_factory=list)
    all_rounds_living_players: list[list[int]] = dataclasses.field(default_factory=list)
    all_rounds_losers: list[list[int]] = dataclasses.field(default_factory=list)
    single_die_round_history: list[bool] = dataclasses.field(default_factory=list)
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
                dice_str = ', '.join(f'{face}: {value}' for face, value in sorted(dice_counter.items()))
                print(
                    "{name} ({dice_count} dice): {dice_string}".format(
                        name=self.players[player_index].name,
                        dice_count=self.player_index_to_num_dice[player_index],
                        dice_string=dice_str,
                    )
                )
            print("-------------------")


    def end_round(self, loser_indexes: ty.Collection[int]) -> bool:
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
            self.start_new_round(
                first_player_index=next_player,
                single_die_round=single_die_round,
            )
            return True
        return False

    def take_turn(self) -> bool:
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

            return self.end_round(loser_indexes=losers)

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

        This is kind of redundant now that verbose is added, but I'm leaving
        it for now because I can convert it into a machine readable format
        later
        """
        if len(self.all_rounds_losers) != len(self.all_rounds_actions):
            raise RuntimeError("print_summary called during active round")

        print("Game Summary:\n==============")
        for round_index, (
            round_players,
            round_actions,
            round_dice,
            round_losers,
            single_die_round,
        ) in enumerate(zip(
            self.all_rounds_living_players,
            self.all_rounds_actions,
            self.all_rounds_dice,
            self.all_rounds_losers,
            self.single_die_round_history,
            strict=True
        ), start=1):
            header = f"Round {round_index} ({single_die_round=})"
            print(f'{header}\n{"-" * len(header)}')
            for player in round_players:
                dice_str = ', '.join(f'{face}: {value}' for face, value in sorted(round_dice[player].items()))
                print(f"    {self.players[player].name} ({sum(round_dice[player].values())} dice): {dice_str}")
            print('    -----------------')

            action_print_width = len(str(len(round_actions)))
            for action_index, action in enumerate(round_actions):
                player_index = round_players[action_index % len(round_players)]
                cur_player = self.players[player_index]
                print(f"    {action_index:>{action_print_width}} - {cur_player.typed_name}: {action}")
            print('    -----------------')
            print(f'    Round Loser(s): {", ".join(self.players[index].typed_name for index in round_losers)}\n')

    def local_main_loop(self) -> int:
        """
        Suitable for running the game purely locally

        returns winning index
        """
        first_player_index = random.randrange(len(self.players))
        self.start_new_round(
            first_player_index=first_player_index,
            single_die_round=False,  # Assuming we're not being weird.
        )
        while self.take_turn():
            pass
        return self.cur_player_index


def local_main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--n-random', '--nr',
        type=int,
        dest='num_random_players',
        default=2,
        help='Number of random players to add to the game'
    )
    parser.add_argument(
        '--n-prob', '--np',
        type=int,
        dest='num_prob_players',
        default=2,
        help='Number of probabilistic players to add to the game'
    )
    parser.add_argument(
        '--humans',
        type=str,
        dest='human_names',
        default=[],
        nargs='+',
        help='Names of human players to add to the game'
    )
    parser.add_argument(
        '--silent',
        action='store_false',
        dest='print_while_playing',
        help='Do not print what is happening while playing the game'
    )
    parser.add_argument(
        '--no-cheat',
        action='store_false',
        dest='print_non_human_dice',
        help='Do not print dice assignments for non-human players'
    )

    args = parser.parse_args()
    players: list[pl.PlayerABC] = [
        pl.RandomLegalPlayer(
            name=f'Rando-{index}'
        )
        for index in range(max(0, args.num_random_players))
    ]
    players.extend(
        pl.ProbalisticPlayer(
            name=f'Prob-{index}'
        )
        for index in range(max(0, args.num_prob_players))
    )
    players.extend((
        pl.HumanPlayer(name=human_name)
        for human_name in args.human_names
    ))
    if len(players) < 2:
        print("Need at least 2 players")
        return 1

    game = PerudoGame.from_player_list(
        players=players,
        print_while_playing=args.print_while_playing,
        print_non_human_dice=args.print_non_human_dice,
    )
    who_won = game.local_main_loop()
    # if not args.verbose:
    #     game.print_summary()  # todo this is kind of redundant
    print(f"The winner was {game.players[who_won].name}")
    return 0


if __name__ == '__main__':
    local_main()
