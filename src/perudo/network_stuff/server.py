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
import random
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

    def __init_subclass__(cls) -> None:
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

    is_alive: bool = True

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

    async def _purge_disconnected(self) -> None:
        while self.is_alive:
            for _ in range(30):
                await asyncio.sleep(1)
                for name, connection in list(self.name_to_connection_d.items()):
                    if connection.is_closing():
                        del self.name_to_connection_d[name]

            names = list(self.name_to_connection_d.keys())
            players = (self.name_to_connection_d[name] for name in names)
            still_connected = await asyncio.gather(*(player.ping() for player in players))
            for name, is_connected in zip(names, still_connected):
                if not is_connected:
                    del self.name_to_connection_d[name]

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
                self._purge_disconnected(),
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
        """
        Make the connection object, and dispatch to handler based on first
        message.

        Note: This method closes the connection when it ends, so make sure
        the handlers that need the connection alive until some condition is met
        do not return until then
        """
        if not self.is_alive:
            print("-- Received connection, but server is dead - closing.")
            writer.close()
            await writer.wait_closed()
            return

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
            self.name_to_connection_d[connection.name] = connection
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
    async def _handle_create_room(self, connection: nc.Connection, message: messaging.CreateRoom) -> None:
        room_name = message.room_name
        if room_name in self.room_name_to_game_manager_d:
            error_message = f"Rejected: Room {room_name} already exists"
            await connection.send_obj(
                messaging.Error(error_message=error_message)
            )
            print(">>>>", error_message)
            await connection.close()
            return

        validation_error = message.check_for_errors(max_num_players=self.max_players_per_game)
        if validation_error:
            await connection.send_obj(
                messaging.Error(error_message=validation_error)
            )
            print(">>>>", validation_error)
            await connection.close()

        room = GameManager.from_create_message(
            message=message,
            connection=connection,
            asyncio_loop=self._asyncio_loop,
        )
        self.room_name_to_game_manager_d[room_name] = room
        await room.start_manager()

    @_register_handler
    async def _handle_join_room(self, connection: nc.Connection, message: messaging.JoinRoom) -> None:
        room_name = message.room_name
        # Pick room at random if not specified
        if room_name is None:
            rooms_with_space = [room for room in self.room_name_to_game_manager_d.values() if len(room.players) < room.num_players]
            if not rooms_with_space:
                error_message = "Rejected: No rooms with space"
                await connection.send_obj(
                    messaging.Error(error_message=error_message)
                )
                print(">>>>", error_message)
                await connection.close()
                return
            room_name = random.choice(rooms_with_space).room_name

        # Otherwise, make sure room exists
        elif room_name not in self.room_name_to_game_manager_d:
            error_message = f"Rejected: Room {room_name} does not exist"
            await connection.send_obj(
                messaging.Error(error_message=error_message)
            )
            print(">>>>", error_message)
            await connection.close()
            return

        room = self.room_name_to_game_manager_d[room_name]
        player = await room.add_player_from_connection(
            connection=connection,
            asyncio_loop=self._asyncio_loop,
        )

        # If player is not None, was successfully added to room. Wait till game ends
        if player is not None:
            while room.is_alive:
                await asyncio.sleep(2)


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

    def send_round_summary(self, round_summary: pg.RoundSummary) -> None:
        self._async_do(self.connection.send_obj(round_summary))

    def send_game_summary(self, game_summary: pg.GameSummary) -> None:
        self._async_do(self.connection.send_obj(game_summary))

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
    is_alive: bool = True

    async def add_player_from_connection(
        self,
        connection: nc.Connection,
        asyncio_loop: asyncio.AbstractEventLoop,
    ) -> RemotePlayer | None:
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
            return None

        if len(self.players) >= self.num_players:
            error_msg = f"Rejected: Game is full"
            await connection.send_obj(
                messaging.Error(error_message=error_msg)
            )
            print(">>>>", error_msg)
            return None

        self.players.append(new_player)
        return new_player

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

    async def start_manager(self) -> None:
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

        self.game_thread = threading.Thread(
            target=self._start_game,
        )
        self.game_thread.start()

        # Pause here until game is done, then shutdown
        while self.game_thread.is_alive():
            await asyncio.sleep(1)
        self.game_thread.join()
        self.game_thread = None
        self.game = None

    def _start_game(self) -> None:
        """
        Intended to be run in a separate thread. Starts the game
        """
        assert self.game is not None, "Game not started yet"
        self.game.main_loop(
            round_end_callback=self._broadcast_round_end_cb,
            game_end_callback=self._broadcast_winner_cb,
        )

    def _broadcast_round_end_cb(self, losers: list[pl.PlayerABC]) -> None:
        assert self.game is not None, "Game not started yet"
        round_summary = pg.RoundSummary.from_game_losers(
            game=self.game,
            losers=losers,
        )
        for player in self.players:
            if isinstance(player, RemotePlayer):
                player.send_round_summary(round_summary=round_summary)

    def _broadcast_winner_cb(self, winner: pl.PlayerABC) -> None:
        assert self.game is not None, "Game not started yet"
        game_summary = pg.GameSummary.from_game(self.game, winner_index=self.game.players.index(winner))
        for player in self.players:
            if isinstance(player, RemotePlayer):
                player.send_game_summary(game_summary=game_summary)

    @classmethod
    def from_create_message(
        cls,
        message: messaging.CreateRoom,
        connection: nc.Connection,
        asyncio_loop: asyncio.AbstractEventLoop,
    ) -> ty.Self:
        players: list[pl.PlayerABC] = []

        players.extend(
            pl.ProbalisticPlayer(name=f'ServerLocal-Prob-{index}')
            for index in range(message.num_probabilistic_players)
        )

        players.extend(
            pl.ProbalisticPlayer(name=f'ServerLocal-Rando-{index}')
            for index in range(message.num_probabilistic_players)
        )

        players.append(RemotePlayer(
            name=connection.name,
            connection=connection,
            asyncio_loop=asyncio_loop,
        ))

        return cls(
            room_name=message.room_name,
            players=players,
            num_players=message.num_players,
        )
