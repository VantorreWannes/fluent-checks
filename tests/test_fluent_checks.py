"""Behaviour-based tests for the refactored fluent_checks.

Since named subclasses are gone, tests assert *behaviour* (results,
short-circuiting, call counts, timing) instead of `isinstance(...)`.
"""

import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from fluent_checks import (
    Check,
    all_of,
    always,
    any_of,
    deadline_exceeded,
    dir_exists,
    file_contains,
    file_exists,
    is_equal,
    is_greater_than,
    is_in,
    is_instance_of,
    is_less_than,
    is_not_equal,
    timeout_exceeded,
)

# --- helpers -----------------------------------------------------------


class Counter:
    """Counts evaluations; optionally becomes true from the nth call on."""

    def __init__(self, true_after: int | None = None) -> None:
        self.calls = 0
        self._true_after = true_after

    def as_check(self) -> Check:
        def condition() -> bool:
            self.calls += 1
            return self._true_after is not None and self.calls >= self._true_after

        return Check(condition, "counter")


def never_evaluated() -> Check:
    return Check(lambda: pytest.fail("this check should not have been evaluated"))


def raising(error: Exception) -> Check:
    def condition() -> bool:
        raise error

    return Check(condition, "raising")


# --- core --------------------------------------------------------------


class TestCore:
    def test_check(self):
        assert always(True).check() is True
        assert always(False).check() is False

    def test_implicit_bool(self):
        assert always(True)
        assert not always(False)

    def test_repr_composes(self):
        composed = (always(True) & ~always(False)).named("everything is fine")
        assert repr(composed) == "<Check: everything is fine>"

    def test_lazy(self):
        never_evaluated()  # constructing must not evaluate


# --- logic -------------------------------------------------------------


class TestLogic:
    @pytest.mark.parametrize(
        "left, right, expected",
        [
            (True, True, True),
            (True, False, False),
            (False, True, False),
            (False, False, False),
        ],
    )
    def test_and(self, left, right, expected):
        assert (always(left) & always(right)).check() == expected

    @pytest.mark.parametrize(
        "left, right, expected",
        [
            (True, True, True),
            (True, False, True),
            (False, True, True),
            (False, False, False),
        ],
    )
    def test_or(self, left, right, expected):
        assert (always(left) | always(right)).check() == expected

    @pytest.mark.parametrize("value, expected", [(True, False), (False, True)])
    def test_invert(self, value, expected):
        assert (~always(value)).check() == expected

    def test_and_short_circuits(self):
        assert not (always(False) & never_evaluated()).check()

    def test_or_short_circuits(self):
        assert (always(True) | never_evaluated()).check()

    @pytest.mark.parametrize(
        "values, expected",
        [((True, True), True), ((True, False), False), ((False, False), False)],
    )
    def test_all_of(self, values, expected):
        assert all_of(*map(always, values)).check() == expected

    @pytest.mark.parametrize(
        "values, expected",
        [((True, True), True), ((False, True), True), ((False, False), False)],
    )
    def test_any_of(self, values, expected):
        assert any_of(*map(always, values)).check() == expected

    def test_all_of_short_circuits(self):
        all_of(always(False), never_evaluated()).check()

    def test_any_of_short_circuits(self):
        any_of(always(True), never_evaluated()).check()


# --- callbacks ---------------------------------------------------------


class TestCallbacks:
    @pytest.mark.parametrize("result, fired", [(True, True), (False, False)])
    def test_on_success(self, result, fired):
        events: list[str] = []
        always(result).on_success(lambda: events.append("hit")).check()
        assert bool(events) == fired

    @pytest.mark.parametrize("result, fired", [(True, False), (False, True)])
    def test_on_failure(self, result, fired):
        events: list[str] = []
        always(result).on_failure(lambda: events.append("hit")).check()
        assert bool(events) == fired

    def test_tap_preserves_result(self):
        assert always(True).tap(on_success=lambda: None).check() is True
        assert always(False).tap(on_failure=lambda: None).check() is False


# --- repetition --------------------------------------------------------


class TestRepetition:
    def test_all_attempts_passes_when_stable(self):
        counter = Counter(true_after=1)
        assert counter.as_check().all_attempts(5).check()
        assert counter.calls == 5

    def test_all_attempts_stops_at_first_failure(self):
        counter = Counter(true_after=None)  # always false
        assert not counter.as_check().all_attempts(5).check()
        assert counter.calls == 1

    def test_any_attempt_stops_at_first_success(self):
        counter = Counter(true_after=3)
        assert counter.as_check().any_attempt(10).check()
        assert counter.calls == 3

    def test_any_attempt_exhausts_on_failure(self):
        counter = Counter(true_after=None)
        assert not counter.as_check().any_attempt(4).check()
        assert counter.calls == 4


# --- timing ------------------------------------------------------------


