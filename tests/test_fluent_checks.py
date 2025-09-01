from pathlib import Path
import random
from typing import Generic, TypeVar
import pytest
import time
from datetime import datetime, timedelta
from fluent_checks import (
    AndCheck,
    BackgroundCheck,
    Check,
    CheckedLessTimesThanCheck,
    CheckedMoreTimesThanCheck,
    CustomCheck,
    AllCheck,
    AnyCheck,
    DeadlineExceededCheck,
    DelayedCheck,
    DirectoryExistsCheck,
    FileContainsCheck,
    FileExistsCheck,
    FinishesBeforeDeadlineCheck,
    FinishesBeforeTimeoutCheck,
    InvertedCheck,
    IsTrueBeforeTimeoutCheck,
    OrCheck,
    RaisesCheck,
    RepeatingAndCheck,
    RepeatingOrCheck,
    TimeoutExceededCheck,
    WaitForTrueCheck,
    WithFailureCallbackCheck,
    WithSuccessCallbackCheck,
    is_equal,
    is_greater_than,
    is_in,
    is_instance_of,
    is_less_than,
    is_not_equal,
)

# --- Helpers ---

FAILING_CHECK = CustomCheck(
    lambda: pytest.fail("This check should not have been evaluated")
)


def crash_check():
    """A check that fails if evaluated."""
    return


def missing_file(tmp_path_factory: pytest.TempPathFactory):
    return tmp_path_factory.mktemp("empty_folder") / "missing.txt"


def file(tmp_path: Path):
    file_path = tmp_path / "exists.txt"
    with open(file_path, "w") as f:
        f.write("hello fluent checks")
    return tmp_path


def dir(tmp_path: Path):
    return tmp_path


T = TypeVar("T")


class State(Generic[T]):
    def __init__(self, value: T):
        self._value = value

    def set_value(self, value: T):
        self._value = value

    def value(self) -> T:
        return self._value


class TestCustomCheck:
    def test_check(self):
        assert CustomCheck(lambda: True).check()

    def test_implicit_bool(self):
        assert CustomCheck(lambda: True)


class TestAllCheck:
    @pytest.mark.parametrize(
        "checks, expected",
        [
            ([CustomCheck(lambda: True), CustomCheck(lambda: True)], True),
            ([CustomCheck(lambda: False), CustomCheck(lambda: True)], False),
            ([CustomCheck(lambda: True), CustomCheck(lambda: False)], False),
            ([CustomCheck(lambda: False), CustomCheck(lambda: False)], False),
        ],
    )
    def test_check(self, checks: list[Check], expected: bool):
        assert AllCheck(*checks).check() == expected

    def test_short_ciruiting(self):
        false_check = CustomCheck(lambda: False)
        failing_check = FAILING_CHECK
        AllCheck(false_check, failing_check).check()


class TestAnyCheck:
    @pytest.mark.parametrize(
        "checks, expected",
        [
            ([CustomCheck(lambda: True), CustomCheck(lambda: True)], True),
            ([CustomCheck(lambda: False), CustomCheck(lambda: True)], True),
            ([CustomCheck(lambda: True), CustomCheck(lambda: False)], True),
            ([CustomCheck(lambda: False), CustomCheck(lambda: False)], False),
        ],
    )
    def test_check(self, checks: list[Check], expected: bool):
        assert AnyCheck(*checks).check() == expected

    def test_short_ciruiting(self):
        true_check = CustomCheck(lambda: True)
        failing_check = FAILING_CHECK
        AnyCheck(true_check, failing_check).check()


class TestAndCheck:
    @pytest.mark.parametrize(
        "lhs, rhs, expected",
        [
            (CustomCheck(lambda: True), CustomCheck(lambda: True), True),
            (CustomCheck(lambda: False), CustomCheck(lambda: True), False),
            (CustomCheck(lambda: True), CustomCheck(lambda: False), False),
            (CustomCheck(lambda: False), CustomCheck(lambda: False), False),
        ],
    )
    def test_check(self, lhs: Check, rhs: Check, expected: bool):
        assert AndCheck(lhs, rhs).check() == expected

    @pytest.mark.parametrize(
        "lhs, rhs",
        [
            (CustomCheck(lambda: True), CustomCheck(lambda: True)),
            (CustomCheck(lambda: False), CustomCheck(lambda: True)),
            (CustomCheck(lambda: True), CustomCheck(lambda: False)),
            (CustomCheck(lambda: False), CustomCheck(lambda: False)),
        ],
    )
    def test_operator(self, lhs: Check, rhs: Check):
        assert isinstance(lhs & rhs, AndCheck)

    def test_short_ciruiting(self):
        false_check = CustomCheck(lambda: False)
        failing_check = FAILING_CHECK
        AndCheck(false_check, failing_check).check()


