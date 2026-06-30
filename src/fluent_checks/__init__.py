import datetime
import os
import time
from itertools import repeat
from pathlib import Path
from threading import Thread
from typing import Any, Callable, Optional, Self, Union

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


class Check:
    """A boolean condition wrapped in a fluent, composable interface."""

    def __init__(self, condition: Condition) -> None:
        self._condition: Condition = condition

    def check(self) -> bool:
        return self._condition()

    def on_success(self, callback: Callable[[], None]) -> "WithSuccessCallbackCheck":
        return WithSuccessCallbackCheck(self, callback)

    def on_failure(self, callback: Callable[[], None]) -> "WithFailureCallbackCheck":
        return WithFailureCallbackCheck(self, callback)

    def all_attempts(self, times: int) -> "RepeatingAndCheck":
        return RepeatingAndCheck(self, times)

    def any_attempt(self, times: int) -> "RepeatingOrCheck":
        return RepeatingOrCheck(self, times)

    def before(self, deadline: datetime.datetime) -> "IsTrueBeforeDeadlineCheck":
        return IsTrueBeforeDeadlineCheck(self, deadline)

    def within(self, timeout: datetime.timedelta) -> "IsTrueBeforeTimeoutCheck":
        return IsTrueBeforeTimeoutCheck(self, timeout)

    def wait(self) -> "WaitForTrueCheck":
        return WaitForTrueCheck(self)

    def raises(self, exception: type[Exception]) -> "RaisesCheck":
        return RaisesCheck(self, exception)

    def with_delay(self, delay: datetime.timedelta) -> "DelayedCheck":
        return DelayedCheck(self, delay)

    def invert(self) -> "InvertedCheck":
        return InvertedCheck(self)

    def background(self) -> "BackgroundCheck":
        return BackgroundCheck(self)

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
    """A check built directly from a ``Condition``. Identical to ``Check``."""


class AllCheck(Check):
    def __init__(self, *checks: Check) -> None:
        self._checks: tuple[Check, ...] = checks
        super().__init__(lambda: all(c.check() for c in checks))


class AnyCheck(Check):
    def __init__(self, *checks: Check) -> None:
        self._checks: tuple[Check, ...] = checks
        super().__init__(lambda: any(c.check() for c in checks))


class AndCheck(Check):
    def __init__(self, left: Check, right: Check) -> None:
        self._left: Check = left
        self._right: Check = right
        super().__init__(lambda: left.check() and right.check())


class OrCheck(Check):
    def __init__(self, left: Check, right: Check) -> None:
        self._left: Check = left
        self._right: Check = right
        super().__init__(lambda: left.check() or right.check())


class InvertedCheck(Check):
    def __init__(self, check: Check) -> None:
        self._check: Check = check
        super().__init__(lambda: not check.check())


class WithSuccessCallbackCheck(Check):
    def __init__(self, check: Check, callback: Callable[[], None]) -> None:
        def run() -> bool:
            result = check.check()
            if result:
                callback()
            return result

        self._check = check
        self._callback = callback
        super().__init__(run)


class WithFailureCallbackCheck(Check):
    def __init__(self, check: Check, callback: Callable[[], None]) -> None:
        def run() -> bool:
            result = check.check()
            if not result:
                callback()
            return result

        self._check = check
        self._callback = callback
        super().__init__(run)


class DeadlineExceededCheck(Check):
    def __init__(self, deadline: datetime.datetime) -> None:
        self._deadline: datetime.datetime = deadline
        super().__init__(lambda: datetime.datetime.now() > deadline)


class TimeoutExceededCheck(DeadlineExceededCheck):
    def __init__(self, timeout: datetime.timedelta) -> None:
        super().__init__(datetime.datetime.now() + timeout)


class DelayedCheck(Check):
    def __init__(self, check: Check, delay: datetime.timedelta) -> None:
        def run() -> bool:
            time.sleep(delay.total_seconds())
            return check.check()

        self._check: Check = check
        self._delay: datetime.timedelta = delay
        super().__init__(run)


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


class CheckedLessTimesThanCheck(Check):
    def __init__(self, times) -> None:
        self._times_checked: int = 0
        self._max_times: int = times
        super().__init__(lambda: self._tick() < self._max_times)

    def _tick(self) -> int:
        self._times_checked += 1
        return self._times_checked

    def times_checked(self) -> int:
        return self._times_checked


class CheckedMoreTimesThanCheck(Check):
    def __init__(self, times) -> None:
        self._times_checked: int = 0
        self._max_times: int = times
        super().__init__(lambda: self._tick() > self._max_times)

    def _tick(self) -> int:
        self._times_checked += 1
        return self._times_checked

    def times_checked(self) -> int:
        return self._times_checked


class BackgroundCheck(Check):
    """Runs a check in a daemon thread and exposes its eventual result."""

    def __init__(self, check: Check) -> None:
        self._check: Check = check
        self._result: Optional[bool] = None
        self._exception: Optional[Exception] = None
        self._thread: Optional[Thread] = None
        super().__init__(self._blocking_check)

    def is_finished(self) -> Check:
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

    def _blocking_check(self) -> bool:
        self.start()
        self.stop()
        return self.result() is True


