"""
CLI entry point for hosting a server

can be run directly, or through cli_main.py or __main__.py
"""
import argparse
import sys

from perudo.network_stuff import network_common as nc
from perudo.network_stuff import server as nss

DESCRIPTION: str = '- Host a server for games of Perudo.'

def make_parser(parser: argparse.ArgumentParser | None=None) -> argparse.ArgumentParser:
    if parser is None:
        parser = argparse.ArgumentParser(description=DESCRIPTION)

    parser.add_argument(
        '--max-players-per-game', '--mpg',
        type=int,
        dest='max_players_per_game',
        default=nc.DEFAULT_MAX_PLAYERS_PER_GAME,
        help='Maximum number of players per game',
    )
    parser.add_argument(
        '--max-games-per-server', '--mgs',
        type=int,
        dest='max_concurrent_games',
        default=nc.DEFAULT_MAX_GAMES_PER_SERVER,
        help='Maximum number of concurrent games per server',
    )
    parser.add_argument(
        '--port',
        type=int,
        dest='port',
        default=nc.DEFAULT_SERVER_PORT,
        help='Port to host server on',
    )
    return parser

def main(args: argparse.Namespace | None = None) -> int:
    if args is None:
        parser = make_parser()
        args = parser.parse_args()

    server = nss.Server(
        max_players_per_game=args.max_players_per_game,
        max_concurrent_games=args.max_concurrent_games,
        port=args.port,
    )
    server.start()
    server.join()
    return 0

if __name__ == '__main__':
    sys.exit(main())