class TestOrCheck:
    @pytest.mark.parametrize(
        "lhs, rhs, expected",
        [
            (CustomCheck(lambda: True), CustomCheck(lambda: True), True),
            (CustomCheck(lambda: False), CustomCheck(lambda: True), True),
            (CustomCheck(lambda: True), CustomCheck(lambda: False), True),
            (CustomCheck(lambda: False), CustomCheck(lambda: False), False),
        ],
    )
    def test_check(self, lhs: Check, rhs: Check, expected: bool):
        assert OrCheck(lhs, rhs).check() == expected

    @pytest.mark.parametrize(
        "lhs, rhs",
        [
            (CustomCheck(lambda: True), CustomCheck(lambda: True)),
            (CustomCheck(lambda: False), CustomCheck(lambda: True)),
            (CustomCheck(lambda: True), CustomCheck(lambda: False)),
            (CustomCheck(lambda: False), CustomCheck(lambda: False)),
        ],
    )
    def test_operator(self, lhs: Check, rhs: Check):
        assert isinstance(lhs | rhs, OrCheck)

    def test_short_ciruiting(self):
        true_check = CustomCheck(lambda: True)
        failing_check = FAILING_CHECK
        OrCheck(true_check, failing_check).check()


class TestInvertedCheck:
    @pytest.mark.parametrize(
        "check, expected",
        [
            (CustomCheck(lambda: True), False),
            (CustomCheck(lambda: False), True),
        ],
    )
    def test_check(self, check: Check, expected: bool):
        assert InvertedCheck(check).check() == expected

    @pytest.mark.parametrize(
        "check",
        [
            (CustomCheck(lambda: True)),
            (CustomCheck(lambda: False)),
        ],
    )
    def test_operator(self, check: Check):
        assert isinstance(~check, InvertedCheck)


class TestWithSuccessCallbackCheck:
    @pytest.mark.parametrize(
        "check, expected",
        [
            (CustomCheck(lambda: True), True),
            (CustomCheck(lambda: False), False),
        ],
    )
    def test_check(self, check: Check, expected: bool):
        state = State[bool](False)

        def callback():
            return state.set_value(True)

        WithSuccessCallbackCheck(check, callback).check()
        assert state.value() == expected


class TestWithFailureCallbackCheck:
    @pytest.mark.parametrize(
        "check, expected",
        [
            (CustomCheck(lambda: True), False),
            (CustomCheck(lambda: False), True),
        ],
    )
    def test_check(self, check: Check, expected: bool):
        state = State[bool](False)

        def callback():
            return state.set_value(True)

        WithFailureCallbackCheck(check, callback).check()
        assert state.value() == expected


class TestDeadlineExceededCheck:
    @pytest.mark.parametrize(
        "deadline, exceeded",
        [
            (datetime.now() - timedelta(seconds=1), True),
            (datetime.now() + timedelta(seconds=1), False),
        ],
    )
    def test_check(self, deadline: datetime, exceeded: bool):
        assert DeadlineExceededCheck(deadline).check() == exceeded


class TestTimeoutExceededCheck:
    @pytest.mark.parametrize(
        "timeout, delay, exceeded",
        [
            (timedelta(milliseconds=10), timedelta(milliseconds=0), False),
            (timedelta(milliseconds=0), timedelta(milliseconds=10), True),
        ],
    )
    def test_check(self, timeout: timedelta, delay: timedelta, exceeded: bool):
        timeout_exceeded_check = TimeoutExceededCheck(timeout)
        time.sleep(delay.total_seconds())
        assert timeout_exceeded_check.check() == exceeded


class TestDelayedCheck:
    @pytest.mark.parametrize(
        "delay",
        [
            (timedelta(milliseconds=100)),
            (timedelta(milliseconds=50)),
        ],
    )
    def test_check(self, delay: timedelta):
        inner_check = CustomCheck(lambda: True)
        start_time = time.time()
        DelayedCheck(inner_check, delay).check()
        end_time = time.time()
        assert end_time - start_time >= delay.total_seconds()


class TestRepeatingAndCheck:
    @pytest.mark.parametrize(
        "check, times, expected",
        [
            (CustomCheck(lambda: True), 10, True),
            (CustomCheck(lambda: False), 10, False),
        ],
    )
    def test_check(self, check: Check, times: int, expected: bool):
        assert RepeatingAndCheck(check, times).check() == expected


