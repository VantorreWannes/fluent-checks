from abc import ABC

import datetime
from itertools import repeat
from threading import Event, Thread
import time
from typing import Any, Callable, Generic, Optional, Protocol, Union, override, TypeVar
import os

type Condition = Callable[[], bool]


class Check(ABC):
    def __init__(self, condition: Condition) -> None:
        super().__init__()
        self._condition: Condition = condition
        self._on_success_callback: Optional[Callable[[], None]] = None
        self._on_failure_callback: Optional[Callable[[], None]] = None

    def check(self) -> bool:
        result = self._condition()
        if result:
            if self._on_success_callback:
                self._on_success_callback()
        else:
            if self._on_failure_callback:
                self._on_failure_callback()
        return result

    def on_success(self, callback: Callable[[], None]) -> "Check":
        """Registers a callback to be executed when the check succeeds."""
        self._on_success_callback = callback
        return self

    def on_failure(self, callback: Callable[[], None]) -> "Check":
        """Registers a callback to be executed when the check fails."""
        self._on_failure_callback = callback
        return self

    def with_delay(self, delay: float) -> "DelayedCheck":
        return DelayedCheck(self, delay)

    def succeeds_in_attempts(self, times: int) -> "RepeatingOrCheck":
        return RepeatingOrCheck(self, times)

    def is_consistent_for(self, times: int) -> "RepeatingAndCheck":
        return RepeatingAndCheck(self, times)

    def succeeds_within(self, timeout: float) -> "SucceedsWithinCheck":
        return SucceedsWithinCheck(self, timeout)

    def eventually(self, timeout: float) -> "SucceedsWithinCheck":
        """Alias for succeeds_within for better readability."""
        return self.succeeds_within(timeout)

    def fails_within(self, timeout: float) -> "FailsWithinCheck":
        return FailsWithinCheck(self, timeout)

    def sometimes(self) -> "LoopingOrCheck":
        return LoopingOrCheck(self)

    def always(self) -> "LoopingAndCheck":
        return LoopingAndCheck(self)

    def as_waiting(self, timeout: float) -> "WaitingCheck":
        return WaitingCheck(self, timeout)

    def with_deadline(self, deadline: datetime.datetime) -> "DeadlineCheck":
        return DeadlineCheck(self, deadline)

    def with_timeout(self, timeout: float) -> "TimeoutCheck":
        return TimeoutCheck(self, timeout)

    def raises(self, exception: type[Exception]) -> "RaisesCheck":
        return RaisesCheck(self, exception)

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
        return f"Check({self._condition.__name__})"


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
        return f"{self._left.__repr__()} and {self._right.__repr__()}"


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
        return f"not {self._inverted.__repr__()}"


class DelayedCheck(Check):
    def __init__(self, check: Check, delay: float) -> None:
        super().__init__(condition=lambda: check.check())
        self._check: Check = check
        self._delay: float = delay

    @override
    def check(self) -> bool:
        time.sleep(self._delay)
        return self._condition()

    def __repr__(self) -> str:
        return f"DelayedCheck({self._check.__repr__()}, {self._delay})"


class RepeatingAndCheck(AllCheck):
    def __init__(self, check: Check, times: int) -> None:
        super().__init__(*repeat(check, times))
        self._check: Check = check
        self._times: int = times

    def __repr__(self) -> str:
        return f"RepeatingAndCheck({self._check.__repr__()}, {self._times})"


class RepeatingOrCheck(AnyCheck):
    def __init__(self, check: Check, times: int) -> None:
        super().__init__(*repeat(check, times))
        self._check: Check = check
        self._times: int = times

    def __repr__(self) -> str:
        return f"RepeatingOrCheck({self._check.__repr__()}, {self._times})"


class LoopingCheck(Check):
    def __init__(self, check: Check, initial_result: bool) -> None:
        super().__init__(self.check)
        self._check: Check = check
        self._result = initial_result
        self._stop_event = Event()
        self._thread: Optional[Thread] = None

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            self._result = self._check.check()
            time.sleep(0.025)

    def _start_thread_if_needed(self) -> None:
        if self._thread is None:
            self._stop_event.clear()
            self._thread = Thread(target=self._loop)
            self._thread.daemon = True
            self._thread.start()

    def stop(self) -> None:
        """Stops the background looping thread if it is running."""
        if self._thread and self._thread.is_alive():
            self._stop_event.set()
            self._thread.join()
        self._thread = None

    def __del__(self) -> None:
        self.stop()

    @override
    def check(self) -> bool:
        self._start_thread_if_needed()
        return self._result

    def __repr__(self) -> str:
        return f"LoopingCheck({self._check.__repr__()})"


class LoopingAndCheck(LoopingCheck):
    def __init__(self, check: Check) -> None:
        super().__init__(check, initial_result=True)

    @override
    def _loop(self) -> None:
        while not self._stop_event.is_set():
            if not self._check.check():
                self._result = False
            time.sleep(0.025)

    def __repr__(self) -> str:
        return f"LoopingAndCheck({self._check.__repr__()})"


class LoopingOrCheck(LoopingCheck):
    def __init__(self, check: Check) -> None:
        super().__init__(check, initial_result=False)

    @override
    def _loop(self) -> None:
        while not self._stop_event.is_set():
            if self._check.check():
                self._result = True
            time.sleep(0.025)

    def __repr__(self) -> str:
        return f"LoopingOrCheck({self._check.__repr__()})"


class DeadlineException(Exception):
    def __init__(self, deadline: datetime.datetime) -> None:
        super().__init__(
            f"Polling did not complete by {deadline.strftime('%Y-%m-%d %H:%M:%S')}"
        )


