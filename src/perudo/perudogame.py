import abc
import argparse
import collections
import dataclasses
import json
import math
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

@dataclasses.dataclass
class Base:
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
    def from_dict(cls, action_d: dict[str, ty.Any]) -> ty.Self:
        try:
            return cls(**action_d)  # type: ignore (pycharm is stupid about this)
        except:
            raise ConstructionError(f"Can't construct {cls.__name__} from {action_d}")

    @classmethod
    def from_json(cls, json_str: str) -> ty.Self:
        try:
            return cls.from_dict(json.loads(json_str))
        except:
            raise ConstructionError(f"Can't construct {cls.__name__} from:\n\n{json_str}")

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

@dataclasses.dataclass
class Action(Base):
    """
    All player actions should subclass this
    """
    ACTION_NAME: ty.ClassVar[str]
    _ACTION_NAME_TO_ACTION_TYPE_D: ty.ClassVar[dict[str, type[ty.Self]]] = {}

    @abc.abstractmethod
    def validate(
        self,
        previous: None | ty.Self,
        is_single_die_round: bool,
    ) -> 'Action':
        """
        Check if this action was valid in its context, return an InvalidAction
        object if not and itself if so.

        :param previous: Previous action taken
        :param is_single_die_round: Whether this is a round started by a single die
        :return: The action if it was valid, or an InvalidAction object if not
        """
        raise NotImplemented('Implement me bro.')

    @classmethod
    @abc.abstractmethod
    def get_from_human(cls, fixed_face: int | None) -> ty.Self:
        action_name = get_option_from_human(cls._ACTION_NAME_TO_ACTION_TYPE_D.keys())
        return cls._ACTION_NAME_TO_ACTION_TYPE_D[action_name].get_from_human(fixed_face)


    @classmethod
    def register_action[T: type['Action']](cls, ToRegister: T) -> T:
        if ToRegister.ACTION_NAME in cls._ACTION_NAME_TO_ACTION_TYPE_D:
            raise TypeError(f'Registered Action with name {ToRegister.ACTION_NAME} multiple times')
        cls._ACTION_NAME_TO_ACTION_TYPE_D[ToRegister.ACTION_NAME] = ToRegister
        return ToRegister


# DO NOT REGISTER THIS ACTION
@dataclasses.dataclass
class EndAction(Action):
    """
    Actions that end a round should subclass this
    """
    @abc.abstractmethod
    def get_losers[T](
        self,
        previous_action: Action,
        all_dice: ty.Collection[int],
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
        raise NotImplemented('Implement me bro.')

    @classmethod
    def get_from_human(cls, fixed_face:int) -> ty.Self:
        return cls()

    def validate(
        self,
        previous: None | ty.Self,
        is_single_die_round: bool,
    ) -> ty.Self:
        return self


@dataclasses.dataclass
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
        previous_action: Action,
        all_dice: ty.Collection[int],
        is_single_die_round: bool,
        caller: T,
        previous_player: T,
        other_players: ty.Collection[T],
    ) -> list[T]:
        return [caller]

    @classmethod
    def get_from_human(cls, fixed_face:int) -> ty.Self:
        raise RuntimeError(f'{cls.__name__} should not call get_from_human')

