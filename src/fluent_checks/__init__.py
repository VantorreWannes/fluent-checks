from abc import ABC
from typing import Callable, Self, final

type Condition = Callable[[], bool]


class Check(ABC):
    def __init__(self, condition: Condition) -> None:
        super().__init__()
        self.condition = condition

    @final
    def as_bool(self) -> bool:
        return bool(self)

    def __and__(self, other: Self) -> "Check":
        return AndCheck(self, other)

    def __or__(self, other: Self) -> "Check":
        return OrCheck(self, other)

    def __invert__(self) -> "Check":
        return InvertedCheck(self)

    def __bool__(self) -> bool:
        return self.condition()

    def __repr__(self) -> str:
        return f"Check({self.as_bool()})"


class AllCheck(Check):
    def __init__(self, *checks: Check) -> None:
        super().__init__(lambda: all(checks))
        self.checks = checks

    def __repr__(self) -> str:
        return " and ".join([check.__repr__() for check in self.checks])


class AnyCheck(Check):
    def __init__(self, *checks: Check) -> None:
        super().__init__(lambda: any(checks))
        self.checks = checks

    def __repr__(self) -> str:
        return " or ".join([check.__repr__() for check in self.checks])


class AndCheck(AllCheck):
    def __init__(self, left: Check, right: Check) -> None:
        super().__init__(*[left, right])
        self.left: Check = left
        self.right: Check = right

    def __repr__(self) -> str:
        return f"{self.left.__repr__()} or {self.right.__repr__()}"


class OrCheck(AnyCheck):
    def __init__(self, left: Check, right: Check) -> None:
        super().__init__(*[left, right])
        self.left: Check = left
        self.right: Check = right

    def __repr__(self) -> str:
        return f"{self.left.__repr__()} or {self.right.__repr__()}"


class InvertedCheck(Check):
    def __init__(self, check: Check) -> None:
        super().__init__(lambda: not check)
        self.check = check

    def __repr__(self) -> str:
        return f"not {super().__repr__()}"
