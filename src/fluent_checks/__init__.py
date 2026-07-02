from __future__ import annotations

import time
from datetime import datetime, timedelta
from pathlib import Path
from threading import Thread
from typing import Any, Callable, Optional, Self, Union

__all__ = [
    "Check",
    "Condition",
    "BackgroundCheck",
    "check",
    "always",
    "all_of",
    "any_of",
    "deadline_exceeded",
    "timeout_exceeded",
    "file_exists",
    "dir_exists",
    "file_contains",
    "is_equal",
    "is_not_equal",
    "is_greater_than",
    "is_less_than",
    "is_in",
    "is_instance_of",
    "CustomCheck",
    "AllCheck",
    "AnyCheck",
]

type Condition = Callable[[], bool]

POLL_INTERVAL = timedelta(milliseconds=25)


class Check:
    """A lazily evaluated boolean condition with fluent combinators.

    Core contract: ``check()`` calls the wrapped condition. Every combinator
    returns a plain ``Check`` wrapping a lambda that composes ``self`` —
    so any combinator can follow any other.
    """

    def __init__(self, condition: Condition, name: str = "check") -> None:
        self._condition: Condition = condition
        self._name: str = name

    def check(self) -> bool:
        return self._condition()

    def __bool__(self) -> bool:
        return self.check()

    def __repr__(self) -> str:
        return f"<Check: {self._name}>"

    @property
    def name(self) -> str:
        return self._name

    def named(self, name: str) -> "Check":
        """Same condition, better repr."""
        return Check(self._condition, name)

    def __and__(self, other: "Check") -> "Check":
        return Check(
            lambda: self.check() and other.check(),
            f"({self._name} & {other._name})",
        )

    def __or__(self, other: "Check") -> "Check":
        return Check(
            lambda: self.check() or other.check(),
            f"({self._name} | {other._name})",
        )

    def __invert__(self) -> "Check":
        return Check(lambda: not self.check(), f"~{self._name}")

    invert = __invert__

    def tap(
        self,
        on_success: Optional[Callable[[], None]] = None,
        on_failure: Optional[Callable[[], None]] = None,
    ) -> "Check":
        """Fire a callback on the outcome without changing the result."""

        def run() -> bool:
            result = self.check()
            callback = on_success if result else on_failure
            if callback is not None:
                callback()
            return result

        return Check(run, self._name)

    def on_success(self, callback: Callable[[], None]) -> "Check":
        return self.tap(on_success=callback)

    def on_failure(self, callback: Callable[[], None]) -> "Check":
        return self.tap(on_failure=callback)

    def all_attempts(self, times: int) -> "Check":
        """True iff the check passes ``times`` consecutive times."""
        return Check(
            lambda: all(self.check() for _ in range(times)),
            f"{self._name} x{times} (all)",
        )

    def any_attempt(self, times: int) -> "Check":
        """True iff the check passes at least once in ``times`` tries."""
        return Check(
            lambda: any(self.check() for _ in range(times)),
            f"{self._name} x{times} (any)",
        )

    def raises(self, exception: type[BaseException]) -> "Check":
        """True iff evaluating the check raises ``exception``."""

        def run() -> bool:
            try:
                self.check()
            except exception:
                return True
            return False

        return Check(run, f"{self._name} raises {exception.__name__}")

    def absorbing(
        self, *exceptions: type[BaseException], default: bool = False
    ) -> "Check":
        """Turn the given exceptions (default: ``Exception``) into ``default``.

        Useful for making checks safe to poll: a condition that throws
        mid-evaluation becomes simply False instead of aborting a wait loop.
        """
        caught = exceptions or (Exception,)

        def run() -> bool:
            try:
                return self.check()
            except caught:
                return default

        return Check(run, f"{self._name} (absorbing)")

    def with_delay(self, delay: timedelta) -> "Check":
        def run() -> bool:
            time.sleep(delay.total_seconds())
            return self.check()

        return Check(run, f"{self._name} after {delay}")

    def wait(self, poll_interval: timedelta = POLL_INTERVAL) -> "Check":
        """Block, re-evaluating until true. Always returns True."""

        def run() -> bool:
            while not self.check():
                time.sleep(poll_interval.total_seconds())
            return True

        return Check(run, f"wait for {self._name}")

    def before(self, deadline: datetime) -> "Check":
        """True iff a single evaluation completes truthy before ``deadline``."""
        return Check(
            lambda: _race(self, deadline).result() is True,
            f"{self._name} before {deadline}",
        )

    def within(self, timeout: timedelta) -> "Check":
        """Like ``before``, with the deadline computed at evaluation time."""
        return Check(
            lambda: _race(self, datetime.now() + timeout).result() is True,
            f"{self._name} within {timeout}",
        )

    def finishes_before(self, deadline: datetime) -> "Check":
        """True iff the evaluation *finishes* (either way) before ``deadline``."""
        return Check(
            lambda: _race(self, deadline).is_finished().check(),
            f"{self._name} finishes before {deadline}",
        )

    def finishes_within(self, timeout: timedelta) -> "Check":
        return Check(
            lambda: _race(self, datetime.now() + timeout).is_finished().check(),
            f"{self._name} finishes within {timeout}",
        )

    def background(self) -> "BackgroundCheck":
        return BackgroundCheck(self)