@Action.register_action
@dataclasses.dataclass
class Bid(Action):
    ACTION_NAME: ty.ClassVar[str] = 'Bid'
    face: int
    count: int

    def validate(
        self,
        previous: None | Action,
        is_single_die_round: bool,
    ) -> Action:
        # Handle always impossible
        if not validate_face(self.face):
            return InvalidAction(self, "Invalid Face")

        if self.count <= 0:
            return InvalidAction(self, "Non-positive Count")

        # Handle first bid
        if previous is None:
            if (
                self.face == 1
                and not is_single_die_round
            ):
                return InvalidAction(self, "Invalid Starting Bid")
            return self

        if not isinstance(previous, Bid):
            return InvalidAction(self, "Following non-bid (should be impossible)")

        # Handle following other bids
        assert isinstance(previous, Bid)
        min_count = previous.min_next_count(self.face)
        if self.count < min_count:
            return InvalidAction(self, f"Count for face {self.face} must be at least {min_count} (because of {previous=})")

        return self

    def min_next_count(self, next_face: int) -> int:
        assert validate_face(next_face)
        assert validate_face(self.face)
        if next_face == self.face:
            return self.count + 1
        if next_face > self.face and self.face != WILD_FACE_VAL:
            return self.count  # + 1 # TODO This might be wrong, but it stops some infinite loops.
        if next_face == WILD_FACE_VAL:
            return math.ceil(self.count / 2)
        if self.face == WILD_FACE_VAL:
            return self.count * 2 + 1
        return math.ceil(self.count / 2) * 2 + 1

    @classmethod
    def get_from_human(cls, fixed_face: int | None) -> ty.Self:
        if fixed_face is None:
            return cls(
                face=get_face_from_human(),
                count=get_count_from_human(),
            )
        return cls(
            face=fixed_face,
            count=get_count_from_human()
        )


