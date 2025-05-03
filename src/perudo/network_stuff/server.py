"""
Server code - handle connections, client objects from the perspective of the
server
"""

import abc
import asyncio
import collections
import concurrent.futures
import contextlib
import dataclasses
import functools
import inspect
import socket
import threading
import typing as ty

from perudo.network_stuff import messaging
from perudo.network_stuff import network_common as nc
from perudo import players as pl
from perudo import actions
from perudo import common
from perudo import perudo_game as pg

from cryptography.hazmat.primitives.asymmetric import ed25519


@dataclasses.dataclass
class _DummyServer(abc.ABC, metaclass=abc.ABCMeta):
    """
    This is an over engineered and stupid way to register handlers, but I wanna.
    I'm being fancy for the purpose of playing with the capability.

    Essentially, this base class makes it so that subclasses can register
    handlers by use of the decorator
    """
    MESSAGE_TYPE_TO_HANDLER_D: ty.ClassVar[dict[
        type[common.BaseFrozen],
        ty.Callable[[nc.Connection, common.BaseFrozen], ty.Awaitable[None]]
    ]] = {}

    @staticmethod
    def _register_handler[T: ty.Callable[..., ty.Awaitable[None]]](
        handler: T
    ) -> T:
        """
        This method marks methods for registrations
        """
        handler.is_handler = True  # type: ignore
        return handler

    def __init_subclass__(cls):
        super().__init_subclass__()
        for handler in cls.__dict__.values():
            if not getattr(handler, 'is_handler', False):
                continue

            sig = inspect.signature(handler)
            params = list(sig.parameters.values())

            # Expect: (self, connection, message)
            assert len(params) == 3, f"All handlers should take (self, conn, msg)"

            param_annotations = [
                p.annotation for p in params[1:]  # 1 is self
            ]
            assert len(param_annotations) == 2, "too many arguments"
            assert param_annotations[0] is nc.Connection, "First argument after self must be Connection"
            MessageType = param_annotations[1]

            assert isinstance(MessageType, type), "Second must be a subclass of BaseFrozen"
            assert inspect.isclass(MessageType) and issubclass(
                MessageType, common.BaseFrozen
            ), "Second must be subclass of BaseFrozen"

            if MessageType in cls.MESSAGE_TYPE_TO_HANDLER_D:
                raise ValueError(f"Handler already registered for {MessageType}")

            cls.MESSAGE_TYPE_TO_HANDLER_D[MessageType] = handler