class TestRepeatingOrCheck:
    @pytest.mark.parametrize(
        "check, times, expected",
        [
            (CheckedMoreTimesThanCheck(1), 2, True),
            (CheckedMoreTimesThanCheck(1), 1, False),
            (CheckedMoreTimesThanCheck(1), 0, False),
        ],
    )
    def test_check(self, check: Check, times: int, expected: bool):
        assert RepeatingOrCheck(check, times).check() == expected


class TestCheckedLessTimesThanCheck:
    @pytest.mark.parametrize(
        "check_amount, times, expected",
        [
            (1, 2, True),
            (2, 2, False),
            (2, 1, False),
        ],
    )
    def test_check(self, check_amount: int, times: int, expected: bool):
        check = CheckedLessTimesThanCheck(times)
        for _ in range(check_amount - 1):
            check.check()
        assert check.check() == expected

    def test_times_checked(self):
        check = CheckedMoreTimesThanCheck(0)
        assert check.times_checked() == 0


class TestCheckedMoreTimesThanCheck:
    @pytest.mark.parametrize(
        "check_amount, times, expected",
        [
            (2, 1, True),
            (2, 2, False),
            (1, 2, False),
        ],
    )
    def test_check(self, check_amount: int, times: int, expected: bool):
        check = CheckedMoreTimesThanCheck(times)
        for _ in range(check_amount - 1):
            check.check()
        assert check.check() == expected

    def test_times_checked(self):
        check = CheckedMoreTimesThanCheck(0)
        assert check.times_checked() == 0


class TestBackgroundCheck:
    @pytest.mark.parametrize(
        "delay",
        [
            (timedelta(milliseconds=100)),
            (timedelta(milliseconds=50)),
        ],
    )
    def test_is_finished(self, delay: timedelta):
        true_check = CustomCheck(lambda: True)
        delayed_check = true_check.with_delay(delay)
        background_check = BackgroundCheck(delayed_check)
        assert not background_check.is_finished()
        background_check.start()
        assert not background_check.is_finished()
        time.sleep(delay.total_seconds() + 0.1)
        assert background_check.is_finished()

    @pytest.mark.parametrize(
        "result, delay",
        [
            (True, timedelta(milliseconds=100)),
            (True, timedelta(milliseconds=50)),
            (False, timedelta(milliseconds=100)),
            (False, timedelta(milliseconds=50)),
        ],
    )
    def test_result(self, result: bool, delay: timedelta):
        true_check = CustomCheck(lambda: result)
        delayed_check = true_check.with_delay(delay)
        background_check = BackgroundCheck(delayed_check)
        assert background_check.result() is None
        background_check.start()
        assert background_check.result() is None
        time.sleep(delay.total_seconds() + 0.1)
        assert background_check.result() == result

    @pytest.mark.parametrize(
        "delay",
        [
            (timedelta(milliseconds=100)),
            (timedelta(milliseconds=50)),
        ],
    )
    def test_check(self, delay: timedelta):
        true_check = TimeoutExceededCheck(delay - timedelta(milliseconds=10))
        delayed_check = true_check.with_delay(delay)
        background_check = BackgroundCheck(delayed_check)
        assert background_check.check()


class TestFinishesBeforeDeadlineCheck:
    @pytest.mark.parametrize(
        "check_delay, timeout, expected",
        [
            (timedelta(milliseconds=50), timedelta(milliseconds=100), True),
            (timedelta(milliseconds=100), timedelta(milliseconds=50), False),
        ],
    )
    def test_check(self, check_delay: timedelta, timeout: timedelta, expected: bool):
        inner_check = CustomCheck(lambda: True).with_delay(check_delay)
        deadline = datetime.now() + timeout
        check = FinishesBeforeDeadlineCheck(inner_check, deadline)
        assert check.check() == expected


class TestFinishesBeforeTimeoutCheck:
    @pytest.mark.parametrize(
        "check_delay, timeout, expected",
        [
            (timedelta(milliseconds=50), timedelta(milliseconds=100), True),
            (timedelta(milliseconds=100), timedelta(milliseconds=50), False),
        ],
    )
    def test_check(self, check_delay: timedelta, timeout: timedelta, expected: bool):
        inner_check = CustomCheck(lambda: True).with_delay(check_delay)
        check = FinishesBeforeTimeoutCheck(inner_check, timeout)
        assert check.check() == expected


