"""
Connects to servers, manages network play
"""
import asyncio
import dataclasses
import typing as ty

from perudo.network_stuff import network_common as nc
from perudo.network_stuff import messaging

from perudo import common
from perudo import perudo_game as pg
from perudo import players as pl

from cryptography.hazmat.primitives.asymmetric import ed25519

@dataclasses.dataclass
class ClientPlayer:
    """
    Wraps a PlayerABC object, and uses it to interact with a game running
    on a server
    """
    connection: nc.Connection
    player: pl.PlayerABC

    async def run_game_loop(self) -> None:
        """
        Interact with the game until it's over

        # Todo: Change to the registered callback paradigm, if I feel like it.
        """
        while True:
            message = await self.connection.receive_obj()
            if isinstance(message, (messaging.Error, messaging.Corrupted)):
                print(message.contents)
                return
            elif isinstance(message, messaging.NoOpMessage):
                pass
            elif isinstance(message, messaging.SetDice):
                print(f"Player {self.player.name} set dice to {message.dice_faces}")
                self.player.set_dice(
                    common.dice_list_to_counter(message.dice_faces)
                )
            elif isinstance(message, messaging.Initialize):
                self.player.initialize(
                    index=message.index,
                    num_players=message.num_players,
                )
            elif isinstance(message, messaging.ActionRequest):
                action = self.player.get_action(
                    previous_action=message.previous_action,
                    is_single_die_round=message.is_single_die_round,
                    num_dice_in_play=message.num_dice_in_play,
                    player_dice_count_history=message.player_dice_count_history,
                    all_rounds_actions=message.all_rounds_actions,
                    dice_reveal_history=[
                        [common.dice_list_to_counter(dice_l) for dice_l in reveal_round]
                        for reveal_round in message.dice_reveal_history_listified
                    ],
                )
                await self.connection.send_obj(action)
            elif isinstance(message, pg.RoundSummary):
                # Only does things if the Player subclass does so.
                self.player.react_to_round_summary(message)
                # Only print this for human players, bots wait till end to see details.
                if isinstance(self.player, pl.HumanPlayer):
                    message.print()
            elif isinstance(message, pg.GameSummary):  # this means the game is over
                message.print()
                return
            else:
                print(f"Unknown message: {message}")
                return

    @classmethod
    def from_connection(
        cls,
        player_constructor: str | pl.PlayerConstructorType,
        connection: nc.Connection,
    ) -> ty.Self:

        player = pl.PlayerABC.from_constructor(
            player_name=connection.name,
            constructor=player_constructor,
        )

        return cls(
            connection=connection,
            player=player
        )


@dataclasses.dataclass
class ClientManager:
    connection: nc.Connection

    @classmethod
    async def from_network(
        cls,
        name: str,
        ipaddress: str,
        port: int,
    ) -> ty.Self:
        reader, writer = await asyncio.open_connection(ipaddress, port)
        connection = await nc.Connection.from_handshake_client_side(
            reader=reader,
            writer=writer,
            self_private_key=ed25519.Ed25519PrivateKey.generate(),
            name=name,
        )
        return cls(
            connection=connection,
        )

    async def close(self) -> None:
        await self.connection.close()

    async def send_obj(self, obj: common.BaseFrozen) -> None:
        await self.connection.send_obj(obj)

    async def receive_obj(self) -> common.BaseFrozen:
        return await self.connection.receive_obj()

    async def ping(self) -> bool:
        return await self.connection.ping()

    async def get_room_list(self) -> None:
        await self.send_obj(messaging.RequestRoomList())
        room_list_response = await self.receive_obj()
        if not isinstance(room_list_response, messaging.RoomsListResponse):
            await self.close()
            if isinstance(room_list_response, (messaging.Corrupted, messaging.Error,)):
                print(room_list_response.contents)
            raise common.ConstructionError(f"Expected room list, but got {type(room_list_response).__name__}")
        room_list_response.print()

    async def join_room(
        self,
        room_name: str | None,
        player_constructor: str | pl.PlayerConstructorType,
    ) -> None:
        player = ClientPlayer.from_connection(
            player_constructor=player_constructor,
            connection=self.connection,
        )
        await asyncio.gather(
            player.run_game_loop(),
            self.send_obj(messaging.JoinRoom(room_name=room_name))
        )

    async def create_room(
        self,
        room_name: str,
        player_constructor: str | pl.PlayerConstructorType,
        num_network_players: int,
        num_random_players: int,
        num_probabilistic_players: int,
    ) -> None:
        player = ClientPlayer.from_connection(
            player_constructor=player_constructor,
            connection=self.connection,
        )
        create_message = messaging.CreateRoom(
            room_name=room_name,
            num_network_players=num_network_players,
            num_random_players=num_random_players,
            num_probabilistic_players=num_probabilistic_players,
        )

        error = create_message.check_for_errors()
        if error is not None:
            await self.close()
            raise common.ConstructionError(error)

        await self.send_obj(create_message)
        await player.run_game_loop()
