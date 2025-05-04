"""
Network Message Format
"""

import binascii
import collections
import dataclasses
import json
import secrets
import typing as ty

from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization

from perudo import common
from perudo import actions
from perudo import perudo_game as pg

@dataclasses.dataclass(frozen=True)
class WrappedMessage:
    """
    Message format. Actual contents are contained in the data field, and must
    also be a common.BaseFrozen object.

    This class probably won't be used directly, outside of the handshake
    in network_common. Most code should use Connection.send_obj and receive_obj
    from that module to send and receive BaseFrozen objects directly

    RECEIVED_SALTS and SENT_SALTS are used to prevent replay attacks.
    """
    SALT_LEN: ty.ClassVar[int] = 32
    TYPE_NAME_TO_TYPE_D: ty.ClassVar[dict[str, type[common.BaseFrozen]]] = {}
    RECEIVED_SALTS: ty.ClassVar[collections.defaultdict[bytes, set[bytes]]] = collections.defaultdict(set)
    SENT_SALTS: ty.ClassVar[set[bytes]] = set()
    VERSION: ty.ClassVar[str] = "0.1"

    salt: bytes
    public_key: ed25519.Ed25519PublicKey
    type_name: str
    data: common.BaseFrozen
    signature: bytes
    version: str = VERSION

    @classmethod
    def register_type[T: type[common.BaseFrozen]](cls, ToRegister: T) -> T:
        cls.TYPE_NAME_TO_TYPE_D[ToRegister.__name__] = ToRegister
        return ToRegister

    @staticmethod
    def _get_thing_to_sign(
        public_key: ed25519.Ed25519PublicKey,
        type_name: str,
        data_bytes: bytes,
        salt: bytes,
    ) -> bytes:
        return (
            salt
            + public_key.public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
            + type_name.encode()
            + data_bytes
        )

    @classmethod
    def from_bytes(cls, json_str: str | bytes, ) -> ty.Self:
        """
        Also verifies the signature.
        """
        try:
            as_dict = json.loads(json_str)
            public_key_bytes = binascii.unhexlify(as_dict['public_key'])
            salt = binascii.unhexlify(as_dict['salt'])
            if salt in cls.RECEIVED_SALTS[public_key_bytes]:
                raise common.ConstructionError(f"Received duplicate salt: {salt!r}")

            public_key = ed25519.Ed25519PublicKey.from_public_bytes(public_key_bytes)
            signature = binascii.unhexlify(as_dict['signature'])
            type_name = as_dict['type']
            DataType = cls.TYPE_NAME_TO_TYPE_D[type_name]
            data_bytes = as_dict['data'].encode()
            version = as_dict['version']

            assert version == cls.VERSION, f"Version mismatch: {version} != {cls.VERSION}"

            # raises if not valid signature
            public_key.verify(
                signature,
                cls._get_thing_to_sign(
                    public_key=public_key,
                    type_name=type_name,
                    data_bytes=data_bytes,
                    salt=salt,
                ),
            )

            data = DataType.from_json(data_bytes)

        except Exception as exc:
            raise common.ConstructionError(f"Can't construct {cls.__name__} from:\n\n{json_str!r}") from exc

        cls.RECEIVED_SALTS[public_key_bytes].add(salt)
        return cls(
            salt=salt,
            public_key=public_key,
            type_name=type_name,
            data=data,
            signature=signature,
        )

    def to_bytes(self) -> bytes:
        data_str = self.data.to_json()

        as_dict = {
            'salt': binascii.hexlify(self.salt).decode(),
            'public_key': binascii.hexlify(self.public_key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode(),
            'type': self.type_name,
            'data': data_str,
            'signature': self.signature.hex(),
            'version': self.version,
        }

        return json.dumps(as_dict).encode()

    @classmethod
    def from_data(
        cls,
        data: common.BaseFrozen,
        private_key: ed25519.Ed25519PrivateKey,
    ) -> ty.Self:
        while (salt := secrets.token_bytes(cls.SALT_LEN)) in cls.SENT_SALTS:
            pass

        if type(data).__name__ not in cls.TYPE_NAME_TO_TYPE_D:
            raise common.ConstructionError(f"Can't construct {cls.__name__} from {data} because it's not a known type")

        to_sign = cls._get_thing_to_sign(
            public_key=private_key.public_key(),
            type_name=type(data).__name__,
            data_bytes=data.to_json().encode(),
            salt=salt,
        )

        signature = private_key.sign(to_sign)

        return cls(
            salt=salt,
            public_key=private_key.public_key(),
            type_name=type(data).__name__,
            data=data,
            signature=signature,
        )

    @classmethod
    def data_to_bytes(
        cls,
        data: common.BaseFrozen,
        private_key: ed25519.Ed25519PrivateKey,
    ) -> bytes:
        message = cls.from_data(
            data=data,
            private_key=private_key,
        )
        return message.to_bytes()

@WrappedMessage.register_type
@dataclasses.dataclass(frozen=True)
class Error(common.BaseFrozen):
    contents: str


# Kinda gross-ish, but I'm doing this to keep the base game not caring about
# network stuff while simplifying the messages and avoid a message wrapping
# a message that says what kind of action it is.
WrappedMessage.register_type(actions.Bid)
WrappedMessage.register_type(actions.Challenge)
WrappedMessage.register_type(actions.Exact)
WrappedMessage.register_type(pg.RoundSummary)

### Handshake Messages
@WrappedMessage.register_type
@dataclasses.dataclass(frozen=True)
class FromServerHandshake(common.BaseFrozen):
    message: str = "Who dis?"

@WrappedMessage.register_type
@dataclasses.dataclass(frozen=True)
class ToServerHandshake(common.BaseFrozen):
    name: str

### Can be used by client or server
@WrappedMessage.register_type
@dataclasses.dataclass(frozen=True)
class NoOp(common.BaseFrozen):
    """
    Exists mostly just to test that the connection is alive
    """

@WrappedMessage.register_type
@dataclasses.dataclass(frozen=True)
class Corrupted(common.BaseFrozen):
    """
    Exists so something can be returned on reception of a corrupted message.
    """
    contents: object

### General Use Messages: FROM SERVER TO CLIENT
@WrappedMessage.register_type
@dataclasses.dataclass(frozen=True)
class ActionRequest(common.BaseFrozen):
    """
    FROM SERVER TO CLIENT: request an action. Client should respond with action

    Fields should match argument to players.PlayerABC.get_action
    """
    round_actions: list[actions.Action]
    is_single_die_round: bool
    num_dice_in_play: int
    num_players_alive: int

@WrappedMessage.register_type
@dataclasses.dataclass(frozen=True)
class SetDice(common.BaseFrozen):
    """
    FROM SERVER TO CLIENT: tell the client what dice they get
    """
    dice: collections.Counter[int]

@WrappedMessage.register_type
@dataclasses.dataclass(frozen=True)
class RoomsListResponse(common.BaseFrozen):
    room_to_members: dict[str, list[str]]

    def print(self) -> None:
        if not self.room_to_members:
            print("No rooms")
            return
        for room, members in self.room_to_members.items():
            print(f'Room: {room}')
            for member in members:
                print(f'  {member}')
            print()

### General Use Messages: FROM CLIENT TO SERVER
@WrappedMessage.register_type
@dataclasses.dataclass(frozen=True)
class RequestRoomList(common.BaseFrozen):
    pass

@WrappedMessage.register_type
@dataclasses.dataclass(frozen=True)
class JoinRoom(common.BaseFrozen):
    room_name: str | None  # value of None means to pick a room at random

@WrappedMessage.register_type
@dataclasses.dataclass(frozen=True)
class CreateRoom(common.BaseFrozen):
    room_name: str
    num_network_players: int
    num_random_players: int
    num_probabilistic_players: int

    def check_for_errors(self, max_num_players: float = float('inf')) -> str | None:
        if self.num_network_players <= 0:
            return "Must have at least one network player"
        elif self.num_random_players < 0:
            return "Random player count must be non-negative"
        elif self.num_probabilistic_players < 0:
            return "Probabilistic player count must be non-negative"
        elif self.num_players > max_num_players:
            return f"Too many players: {self.num_players} > {max_num_players}"
        elif self.num_players < 2:
            return "Must have at least two players"

        return None

    @property
    def num_players(self) -> int:
        return self.num_network_players + self.num_random_players + self.num_probabilistic_players
