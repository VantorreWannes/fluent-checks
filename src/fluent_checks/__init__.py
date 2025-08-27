from abc import ABC
from itertools import repeat
import time
from typing import Callable, Self, final, override

type Condition = Callable[[], bool]


class Check(ABC):
    def __init__(self, condition: Condition) -> None:
        super().__init__()
        self._condition = condition

    @final
    def as_bool(self) -> bool:
        return bool(self)

    def with_delay(self, delay: float) -> "DelayedCheck":
        return DelayedCheck(self, delay)

    def sometimes(self) -> "LoopingOrCheck":
        return LoopingOrCheck(self)

    def always(self) -> "LoopingOrCheck":
        return LoopingOrCheck(self)

    def succeeds_within(self, times: int) -> "RepeatingAndCheck":
        return RepeatingAndCheck(self, times)

    def is_consistent_for(self, times: int) -> "RepeatingOrCheck":
        return RepeatingOrCheck(self, times)

    def __and__(self, other: Self) -> "Check":
        return AndCheck(self, other)

    def __or__(self, other: Self) -> "Check":
        return OrCheck(self, other)

    def __invert__(self) -> "Check":
        return InvertedCheck(self)

    def __bool__(self) -> bool:
        return self._condition()

    def __repr__(self) -> str:
        return f"Check({self.as_bool()})"


class AllCheck(Check):
    def __init__(self, *checks: Check) -> None:
        super().__init__(condition=lambda: all(checks))
        self._checks: tuple[Check, ...] = checks

    def __repr__(self) -> str:
        return " and ".join([check.__repr__() for check in self._checks])


class AnyCheck(Check):
    def __init__(self, *checks: Check) -> None:
        super().__init__(condition=lambda: any(checks))
        self._checks: tuple[Check, ...] = checks

    def __repr__(self) -> str:
        return " or ".join([check.__repr__() for check in self._checks])


class AndCheck(AllCheck):
    def __init__(self, left: Check, right: Check) -> None:
        super().__init__(*[left, right])
        self._left: Check = left
        self._right: Check = right

    def __repr__(self) -> str:
        return f"{self._left.__repr__()} or {self._right.__repr__()}"


class OrCheck(AnyCheck):
    def __init__(self, left: Check, right: Check) -> None:
        super().__init__(*[left, right])
        self._left: Check = left
        self._right: Check = right

    def __repr__(self) -> str:
        return f"{self._left.__repr__()} or {self._right.__repr__()}"


class InvertedCheck(Check):
    def __init__(self, check: Check) -> None:
        super().__init__(condition=lambda: not check)
        self._inverted: Check = check

    def __repr__(self) -> str:
        return f"not {super().__repr__()}"


class DelayedCheck(Check):
    def __init__(self, check: Check, delay: float) -> None:
        super().__init__(condition=lambda: bool(check))
        self._check: Check = check
        self._delay: float = delay

    @override
    def __bool__(self) -> bool:
        time.sleep(self._delay)
        return self._check.as_bool()


class RepeatingAndCheck(AllCheck):
    def __init__(self, check: Check, times: int) -> None:
        super().__init__(*repeat[Check](check, times))
        self._check: Check = check
        self._times: int = times


class RepeatingOrCheck(AnyCheck):
    def __init__(self, check: Check, times: int) -> None:
        super().__init__(*repeat[Check](check, times))
        self._check: Check = check
        self._times: int = times


class LoopingAndCheck(AllCheck):
    def __init__(self, check: Check) -> None:
        super().__init__(*repeat[Check](check))
        self._check: Check = check


class LoopingOrCheck(AnyCheck):
    def __init__(self, check: Check) -> None:
        super().__init__(*repeat[Check](check))
        self._check: Check = check
