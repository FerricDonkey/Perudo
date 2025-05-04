"""
CLI entry point for joining/querrying a server

can be run directly, or through cli_main.py or __main__.py
"""
import argparse
import asyncio
import sys

from perudo.cli import cli_common as cc
from perudo import players as pl

from perudo.network_stuff import network_common as nc
from perudo.network_stuff import client as nsc

DESCRIPTION: str = '- Join or query a server for a game of Perudo.'

def make_parser(parser: argparse.ArgumentParser | None=None) -> argparse.ArgumentParser:
    if parser is None:
        parser = argparse.ArgumentParser(description=DESCRIPTION)

    subsubparsers = parser.add_subparsers(dest='subcommand', required=True)
    join_parser = subsubparsers.add_parser('join', help='- Join a game')
    _query_parser = subsubparsers.add_parser('query', help='- Get list of rooms')
    create_parser = subsubparsers.add_parser('create', help='- Create a new game')

    for subsubparser in (join_parser, _query_parser, create_parser):
        subsubparser.add_argument(
            '--host',
            type=str,
            dest='ipaddress',
            default='localhost',
            help='Host to connect to'
        )

        subsubparser.add_argument(
            '--port',
            type=int,
            dest='port',
            default=nc.DEFAULT_SERVER_PORT,
            help='Port to connect to'
        )

        subsubparser.add_argument(
            '--name',
            type=str,
            dest='name',
            required=True,
            help='Name to use for this player'
        )

    cc.add_n_prob_arg(create_parser, default=0)
    cc.add_n_random_arg(create_parser, default=0)
    create_parser.add_argument(
        '--num-network-players', '--nn',
        type=int,
        dest='num_network_players',
        required=True,
        help=(
            'Number of network players to host in this game. Game will start when this '
            'many join. Use 1 to play with server bots only - but this requires '
            'specifying random or probabilistic players as well.'
        )
    )

    for subsubparser in (join_parser, create_parser):
        subsubparser.add_argument(
            '--client-class', '--cc',
            type=str,
            dest='client_class',
            required=True,
            choices=sorted(pl.PlayerABC.NAME_TO_TO_PLAYER_CONSTRUCTOR_D.keys()),
            help='Player class that will run locally.',
        )

        subsubparser.add_argument(
            '--room-name', '--rn',
            type=str,
            dest='room_name',
            default=None,
            required=(subsubparser is create_parser),
            help=(
                'Name of room to create.' if subsubparser is create_parser
                else 'Name of room to join. If not specified, will try to join a random room'
            )
        )

    return parser

async def query(
    name:str,
    ipaddress:str,
    port:int,
) -> int:
    manager = await nsc.ClientManager.from_network(
        name=name,
        ipaddress=ipaddress,
        port=port,
    )
    await manager.get_room_list()
    await manager.close()

    return 0

async def join(
    name:str,
    ipaddress:str,
    port:int,
    constructor_name:str,
) -> int:
    manager = await nsc.ClientManager.from_network(
        name=name,
        ipaddress=ipaddress,
        port=port,
    )
    await manager.join_room(
        room_name=None,
        player_constructor=constructor_name,
    )
    return 0

async def create(
    name:str,
    room_name: str,
    ipaddress:str,
    port:int,
    client_class:str,
    num_network_players:int,
    num_random_players:int,
    num_probabilistic_players:int,
) -> int:
    manager = await nsc.ClientManager.from_network(
        name=name,
        ipaddress=ipaddress,
        port=port,
    )
    await manager.create_room(
        room_name=room_name,
        player_constructor=client_class,
        num_network_players=num_network_players,
        num_random_players=num_random_players,
        num_probabilistic_players=num_probabilistic_players,
    )
    return 0

def main(args: argparse.Namespace | None = None) -> int:
    if args is None:
        parser = make_parser()
        args = parser.parse_args()

    if args.subcommand == 'query':
        return asyncio.run(query(
            name=args.name,
            ipaddress=args.ipaddress,
            port=args.port,
        ))
    elif args.subcommand == 'join':
        return asyncio.run(join(
            name=args.name,
            ipaddress=args.ipaddress,
            port=args.port,
            constructor_name=args.arbitrary_player,
        ))
    elif args.subcommand == 'create':
        return asyncio.run(create(
            name=args.name,
            room_name=args.room_name,
            ipaddress=args.ipaddress,
            port=args.port,
            client_class=args.client_class,
            num_network_players=args.num_network_players,
            num_random_players=args.num_random_players,
            num_probabilistic_players=args.num_prob_players,
        ))
    else:
        raise ValueError(f"Unknown command: {args.command}")

if __name__ == '__main__':
    sys.exit(main())