@dataclasses.dataclass
class Server(_DummyServer):
    MESSAGE_TYPE_TO_HANDLER_D: ty.ClassVar[dict[
        type[common.BaseFrozen],
        ty.Callable[[nc.Connection, common.BaseFrozen], ty.Awaitable[None]]
    ]] = {}

    room_name_to_game_manager_d: dict[str, 'GameManager'] = dataclasses.field(default_factory=dict[str, 'GameManager'])
    name_to_connection_d: dict[str, nc.Connection] = dataclasses.field(default_factory=dict[str, nc.Connection])

    max_players_per_game: int = 100
    max_concurrent_games: int = 100

    port: int = 1337
    private_key: ed25519.Ed25519PrivateKey = dataclasses.field(default_factory=ed25519.Ed25519PrivateKey.generate)
    _asyncio_loop: asyncio.AbstractEventLoop = dataclasses.field(default_factory=asyncio.new_event_loop)

    _register_handler = _DummyServer._register_handler

    @functools.cached_property
    def public_key(self) -> ed25519.Ed25519PublicKey:
        return self.private_key.public_key()

    @functools.cached_property
    def _async_thread(self) -> threading.Thread:
        return threading.Thread(target=self._asyncio_loop.run_until_complete, args=(self.start_server(),))

    async def start_server(self) -> None:
        """
        Starts the server - but if you want it to actually manage the game,
        use sync_run instead.
        """
        async with (
            self._make_server(socket.AF_INET) as server_v4,
            self._make_server(socket.AF_INET6) as server_v6,
        ):
            await asyncio.gather(
                server_v4.serve_forever(),
                server_v6.serve_forever(),
            )

    def sync_run(self) -> None:
        """
        Starts the server in a new thread, runs the game in the current thread
        """
        self._async_thread.start()

    @contextlib.asynccontextmanager
    async def _make_server(self, mode: socket.AddressFamily) -> ty.AsyncIterator[asyncio.Server]:
        if mode == socket.AF_INET:
            host='0.0.0.0'
        elif mode == socket.AF_INET6:
            host='::'
        else:
            raise ValueError(f"Invalid mode: {mode}")

        server = await asyncio.start_server(
            client_connected_cb=self._handle_client,
            host=host,
            port=self.port,
            family=mode,
        )
        try:
            yield server
        finally:
            server.close()
            await server.wait_closed()

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        # Make the connection object
        try:
            connection = await nc.Connection.from_handshake_server_side(
                reader=reader,
                writer=writer,
                self_private_key=self.private_key,
            )
        except Exception as exc:
            print(f"Error in handling client: {exc}")
            writer.close()
            await writer.wait_closed()
            return

        # Dispatch to handler based on first message.
        try:
            message_obj = await connection.receive_obj()
            handler = self.MESSAGE_TYPE_TO_HANDLER_D[type(message_obj)]
            await handler(connection, message_obj)
        except Exception as exc:
            error_message = (
                f"Error in handling client {connection.name}: {type(exc).__name__} - "
                + ", ".join(map(str, exc.args))
            )
            print('>>>>>', error_message)
            try:
                await connection.send_obj(
                    obj=messaging.Error(error_message=error_message),
                )
            except Exception as exc2:
                print(
                    f">>>>> Error in sending error message {connection.name}: {type(exc2).__name__} - "
                    + ", ".join(map(str, exc2.args))
                )
        finally:
            await connection.close()

    @_register_handler
    async def _handle_request_room_list(self, connection: nc.Connection, _message: messaging.RequestRoomList) -> None:
        await connection.send_obj(
            messaging.HereRoomsList(
                room_to_members={
                    room_name: sorted(
                        player.name for player in game_manager.players
                    )
                    for room_name, game_manager in self.room_name_to_game_manager_d.items()
                }
            )
        )

    @_register_handler
    async def _handle_new_room(self, connection: nc.Connection, message: messaging.CreateRoom) -> None:
        pass

@dataclasses.dataclass
class RemotePlayer(pl.PlayerABC):
    """
    The player from the perspective of the server.

    Has both async and sync methods, to allow for use within the game and
    for basic communication with the server.
    """
    TIMEOUT: ty.ClassVar[int] = 10

    connection: nc.Connection
    asyncio_loop: asyncio.AbstractEventLoop

    def is_closing(self) -> bool:
        return self.connection.is_closing()

    async def close(self) -> None:
        await self.connection.close()

    async def ping(self) -> bool:
        return await self.connection.ping()

    def _async_do[T](self, coroutine: ty.Coroutine[None, None, T]) -> T:
        """
        blocking call to coroutine
        """
        future: concurrent.futures.Future[T] = asyncio.run_coroutine_threadsafe(
            coroutine,
            self.asyncio_loop,
        )
        return future.result(timeout=self.TIMEOUT)

    def get_action(
        self,
        round_actions: list[actions.Action],
        is_single_die_round: bool,
        num_dice_in_play: int,
        num_players_alive: int
    ) -> actions.Action:
        try:
            self._async_do(self.connection.send_obj(messaging.ActionRequest(
                round_actions=round_actions,
                is_single_die_round=is_single_die_round,
                num_dice_in_play=num_dice_in_play,
                num_players_alive=num_players_alive,
            )))
            putative_action = self._async_do(self.connection.receive_obj())
            if not isinstance(putative_action, actions.Action):
                return actions.InvalidAction(
                    attempted_action=putative_action,
                    reason=f"Expected {actions.Action}, got {type(putative_action)}",
                )
            return putative_action

        except Exception as exc:
            return actions.InvalidAction(
                attempted_action=None,
                reason=f"Error communicating with {self.connection.name}: {exc}",
            )

    def set_dice(
        self,
        dice: collections.Counter[int]
    ) -> None:
        try:
            self._async_do(self.connection.send_obj(
                messaging.SetDice(dice=dice)
            ))
        except Exception as exc:
            # TODO: Disconnect maybe, and give opportunity to reconnect?
            print(
                f">>> Error communicating with {self.connection.name}: {exc}. " 
                "Player may not have received dice update."
            )


