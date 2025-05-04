"""
Contains common constants, functions, and classes used throughout the project.
"""
import collections
import dataclasses
import json
import random
import traceback
import typing as ty

WILD_FACE_VAL = 1
MIN_FACE_VAL = 1
MAX_FACE_VAL = 6
NUM_FACES = MAX_FACE_VAL - MIN_FACE_VAL + 1
assert NUM_FACES > 1, "Can't have only one face"
# may remove this restriction later, but some code would have to change
assert MIN_FACE_VAL <= WILD_FACE_VAL <= MAX_FACE_VAL, "Wild card must be in range"
assert WILD_FACE_VAL == MIN_FACE_VAL, "Wild card must be first"  # TODO fix bid looping logic so this isn't necessary


def validate_face(face: int) -> bool:
    return MIN_FACE_VAL <= face <= MAX_FACE_VAL

def exception_to_str(exception: Exception) -> str:
    return ''.join(traceback.format_exception(type(exception), exception, exception.__traceback__))


class ConstructionError(Exception):
    """
    This exception is always raised if construction of an object in this module
    fails (eg, wrong json fields, etc)
    """

def get_option_from_human(options: ty.Collection[str]) -> str:
    while True:
        selected = input(f'Choose from:\n  - {'\n  - '.join(options)}\n')
        if selected in options:
            break
    return selected

def get_face_from_human() -> int:
    while True:
        try:
            face = int(input('Enter dice face value: '))
        except ValueError:
            continue
        if MIN_FACE_VAL <= face <= MAX_FACE_VAL:
            return face
    raise RuntimeError("Reached impossible code")  # Makes type checker happier

def get_count_from_human(min_val: int = MIN_FACE_VAL) -> int:
    while True:
        try:
            count = int(input('Enter dice count value: '))
        except ValueError:
            continue
        if count >= min_val:
            return count

    raise RuntimeError("Reached impossible code")  # Makes type checker happier

def get_random_face() -> int:
    return random.randint(MIN_FACE_VAL, MAX_FACE_VAL)

def get_random_non_wild_face() -> int:
    face = get_random_face()
    while face == WILD_FACE_VAL:
        face = get_random_face()
    return face

# pyright: reportUnknownVariableType=false, reportUnknownArgumentType=false
def _is_instance_of_typehint(obj: object, hint: ty.Any) -> bool:
    """
    check if object is of type hint.

    pyright is silenced for a lot of this function, because the whole point of
    this function is to determine if there are any problems with the types at
    run time, and pyright will just complain uselessly unless I add a lot of
    useless type ignore comments or ty.Any or similar.

    What this function is telling me is that I should have used pydantic.
    """
    origin = ty.get_origin(hint)
    args = ty.get_args(hint)

    if origin is None:
        return isinstance(obj, hint)

    if origin is list:
        return (
            isinstance(obj, list)
            and all(_is_instance_of_typehint(item, args[0]) for item in obj)
        )

    # Add support for more container types as needed
    if origin is dict:
        key_type, val_type = args
        return (
            isinstance(obj, dict)
            and all(
            _is_instance_of_typehint(k, key_type) and _is_instance_of_typehint(v, val_type)
            for k, v in obj.items()
            )
        )
    if origin is collections.Counter:
        key_type = args[0]
        return (
            isinstance(obj, collections.Counter)
            and all(
                _is_instance_of_typehint(key, key_type)
                for key in obj.keys()
            )
        )

    if origin is ty.Union:
        return any(_is_instance_of_typehint(obj, arg) for arg in args)

    raise TypeError(f"Unsupported type hint: {hint}")

@dataclasses.dataclass(frozen=True)
class BaseFrozen:
    """
    Represents a base frozen dataclass with type validation and utility methods for
    serialization and deserialization.

    NOTE: Type hints must work with _is_instance_of_typehint.

    I really should have used pydantic for this.

    This immutable dataclass validates the types of its attributes upon initialization.
    It provides methods to create an instance from a dictionary or a JSON string and
    to convert the instance into a dictionary or a JSON string.
    """
    def __post_init__(self) -> None:
        errors: list[str] = []
        for field in dataclasses.fields(self):
            value = getattr(self, field.name)
            if not _is_instance_of_typehint(value, field.type):
                errors.append(
                    f'Field {field.name} expected type {field.type}, but got '
                    f'object {value} of type {type(value)}.'
                )
        if errors:
            raise ConstructionError('- '+'\n- '.join(errors))

    @classmethod
    def from_dict(cls, input_d: dict[str, ty.Any]) -> ty.Self:
        try:
            # Handle nested BaseFrozen types
            errors: list[str] = []
            kwargs: dict[str, ty.Any] = {}

            # really always a type dict[str, type], but that's handled below
            # to keep type checking happy.
            field_name_to_type_d: dict[str, ty.Any] = {
                field.name: field.type
                for field in dataclasses.fields(cls)
            }

            for field_name, value in input_d.items():
                if field_name not in field_name_to_type_d:
                    errors.append(f"Invalid field {field_name} in input_d to {cls.__name__}")
                    continue

                FieldType = field_name_to_type_d[field_name]
                if isinstance(FieldType, type) and issubclass(FieldType, BaseFrozen):
                    kwargs[field_name] = FieldType.from_dict(value)
                elif (
                    FieldType is collections.Counter
                    and isinstance(value, dict)
                ):
                    value = collections.Counter(ty.cast(dict[object, int], value))
                    if not _is_instance_of_typehint(value, FieldType):
                        errors.append(
                            f"Field {field_name} in input_d to {cls.__name__} expected "
                            f"type {FieldType}, but got object {value} of type {type(value)}."
                        )
                    kwargs[field_name] = value

                elif not _is_instance_of_typehint(value, FieldType):
                    errors.append(
                        f"Field {field_name} in input_d to {cls.__name__} expected "
                        f"type {FieldType}, but got object {value} of type {type(value)}."
                    )
                else:
                    kwargs[field_name] = value
            if errors:
                raise ConstructionError(
                    f"Could not construct {cls.__name__} from specified input:\n    - "
                    + "\n    - ".join(errors)
                )

            # pycharm's type checker is wrong here
            # noinspection PyArgumentList
            return cls(**kwargs)

        except Exception as exc:
            raise ConstructionError(f"Can't construct {cls.__name__} from {input_d}") from exc


    @classmethod
    def from_json(cls, json_str: str | bytes) -> ty.Self:
        try:
            return cls.from_dict(json.loads(json_str))
        except:
            # display_str exists to make mypy happy, while still allowing actual
            # formatted json to be displayed in the error message if json_str is
            # a string (mypy gets annoyed about dropping bytes objects in fstrings
            # because it's stupid).
            display_str = repr(json_str) if isinstance(json_str, bytes) else json_str
            raise ConstructionError(f"Can't construct {cls.__name__} from:\n\n{display_str!r}")

    def to_dict(self) -> dict[str, ty.Any]:
        return dataclasses.asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict())
