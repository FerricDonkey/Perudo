import argparse

def add_n_random_arg(parser: argparse.ArgumentParser, default: int = 2) -> None:
    parser.add_argument(
        '--n-random', '--nr',
        type=int,
        dest='num_random_players',
        default=default,
        help='Number of random players to add to the game'
    )

def add_n_prob_arg(parser: argparse.ArgumentParser, default: int = 2) -> None:
    parser.add_argument(
        '--n-prob', '--np',
        type=int,
        dest='num_prob_players',
        default=default,
        help='Number of probabilistic players to add to the game'
    )