class TestTiming:
    def test_with_delay(self):
        delay = timedelta(milliseconds=50)
        start = time.monotonic()
        assert always(True).with_delay(delay).check()
        assert time.monotonic() - start >= delay.total_seconds()

    @pytest.mark.parametrize(
        "offset, exceeded",
        [(timedelta(seconds=-1), True), (timedelta(seconds=1), False)],
    )
    def test_deadline_exceeded(self, offset, exceeded):
        assert deadline_exceeded(datetime.now() + offset).check() == exceeded

    def test_timeout_exceeded_is_fixed_at_construction(self):
        stopwatch = timeout_exceeded(timedelta(milliseconds=20))
        assert not stopwatch.check()
        time.sleep(0.03)
        assert stopwatch.check()

    def test_wait_polls_until_true(self):
        counter = Counter(true_after=3)
        assert counter.as_check().wait(poll_interval=timedelta(milliseconds=1)).check()
        assert counter.calls == 3

    @pytest.mark.parametrize(
        "result, delay, timeout, expected",
        [
            (True, timedelta(milliseconds=50), timedelta(milliseconds=200), True),
            (False, timedelta(milliseconds=50), timedelta(milliseconds=200), False),
            (True, timedelta(milliseconds=200), timedelta(milliseconds=50), False),
        ],
    )
    def test_within(self, result, delay, timeout, expected):
        slow = always(result).with_delay(delay)
        assert slow.within(timeout).check() == expected

    def test_before(self):
        slow = always(True).with_delay(timedelta(milliseconds=50))
        assert slow.before(datetime.now() + timedelta(milliseconds=200)).check()
        assert not slow.before(datetime.now() - timedelta(seconds=1)).check()

    @pytest.mark.parametrize(
        "delay, timeout, expected",
        [
            (timedelta(milliseconds=50), timedelta(milliseconds=200), True),
            (timedelta(milliseconds=200), timedelta(milliseconds=50), False),
        ],
    )
    def test_finishes_within(self, delay, timeout, expected):
        slow = always(True).with_delay(delay)
        assert slow.finishes_within(timeout).check() == expected


# --- exceptions --------------------------------------------------------


class TestExceptions:
    def test_raises_matching(self):
        assert raising(ValueError("boom")).raises(ValueError).check()

    def test_raises_nothing(self):
        assert not always(True).raises(ValueError).check()

    def test_raises_wrong_exception_propagates(self):
        with pytest.raises(TypeError):
            raising(TypeError("boom")).raises(ValueError).check()

    def test_absorbing_turns_errors_into_default(self):
        assert raising(ValueError("boom")).absorbing(ValueError).check() is False
        assert raising(ValueError("boom")).absorbing(default=True).check() is True

    def test_absorbing_leaves_other_exceptions(self):
        with pytest.raises(TypeError):
            raising(TypeError("boom")).absorbing(ValueError).check()

    def test_absorbing_makes_waits_safe(self):
        counter = Counter(true_after=3)

        def flaky() -> bool:
            counter.calls += 1
            if counter.calls < 3:
                raise ValueError("not ready")
            return True

        safe = Check(flaky).absorbing(ValueError)
        assert safe.wait(poll_interval=timedelta(milliseconds=1)).check()


# --- background --------------------------------------------------------


class TestBackground:
    def test_lifecycle(self):
        slow = always(True).with_delay(timedelta(milliseconds=50))
        background = slow.background()
        assert not background.is_finished().check()
        assert background.result() is None

        background.start()
        assert background.result() is None  # still running

        background.join()
        assert background.is_finished().check()
        assert background.result() is True

    @pytest.mark.parametrize("result", [True, False])
    def test_result(self, result):
        background = always(result).with_delay(timedelta(milliseconds=20)).background()
        assert background.check() == result  # blocking evaluation

    def test_crashed_check_reraises(self):
        background = raising(ValueError("boom")).background().start().join()
        with pytest.raises(ValueError):
            background.result()

    def test_context_manager_joins(self):
        slow = always(True).with_delay(timedelta(milliseconds=30))
        with slow.background() as background:
            pass
        assert background.is_finished().check()
        assert background.result() is True


# --- filesystem --------------------------------------------------------


class TestFilesystem:
    def test_file_exists(self, tmp_path: Path):
        present = tmp_path / "exists.txt"
        present.touch()
        assert file_exists(present).check()
        assert not file_exists(tmp_path / "missing.txt").check()

    def test_dir_exists(self, tmp_path: Path):
        directory = tmp_path / "dir"
        directory.mkdir()
        assert dir_exists(directory).check()
        assert not dir_exists(tmp_path / "missing").check()

    def test_file_contains(self, tmp_path: Path):
        path = tmp_path / "test.txt"
        path.write_text("hello fluent checks")
        assert file_contains(path, b"fluent").check()
        assert not file_contains(path, b"world").check()
        assert not file_contains(tmp_path / "missing.txt", b"").check()

    def test_checks_are_live(self, tmp_path: Path):
        """A Check observes the world at check() time, not construction time."""
        path = tmp_path / "later.txt"
        exists = file_exists(path)
        assert not exists.check()
        path.touch()
        assert exists.check()


# --- comparisons -------------------------------------------------------


class TestComparisons:
    @pytest.mark.parametrize(
        "factory, args, expected",
        [
            (is_equal, (1, 1), True),
            (is_equal, (1, 2), False),
            (is_not_equal, (1, 2), True),
            (is_not_equal, (1, 1), False),
            (is_greater_than, (2, 1), True),
            (is_greater_than, (1, 2), False),
            (is_less_than, (1, 2), True),
            (is_less_than, (2, 1), False),
            (is_in, (1, [1, 2, 3]), True),
            (is_in, (4, [1, 2, 3]), False),
            (is_instance_of, (1, int), True),
            (is_instance_of, ("a", int), False),
        ],
    )
    def test_comparisons(self, factory, args, expected):
        assert factory(*args).check() == expected
