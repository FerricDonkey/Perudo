"""
Server code - handle connections, client objects from the perspective of the
server
"""

import asyncio
import collections
import concurrent.futures
import contextlib
import dataclasses
import functools
import socket
import threading
import typing as ty

from perudo.network_stuff import messaging
from perudo.network_stuff import network_common as nc
from perudo import players as pl
from perudo import actions
from perudo import common
from perudo import game

from cryptography.hazmat.primitives.asymmetric import ed25519

@dataclasses.dataclass
class Server:
    public_key: ed25519.Ed25519PublicKey
    private_key: ed25519.Ed25519PrivateKey
    name_to_connection_d: dict[str, nc.Connection] = dataclasses.field(default_factory=dict[str, nc.Connection])
    _asyncio_loop: asyncio.AbstractEventLoop = dataclasses.field(default_factory=asyncio.new_event_loop)
    port: int = 1337

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
        try:
            # Handshake

            pass
        except Exception as exc:
            print(f"Error in connection: {exc}")
        finally:
            writer.close()
            await writer.wait_closed()

@dataclasses.dataclass
class RemotePlayer(pl.PlayerABC):
    """
    The player from the perspective of the server.
    """
    TIMEOUT: ty.ClassVar[int] = 10

    connection: nc.Connection
    asyncio_loop: asyncio.AbstractEventLoop

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
