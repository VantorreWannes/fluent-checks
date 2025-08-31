from abc import ABC, abstractmethod

import datetime
from itertools import repeat
import time
from typing import Any, Callable, Generic, Protocol, Union, TypeVar
import os

type Condition = Callable[[], bool]


class RichComparable(Protocol):
    def __lt__(self, other: Any) -> bool: ...
    def __gt__(self, other: Any) -> bool: ...
    def __eq__(self, other: Any) -> bool: ...
    def __contains__(self, key: Any) -> bool: ...


T = TypeVar("T", bound=RichComparable)


class Check(ABC):
    def __init__(self) -> None:
        super().__init__()

    @abstractmethod
    def check(self) -> bool:
        pass

    def is_consistent_for(self, times: int) -> "RepeatingAndCheck":
        return RepeatingAndCheck(self, times)

    def as_waiting(self) -> "WaitingCheck":
        return WaitingCheck(self)

    def raises(self, exception: type[Exception]) -> "RaisesCheck":
        return RaisesCheck(self, exception)

    def with_delay(self, delay: datetime.timedelta) -> "DelayedCheck":
        return DelayedCheck(self, delay)

    def __and__(self, other: "Check") -> "AndCheck":
        return AndCheck(self, other)

    def __or__(self, other: "Check") -> "OrCheck":
        return OrCheck(self, other)

    def __invert__(self) -> "InvertedCheck":
        return InvertedCheck(self)

    def __not__(self) -> "InvertedCheck":
        return InvertedCheck(self)

    def __bool__(self) -> bool:
        return self.check()

    def __repr__(self) -> str:
        check = None
        try:
            check = self.check()
        except Exception as e:
            check = e
        return f"{check.__repr__()} is true"


class CustomCheck(Check):
    def __init__(self, check: Condition) -> None:
        super().__init__()
        self._condition = check

    def check(self) -> bool:
        return self._condition()


class AllCheck(Check):
    def __init__(self, *checks: Check) -> None:
        super().__init__()
        self._checks: tuple[Check, ...] = checks

    def check(self) -> bool:
        return all(self._checks)

    def __repr__(self) -> str:
        return " and ".join([f"({check.__repr__()})" for check in self._checks])


class AnyCheck(Check):
    def __init__(self, *checks: Check) -> None:
        super().__init__()
        self._checks: tuple[Check, ...] = checks

    def check(self) -> bool:
        return any(self._checks)

    def __repr__(self) -> str:
        return " or ".join([f"({check.__repr__()})" for check in self._checks])


class AndCheck(Check):
    def __init__(self, left: Check, right: Check) -> None:
        super().__init__()
        self._left: Check = left
        self._right: Check = right

    def check(self) -> bool:
        return self._left.check() and self._right.check()

    def __repr__(self) -> str:
        return f"({self._left.__repr__()}) and ({self._right.__repr__()})"


class OrCheck(Check):
    def __init__(self, left: Check, right: Check) -> None:
        super().__init__()
        self._left: Check = left
        self._right: Check = right

    def check(self) -> bool:
        return self._left.check() or self._right.check()

    def __repr__(self) -> str:
        return f"({self._left.__repr__()}) or ({self._right.__repr__()})"


class InvertedCheck(Check):
    def __init__(self, check: Check) -> None:
        super().__init__()
        self._check: Check = check

    def check(self) -> bool:
        return not self._check

    def __repr__(self) -> str:
        return f"not ({self._check.__repr__()})"


class DelayedCheck(Check):
    def __init__(self, check: Check, delay: datetime.timedelta) -> None:
        super().__init__()
        self._check: Check = check
        self._delay: datetime.timedelta = delay

    def check(self) -> bool:
        time.sleep(self._delay.seconds)
        return self._check.check()

    def __repr__(self) -> str:
        return f"({self._check.__repr__()}) after ({self._delay}))"


class RepeatingAndCheck(AllCheck):
    def __init__(self, check: Check, times: int) -> None:
        super().__init__(*repeat(check, times))
        self._check: Check = check
        self._times: int = times

    def __repr__(self) -> str:
        return super().__repr__()


class RepeatingOrCheck(AnyCheck):
    def __init__(self, check: Check, times: int) -> None:
        super().__init__(*repeat(check, times))
        self._check: Check = check
        self._times: int = times

    def __repr__(self) -> str:
        return super().__repr__()


