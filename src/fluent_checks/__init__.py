from abc import ABC, abstractmethod
import datetime
from itertools import repeat
from threading import Event, Thread
import time
from typing import Callable, Optional, Self, final, override

type Condition = Callable[[], bool]


class Check(ABC):
    def __init__(self, condition: Condition) -> None:
        super().__init__()
        self._condition: Condition = condition

    @final
    def as_bool(self) -> bool:
        return bool(self)

    def with_delay(self, delay: float) -> "DelayedCheck":
        return DelayedCheck(self, delay)

    def succeeds_within(self, times: int) -> "RepeatingOrCheck":
        return RepeatingOrCheck(self, times)

    def is_consistent_for(self, times: int) -> "RepeatingAndCheck":
        return RepeatingAndCheck(self, times)

    def sometimes(self) -> "LoopingOrCheck":
        return LoopingOrCheck(self)

    def always(self) -> "LoopingAndCheck":
        return LoopingAndCheck(self)

    def as_waiting(self, timeout: float) -> "WaitingCheck":
        return WaitingCheck(self, timeout)

    def wait_for(self, timeout: float) -> bool:
        return self.as_waiting(timeout).wait()

    def with_deadline(self, deadline: datetime.datetime) -> "DeadlineCheck":
        return DeadlineCheck(self, deadline)

    def with_timeout(self, timeout: float) -> "TimeoutCheck":
        return TimeoutCheck(self, timeout)

    def raises(self, exception: type[Exception]) -> "RaisesCheck":
        return RaisesCheck(self, exception)

    def __and__(self, other: Self) -> "Check":
        return AndCheck(self, other)

    def __or__(self, other: Self) -> "Check":
        return OrCheck(self, other)

    def __invert__(self) -> "Check":
        return InvertedCheck(self)

    def __bool__(self) -> bool:
        return self._condition()

    def __repr__(self) -> str:
        try:
            result = self.as_bool()
        except Exception:
            result = "<error>"
        return f"Check({result})"


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
        super().__init__(condition=lambda: bool(check))
        self._check: Check = check
        self._delay: float = delay

    @override
    def __bool__(self) -> bool:
        time.sleep(self._delay)
        return self._condition()

    def __repr__(self) -> str:
        return f"DelayedCheck({self._check.__repr__()}, {self._delay})"


class RepeatingAndCheck(AllCheck):
    def __init__(self, check: Check, times: int) -> None:
        super().__init__(*repeat[Check](check, times))
        self._check: Check = check
        self._times: int = times

    def __repr__(self) -> str:
        return f"RepeatingAndCheck({self._check.__repr__()}, {self._times})"


class RepeatingOrCheck(AnyCheck):
    def __init__(self, check: Check, times: int) -> None:
        super().__init__(*repeat[Check](check, times))
        self._check: Check = check
        self._times: int = times

    def __repr__(self) -> str:
        return f"RepeatingOrCheck({self._check.__repr__()}, {self._times})"


class LoopingCheck(Check):
    def __init__(self, check: Check, initial_result: bool) -> None:
        super().__init__(lambda: bool(check))
        self._check: Check = check
        self._result = initial_result
        self._stop_event = Event()
        self._thread: Optional[Thread] = None

    @abstractmethod
    def _loop(self) -> None:
        pass

    def __enter__(self) -> Self:
        if self._thread is None:
            self._thread = Thread(target=self._loop)
            self._thread.start()
        return self

    def __exit__(self, type, value, traceback) -> None:
        if self._thread is not None and self._thread.is_alive():
            self._stop_event.set()
            self._thread.join()
            self._thread = None

    @override
    def __bool__(self) -> bool:
        return self._result

    def __repr__(self) -> str:
        return f"LoopingCheck({self._check.__repr__()})"


class LoopingAndCheck(LoopingCheck):
    def __init__(self, check: Check) -> None:
        super().__init__(check, initial_result=True)

    @override
    def _loop(self) -> None:
        while not self._stop_event.is_set():
            if not self._check.as_bool():
                self._result = False
            time.sleep(0.01)

    def __repr__(self) -> str:
        return f"LoopingAndCheck({self._check.__repr__()})"


class LoopingOrCheck(LoopingCheck):
    def __init__(self, check: Check) -> None:
        super().__init__(check, initial_result=False)

    @override
    def _loop(self) -> None:
        while not self._stop_event.is_set():
            if self._check.as_bool():
                self._result = True
            time.sleep(0.01)

    def __repr__(self) -> str:
        return f"LoopingOrCheck({self._check.__repr__()})"


class DeadlineException(Exception):
    def __init__(self, deadline: datetime.datetime) -> None:
        super().__init__(
            f"Polling did not complete by {deadline.strftime('%Y-%m-%d %H:%M:%S')}"
        )


class DeadlineCheck(Check):
    def __init__(self, check: Check, deadline: datetime.datetime) -> None:
        super().__init__(lambda: bool(check))
        self._check: Check = check
        self._deadline: datetime.datetime = deadline

    @override
    def __bool__(self) -> bool:
        if datetime.datetime.now() > self._deadline:
            raise DeadlineException(deadline=self._deadline)
        return self._condition()

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
    def __bool__(self) -> bool:
        try:
            return super().__bool__()
        except DeadlineException:
            raise TimeoutException(self._timeout)

    def __repr__(self) -> str:
        return f"TimeoutCheck({self._check.__repr__()}, {self._timeout})"


class WaitingCheck(TimeoutCheck):
    def __init__(self, check: Check, timeout: float) -> None:
        super().__init__(check, timeout)
        self._check: Check = check

    @override
    def __bool__(self) -> bool:
        try:
            while not super().as_bool():
                continue
            return True
        except TimeoutException:
            return False

    def wait(self) -> bool:
        return bool(self)

    def __repr__(self) -> str:
        return f"WatingCheck({self._check.__repr__()})"


class RaisesCheck(Check):
    def __init__(self, check: Check, exception: type[Exception]) -> None:
        super().__init__(condition=lambda: bool(check))
        self._check: Check = check
        self._exception: type[Exception] = exception

    def __bool__(self) -> bool:
        try:
            self._condition()
            return False
        except self._exception:
            return True

    def __repr__(self) -> str:
        return f"RaisesCheck({self._check.__repr__()}, {self._exception.__name__})"
