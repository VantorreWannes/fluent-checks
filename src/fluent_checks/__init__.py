from abc import ABC, abstractmethod
from calendar import c
import datetime
from itertools import repeat
from threading import Thread
import time
from typing import Any, Callable, Generic, Optional, Protocol, Self, Union, TypeVar
import os

__all__ = [
    "Check",
    "CustomCheck",
    "AllCheck",
    "AnyCheck",
    "AndCheck",
    "OrCheck",
    "InvertedCheck",
    "DelayedCheck",
    "RepeatingAndCheck",
    "RepeatingOrCheck",
    "IsTrueBeforeDeadlineCheck",
    "IsTrueBeforeTimeoutCheck",
    "WaitForTrueCheck",
    "RaisesCheck",
    "FileExistsCheck",
    "DirectoryExistsCheck",
    "FileContainsCheck",
    "IsEqualCheck",
    "IsNotEqualCheck",
    "IsGreaterThanCheck",
    "IsLessThanCheck",
    "IsInCheck",
    "IsInstanceOfCheck",
    "is_equal",
    "is_not_equal",
    "is_greater_than",
    "is_less_than",
    "is_in",
    "is_instance_of",
    "file_exists",
    "dir_exists",
    "file_contains",
]


type Condition = Callable[[], bool]


class RichComparable(Protocol):
    def __lt__(self, other: Any) -> bool: ...
    def __gt__(self, other: Any) -> bool: ...
    def __eq__(self, other: Any) -> bool: ...
    def __contains__(self, key: Any) -> bool: ...


T = TypeVar("T", bound=RichComparable)


# --- Base Check Class ---


class Check(ABC):
    def __init__(self) -> None:
        super().__init__()

    @abstractmethod
    def check(self) -> bool:
        pass

    # --- Callbacks ---

    def on_success(self, callback: Callable[[], None]) -> "WithSuccessCallbackCheck":
        return WithSuccessCallbackCheck(self, callback)

    def on_failure(self, callback: Callable[[], None]) -> "WithFailureCallbackCheck":
        return WithFailureCallbackCheck(self, callback)

    # --- Modifiers ---

    def is_true_for_attempts(self, times: int) -> "RepeatingAndCheck":
        return RepeatingAndCheck(self, times)

    def succeeds_within_attempts(self, times: int) -> "RepeatingOrCheck":
        return RepeatingOrCheck(self, times)

    def succeeds_before_deadline(
        self, deadline: datetime.datetime
    ) -> "IsTrueBeforeDeadlineCheck":
        return IsTrueBeforeDeadlineCheck(self, deadline)

    def succeeds_within_timeout(
        self, timeout: datetime.timedelta
    ) -> "IsTrueBeforeTimeoutCheck":
        return IsTrueBeforeTimeoutCheck(self, timeout)

    def eventually(self, timeout: datetime.timedelta) -> "IsTrueBeforeTimeoutCheck":
        return self.succeeds_within_timeout(timeout)

    def wait_until_true(self) -> "WaitForTrueCheck":
        return WaitForTrueCheck(self)

    def raises(self, exception: type[Exception]) -> "RaisesCheck":
        return RaisesCheck(self, exception)

    def with_delay(self, delay: datetime.timedelta) -> "DelayedCheck":
        return DelayedCheck(self, delay)

    def invert(self) -> "InvertedCheck":
        return InvertedCheck(self)

    def as_background(self) -> "BackgroundCheck":
        return BackgroundCheck(self)

    # --- Dunder Methods ---

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
        return f"<{self.__class__.__name__}>"


class CustomCheck(Check):
    def __init__(self, check: Condition) -> None:
        super().__init__()
        self._condition = check

    def check(self) -> bool:
        return self._condition()


# --- Logical Checks ---


class AllCheck(Check):
    def __init__(self, *checks: Check) -> None:
        super().__init__()
        self._checks: tuple[Check, ...] = checks

    def check(self) -> bool:
        return all(self._checks)


class AnyCheck(Check):
    def __init__(self, *checks: Check) -> None:
        super().__init__()
        self._checks: tuple[Check, ...] = checks

    def check(self) -> bool:
        return any(self._checks)


class AndCheck(Check):
    def __init__(self, left: Check, right: Check) -> None:
        super().__init__()
        self._left: Check = left
        self._right: Check = right

    def check(self) -> bool:
        return self._left.check() and self._right.check()


