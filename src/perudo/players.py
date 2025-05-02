import abc
import collections
import dataclasses
import math
import random
import typing

from perudo import actions, common


@dataclasses.dataclass(kw_only=True)
class PlayerABC:
    name: str
    cur_dice: collections.Counter[int] = dataclasses.field(default_factory=collections.Counter[int])
    #action_histories: list[list[Action]] = dataclasses.field(default_factory=list)

    @property
    def typed_name(self) -> str:
        return f"{self.name} ({type(self).__name__})"

    @abc.abstractmethod
    def get_action(
        self,
        round_actions: list[actions.Action],
        is_single_die_round: bool,
        num_dice_in_play: int,
        num_players_alive: int,
    ) -> actions.Action:
        raise NotImplementedError('Implement me bro.')

    @abc.abstractmethod
    def set_dice(self, dice: collections.Counter[int]) -> None:
        """
        Set players current dice to specified list.

        This is a method so that it can be overridden for network players
        """
        raise NotImplementedError('Implement me bro')


@dataclasses.dataclass(kw_only=True)
class HumanPlayer(PlayerABC):
    """
    Gets action from player via use of input
    """
    def get_action(
        self,
        round_actions: list[actions.Action],
        is_single_die_round: bool,
        num_dice_in_play: int,
        num_players_alive: int,
    ) -> actions.Action:
        last_action = None
        if round_actions:
            last_action = round_actions[-1]
        assert isinstance(last_action, actions.Bid | None)

        fixed_face = None
        if is_single_die_round and isinstance(last_action, actions.Bid):
            fixed_face = last_action.face

        action: actions.Action
        while True:
            if not round_actions:
                action = actions.Bid.get_from_human(fixed_face=fixed_face)
            else:
                action = actions.Action.get_from_human(fixed_face=fixed_face)

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


@dataclasses.dataclass(kw_only=True)
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

    def get_end_action(self) -> actions.EndAction:
        if random.random() < self.exact_pct_change:
            return actions.Exact()
        return actions.Challenge()

    def get_action(
        self,
        round_actions: list[actions.Action],
        is_single_die_round: bool,
        num_dice_in_play: int,
        num_players_alive: int,
    ) -> actions.Action:
        if round_actions and random.random() < self.end_pct_chance:
            return self.get_end_action()

        if not round_actions:
            face = common.WILD_FACE_VAL
            # Note: Don't want to assume that the WILD is the MIN, even though
            # that's true and always will be because I'm pedantic as crap.
            while face == common.WILD_FACE_VAL:
                face = random.randint(common.MIN_FACE_VAL, common.MAX_FACE_VAL)
            min_count = 1
        else:
            face = random.randint(common.MIN_FACE_VAL, common.MAX_FACE_VAL)
            previous_action = round_actions[-1]
            assert isinstance(previous_action, actions.Bid)
            min_count = previous_action.min_next_count(face)


        if min_count > num_dice_in_play:
            return self.get_end_action()

        count = random.randint(min_count, num_dice_in_play)
        return actions.Bid(face=face, count=count)


@dataclasses.dataclass(kw_only=True)
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

    def _get_opening_bid(
        self,
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
        round_actions: list[actions.Action],
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
        assert round_actions
        previous_bid = round_actions[-1]
        assert isinstance(previous_bid, actions.Bid)

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
        allowed_faces: typing.Iterable[int]
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
        round_actions: list[actions.Action],
        is_single_die_round: bool,
        num_dice_in_play: int,
        num_players_alive: int,
    ) -> actions.Action:
        num_other_dice = num_dice_in_play - len(self.cur_dice)
        if num_other_dice == 0:
            return actions.InvalidAction('NO BASE', "No other players have dice")
        if is_single_die_round:
            non_wild_avg_count = 2*num_other_dice / common.NUM_FACES
            #avg_wild_count = num_other_dice/NUM_FACES
        else:
            non_wild_avg_count = num_other_dice / common.NUM_FACES
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