def _race_against_deadline(
    check: Check, deadline: datetime.datetime
) -> "BackgroundCheck":
    background = check.background().start()
    (DeadlineExceededCheck(deadline) | background.is_finished()).wait().check()
    return background


class FinishesBeforeDeadlineCheck(Check):
    def __init__(self, check: Check, deadline: datetime.datetime) -> None:
        self._check = check
        self._deadline = deadline
        super().__init__(
            lambda: _race_against_deadline(check, deadline).is_finished().check()
        )


class FinishesBeforeTimeoutCheck(Check):
    def __init__(self, check: Check, timeout: datetime.timedelta) -> None:
        self._check = check
        self._timeout = timeout
        super().__init__(
            lambda: _race_against_deadline(check, datetime.datetime.now() + timeout)
            .is_finished()
            .check()
        )


class IsTrueBeforeDeadlineCheck(Check):
    def __init__(self, check: Check, deadline: datetime.datetime) -> None:
        self._check = check
        self._deadline = deadline
        super().__init__(
            lambda: _race_against_deadline(check, deadline).result() is True
        )


class IsTrueBeforeTimeoutCheck(Check):
    def __init__(self, check: Check, timeout: datetime.timedelta) -> None:
        self._check = check
        self._timeout = timeout
        super().__init__(
            lambda: _race_against_deadline(
                check, datetime.datetime.now() + timeout
            ).result()
            is True
        )


class WaitForTrueCheck(Check):
    def __init__(self, check: Check) -> None:
        self._check: Check = check

        def run() -> bool:
            while not check.check():
                time.sleep(0.025)
            return True

        super().__init__(run)


class RaisesCheck(Check):
    def __init__(self, check: Check, exception: type[Exception]) -> None:
        def run() -> bool:
            try:
                check.check()
                return False
            except exception:
                return True

        self._check: Check = check
        self._exception: type[Exception] = exception
        super().__init__(run)


class FileExistsCheck(Check):
    def __init__(self, path: Path) -> None:
        self._path = path
        super().__init__(lambda: os.path.exists(path))


class DirectoryExistsCheck(Check):
    def __init__(self, path: Path) -> None:
        self._path = path
        super().__init__(lambda: os.path.isdir(path))


class FileContainsCheck(Check):
    def __init__(self, path: Path, content: bytes) -> None:
        def run() -> bool:
            try:
                with open(path, "rb") as f:
                    return content in f.read()
            except FileNotFoundError:
                return False

        self._path = path
        self._content = content
        super().__init__(run)


class IsEqualCheck(Check):
    def __init__(self, lhs: Any, rhs: Any) -> None:
        self._lhs = lhs
        self._rhs = rhs
        super().__init__(lambda: lhs == rhs)


class IsNotEqualCheck(Check):
    def __init__(self, lhs: Any, rhs: Any) -> None:
        self._lhs = lhs
        self._rhs = rhs
        super().__init__(lambda: lhs != rhs)


class IsGreaterThanCheck(Check):
    def __init__(self, lhs: Any, rhs: Any) -> None:
        self._lhs = lhs
        self._rhs = rhs
        super().__init__(lambda: lhs > rhs)


class IsLessThanCheck(Check):
    def __init__(self, lhs: Any, rhs: Any) -> None:
        self._lhs = lhs
        self._rhs = rhs
        super().__init__(lambda: lhs < rhs)


class IsInCheck(Check):
    def __init__(self, needle: Any, haystack: Any) -> None:
        self._needle = needle
        self._haystack = haystack
        super().__init__(lambda: needle in haystack)


class IsInstanceOfCheck(Check):
    def __init__(
        self, obj: object, class_or_tuple: Union[type, tuple[type, ...]]
    ) -> None:
        self._obj = obj
        self._class_or_tuple = class_or_tuple
        super().__init__(lambda: isinstance(obj, class_or_tuple))


def is_equal(lhs: Any, rhs: Any) -> IsEqualCheck:
    return IsEqualCheck(lhs, rhs)


def is_not_equal(lhs: Any, rhs: Any) -> IsNotEqualCheck:
    return IsNotEqualCheck(lhs, rhs)


def is_greater_than(lhs: Any, rhs: Any) -> IsGreaterThanCheck:
    return IsGreaterThanCheck(lhs, rhs)


def is_less_than(lhs: Any, rhs: Any) -> IsLessThanCheck:
    return IsLessThanCheck(lhs, rhs)


def is_in(needle: Any, haystack: Any) -> IsInCheck:
    return IsInCheck(needle, haystack)


def is_instance_of(
    obj: object, class_or_tuple: Union[type, tuple[type, ...]]
) -> IsInstanceOfCheck:
    return IsInstanceOfCheck(obj, class_or_tuple)


def file_exists(path: Path) -> FileExistsCheck:
    return FileExistsCheck(path)


def dir_exists(path: Path) -> DirectoryExistsCheck:
    return DirectoryExistsCheck(path)


def file_contains(path: Path, content: bytes) -> FileContainsCheck:
    return FileContainsCheck(path, content)
