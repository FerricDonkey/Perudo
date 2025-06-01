import asyncio
import dataclasses
import functools
import struct
import typing as ty

from perudo import common
from perudo.network_stuff import messaging

from cryptography.hazmat.primitives.asymmetric import ed25519

DEFAULT_SERVER_PORT: int = 1337
DEFAULT_MAX_PLAYERS_PER_GAME: int = 100
DEFAULT_MAX_GAMES_PER_SERVER: int = 100

@dataclasses.dataclass(frozen=True)
class Connection:
    LEN_PREFIX_FORMAT: ty.ClassVar[str] = '!I'
    LEN_PREFIX_LEN: ty.ClassVar[int] = 4
    MAX_MESSAGE_LEN: ty.ClassVar[int] = 10_000_000
    SEND_TIMEOUT: ty.ClassVar[int] = 10
    RECV_TIMEOUT: ty.ClassVar[float] = float('inf')  # Need heartbeats to set this to be finite (or something)

    name: str
    _reader: asyncio.StreamReader
    _writer: asyncio.StreamWriter
    _target_public_key: ed25519.Ed25519PublicKey
    _self_private_key: ed25519.Ed25519PrivateKey

    async def close(self) -> None:
        self._writer.close()
        try:
            await self._writer.wait_closed()
        except (ConnectionResetError, ConnectionAbortedError, OSError) as exc:
            print(f"Socket closed with error: {common.exception_to_str(exc)}")

    @functools.cached_property
    def ipaddress(self) -> str:
        return ty.cast(str, self._writer.get_extra_info('peername')[0])

    @functools.cached_property
    def port(self) -> int:
        return ty.cast(int, self._writer.get_extra_info('peername')[1])

    @classmethod
    async def from_handshake_client_side(
        cls,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        self_private_key: ed25519.Ed25519PrivateKey,
        name: str,
    ) -> ty.Self:
        incoming_handshake = await cls._receive_wrapped_message(reader=reader)
        if not isinstance(incoming_handshake.data, messaging.FromServerHandshake):
            raise common.ConstructionError(f"Expected wrapped handshake, but got {incoming_handshake}")

        target_public_key = incoming_handshake.public_key
        outgoing_handshake = messaging.WrappedMessage.from_data(
            data=messaging.ToServerHandshake(name=name),
            private_key=self_private_key,
        )
        await cls._send_wrapped_message(outgoing_handshake, writer)
        return cls(
            name=name,
            _reader=reader,
            _writer=writer,
            _target_public_key=target_public_key,
            _self_private_key=self_private_key,
        )

    @classmethod
    async def from_handshake_server_side(
        cls,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        self_private_key: ed25519.Ed25519PrivateKey,
    ) -> ty.Self:
        outgoing_handshake = messaging.WrappedMessage.from_data(
            data=messaging.FromServerHandshake(),
            private_key=self_private_key,
        )
        await cls._send_wrapped_message(outgoing_handshake, writer)
        incoming_handshake = await cls._receive_wrapped_message(reader=reader)
        if not isinstance(incoming_handshake.data, messaging.ToServerHandshake):
            raise common.ConstructionError(f"Expected wrapped handshake, but got {incoming_handshake}")

        return cls(
            name=incoming_handshake.data.name,
            _reader=reader,
            _writer=writer,
            _target_public_key=incoming_handshake.public_key,
            _self_private_key=self_private_key,
        )

    @classmethod
    async def _send_wrapped_message(
        cls,
        message: messaging.WrappedMessage,
        writer: asyncio.StreamWriter,
    ) -> None:
        try:
            wrapped = message.to_bytes()
            if len(wrapped) > cls.MAX_MESSAGE_LEN:
                raise common.ConstructionError(f"Message too long: {len(wrapped)} > {cls.MAX_MESSAGE_LEN}")
            to_send = struct.pack(cls.LEN_PREFIX_FORMAT, len(wrapped)) + wrapped
            writer.write(to_send)
            await asyncio.wait_for(writer.drain(), timeout=cls.SEND_TIMEOUT)

        except Exception as exc:
            print(f"Send failed: {common.exception_to_str(exc)}")
            writer.close()
            try:
                await writer.wait_closed()
            except (ConnectionResetError, ConnectionAbortedError, OSError) as exc:
                print(f"Socket closed with error: {common.exception_to_str(exc)}")

    @classmethod
    async def _receive_wrapped_message(
        cls,
        reader: asyncio.StreamReader,
    ) -> messaging.WrappedMessage:
        """
        DOES NOT CHECK THE PUBLIC KEY IS CORRECT. The message must be signed by
        whatever key is sent with it for it to get this far, but this does
        not check if the same public key was used to sign the message as the
        connection expects to be used.

        This is because this is a classmethod, and the public key is not yet
        known.

        It is expected that the rest of the code will use receive_obj to get
        actual information, and that method DOES verify that the public key is
        correct. If it becomes necessary to operate on WrappedMessage objects
        outside of the handshake, then an additional regular method should be
        added to handle that and also confirm the public key.
        """
        len_bytes = await asyncio.wait_for(reader.readexactly(cls.LEN_PREFIX_LEN), timeout=cls.RECV_TIMEOUT)
        wrapped_len = struct.unpack(cls.LEN_PREFIX_FORMAT, len_bytes)[0]
        if wrapped_len > cls.MAX_MESSAGE_LEN:
            raise common.ConstructionError(f"Message too long: {wrapped_len} > {cls.MAX_MESSAGE_LEN}")
        wrapped = await asyncio.wait_for(reader.readexactly(wrapped_len), timeout=cls.RECV_TIMEOUT)
        return messaging.WrappedMessage.from_bytes(wrapped)

    async def send_obj(self, obj: common.BaseFrozen) -> None:
        print(f"-->> send {obj}")
        await self._send_wrapped_message(
            message=messaging.WrappedMessage.from_data(obj, self._self_private_key),
            writer=self._writer,
        )

    async def receive_obj(self) -> common.BaseFrozen:
        try:
            wrapped = await self._receive_wrapped_message(reader=self._reader)
        except Exception as exc:
            await self.close()
            error_message = f"Receive failed: {common.exception_to_str(exc)}"
            print('>>>>>', error_message)
            return messaging.Corrupted(contents=error_message)

        if wrapped.public_key != self._target_public_key:
            await self.close()
            error_message = f"Public key mismatch: {wrapped.public_key} != {self._target_public_key}"
            print('>>>>>', error_message)
            return messaging.Corrupted(contents=error_message)
        print(f"<<-- recv {wrapped.data}")
        return wrapped.data

    async def ping(self) -> bool:
        """
        Send a noop message to check if the connection is still alive.

        Note that the send_obj method will close the connection if it fails.
        """
        await self.send_obj(messaging.NoOpMessage())
        if self._writer.is_closing():
            return False
        return True

    def is_closing(self) -> bool:
        return self._writer.is_closing()