class BackgroundCheck(Check):
    """Runs a check in a daemon thread and exposes its eventual result.

    This is the one genuine subclass: it carries state (thread, result,
    exception). Its ``check()`` still follows the core contract — it is a
    condition that starts the thread, joins it, and reports the outcome.
    """

    def __init__(self, check: Check) -> None:
        self._check: Check = check
        self._result: Optional[bool] = None
        self._exception: Optional[BaseException] = None
        self._thread: Optional[Thread] = None
        super().__init__(self._blocking_check, f"background({check.name})")

    def is_finished(self) -> Check:
        return Check(
            lambda: self._thread is not None and not self._thread.is_alive(),
            f"{self._name} is finished",
        )

    def _run(self) -> None:
        try:
            self._result = self._check.check()
        except Exception as error:
            self._exception = error

    def start(self) -> Self:
        if self._thread is None:
            self._thread = Thread(target=self._run, daemon=True)
            self._thread.start()
        return self

    def join(self) -> Self:
        if self._thread is not None:
            self._thread.join()
        return self

    def result(self) -> Optional[bool]:
        """The outcome, or None while running. Re-raises a crashed check."""
        if self._exception is not None:
            raise self._exception
        return self._result

    def __enter__(self) -> Self:
        return self.start()

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.join()

    def _blocking_check(self) -> bool:
        return self.start().join().result() is True


def _race(check: Check, deadline: datetime) -> BackgroundCheck:
    """Evaluate ``check`` once in the background, racing it against ``deadline``.

    Returns once either the evaluation finished or the deadline passed.
    Note: if the deadline wins, the daemon thread keeps running detached.
    """
    background = check.background().start()
    (deadline_exceeded(deadline) | background.is_finished()).wait().check()
    return background


def check(condition: Condition, name: str = "check") -> Check:
    return Check(condition, name)


def always(value: bool) -> Check:
    return Check(lambda: value, str(value))


def all_of(*checks: Check) -> Check:
    """True iff every check passes. Short-circuits on the first failure."""
    return Check(lambda: all(c.check() for c in checks), "all_of")


def any_of(*checks: Check) -> Check:
    """True iff at least one check passes. Short-circuits on the first pass."""
    return Check(lambda: any(c.check() for c in checks), "any_of")


def deadline_exceeded(deadline: datetime) -> Check:
    return Check(lambda: datetime.now() > deadline, f"past {deadline}")


def timeout_exceeded(timeout: timedelta) -> Check:
    """Deadline fixed at construction time, by design (a stopwatch, not a timer)."""
    return deadline_exceeded(datetime.now() + timeout)


def file_exists(path: Union[str, Path]) -> Check:
    return Check(lambda: Path(path).exists(), f"exists: {path}")


def dir_exists(path: Union[str, Path]) -> Check:
    return Check(lambda: Path(path).is_dir(), f"dir exists: {path}")


def file_contains(path: Union[str, Path], content: bytes) -> Check:
    def run() -> bool:
        try:
            return content in Path(path).read_bytes()
        except FileNotFoundError:
            return False

    return Check(run, f"{path} contains {content!r}")


def is_equal(lhs: Any, rhs: Any) -> Check:
    return Check(lambda: lhs == rhs, f"{lhs!r} == {rhs!r}")


def is_not_equal(lhs: Any, rhs: Any) -> Check:
    return Check(lambda: lhs != rhs, f"{lhs!r} != {rhs!r}")


def is_greater_than(lhs: Any, rhs: Any) -> Check:
    return Check(lambda: lhs > rhs, f"{lhs!r} > {rhs!r}")


def is_less_than(lhs: Any, rhs: Any) -> Check:
    return Check(lambda: lhs < rhs, f"{lhs!r} < {rhs!r}")


def is_in(needle: Any, haystack: Any) -> Check:
    return Check(lambda: needle in haystack, f"{needle!r} in {haystack!r}")


def is_instance_of(obj: object, class_or_tuple: Union[type, tuple[type, ...]]) -> Check:
    return Check(
        lambda: isinstance(obj, class_or_tuple),
        f"isinstance({obj!r}, {class_or_tuple!r})",
    )


CustomCheck = Check
AllCheck = all_of
AnyCheck = any_of