class OrCheck(Check):
    def __init__(self, left: Check, right: Check) -> None:
        super().__init__()
        self._left: Check = left
        self._right: Check = right

    def check(self) -> bool:
        return self._left.check() or self._right.check()


class InvertedCheck(Check):
    def __init__(self, check: Check) -> None:
        super().__init__()
        self._check: Check = check

    def check(self) -> bool:
        return not self._check.check()


class WithSuccessCallbackCheck(Check):
    def __init__(self, check: Check, callback: Callable[[], None]) -> None:
        super().__init__()
        self._check = check
        self._callback = callback

    def check(self) -> bool:
        result = self._check.check()
        if result:
            self._callback()
        return result


class WithFailureCallbackCheck(WithSuccessCallbackCheck):
    def __init__(self, check: Check, callback: Callable[[], None]) -> None:
        super().__init__(check.invert(), callback)


# --- Timing and Repetition Checks ---


class DeadlineExceededCheck(Check):
    def __init__(self, deadline: datetime.datetime) -> None:
        super().__init__()
        self._deadline: datetime.datetime = deadline

    def check(self) -> bool:
        return datetime.datetime.now() > self._deadline


class TimeoutExceededCheck(Check):
    def __init__(self, timeout: datetime.timedelta) -> None:
        super().__init__()
        self._timeout: datetime.timedelta = timeout

    def check(self) -> bool:
        return DeadlineExceededCheck(datetime.datetime.now() + self._timeout).check()


class DelayedCheck(Check):
    def __init__(self, check: Check, delay: datetime.timedelta) -> None:
        super().__init__()
        self._check: Check = check
        self._delay: datetime.timedelta = delay

    def check(self) -> bool:
        time.sleep(self._delay.total_seconds())
        return self._check.check()


class RepeatingAndCheck(AllCheck):
    def __init__(self, check: Check, times: int) -> None:
        super().__init__(*repeat(check, times))
        self._check: Check = check
        self._times: int = times


class RepeatingOrCheck(AnyCheck):
    def __init__(self, check: Check, times: int) -> None:
        super().__init__(*repeat(check, times))
        self._check: Check = check
        self._times: int = times


class BackgroundCheck(Check):
    def __init__(self, check: Check) -> None:
        super().__init__()
        self._check: Check = check
        self._result: Optional[bool] = None
        self._exception: Optional[Exception] = None
        self._thread: Optional[Thread] = None

    def is_finished(self) -> CustomCheck:
        return CustomCheck(
            lambda: self._thread is not None and not self._thread.is_alive()
        )

    def _run(self) -> None:
        try:
            self._result = self._check.check()
        except Exception as e:
            self._exception = e

    def start(self) -> Self:
        if self._thread is None:
            self._thread = Thread(target=self._run, daemon=True)
            self._thread.start()
        return self

    def _cleanup(self) -> Self:
        if self._thread is not None and not self._thread.is_alive():
            self.stop()
        return self

    def stop(self) -> None:
        if self._thread is not None:
            self._thread.join()
            self._thread = None

    def __enter__(self) -> Self:
        self.start()
        return self

    def __exit__(self, type, value, traceback) -> None:
        pass

    def result(self) -> Optional[bool]:
        if self._exception:
            raise self._exception
        return self._result

    def check(self) -> bool:
        self.start()
        self.stop()
        return self.result() is True


class FinishesBeforeDeadlineCheck(Check):
    def __init__(self, check: Check, deadline: datetime.datetime):
        super().__init__()
        self._check = check
        self._deadline = deadline

    def check(self) -> bool:
        background_check = self._check.as_background().start()
        (
            DeadlineExceededCheck(self._deadline) | background_check.is_finished()
        ).wait_until_true()
        return background_check.is_finished().check()


class FinishesBeforeTimeoutCheck(Check):
    def __init__(self, check: Check, timeout: datetime.timedelta):
        super().__init__()
        self._check = check
        self._timeout = timeout

    def check(self) -> bool:
        return FinishesBeforeDeadlineCheck(
            self._check, datetime.datetime.now() + self._timeout
        ).check()


class IsTrueBeforeDeadlineCheck(Check):
    def __init__(self, check: Check, deadline: datetime.datetime) -> None:
        super().__init__()
        self._check = check
        self._deadline = deadline

    def check(self) -> bool:
        background_check = self._check.as_background().start()
        (
            DeadlineExceededCheck(self._deadline) | background_check.is_finished()
        ).wait_until_true()
        return background_check.result() is True