class DeadlineExceededCheck(Check):
    def __init__(self, deadline: datetime.datetime) -> None:
        super().__init__()
        self._deadline: datetime.datetime = deadline

    def check(self) -> bool:
        return datetime.datetime.now() > self._deadline

    def __repr__(self) -> str:
        return f"{datetime.datetime.now().__repr__()} > {self._deadline.__repr__()}"


class TimeoutExceededCheck(DeadlineExceededCheck):
    def __init__(self, timeout: datetime.timedelta) -> None:
        super().__init__(
            datetime.datetime.now() + timeout,
        )
        self._timeout: datetime.timedelta = timeout

    def __repr__(self) -> str:
        return super().__repr__()


class WaitingCheck(Check):
    def __init__(self, check: Check) -> None:
        super().__init__()
        self._check: Check = check

    def check(self) -> bool:
        while not self._check.check():
            time.sleep(0.025)
        return True

    def __repr__(self) -> str:
        return f"wait for ({self._check.__repr__()})"


class RaisesCheck(Check):
    def __init__(self, check: Check, exception: type[Exception]) -> None:
        super().__init__()
        self._check: Check = check
        self._exception: type[Exception] = exception

    def check(self) -> bool:
        try:
            self._check.check()
            return False
        except self._exception:
            return True

    def __repr__(self) -> str:
        return f"{self._check.__repr__()} raises {self._exception.__name__}"


class FileExistsCheck(Check):
    def __init__(self, path: str) -> None:
        super().__init__()
        self._path = path

    def check(self) -> bool:
        return os.path.exists(self._path)

    def __repr__(self) -> str:
        return f'file "{self._path}" exists'


class DirectoryExistsCheck(Check):
    def __init__(self, path: str) -> None:
        super().__init__()
        self._path = path

    def check(self) -> bool:
        return os.path.isdir(self._path)

    def __repr__(self) -> str:
        return f'dir "{self._path}" exists'


class FileContainsCheck(Check):
    def __init__(self, path: str, content: bytes) -> None:
        super().__init__()
        self._path = path
        self._content = content

    def check(self) -> bool:
        with open(self._path, "rb") as f:
            return self._content in f.read()

    def __repr__(self) -> str:
        return f"{self._content} in {self._path}"


class IsEqualCheck(Check, Generic[T]):
    def __init__(self, lhs: T, rhs: T) -> None:
        super().__init__()
        self._lhs = lhs
        self._rhs = rhs

    def check(self) -> bool:
        return self._lhs == self._rhs

    def __repr__(self) -> str:
        return f"({self._lhs.__repr__()}) == ({self._rhs.__repr__()})"


class IsGreaterThanCheck(Check, Generic[T]):
    def __init__(self, lhs: T, rhs: T) -> None:
        super().__init__()
        self._lhs = lhs
        self._rhs = rhs

    def check(self) -> bool:
        return self._lhs > self._rhs

    def __repr__(self) -> str:
        return f"({self._lhs.__repr__()}) > ({self._rhs.__repr__()})"


class IsLessThanCheck(Check, Generic[T]):
    def __init__(self, lhs: T, rhs: T) -> None:
        super().__init__()
        self._lhs = lhs
        self._rhs = rhs

    def check(self) -> bool:
        return self._lhs > self._rhs

    def __repr__(self) -> str:
        return f"({self._lhs.__repr__()}) < ({self._rhs.__repr__()})"


class ContainsCheck(Check, Generic[T]):
    def __init__(self, needle: T, haystack: T) -> None:
        super().__init__()
        self._needle = needle
        self._haystack = haystack

    def check(self) -> bool:
        return self._needle in self._haystack

    def __repr__(self) -> str:
        return f"({self._needle.__repr__()}) in ({self._haystack.__repr__()})"


class IsInstanceOfCheck(Check):
    def __init__(
        self, obj: object, class_or_tuple: Union[type, tuple[type, ...]]
    ) -> None:
        super().__init__()
        self._obj = obj
        self._class_or_tuple = class_or_tuple

    def check(self) -> bool:
        return isinstance(self._obj, self._class_or_tuple)

    def __repr__(self) -> str:
        return (
            f"{self._obj.__repr__()} is instance of {self._class_or_tuple.__repr__()})"
        )
