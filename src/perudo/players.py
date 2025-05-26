import abc
import collections
import dataclasses
import math
import random
import typing as ty

from perudo import actions, common
if ty.TYPE_CHECKING:
    from perudo.perudo_game import RoundSummary

type PlayerConstructorType = ty.Callable[[str], 'PlayerABC']

@dataclasses.dataclass(kw_only=True)
class PlayerABC:
    NAME_TO_TO_PLAYER_CONSTRUCTOR_D: ty.ClassVar[dict[str, PlayerConstructorType]] = {}

    name: str
    cur_dice: collections.Counter[int] = dataclasses.field(default_factory=collections.Counter[int])

    @ty.overload
    @classmethod
    def register_constructor[T: PlayerConstructorType | type['PlayerABC']](
        cls,
        name_or_constructor: str | None,
    ) -> ty.Callable[[T], T]:
        ...

    @ty.overload
    @classmethod
    def register_constructor[T: PlayerConstructorType | type['PlayerABC']](
        cls,
        name_or_constructor: T,
    ) -> T:
        ...

    @classmethod
    def register_constructor[T: PlayerConstructorType | type['PlayerABC']](
        cls,
        name_or_constructor: str | T | None = None,
    ) -> ty.Callable[[T], T] | T:
        def inner(constructor: T) -> T:
            name: str | None
            error_message = (  # this is defined up here just because type checkers are confused if it's not
                f'Tried to register {constructor} ({type(constructor).__name__}) '
                'as a player class, but it is a type and not a subclass of PlayerABC. '
                'This is not allowed.'
            )
            if isinstance(name_or_constructor, str):
                name = name_or_constructor
            else:
                name = getattr(constructor, '__name__', None)
                if name is None:
                    raise TypeError(
                        f'Tried to register {name_or_constructor} ({type(name_or_constructor).__name__}) '
                        'as a player class, but it has no __name__ attribute. Use '
                        '@ClientPlayer.register_player_class(name) as a decorator instead, '
                        'or ClientPlayer.register_player_class(name)(constructor).'
                    )

            if isinstance(constructor, type):
                if not issubclass(constructor, PlayerABC):
                    raise TypeError(error_message)

                cls.NAME_TO_TO_PLAYER_CONSTRUCTOR_D[name] = constructor.from_name
            else:
                cls.NAME_TO_TO_PLAYER_CONSTRUCTOR_D[name] = constructor

            return ty.cast(T, constructor)  # this cast wouldn't be necessary if type checkers were smarter.

        if name_or_constructor is None or isinstance(name_or_constructor, str):
            return inner

        return inner(name_or_constructor)

    @property
    def typed_name(self) -> str:
        return f"{self.name} ({type(self).__name__})"

    @abc.abstractmethod
    def get_action(
        self,
        previous_action: actions.Bid | None,
        is_single_die_round: bool,
        num_dice_in_play: int,
        player_dice_count_history: list[list[int]],
        all_rounds_actions: list[list[actions.Action]],
        dice_reveal_history: list[list[collections.Counter[int]]],
    ) -> actions.Action:
        raise NotImplementedError('Implement me bro.')

    def set_dice(self, dice: collections.Counter[int]) -> None:
        """
        Set the players dice. Makes a copy out of paranoia. Shouldn't matter.
        """
        self.cur_dice = dice.copy()  # paranoid aliasing prevention - shouldn't ever matter

    @classmethod
    def from_name(cls, name: str) -> ty.Self:
        """
        This factory method is dumb, but it simplifies type checking in the
        ClientPlayer class
        """
        return cls(name=name)

    def react_to_round_summary(
        self,
        round_summary: 'RoundSummary',
    ) -> None:
        """
        This method is here so that subclasses can use it if they want -
        but the few provided defaults don't.
        """
        pass

    @classmethod
    def from_constructor(
        cls,
        player_name: str,
        constructor: PlayerConstructorType | str
    ) -> 'PlayerABC':
        if isinstance(constructor, str):
            constructor = cls.NAME_TO_TO_PLAYER_CONSTRUCTOR_D[constructor]
        return constructor(player_name)

@PlayerABC.register_constructor
@dataclasses.dataclass(kw_only=True)
class HumanPlayer(PlayerABC):
    """
    Gets action from player via use of input
    """
    def get_action(
        self,
        previous_action: actions.Bid | None,
        is_single_die_round: bool,
        num_dice_in_play: int,
        player_dice_count_history: list[list[int]],
        all_rounds_actions: list[list[actions.Action]],
        dice_reveal_history: list[list[collections.Counter[int]]],
    ) -> actions.Action:
        assert isinstance(previous_action, actions.Bid | None)

        fixed_face = None
        if is_single_die_round and isinstance(previous_action, actions.Bid):
            fixed_face = previous_action.face

        action: actions.Action
        while True:
            if previous_action is None:
                action = actions.Bid.get_from_human(fixed_face=fixed_face)
            else:
                action = actions.Action.get_from_human(fixed_face=fixed_face)

            action = action.validate(
                previous_action=previous_action,
                is_single_die_round=is_single_die_round,
            )
            if isinstance(action, actions.InvalidAction):
                print(
                    f"Illegal Action. Must legally follow {previous_action}"
                    + f" and use face {fixed_face}" * (fixed_face is not None)
                )
                continue
            break
        return action

    def set_dice(self, dice: collections.Counter[int]) -> None:
        print(f"{self.name} has dice {", ".join(map(str, sorted(dice)))}")
        super().set_dice(dice)