@Action.register_action
@dataclasses.dataclass
class Challenge(EndAction):
    ACTION_NAME: ty.ClassVar[str] = 'Challenge'
    def validate(
        self,
        previous: None | Action,
        is_single_die_round: bool,
    ) -> EndAction:
        if previous is None:
            return InvalidAction(self, f"Can't use {self.ACTION_NAME} as opening move")

        return self

    def get_losers[T](
        self,
        previous_action: Action,
        all_dice: ty.Collection[int],
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

        if is_single_die_round:
            num_existing = sum(face == previous_action.face for face in all_dice)
        else:
            num_existing = sum(
                face == previous_action.face or face == WILD_FACE_VAL
                for face in all_dice
            )

        if num_existing < previous_action.count:
            return [previous_player]
        return [caller]


@Action.register_action
@dataclasses.dataclass
class Exact(EndAction):
    ACTION_NAME: ty.ClassVar[str] = 'Exact'

    validate = Challenge.validate  # Use same method as Challenge uses for this

    def get_losers[T](
        self,
        previous_action: Action,
        all_dice: ty.Collection[int],
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

        if is_single_die_round:
            num_existing = sum(face == previous_action.face for face in all_dice)
        else:
            num_existing = sum(
                face == previous_action.face or face == WILD_FACE_VAL
                for face in all_dice
            )
        #print(f"{num_existing=}, {previous_action.count=}, {all_dice=}")
        if num_existing == previous_action.count:
            #print("WIN")
            return list(other_players)
        #print("LOSE")
        return [caller]


@dataclasses.dataclass
class PlayerABC:
    name: str
    cur_dice: collections.Counter[int] = dataclasses.field(default_factory=collections.Counter)
    #action_histories: list[list[Action]] = dataclasses.field(default_factory=list)

    @property
    def typed_name(self) -> str:
        return f"{self.name} ({type(self).__name__})"

    @abc.abstractmethod
    def get_action(
        self,
        round_actions: list[Action],
        is_single_die_round: bool,
        num_dice_in_play: int,
        num_players_alive: int,
    ) -> Action:
        raise NotImplementedError('Implement me bro.')

    @abc.abstractmethod
    def set_dice(self, dice: collections.Counter[int]) -> None:
        """
        Set players current dice to specified list.

        This is a method so that it can be overridden for network players
        """
        raise NotImplementedError('Implement me bro')


@dataclasses.dataclass
class HumanPlayer(PlayerABC):
    """
    Gets action from player via use of input
    """
    def get_action(
        self,
        round_actions: list[Action],
        is_single_die_round: bool,
        num_dice_in_play: int,
        num_players_alive: int,
    ) -> Action:
        last_action = None
        if round_actions:
            last_action = round_actions[-1]
        assert isinstance(last_action, Bid | None)

        fixed_face = None
        if is_single_die_round and isinstance(last_action, Bid):
            fixed_face = last_action.face

        while True:
            if not round_actions:
                action = Bid.get_from_human(fixed_face=fixed_face)
            else:
                action = Action.get_from_human(fixed_face=fixed_face)

            action = action.validate(
                previous=last_action,
                is_single_die_round=is_single_die_round,
            )
            if not action:
                print(
                    f"Illegal Action. Must legally follow {last_action}"
                    + f" and use face {fixed_face}" * (fixed_face is not None)
                )
                continue
            break
        return action

    def set_dice(self, dice: collections.Counter[int]) -> None:
        print(f"{self.name} has dice {", ".join(map(str, sorted(dice)))}")
        self.cur_dice = dice.copy()  # paranoid aliasing prevention - shouldn't ever matter


@dataclasses.dataclass
class RandomLegalPlayer(PlayerABC):
    """
    Chooses a random move that's legal and does it. Has a max bid it will never
    exceed.
    """
    max_count: int = 100  # maximum bid bot will ever submit
    end_pct_chance: float = 0.5
    exact_pct_change: float = 0.5

    def set_dice(self, dice: collections.Counter[int]) -> None:
        self.cur_dice = dice.copy()  # paranoid aliasing prevention - shouldn't ever matter

    def get_end_action(self) -> EndAction:
        if random.random() < self.exact_pct_change:
            return Exact()
        return Challenge()

    def get_action(
        self,
        round_actions: list[Action],
        is_single_die_round: bool,
        num_dice_in_play: int,
        num_players_alive: int,
    ) -> Action:
        if round_actions and random.random() < self.end_pct_chance:
            return self.get_end_action()

        if not round_actions:
            face = WILD_FACE_VAL
            # Note: Don't want to assume that the WILD is the MIN, even though
            # that's true and always will be because I'm pedantic as crap.
            while face == WILD_FACE_VAL:
                face = random.randint(MIN_FACE_VAL, MAX_FACE_VAL)
            min_count = 1
        else:
            face = random.randint(MIN_FACE_VAL, MAX_FACE_VAL)
            previous_action = round_actions[-1]
            assert isinstance(previous_action, Bid)
            min_count = previous_action.min_next_count(face)


        if min_count > num_dice_in_play:
            return self.get_end_action()

        count = random.randint(min_count, num_dice_in_play)
        return Bid(face=face, count=count)


@dataclasses.dataclass
class ProbalisticPlayer(PlayerABC):
    set_dice = RandomLegalPlayer.set_dice

    def _get_prob_of_challenge_success(
        self,
        face: int,
        count: int,
        is_single_die_round: bool,
        num_other_dice: int,
    ) -> float:
        if self.cur_dice[face] >= count:
            return 0

        if is_single_die_round or face == WILD_FACE_VAL:
            p = 1/6
        else:
            p = 1/3

        needed_from_others = count - self.cur_dice[face]

        prob = 0.0
        for k in range(0, needed_from_others):
            prob += math.comb(num_other_dice, k) * (p ** k) * ((1 - p) ** (num_other_dice - k))

        return prob

    def _get_prob_of_exact_count(
        self,
        face: int,
        count: int,
        is_single_die_round: bool,
        num_other_dice: int,
    ) -> float:
        # How many matching dice we need from others
        needed_from_others = count - self.cur_dice[face]

        # Edge cases
        if needed_from_others < 0:
            return 0.0  # We already have more than needed
        if needed_from_others > num_other_dice:
            return 0.0  # Not enough dice to reach count

        # Set matching probability
        if is_single_die_round or face == WILD_FACE_VAL:
            p = 1 / 6
        else:
            p = 1 / 3

        # Single binomial term
        prob = math.comb(num_other_dice, needed_from_others) * (p ** needed_from_others) * (
                (1 - p) ** (num_other_dice - needed_from_others))

        return prob

    def _get_opening_bid(
        self,
        is_single_die_round: bool,
        non_wild_avg_count: float,
        #avg_wild_count: int,
    ) -> Action:
        """
        Choose an opening bid. Currently just chooses a random face and a bit
        less than the expected count

        Does not consider own dice at all atm. TODO: This can be silly at the end, but also maybe not

        :param is_single_die_round: Whether this is a single die round (must bid same face)
        :param non_wild_avg_count: Expected average count of non-wild dice faces
        #:param avg_wild_count: Expected average count of wild (1) dice faces
        :return: Chosen opening bid action
        """
        if is_single_die_round:
            face = get_random_face()
            count = non_wild_avg_count
        else:
            face = get_random_non_wild_face()
            count = non_wild_avg_count

        return Bid(face=face, count=math.ceil(count/2))

    def _get_expected_best_action(
        self,
        round_actions: list[Action],
        is_single_die_round: bool,
        num_other_dice: int,
        num_players_alive: int,
    ) -> Action:
        # TODO: It seems like using expected value causes the challenger to
        #       fail more often, while using probability causes a more even
        #       split. Is this because the bids are forcing the other player
        #       into a worse position making challenging more risky (but still
        #       the right play at that time) or because the calculations for
        #       expected value are wrong?
        assert round_actions
        previous_bid = round_actions[-1]
        assert isinstance(previous_bid, Bid)

        p_challenge = self._get_prob_of_challenge_success(
            face=previous_bid.face,
            count=previous_bid.count,
            is_single_die_round=is_single_die_round,
            num_other_dice=num_other_dice,
        )
        p_exact = self._get_prob_of_exact_count(
            face=previous_bid.face,
            count=previous_bid.count,
            is_single_die_round=is_single_die_round,
            num_other_dice=num_other_dice,
        )
        e_challenge = p_challenge - (1 - p_challenge)
        e_exact = p_exact * (num_players_alive - 1) - (1 - p_exact)
        # TODO compare to e_ version
        actions_values: list[tuple[Action, float]] = [
            (Challenge(), p_challenge),
            (Exact(), p_exact),
        ]

        # For bids, the expected value is calculated assuming the next player
        # challenges
        if is_single_die_round:
            allowed_faces = (previous_bid.face,)
        else:
            allowed_faces = range(MIN_FACE_VAL, MAX_FACE_VAL + 1)
        for face in allowed_faces:
            min_count = previous_bid.min_next_count(face)
            p_challenge = self._get_prob_of_challenge_success(
                face=face,
                count=min_count,
                is_single_die_round=is_single_die_round,
                num_other_dice=num_other_dice,
            )
            p_exact = self._get_prob_of_exact_count(
                face=face,
                count=min_count,
                is_single_die_round=is_single_die_round,
                num_other_dice=num_other_dice,
            )
            # Here, challenge succeeding is valued at -1, and failing at +1.
            # We could say that the other guy doing an exact is better for us
            # because other people also lose dice, but we're not gonna, because
            # we don't really think that's gonna happen.
            e_challenge = -p_challenge + (1 - p_challenge)
            e_exact = -p_exact + (1 - p_exact)

            # TODO compare to e_ version
            actions_values.append((Bid(face=face, count=min_count), min(1-p_challenge, 1-p_exact)))

        return max(actions_values, key=lambda x: x[1])[0]

    def get_action(
        self,
        round_actions: list[Action],
        is_single_die_round: bool,
        num_dice_in_play: int,
        num_players_alive: int,
    ) -> Action:
        num_other_dice = num_dice_in_play - len(self.cur_dice)
        if num_other_dice == 0:
            return InvalidAction('NO BASE', "No other players have dice")
        if is_single_die_round:
            non_wild_avg_count = 2*num_other_dice/NUM_FACES
            #avg_wild_count = num_other_dice/NUM_FACES
        else:
            non_wild_avg_count = num_other_dice / NUM_FACES
            #avg_wild_count = num_other_dice / NUM_FACES

        if not round_actions:
            return self._get_opening_bid(
                is_single_die_round=is_single_die_round,
                non_wild_avg_count=non_wild_avg_count,
            )

        return self._get_expected_best_action(
            round_actions=round_actions,
            is_single_die_round=is_single_die_round,
            num_other_dice=num_other_dice,
            num_players_alive=num_players_alive,
        )


@dataclasses.dataclass
class PerudoGame:
    """
    Represents a game of Perudo.

    The PerudoGame class manages the game logic, players, rounds, and their respective states in
    the game of Perudo. It provides functionalities for starting new rounds, ending
    rounds, determining valid moves, and keeping track of the game's progress. The game
    operates with a turn-by-turn mechanism involving players, dice, and actions. This
    class encapsulates the core rules and mechanics and serves as the central engine of
    the game.

    The game does not trust the Player objects to validate their actions, or to report accurate
    information about their current state (held dice, number of dice, etc.). Instead, it tracks
    these itself. This makes things a bit more clunky, but it means that extensions of player
    classes are less likely to break the game logic.

    I have no idea what the below syntax means or what system it is for, but it's what the AI did,
    and I'm leaving it until I get around to replacing it with something more compact.

    :ivar STARTING_NUM_DICE: The default starting number of dice each player begins with.
    :type STARTING_NUM_DICE: int

    :ivar players: List of players participating in the game.
    :type players: list[PlayerABC]

    :ivar player_index_to_num_dice: List mapping each player's index to the number of dice they hold.
    :type player_index_to_num_dice: list[int]

    :ivar cur_player_index: The index of the current player whose turn it is.
    :type cur_player_index: int

    :ivar cur_round_single_die: Indicates if the current round is a single-die round.
    :type cur_round_single_die: bool

    :ivar all_rounds_actions: History of actions taken in all rounds, stored as a list of lists.
    :type all_rounds_actions: list[list[Action]]

    :ivar all_rounds_dice: History of dice rolls for all players across all rounds.
    :type all_rounds_dice: list[list[list[int]]]

    :ivar all_rounds_living_players: Tracks the living players for each round.
    :type all_rounds_living_players: list[list[int]]

    :ivar all_rounds_losers: Tracks players who lost dice in each round.
    :type all_rounds_losers: list[list[int]]
    """
    STARTING_NUM_DICE: ty.ClassVar[int] = 5

    players: list[PlayerABC]
    player_index_to_num_dice: list[int]
    cur_player_index: int = -1
    cur_round_single_die: bool = False
    all_rounds_actions: list[list[Action]] = dataclasses.field(default_factory=list)
    all_rounds_dice: list[list[collections.Counter[int]]] = dataclasses.field(default_factory=list)
    all_rounds_living_players: list[list[int]] = dataclasses.field(default_factory=list)
    all_rounds_losers: list[list[int]] = dataclasses.field(default_factory=list)
    single_die_round_history: list[bool] = dataclasses.field(default_factory=list)
    print_while_playing: bool = False
    print_non_human_dice: bool = True

    @property
    def current_round_actions(self) -> list[Action]:
        if not self.all_rounds_actions:
            raise RuntimeError('No current round')
        return self.all_rounds_actions[-1]

    @property
    def current_round_dice_by_player(self) -> list[collections.Counter[int]]:
        if not self.all_rounds_actions:
            raise RuntimeError('No current round')
        return self.all_rounds_dice[-1]

    @property
    def previous_living_player_index(self) -> int:
        """
        Raises an error if no player (excluding the current player) has any
        dice
        """
        prev_index = (self.cur_player_index - 1) % len(self.players)
        while self.player_index_to_num_dice[prev_index] == 0:
            if prev_index == self.cur_player_index:
                raise RuntimeError("previous_living_player_index used when there wasn't one")
            prev_index = (prev_index - 1) % len(self.players)
        return prev_index

    @property
    def next_living_player_index(self) -> int:
        """
        Raises an error if no player (excluding the current player) has any
        dice
        """
        next_index = (self.cur_player_index + 1) % len(self.players)
        while self.player_index_to_num_dice[next_index] == 0:
            if next_index == self.cur_player_index:
                raise RuntimeError("next_living_player_index used when there wasn't one")
            next_index = (next_index + 1) % len(self.players)
        return next_index

    def start_new_round(
        self,
        first_player_index: int,
        single_die_round: bool
    ) -> None:
        if not (0 <= first_player_index < len(self.players)):
            raise RuntimeError(f'Invalid first_player_index {first_player_index} (Out of range)')

        if self.player_index_to_num_dice[first_player_index] < 1:
            raise RuntimeError(f'Invalid first_player_index {first_player_index} (does not have dice)')

        self.single_die_round_history.append(single_die_round)
        self.cur_round_single_die = single_die_round
        self.all_rounds_actions.append([])
        self.all_rounds_dice.append([])
        living_players = [
            index % len(self.players)
            for index in range(first_player_index, first_player_index + len(self.players))
            if self.player_index_to_num_dice[index % len(self.players)] > 0
        ]
        self.all_rounds_living_players.append(living_players)
        self.cur_player_index = first_player_index

        for player, num_dice in zip(self.players, self.player_index_to_num_dice):
            dice = collections.Counter(random.choices(  # sorted makes display nicer
                range(MIN_FACE_VAL, MAX_FACE_VAL),
                k=num_dice
            ))
            player.set_dice(dice)
            self.current_round_dice_by_player.append(dice)

        if self.print_while_playing:
            print(f"\nStarting new round ({single_die_round=} num_die={sum(self.player_index_to_num_dice)}):\n====================")
            for player_index in self.all_rounds_living_players[-1]:
                if not (self.print_non_human_dice or isinstance(self.players[player_index], HumanPlayer)):
                    continue
                dice_counter = self.current_round_dice_by_player[player_index]
                dice_str = ', '.join(f'{face}: {value}' for face, value in sorted(dice_counter.items()))
                print(
                    "{name} ({dice_count} dice): {dice_string}".format(
                        name=self.players[player_index].name,
                        dice_count=self.player_index_to_num_dice[player_index],
                        dice_string=dice_str,
                    )
                )
            print("-------------------")


    def end_round(self, loser_indexes: ty.Collection[int]) -> bool:
        """
        End this round, start a new one IF anyone survived.

        :param loser_indexes: The players who lose a die at the end of this round
        :return: Whether there's a next round
        """
        self.all_rounds_losers.append(sorted(loser_indexes))
        for index in loser_indexes:
            self.player_index_to_num_dice[index] = max(0, self.player_index_to_num_dice[index] - 1)

        # Start a new round if multiple people are still alive
        if sum(num > 0 for num in self.player_index_to_num_dice) > 1:
            losers_with_dice = [
                index for index in loser_indexes
                if self.player_index_to_num_dice[index] > 0
            ]
            # TODO: Is this right?
            if losers_with_dice:
                next_player = random.choice(losers_with_dice)
            else:
                next_player = self.next_living_player_index
            if any(
                self.player_index_to_num_dice[index] == 1
                for index in losers_with_dice
            ):
                single_die_round = True
            else:
                single_die_round = False
            self.start_new_round(
                first_player_index=next_player,
                single_die_round=single_die_round,
            )
            return True
        return False

    def take_turn(self) -> bool:
        """
        returns True if the game continues, False if not
        """
        # Get action from player
        if len(self.current_round_actions) > 20:
            raise
        action = self.players[self.cur_player_index].get_action(
            round_actions=self.current_round_actions,
            is_single_die_round=self.cur_round_single_die,
            num_dice_in_play=sum(self.player_index_to_num_dice),
            num_players_alive=sum(count > 0 for count in self.player_index_to_num_dice),
        )
        if not self.current_round_actions:
            prev_action = None
        else:
            prev_action = self.current_round_actions[-1]

        # Check if the action was valid. Will be an InvalidAction object if not
        action = action.validate(
            previous=prev_action,
            is_single_die_round=self.cur_round_single_die,
        )
        if self.print_while_playing:
            print(f"    {self.players[self.cur_player_index].typed_name}: {action}")
        self.current_round_actions.append(action)

        # Handle round ending actions (including InvalidActions)
        if isinstance(action, EndAction):
            all_dice = [
                die
                for player_dice in self.current_round_dice_by_player
                for die in player_dice
            ]
            other_living_players = [
                player_index
                for player_index, num_dice in enumerate(self.player_index_to_num_dice)
                if player_index != self.cur_player_index and num_dice > 0
            ]
            losers = action.get_losers(
                previous_action=prev_action,
                all_dice=all_dice,
                is_single_die_round=self.cur_round_single_die,
                caller=self.cur_player_index,
                previous_player=self.previous_living_player_index,
                other_players=other_living_players,
            )
            if self.print_while_playing:
                print(f'Loser(s): {", ".join(self.players[loser].typed_name for loser in losers)}')

            return self.end_round(loser_indexes=losers)

        self.cur_player_index = self.next_living_player_index
        return True

    @classmethod
    def from_player_list(
        cls, players:
        list[PlayerABC],
        print_while_playing: bool=True,
        print_non_human_dice: bool=True,
    ) -> ty.Self:
        return cls(
            players=players,
            player_index_to_num_dice=[cls.STARTING_NUM_DICE for _ in players],
            print_while_playing=print_while_playing,
            print_non_human_dice=print_non_human_dice,
        )

    def print_summary(self) -> None:
        """
        Print a summary of the game. DO NOT CALL DURING A ROUND

        This is kind of redundant now that verbose is added, but I'm leaving
        it for now because I can convert it into a machine readable format
        later
        """
        if len(self.all_rounds_losers) != len(self.all_rounds_actions):
            raise RuntimeError("print_summary called during active round")

        print("Game Summary:\n==============")
        for round_index, (
            round_players,
            round_actions,
            round_dice,
            round_losers,
            single_die_round,
        ) in enumerate(zip(
            self.all_rounds_living_players,
            self.all_rounds_actions,
            self.all_rounds_dice,
            self.all_rounds_losers,
            self.single_die_round_history,
            strict=True
        ), start=1):
            header = f"Round {round_index} ({single_die_round=})"
            print(f'{header}\n{"-" * len(header)}')
            for player in round_players:
                dice_str = ', '.join(f'{face}: {value}' for face, value in sorted(round_dice[player].items()))
                print(f"    {self.players[player].name} ({sum(round_dice[player].values())} dice): {dice_str}")
            print('    -----------------')

            action_print_width = len(str(len(round_actions)))
            for action_index, action in enumerate(round_actions):
                player_index = round_players[action_index % len(round_players)]
                cur_player = self.players[player_index]
                print(f"    {action_index:>{action_print_width}} - {cur_player.typed_name}: {action}")
            print('    -----------------')
            print(f'    Round Loser(s): {", ".join(self.players[index].typed_name for index in round_losers)}\n')

    def local_main_loop(self) -> int:
        """
        Suitable for running the game purely locally

        returns winning index
        """
        first_player_index = random.randrange(len(self.players))
        self.start_new_round(
            first_player_index=first_player_index,
            single_die_round=False,  # Assuming we're not being weird.
        )
        while self.take_turn():
            pass
        return self.cur_player_index


def local_main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--n-random', '--nr',
        type=int,
        dest='num_random_players',
        default=2,
        help='Number of random players to add to the game'
    )
    parser.add_argument(
        '--n-prob', '--np',
        type=int,
        dest='num_prob_players',
        default=2,
        help='Number of probabilistic players to add to the game'
    )
    parser.add_argument(
        '--humans',
        type=str,
        dest='human_names',
        default=[],
        nargs='+',
        help='Names of human players to add to the game'
    )
    parser.add_argument(
        '--silent',
        action='store_false',
        dest='print_while_playing',
        help='Do not print what is happening while playing the game'
    )
    parser.add_argument(
        '--no-cheat',
        action='store_false',
        dest='print_non_human_dice',
        help='Do not print dice assignments for non-human players'
    )

    args = parser.parse_args()
    players: list[PlayerABC] = [
        RandomLegalPlayer(
            name=f'Rando-{index}'
        )
        for index in range(max(0, args.num_random_players))
    ]
    players.extend(
        ProbalisticPlayer(
            name=f'Prob-{index}'
        )
        for index in range(max(0, args.num_prob_players))
    )
    players.extend((
        HumanPlayer(name=human_name)
        for human_name in args.human_names
    ))
    if len(players) < 2:
        print("Need at least 2 players")
        return 1

    game = PerudoGame.from_player_list(
        players=players,
        print_while_playing=args.print_while_playing,
        print_non_human_dice=args.print_non_human_dice,
    )
    who_won = game.local_main_loop()
    if not args.verbose:
        game.print_summary()  # todo this is kind of redundant
    print(f"The winner was {game.players[who_won].name}")
    return 0


if __name__ == '__main__':
    local_main()