class IsTrueBeforeTimeoutCheck(Check):
    def __init__(self, check: Check, timeout: datetime.timedelta) -> None:
        super().__init__()
        self._check = check
        self._timeout = timeout

    def check(self) -> bool:
        return IsTrueBeforeDeadlineCheck(
            self._check, datetime.datetime.now() + self._timeout
        ).check()


class WaitForTrueCheck(Check):
    def __init__(self, check: Check) -> None:
        super().__init__()
        self._check = check

    def check(self) -> bool:
        while not self._check.check():
            time.sleep(0.025)
        return True


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


# --- Filesystem Checks ---


class FileExistsCheck(Check):
    def __init__(self, path: str) -> None:
        super().__init__()
        self._path = path

    def check(self) -> bool:
        return os.path.exists(self._path)


class DirectoryExistsCheck(Check):
    def __init__(self, path: str) -> None:
        super().__init__()
        self._path = path

    def check(self) -> bool:
        return os.path.isdir(self._path)


class FileContainsCheck(Check):
    def __init__(self, path: str, content: bytes) -> None:
        super().__init__()
        self._path = path
        self._content = content

    def check(self) -> bool:
        try:
            with open(self._path, "rb") as f:
                return self._content in f.read()
        except FileNotFoundError:
            return False


# --- Comparison Checks ---
class IsEqualCheck(Check, Generic[T]):
    def __init__(self, lhs: T, rhs: T) -> None:
        super().__init__()
        self._lhs = lhs
        self._rhs = rhs

    def check(self) -> bool:
        return self._lhs == self._rhs


class IsNotEqualCheck(Check, Generic[T]):
    def __init__(self, lhs: T, rhs: T) -> None:
        super().__init__()
        self._lhs = lhs
        self._rhs = rhs

    def check(self) -> bool:
        return self._lhs != self._rhs


class IsGreaterThanCheck(Check, Generic[T]):
    def __init__(self, lhs: T, rhs: T) -> None:
        super().__init__()
        self._lhs = lhs
        self._rhs = rhs

    def check(self) -> bool:
        return self._lhs > self._rhs


class IsLessThanCheck(Check, Generic[T]):
    def __init__(self, lhs: T, rhs: T) -> None:
        super().__init__()
        self._lhs = lhs
        self._rhs = rhs

    def check(self) -> bool:
        return self._lhs < self._rhs


class IsInCheck(Check, Generic[T]):
    def __init__(self, needle: T, haystack: T) -> None:
        super().__init__()
        self._needle = needle
        self._haystack = haystack

    def check(self) -> bool:
        return self._needle in self._haystack


class IsInstanceOfCheck(Check):
    def __init__(
        self, obj: object, class_or_tuple: Union[type, tuple[type, ...]]
    ) -> None:
        super().__init__()
        self._obj = obj
        self._class_or_tuple = class_or_tuple

    def check(self) -> bool:
        return isinstance(self._obj, self._class_or_tuple)


# --- Factory Functions ---


def is_equal(lhs: T, rhs: T) -> IsEqualCheck[T]:
    return IsEqualCheck(lhs, rhs)


def is_not_equal(lhs: T, rhs: T) -> IsNotEqualCheck[T]:
    return IsNotEqualCheck(lhs, rhs)


def is_greater_than(lhs: T, rhs: T) -> IsGreaterThanCheck[T]:
    return IsGreaterThanCheck(lhs, rhs)


def is_less_than(lhs: T, rhs: T) -> IsLessThanCheck[T]:
    return IsLessThanCheck(lhs, rhs)


def is_in(needle: T, haystack: T) -> IsInCheck[T]:
    return IsInCheck(needle, haystack)


def is_instance_of(
    obj: object, class_or_tuple: Union[type, tuple[type, ...]]
) -> IsInstanceOfCheck:
    return IsInstanceOfCheck(obj, class_or_tuple)


def file_exists(path: str) -> FileExistsCheck:
    return FileExistsCheck(path)


def dir_exists(path: str) -> DirectoryExistsCheck:
    return DirectoryExistsCheck(path)


def file_contains(path: str, content: bytes) -> FileContainsCheck:
    return FileContainsCheck(path, content)
