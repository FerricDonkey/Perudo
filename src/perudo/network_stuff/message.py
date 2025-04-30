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

@dataclasses.dataclass(frozen=True)
class Message:
    """
    Message format. Actual contents are contained in the data field, and must
    also be a common.BaseFrozen object.

    RECEIVED_SALTS and SENT_SALTS are used to prevent replay attacks.
    """
    SALT_LEN: ty.ClassVar[int] = 32
    TYPE_NAME_TO_TYPE_D: ty.ClassVar[dict[str, type[ty.Self]]] = {}
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
    def from_network(cls, json_str: str | bytes,) -> ty.Self:
        """
        Also verifies the signature.
        """
        try:
            as_dict = json.loads(json_str)
            public_key_bytes = binascii.unhexlify(as_dict['public_key'])
            salt = binascii.unhexlify(as_dict['salt'])
            if salt in cls.RECEIVED_SALTS[public_key_bytes]:
                raise common.ConstructionError(f"Received duplicate salt: {salt}")

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
            raise common.ConstructionError(f"Can't construct {cls.__name__} from:\n\n{json_str}") from exc

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

@Message.register_type
@dataclasses.dataclass(frozen=True)
class Error(common.BaseFrozen):
    error_message: str

@Message.register_type
@dataclasses.dataclass(frozen=True)
class DiceSend(common.BaseFrozen):
    """
    How the server sends the dice to the client.

    TODO: Encryption maybe, but maybe not because that might be annoying.

    But if we do encryption, then change the actual contents to the encrypted
    bytes, and convert dice_faces to a cached_property or something.
    """
    dice_faces: list[int]

# Kinda gross-ish, but I'm doing this to keep the base game not caring about
# network stuff while simplifying the messages and avoid a message wrapping
# a message that says what kind of action it is.
Message.register_type(actions.Bid)
Message.register_type(actions.Challenge)
Message.register_type(actions.Exact)
