from abc import ABC, abstractmethod
from itertools import repeat
import random
from threading import Event, Thread
import time
from typing import Callable, Optional, Self, final, override

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

    def succeeds_within(self, times: int) -> "RepeatingAndCheck":
        return RepeatingAndCheck(self, times)

    def is_consistent_for(self, times: int) -> "RepeatingOrCheck":
        return RepeatingOrCheck(self, times)

    def sometimes(self) -> "LoopingOrCheck":
        return LoopingOrCheck(self)

    def always(self) -> "LoopingAndCheck":
        return LoopingAndCheck(self)

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

    def loop(self) -> None:
        if self._thread is None:
            self._thread = Thread(target=self._loop)
            self._thread.start()

    def stop(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            self._stop_event.set()
            self._thread.join()
            self._thread = None

    def __enter__(self) -> Self:
        self.loop()
        return self

    def __exit__(self, type, value, traceback) -> None:
        self.stop()

    def __bool__(self) -> bool:
        return self._result

    def __repr__(self) -> str:
        return f"LoopingAndCheck({self._check.__repr__()})"


class LoopingAndCheck(LoopingCheck):
    def __init__(self, check: Check) -> None:
        super().__init__(check, initial_result=True)

    @override
    def _loop(self) -> None:
        while not self._stop_event.is_set():
            self._loop_ran_once = True
            if not self._check.as_bool():
                self._result = False


class LoopingOrCheck(LoopingCheck):
    def __init__(self, check: Check) -> None:
        super().__init__(check, initial_result=False)

    @override
    def _loop(self) -> None:
        while not self._stop_event.is_set():
            if self._check.as_bool():
                self._result = True 


if __name__ == "__main__":
    check = Check(lambda: random.random() < 0.25)
    check = check.with_delay(1)

    with check.sometimes() as is_true:
        while True:
            print(bool(is_true))
            time.sleep(1)

