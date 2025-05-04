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
    NAME_TO_TO_PLAYER_CONSTRUCTOR_D: ty.ClassVar[dict[
        str,
        pl.PlayerABC.ConstructorType
    ]] = {}

    connection: nc.Connection
    player: pl.PlayerABC

    @ty.overload
    @classmethod
    def register_player_class[
        T: pl.PlayerABC.ConstructorType | type[pl.PlayerABC]
    ](
        cls,
        name_or_constructor: str | None,
    ) -> ty.Callable[[T], T]:
        ...

    @ty.overload
    @classmethod
    def register_player_class[
        T: pl.PlayerABC.ConstructorType | type[pl.PlayerABC]
    ](
        cls,
        name_or_constructor: T,
    ) -> T:
        ...

    @classmethod
    def register_player_class[
        T: pl.PlayerABC.ConstructorType | type[pl.PlayerABC]
    ](
        cls,
        name_or_constructor: str | T | None = None,
    ) -> ty.Callable[[T], T] | T:
        def inner(constructor: T) -> T:
            name: str | None
            error_message = (  # this is defined up here just because type checkers are confused if it's not
                f'Tried to register {constructor} ({type(constructor).__name__}) '
                'as a player class, but it is a type and not a subclass of PlayerABC. '
                'This is not allowed.'
            )
            if isinstance(name_or_constructor, str):
                name = name_or_constructor
            else:
                name = getattr(constructor, '__name__', None)
                if name is None:
                    raise TypeError(
                        f'Tried to register {name_or_constructor} ({type(name_or_constructor).__name__}) '
                        'as a player class, but it has no __name__ attribute. Use '
                        '@ClientPlayer.register_player_class(name) as a decorator instead, '
                        'or ClientPlayer.register_player_class(name)(constructor).'
                    )

            if isinstance(constructor, type):
                if not issubclass(constructor, pl.PlayerABC):
                    raise TypeError(error_message)

                cls.NAME_TO_TO_PLAYER_CONSTRUCTOR_D[name] = constructor.from_name
            else:
                cls.NAME_TO_TO_PLAYER_CONSTRUCTOR_D[name] = constructor

            return ty.cast(T, constructor)  # this cast wouldn't be necessary if type checkers were smarter.

        if name_or_constructor is None or isinstance(name_or_constructor, str):
            return inner

        return inner(name_or_constructor)

    async def run_game_loop(self) -> None:
        """
        Interact with the game until it's over

        # Todo: break into more functions maybe, if I feel like it.
        """
        while True:
            message = await self.connection.receive_obj()
            if isinstance(message, messaging.Error):
                print(message.error_message)
                return
            elif isinstance(message, messaging.Corrupted):
                print(message.details)
                return
            elif isinstance(message, messaging.SetDice):
                print(f"Player {self.player.name} set dice to {message.dice}")
                self.player.set_dice(message.dice)
            elif isinstance(message, messaging.ActionRequest):
                action = self.player.get_action(
                    round_actions=message.round_actions,
                    is_single_die_round=message.is_single_die_round,
                    num_dice_in_play=message.num_dice_in_play,
                    num_players_alive=message.num_players_alive,
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
        player_constructor: str | pl.PlayerABC.ConstructorType,
        connection: nc.Connection,
    ) -> ty.Self:
        if isinstance(player_constructor, str):
            player_constructor = cls.NAME_TO_TO_PLAYER_CONSTRUCTOR_D[player_constructor]

        player = player_constructor(connection.name)

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
        if not isinstance(room_list_response, messaging.HereRoomsList):
            await self.close()
            raise common.ConstructionError(f"Expected room list, but got {room_list_response}")
        room_list_response.print()

    async def join_room(
        self,
        room_name: str | None,
        player_constructor: str | pl.PlayerABC.ConstructorType,
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
        player_constructor: str | pl.PlayerABC.ConstructorType,
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

        await asyncio.gather(
            player.run_game_loop(),
            self.send_obj(create_message)
        )

ClientPlayer.register_player_class(pl.HumanPlayer)
ClientPlayer.register_player_class(pl.ProbalisticPlayer)
ClientPlayer.register_player_class(pl.RandomLegalPlayer)
