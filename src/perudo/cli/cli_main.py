"""
CLI Logic. __main__.py makes this the effective entry point
"""

import argparse
import sys
import typing as ty

from perudo.cli import client
from perudo.cli import local
from perudo.cli import server

def main() -> int:
    parser = argparse.ArgumentParser(description='Perudo game CLI')
    subparsers = parser.add_subparsers(dest='command', required=True)

    dispatch_d: dict[str, ty.Callable[[argparse.Namespace], int]] = {}
    for module in (local, client, server):
        command = module.__name__.split('.')[-1]
        subparser = subparsers.add_parser(
            command,
            help=module.DESCRIPTION,
        )
        module.make_parser(subparser)
        dispatch_d[command] = module.main

    args = parser.parse_args()
    return dispatch_d[args.command](args)

if __name__ == '__main__':
    sys.exit(main())