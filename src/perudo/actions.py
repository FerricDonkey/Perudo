import abc
import dataclasses
import math
import typing as ty

from perudo import common

@dataclasses.dataclass(frozen=True)
class Action(common.BaseFrozen):
    """
    All player actions should subclass this
    """
    _ACTION_NAME_TO_ACTION_TYPE_D: ty.ClassVar[dict[str, type['Action']]] = {}

    @abc.abstractmethod
    def validate(
        self,
        previous_action: None | ty.Self,
        is_single_die_round: bool,
    ) -> 'Action':
        """
        Check if this action was valid in its context, return an InvalidAction
        object if not and itself if so.

        :param previous_action: Previous action taken
        :param is_single_die_round: Whether this is a round started by a single die
        :return: The action if it was valid, or an InvalidAction object if not
        """
        raise NotImplementedError('Implement me bro.')

    @classmethod
    @abc.abstractmethod
    def get_from_human(cls, fixed_face: int | None) -> ty.Self:
        action_name = common.get_option_from_human(cls._ACTION_NAME_TO_ACTION_TYPE_D.keys())
        action = cls._ACTION_NAME_TO_ACTION_TYPE_D[action_name].get_from_human(fixed_face)
        assert isinstance(action, cls)
        return action


    @classmethod
    def register_action[T: type['Action']](cls, ToRegister: T) -> T:

        if ToRegister.__name__ in cls._ACTION_NAME_TO_ACTION_TYPE_D:
            raise TypeError(f'Registered Action with name {ToRegister.__name__} multiple times')
        cls._ACTION_NAME_TO_ACTION_TYPE_D[ToRegister.__name__] = ToRegister
        return ToRegister


@dataclasses.dataclass(frozen=True)
class EndAction(Action):
    """
    Actions that end a round should subclass this
    """
    @abc.abstractmethod
    def get_losers[T](
        self,
        previous_action: Action | None,
        all_dice_counts: common.DiceCounts,
        is_single_die_round: bool,
        caller: T,
        previous_player: T,
        other_players: ty.Collection[T]
    ) -> list[T]:
        """
        Return True if the player won, False if the player lost.

        Logic of what happens on win/lose is currently in the Game class
        rather than the action class, which I'm not super happy about

        :param previous_action: Action prior to this action (eg the bid before a challenge)
        :param all_dice: All the dice in play (just a list of faces or similar)
        :param is_single_die_round: Whether this is a round started by a single die
        :param caller: Who started this
        :param previous_player: Who was the previous player
        :param other_players: All players who aren't the caller
        :return: True if dude who did it was successful, False if not
        """
        raise NotImplementedError('Implement me bro.')

    @classmethod
    def get_from_human(cls, fixed_face:int | None) -> ty.Self:
        return cls()

    @abc.abstractmethod
    def validate(
        self,
        previous_action: None | Action,
        is_single_die_round: bool,
    ) -> 'EndAction':
        raise NotImplementedError('Implement me bro.')


@dataclasses.dataclass(frozen=True)
class InvalidAction(EndAction):
    """
    Always Fails. Contains what the action that failed was

    Do NOT register with the Action class - this should never be explicitly
    specified
    """
    attempted_action: object
    reason: str

    def get_losers[T](
        self,
        previous_action: Action | None,
        all_dice_counts: common.DiceCounts,
        is_single_die_round: bool,
        caller: T,
        previous_player: T,
        other_players: ty.Collection[T],
    ) -> list[T]:
        return [caller]

    @classmethod
    def get_from_human(cls, fixed_face:int | None) -> ty.Self:
        raise RuntimeError(f'{cls.__name__} should not call get_from_human')

    def validate(
        self,
        previous_action: None | Action,
        is_single_die_round: bool,
    ) -> 'EndAction':
        return self

@dataclasses.dataclass(frozen=True)
class NoOp(Action):
    """
    Player took no action - see subclasses for reasons why
    """
    @classmethod
    def get_from_human(cls, fixed_face:int | None) -> ty.Self:
        return cls()

    def validate(
        self,
        previous_action: None | Action,
        is_single_die_round: bool,
    ) -> Action:
        # Todo: should this be always invalid instead?
        raise RuntimeError(f'{type(self).__name__} should not call validate')

@dataclasses.dataclass(frozen=True)
class NoOpFirstTurnSkip(NoOp):
    """
    NoOp for alignment - if the first player is index 2, players 0 and 1
    automatically do this action. This keeps the actions aligned by player index

    subclass of NoOp so isinstance(action, NoOp) is True
    """