class TestIsTrueBeforeTimeoutCheck:
    @pytest.mark.parametrize(
        "check_result, check_delay, timeout, expected",
        [
            (True, timedelta(milliseconds=50), timedelta(milliseconds=100), True),
            (False, timedelta(milliseconds=50), timedelta(milliseconds=100), False),
            (True, timedelta(milliseconds=100), timedelta(milliseconds=50), False),
        ],
    )
    def test_check(
        self,
        check_result: bool,
        check_delay: timedelta,
        timeout: timedelta,
        expected: bool,
    ):
        inner_check = CustomCheck(lambda: check_result).with_delay(check_delay)
        check = IsTrueBeforeTimeoutCheck(inner_check, timeout)
        assert check.check() == expected


class TestWaitForTrueCheck:
    def test_check(self):
        state = State(0)
        check = CustomCheck(lambda: state.value() >= 3)

        def increment_state():
            state.set_value(state.value() + 1)

        waiter = WaitForTrueCheck(check.on_failure(increment_state))
        waiter.check()
        assert state.value() == 3


class TestRaisesCheck:
    def test_check_raises_correct_exception(self):
        def raise_value_error():
            raise ValueError("Test")

        check = CustomCheck(raise_value_error)
        assert RaisesCheck(check, ValueError).check()

    def test_check_raises_no_exception(self):
        check = CustomCheck(lambda: True)
        assert not RaisesCheck(check, ValueError).check()

    def test_check_raises_wrong_exception(self):
        def raise_type_error():
            raise TypeError("Test")

        check = CustomCheck(raise_type_error)
        with pytest.raises(TypeError):
            RaisesCheck(check, ValueError).check()


class TestFilesystemChecks:
    def test_file_exists_check(self, tmp_path: Path):
        existing_file = tmp_path / "exists.txt"
        existing_file.touch()
        missing_file = tmp_path / "missing.txt"

        assert FileExistsCheck(existing_file).check()
        assert not FileExistsCheck(missing_file).check()

    def test_directory_exists_check(self, tmp_path: Path):
        existing_dir = tmp_path / "exists_dir"
        existing_dir.mkdir()
        missing_dir = tmp_path / "missing_dir"

        assert DirectoryExistsCheck(existing_dir).check()
        assert not DirectoryExistsCheck(missing_dir).check()

    def test_file_contains_check(self, tmp_path: Path):
        file_path = tmp_path / "test.txt"
        file_path.write_text("hello fluent checks")

        assert FileContainsCheck(file_path, b"fluent").check()
        assert not FileContainsCheck(file_path, b"world").check()
        assert not FileContainsCheck(tmp_path / "no.txt", b"").check()


class TestComparisonChecks:
    @pytest.mark.parametrize(
        "lhs, rhs, expected",
        [(1, 1, True), (1, 2, False), ("a", "a", True), ("a", "b", False)],
    )
    def test_is_equal(self, lhs, rhs, expected: bool):
        assert is_equal(lhs, rhs).check() == expected

    @pytest.mark.parametrize(
        "lhs, rhs, expected",
        [(1, 2, True), (1, 1, False), ("a", "b", True), ("a", "a", False)],
    )
    def test_is_not_equal(self, lhs, rhs, expected: bool):
        assert is_not_equal(lhs, rhs).check() == expected

    @pytest.mark.parametrize(
        "lhs, rhs, expected", [(2, 1, True), (1, 1, False), (1, 2, False)]
    )
    def test_is_greater_than(self, lhs, rhs, expected: bool):
        assert is_greater_than(lhs, rhs).check() == expected

    @pytest.mark.parametrize(
        "lhs, rhs, expected", [(1, 2, True), (1, 1, False), (2, 1, False)]
    )
    def test_is_less_than(self, lhs, rhs, expected: bool):
        assert is_less_than(lhs, rhs).check() == expected

    @pytest.mark.parametrize(
        "needle, haystack, expected",
        [
            (1, [1, 2, 3], True),
            (4, [1, 2, 3], False),
            ("a", "abc", True),
            ("d", "abc", False),
        ],
    )
    def test_is_in(self, needle, haystack, expected: bool):
        assert is_in(needle, haystack).check() == expected

    @pytest.mark.parametrize(
        "obj, cls, expected",
        [(1, int, True), ("a", str, True), (1, str, False), ("a", int, False)],
    )
    def test_is_instance_of(self, obj, cls, expected: bool):
        assert is_instance_of(obj, cls).check() == expected