class DeadlineCheck(LoopingCheck):
    def __init__(self, check: Check, deadline: datetime.datetime) -> None:
        super().__init__(check, False)
        self._check: Check = check
        self._deadline: datetime.datetime = deadline

    @override
    def check(self) -> bool:
        while not super().check():
            if datetime.datetime.now() > self._deadline:
                raise DeadlineException(deadline=self._deadline)
            time.sleep(0.025)
        return True

    def __repr__(self) -> str:
        return f"DeadlineCheck({self._check.__repr__()}, {self._deadline})"


class TimeoutException(Exception):
    def __init__(self, _timeout: float) -> None:
        super().__init__(f"Polling did not complete in {_timeout} seconds")


class TimeoutCheck(DeadlineCheck):
    def __init__(self, check: Check, timeout: float) -> None:
        super().__init__(
            check,
            datetime.datetime.now() + datetime.timedelta(seconds=timeout),
        )
        self._timeout: float = timeout

    @override
    def check(self) -> bool:
        try:
            return super().check()
        except DeadlineException:
            raise TimeoutException(self._timeout)

    def __repr__(self) -> str:
        return f"TimeoutCheck({self._check.__repr__()}, {self._timeout})"


class WaitingCheck(TimeoutCheck):
    def __init__(self, check: Check, timeout: float) -> None:
        super().__init__(check, timeout)
        self._check: Check = check
        self._timeout = timeout

    @override
    def check(self) -> bool:
        try:
            return super().check()
        except TimeoutException:
            return False

    def __repr__(self) -> str:
        return f"WaitingCheck({self._check.__repr__()})"


class RaisesCheck(Check):
    def __init__(self, check: Check, exception: type[Exception]) -> None:
        def condition() -> bool:
            try:
                check.check()
                return False
            except exception:
                return True

        super().__init__(condition)
        self._check: Check = check
        self._exception: type[Exception] = exception

    def __repr__(self) -> str:
        return f"RaisesCheck({self._check.__repr__()}, {self._exception.__name__})"


class SucceedsWithinCheck(WaitingCheck):
    def __init__(self, check: Check, timeout: float) -> None:
        super().__init__(check, timeout)

    def __repr__(self) -> str:
        return f"SucceedsWithin({self._check.__repr__()}, {self._timeout})"


class FailsWithinCheck(SucceedsWithinCheck):
    def __init__(self, check: Check, timeout: float) -> None:
        super().__init__(~check, timeout)

    def __repr__(self) -> str:
        return f"SucceedsWithin({self._check.__repr__()}, {self._timeout})"


class FileExistsCheck(Check):
    def __init__(self, path: str) -> None:
        super().__init__(lambda: os.path.exists(path))
        self._path = path

    def __repr__(self) -> str:
        return f"FileExists({self._path})"


class DirectoryExistsCheck(Check):
    def __init__(self, path: str) -> None:
        super().__init__(lambda: os.path.isdir(path))
        self._path = path

    def __repr__(self) -> str:
        return f"DirectoryExists({self._path})"


class FileContainsCheck(Check):
    def __init__(self, path: str, content: str) -> None:
        def condition() -> bool:
            if not os.path.exists(path):
                return False
            with open(path, "r") as f:
                return content in f.read()

        super().__init__(condition)
        self._path = path
        self._content = content

    def __repr__(self) -> str:
        return f"FileContains({self._path}, {self._content})"


class RichComparable(Protocol):
    def __lt__(self, other: Any) -> bool: ...
    def __gt__(self, other: Any) -> bool: ...
    def __eq__(self, other: Any) -> bool: ...
    def __contains__(self, key: Any) -> bool: ...


T = TypeVar("T", bound=RichComparable)


class IsEqualCheck(Check, Generic[T]):
    def __init__(self, left_value: T, right_value: T) -> None:
        super().__init__(lambda: left_value == right_value)
        self._left_value = left_value
        self._right_value = right_value

    def __repr__(self) -> str:
        return f"{self._left_value.__repr__()} == {self._right_value.__repr__()} "


class IsNotEqualCheck(Check, Generic[T]):
    def __init__(self, left_value: T, right_value: T) -> None:
        super().__init__(lambda: left_value != right_value)
        self._left_value = left_value
        self._right_value = right_value

    def __repr__(self) -> str:
        return f"{self._left_value.__repr__()} != {self._right_value.__repr__()} "


class IsGreaterThanCheck(Check, Generic[T]):
    def __init__(self, left_value: T, right_value: T) -> None:
        super().__init__(lambda: left_value > right_value)
        self._left_value = left_value
        self._right_value = right_value

    def __repr__(self) -> str:
        return f"{self._left_value.__repr__()} > {self._right_value.__repr__()} "


class IsLessThanCheck(Check, Generic[T]):
    def __init__(self, left_value: T, right_value: T) -> None:
        super().__init__(lambda: left_value < right_value)
        self._left_value = left_value
        self._right_value = right_value

    def __repr__(self) -> str:
        return f"{self._left_value.__repr__()} < {self._right_value.__repr__()} "


class IsInCheck(Check, Generic[T]):
    def __init__(self, member: T, container: T) -> None:
        super().__init__(lambda: member in container)
        self._member = member
        self._container = container

    def __repr__(self) -> str:
        return f"{self._member.__repr__()} in {self._container.__repr__()}"


class IsInstanceOfCheck(Check):
    def __init__(
        self, obj: object, class_or_tuple: Union[type, tuple[type, ...]]
    ) -> None:
        super().__init__(lambda: isinstance(obj, class_or_tuple))
        self._obj = obj
        self._class_or_tuple = class_or_tuple

    def __repr__(self) -> str:
        return f"isinstance({self._obj.__repr__()}, {self._class_or_tuple.__repr__()})"