@PlayerABC.register_constructor
@dataclasses.dataclass(kw_only=True)
class RandomLegalPlayer(PlayerABC):
    """
    Chooses a random move that's legal and does it. Will never bid more dice than are in play.
    """
    end_pct_chance: float = 0.5
    exact_pct_change: float = 0.5

    def get_end_action(self) -> actions.EndAction:
        if random.random() < self.exact_pct_change:
            return actions.Exact()
        return actions.Challenge()

    def get_action(
        self,
        previous_action: actions.Bid | None,
        is_single_die_round: bool,
        num_dice_in_play: int,
        player_dice_count_history: list[list[int]],
        all_rounds_actions: list[list[actions.Action]],
        dice_reveal_history: list[list[collections.Counter[int]]],
    ) -> actions.Action:
        if previous_action is not None and random.random() < self.end_pct_chance:
            return self.get_end_action()

        if previous_action is None:
            face = random.randint(common.MIN_FACE_VAL, common.MAX_FACE_VAL)
            # Note: Don't want to assume that the WILD is the MIN, even though
            # that's true and always will be because I'm pedantic as crap.
            if not is_single_die_round:
                while face == common.WILD_FACE_VAL:
                    face = random.randint(common.MIN_FACE_VAL, common.MAX_FACE_VAL)
            min_count = 1
        else:
            face = random.randint(common.MIN_FACE_VAL, common.MAX_FACE_VAL)
            assert isinstance(previous_action, actions.Bid)
            min_count = previous_action.min_next_count(face)

        if min_count > num_dice_in_play:
            return self.get_end_action()

        count = random.randint(min_count, num_dice_in_play)
        return actions.Bid(face=face, count=count)


@PlayerABC.register_constructor
@dataclasses.dataclass(kw_only=True)
class ProbabilisticPlayer(PlayerABC):
    """
    Player bot who only uses some basic probabilities to decide what to do.
    """

    def _get_prob_of_challenge_success(
        self,
        face: int,
        count: int,
        is_single_die_round: bool,
        num_other_dice: int,
    ) -> float:
        if self.cur_dice[face] >= count:
            return 0

        if is_single_die_round or face == common.WILD_FACE_VAL:
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
        if is_single_die_round or face == common.WILD_FACE_VAL:
            p = 1 / 6
        else:
            p = 1 / 3

        # Single binomial term
        prob = math.comb(num_other_dice, needed_from_others) * (p ** needed_from_others) * (
                (1 - p) ** (num_other_dice - needed_from_others))

        return prob

    @staticmethod
    def _get_opening_bid(
        is_single_die_round: bool,
        non_wild_avg_count: float,
        #avg_wild_count: int,
    ) -> actions.Action:
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
            face = common.get_random_face()
            count = non_wild_avg_count
        else:
            face = common.get_random_non_wild_face()
            count = non_wild_avg_count

        return actions.Bid(face=face, count=math.ceil(count / 2))

    def _get_expected_best_action(
        self,
        previous_bid:actions.Bid,
        is_single_die_round: bool,
        num_other_dice: int,
        num_players_alive: int,
    ) -> actions.Action:
        # TODO: It seems like using expected value causes the challenger to
        #       fail more often, while using probability causes a more even
        #       split. Is this because the bids are forcing the other player
        #       into a worse position making challenging more risky (but still
        #       the right play at that time) or because the calculations for
        #       expected value are wrong?

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
        # e_challenge = p_challenge - (1 - p_challenge)
        # e_exact = p_exact * (num_players_alive - 1) - (1 - p_exact)
        # TODO compare to e_ version
        actions_values: list[tuple[actions.Action, float]] = [
            (actions.Challenge(), p_challenge),
            (actions.Exact(), p_exact),
        ]

        # For bids, the expected value is calculated assuming the next player
        # challenges
        allowed_faces: ty.Iterable[int]
        if is_single_die_round:
            allowed_faces = (previous_bid.face,)
        else:
            allowed_faces = range(common.MIN_FACE_VAL, common.MAX_FACE_VAL + 1)
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
            # e_challenge = -p_challenge + (1 - p_challenge)
            # e_exact = -p_exact + (1 - p_exact)

            # TODO compare to e_ version
            actions_values.append((actions.Bid(face=face, count=min_count), min(1 - p_challenge, 1 - p_exact)))

        return max(actions_values, key=lambda x: x[1])[0]

    def get_action(
        self,
        previous_action: actions.Bid | None,
        is_single_die_round: bool,
        num_dice_in_play: int,
        player_dice_count_history: list[list[int]],
        all_rounds_actions: list[list[actions.Action]],
        dice_reveal_history: list[list[collections.Counter[int]]],
    ) -> actions.Action:
        num_other_dice = num_dice_in_play - len(self.cur_dice)
        if num_other_dice == 0:
            return actions.InvalidAction('NO BASE', "No other players have dice")

        if is_single_die_round:
            non_wild_avg_count = 2*num_other_dice / common.NUM_FACES
        else:
            non_wild_avg_count = num_other_dice / common.NUM_FACES

        if previous_action is None:
            return self._get_opening_bid(
                is_single_die_round=is_single_die_round,
                non_wild_avg_count=non_wild_avg_count,
            )

        assert isinstance(previous_action, actions.Bid)
        return self._get_expected_best_action(
            previous_bid=previous_action,
            is_single_die_round=is_single_die_round,
            num_other_dice=num_other_dice,
            num_players_alive=sum(count != 0 for count in player_dice_count_history[-1]),
        )
