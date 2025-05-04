"""
CLI entry point for purely local games.

can be run directly, or through cli_main.py or __main__.py
"""

import argparse
import collections
import sys

from perudo.cli import cli_common as cc

from perudo import perudo_game as pg
from perudo import players as pl

DESCRIPTION: str = '- Play a local game of Perudo.'

def make_parser(parser: argparse.ArgumentParser | None=None) -> argparse.ArgumentParser:
    if parser is None:
        parser = argparse.ArgumentParser(description=DESCRIPTION)

    cc.add_n_random_arg(parser)
    cc.add_n_prob_arg(parser)

    parser.add_argument(
        '--arbitrary-players', '--ap',
        type=str,
        dest='arbitrary_player_classes',
        choices=sorted(pl.PlayerABC.NAME_TO_TO_PLAYER_CONSTRUCTOR_D.keys()),
        default=[],
        nargs='+',
        help='Names of human players to add to the game'
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

    return parser

def main(args: argparse.Namespace | None = None) -> int:
    if args is None:
        parser = make_parser()
        args = parser.parse_args()

    players: list[pl.PlayerABC] = [
        pl.RandomLegalPlayer(
            name=f'Rando-{index}'
        )
        for index in range(max(0, args.num_random_players))
    ]
    players.extend(
        pl.ProbabilisticPlayer(
            name=f'Prob-{index}'
        )
        for index in range(max(0, args.num_prob_players))
    )
    players.extend(
        (
            pl.HumanPlayer(name=human_name)
            for human_name in args.human_names
        )
    )

    arbitrary_class_counts: collections.Counter[str] = collections.Counter(args.arbitrary_player_classes)
    for player_class, count in arbitrary_class_counts.items():
        players.extend(
            pl.PlayerABC.from_constructor(
                player_name=f'Arb-{player_class}-{index}',
                constructor=player_class,
            )
            for index in range(count)
        )

    if len(players) < 2:
        print("Need at least 2 players")
        return 1

    if len({player.name for player in players}) != len(players):
        print("Player names must be unique")
        return 1

    game = pg.PerudoGame.from_player_list(
        players=players,
        print_while_playing=args.print_while_playing,
        print_non_human_dice=args.print_non_human_dice,
    )
    who_won = game.main_loop()
    # if not args.verbose:
    #     game.print_summary()  # todo this is kind of redundant
    print(f"The winner was {game.players[who_won].name}")
    return 0

if __name__ == '__main__':
    sys.exit(main())
