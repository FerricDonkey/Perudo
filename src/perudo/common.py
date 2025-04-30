"""
Contains common constants, functions, and classes used throughout the project.
"""
import dataclasses
import json
import random
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

@dataclasses.dataclass(frozen=True)
class BaseFrozen:
    """
    Represents a base frozen dataclass with type validation and utility methods for
    serialization and deserialization.

    NOTE: Type hints must be types, not strs.

    This immutable dataclass validates the types of its attributes upon initialization.
    It provides methods to create an instance from a dictionary or a JSON string and
    to convert the instance into a dictionary or a JSON string.
    """
    def __post_init__(self):
        errors = []
        for field in dataclasses.fields(self):
            value = getattr(self, field.name)
            if not isinstance(value, field.type):
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
            errors = []
            kwargs = {}
            field_name_to_type_d: dict[str, type] = {field.name: field.type for field in dataclasses.fields(cls)}
            for field_name, value in input_d.items():
                if field_name not in field_name_to_type_d:
                    errors.append(f"Invalid field {field_name} in input_d to {cls.__name__}")
                    continue
                FieldType = field_name_to_type_d[field_name]

                if issubclass(FieldType, BaseFrozen):
                    kwargs[field_name] = FieldType.from_dict(value)
                elif not isinstance(value, FieldType):
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
            return cls(**kwargs)  # type: ignore[call-arg] pycharm's type checker is wrong here

        except Exception as exc:
            raise ConstructionError(f"Can't construct {cls.__name__} from {input_d}") from exc

    @classmethod
    def from_json(cls, json_str: str | bytes) -> ty.Self:
        try:
            return cls.from_dict(json.loads(json_str))
        except:
            raise ConstructionError(f"Can't construct {cls.__name__} from:\n\n{json_str}")

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict())