@dataclasses.dataclass(frozen=True)
class NoOpDead(NoOp):
    """
    Player didn't take an action because they are dead. This action is recorded
    for action alignment purposes.

    subclass of NoOp so isinstance(action, NoOp) is True
    """

@Action.register_action
@dataclasses.dataclass(frozen=True)
class Bid(Action):
    ACTION_NAME: ty.ClassVar[str] = 'Bid'
    face: int
    count: int

    def validate(
        self,
        previous_action: None | Action,
        is_single_die_round: bool,
    ) -> Action:
        # Handle always impossible
        if not common.validate_face(self.face):
            return InvalidAction(self, "Invalid Face")

        if self.count <= 0:
            return InvalidAction(self, "Non-positive Count")

        # Handle first bid
        if previous_action is None:
            if (
                self.face == 1
                and not is_single_die_round
            ):
                return InvalidAction(self, "Invalid Starting Bid")
            return self

        if not isinstance(previous_action, Bid):
            return InvalidAction(self, "Following non-bid (should be impossible)")

        # Handle following other bids
        assert isinstance(previous_action, Bid)
        min_count = previous_action.min_next_count(self.face)
        if self.count < min_count:
            return InvalidAction(self, f"Count for face {self.face} must be at least {min_count} (because of {previous_action=})")

        return self

    def min_next_count(self, next_face: int) -> int:
        assert common.validate_face(next_face)
        assert common.validate_face(self.face)
        if next_face == self.face:
            return self.count + 1
        if next_face > self.face and self.face != common.WILD_FACE_VAL:
            return self.count  # + 1 # TODO This might be wrong, but it stops some infinite loops.
        if next_face == common.WILD_FACE_VAL:
            return math.ceil(self.count / 2)
        if self.face == common.WILD_FACE_VAL:
            return self.count * 2 + 1
        return math.ceil(self.count / 2) * 2 + 1

    @classmethod
    def get_from_human(cls, fixed_face: int | None) -> ty.Self:
        if fixed_face is None:
            return cls(
                face=common.get_face_from_human(),
                count=common.get_count_from_human(),
            )
        return cls(
            face=fixed_face,
            count=common.get_count_from_human()
        )


@Action.register_action
@dataclasses.dataclass(frozen=True)
class Challenge(EndAction):
    ACTION_NAME: ty.ClassVar[str] = 'Challenge'
    def validate(
        self,
        previous_action: None | Action,
        is_single_die_round: bool,
    ) -> EndAction:
        if previous_action is None:
            return InvalidAction(self, f"Can't use {self.ACTION_NAME} as opening move")

        return self

    def get_losers[T](
        self,
        previous_action: Action | None,
        all_dice_counts: common.DiceCounts,
        is_single_die_round: bool,
        caller: T,
        previous_player: T,
        other_players: ty.Collection[T],
    ) -> list[T]:
        if not isinstance(previous_action, Bid):
            print(
                "WARNING: Challenge Action called check success when not "
                "following a bid, this should not be possible"
            )
            return [caller]

        num_existing = all_dice_counts[previous_action.face]
        if not is_single_die_round and previous_action.face != common.WILD_FACE_VAL:
            num_existing += all_dice_counts[common.WILD_FACE_VAL]

        if num_existing < previous_action.count:
            return [previous_player]
        return [caller]


@Action.register_action
@dataclasses.dataclass(frozen=True)
class Exact(EndAction):
    ACTION_NAME: ty.ClassVar[str] = 'Exact'

    validate = Challenge.validate  # Use same method as Challenge uses for this

    def get_losers[T](
        self,
        previous_action: Action | None,
        all_dice_counts: common.DiceCounts,
        is_single_die_round: bool,
        caller: T,
        previous_player: T,
        other_players: ty.Collection[T],
    ) -> list[T]:
        if not isinstance(previous_action, Bid):
            print(
                "WARNING: Challenge Action called check success when not "
                "following a bid, this should not be possible"
            )
            return [caller]

        num_existing = all_dice_counts[previous_action.face]
        if not is_single_die_round and previous_action.face != common.WILD_FACE_VAL:
            num_existing += all_dice_counts[common.WILD_FACE_VAL]

        if num_existing == previous_action.count:
            return list(other_players)

        return [caller]