@dataclasses.dataclass
class GameManager:
    room_name: str
    players: list[pl.PlayerABC]  # This will mostly be RemotePlayers, but support exists to add some local bots
    num_players: int
    game: pg.PerudoGame | None = None
    game_thread: threading.Thread | None = None

    async def add_player_from_connection(
        self,
        connection: nc.Connection,
        asyncio_loop: asyncio.AbstractEventLoop,
    ) -> None:
        """
        Add a player to the game. NOTE: There currently shouldn't be race
        conditions allowing more players than allowed to be added, because there
        are no awaits unless the player is being booted.

        If awaits are added that aren't immediately followed by a return, then
        we should add a lock to prevent the game from overfilling.

        Note that the start method will purge extra players, but we'd rather
        that not be necessary.
        """
        new_player = RemotePlayer(
            name=connection.name,
            connection=connection,
            asyncio_loop=asyncio_loop,
        )
        if new_player.name in (player.name for player in self.players):
            error_msg = f"Rejected: Player {new_player.name} already in game"
            await connection.send_obj(
                messaging.Error(error_message=error_msg)
            )
            print(">>>>", error_msg)
            return

        if len(self.players) >= self.num_players:
            error_msg = f"Rejected: Game is full"
            await connection.send_obj(
                messaging.Error(error_message=error_msg)
            )
            print(">>>>", error_msg)
            return

        self.players.append(new_player)

    async def _wait_until_full(self) -> None:
        """
        wait until the game is full, checking for disconnects
        """
        # stupid helper function because stupid async doesn't do stupid lambdas
        async def always_true() -> bool:
            return True

        while len(self.players) < self.num_players:
            # This checks if any players are closing (explicitly disconnected already)
            while len(self.players) < self.num_players:
                player_indexes_to_remove: list[int] = []
                for index, player in enumerate(self.players):
                    if isinstance(player, RemotePlayer) and player.is_closing():
                        player_indexes_to_remove.append(index)
                if player_indexes_to_remove:
                    for index in reversed(player_indexes_to_remove):
                        del self.players[index]
                await asyncio.sleep(0.1)

            # If we think we have enough players, do one final check to make
            # sure they all respond to ping
            # TODO this can be asyncified, probably
            tasks = (
                (
                    player.ping() if isinstance(player, RemotePlayer)
                    else always_true()
                )
                for player in self.players
            )
            connection_statuses: list[bool] = await asyncio.gather(*tasks)

            player_indexes_to_remove = []
            for index, still_connected in enumerate(connection_statuses):
                player = self.players[index]
                assert isinstance(player, RemotePlayer)
                if not still_connected:
                    await player.close()
                    player_indexes_to_remove.append(index)

            if player_indexes_to_remove:
                for index in reversed(player_indexes_to_remove):
                    del self.players[index]

    async def start(self) -> None:
        """
        Waits until there are enough players to start the game, then starts it

        We guard against too many players getting in, but don't have a way to
        boot
        """
        await self._wait_until_full()

        for player in self.players[self.num_players:]:
            if isinstance(player, RemotePlayer):
                error_msg = f"Rejected: Somehow more players than expected"
                await player.connection.send_obj(
                    messaging.Error(error_message=error_msg)
                )
                print(">>>>", error_msg)
                await player.connection.close()

        self.players = self.players[:self.num_players]
        self.game = pg.PerudoGame.from_player_list(
            players=self.players,
            print_while_playing=False,
            print_non_human_dice=False,
        )

        self.game_thread = threading.Thread(target=self.game.main_loop)
        self.game_thread.start()
