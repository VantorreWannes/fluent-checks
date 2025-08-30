import pytest
import time
import datetime
import threading
import os
import tempfile
from fluent_checks import (
    Check,
    AllCheck,
    AnyCheck,
    DeadlineException,
    TimeoutException,
    IsEqualCheck,
    IsNotEqualCheck,
    IsGreaterThanCheck,
    IsLessThanCheck,
    IsInCheck,
    IsInstanceOfCheck,
    FileExistsCheck,
    DirectoryExistsCheck,
    FileContainsCheck,
)

# --- Helpers ---

CHECK_TRUE = Check(lambda: True)
CHECK_FALSE = Check(lambda: False)


class State:
    """A simple mutable object to hold state for checks."""

    def __init__(self, value: bool):
        self.value = value

    def get_value(self) -> bool:
        return self.value

    def set_value_after(self, value: bool, delay: float):
        """Sets the state value after a given delay in a separate thread."""

        def target():
            time.sleep(delay)
            self.value = value

        threading.Thread(target=target, daemon=True).start()


def traceable_check(result: bool, tracker: list, name: str):
    """A check that records when it has been evaluated."""

    def condition():
        tracker.append(name)
        return result

    condition.__name__ = name
    return Check(condition)


def crash_check():
    """A check that fails if evaluated."""
    return Check(lambda: pytest.fail("This check should not have been evaluated"))


@pytest.fixture
def temp_file_system():
    """Creates a temporary directory and a file with content for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        test_file_path = os.path.join(temp_dir, "test_file.txt")
        with open(test_file_path, "w") as f:
            f.write("hello fluent checks")
        yield {
            "dir": temp_dir,
            "file": test_file_path,
            "non_existent_file": os.path.join(temp_dir, "not_real.txt"),
        }


# --- Basic Tests ---


def test_basic_check():
    assert CHECK_TRUE
    assert not CHECK_FALSE


def test_invert_check():
    assert not ~CHECK_TRUE
    assert ~CHECK_FALSE


@pytest.mark.parametrize(
    "left, right, expected",
    [
        (CHECK_TRUE, CHECK_TRUE, True),
        (CHECK_TRUE, CHECK_FALSE, False),
        (CHECK_FALSE, CHECK_TRUE, False),
        (CHECK_FALSE, CHECK_FALSE, False),
    ],
)
def test_and_check(left, right, expected):
    assert (left & right).check() == expected


@pytest.mark.parametrize(
    "left, right, expected",
    [
        (CHECK_TRUE, CHECK_TRUE, True),
        (CHECK_TRUE, CHECK_FALSE, True),
        (CHECK_FALSE, CHECK_TRUE, True),
        (CHECK_FALSE, CHECK_FALSE, False),
    ],
)
def test_or_check(left: Check, right: Check, expected):
    assert (left | right).check() == expected


# --- Short-circuiting Tests ---


def test_all_check_short_circuiting():
    tracker = []
    c1 = traceable_check(True, tracker, "c1")
    c2 = traceable_check(False, tracker, "c2")
    c3 = crash_check()

    check = AllCheck(c1, c2, c3)
    assert not check
    assert tracker == ["c1", "c2"]


def test_any_check_short_circuiting():
    tracker = []
    c1 = traceable_check(False, tracker, "c1")
    c2 = traceable_check(True, tracker, "c2")
    c3 = crash_check()

    check = AnyCheck(c1, c2, c3)
    assert check
    assert tracker == ["c1", "c2"]


# --- Modifier Tests ---


def test_delayed_check():
    delay = 0.1
    start_time = time.time()
    result = CHECK_TRUE.with_delay(delay)
    assert result
    end_time = time.time()
    assert end_time - start_time >= delay


def test_repeating_and_check():
    # Test is_consistent_for
    counter = 0

    def condition():
        nonlocal counter
        counter += 1
        return counter <= 3

    check = Check(condition)
    assert not check.is_consistent_for(5)

    counter = 0  # Reset counter
    assert check.is_consistent_for(3)


def test_repeating_or_check():
    # Test succeeds_in_attempts
    counter = 0

    def condition():
        nonlocal counter
        counter += 1
        return counter >= 3

    check = Check(condition)
    assert check.succeeds_in_attempts(5)

    counter = 0  # Reset counter
    assert not check.succeeds_in_attempts(2)


# --- Async / Timed Tests ---


def test_timeout_check():
    with pytest.raises(TimeoutException):
        CHECK_TRUE.with_delay(10).with_timeout(0.1).check()

    # Should not raise if it passes in time
    assert CHECK_TRUE.with_timeout(0.1)


def test_deadline_check():
    deadline = datetime.datetime.now() + datetime.timedelta(seconds=0.1)
    with pytest.raises(DeadlineException):
        CHECK_FALSE.with_delay(10).with_deadline(deadline).check()

    # Should not raise if it passes in time
    deadline = datetime.datetime.now() + datetime.timedelta(seconds=0.1)
    assert CHECK_TRUE.with_deadline(deadline)


def test_waiting_check():
    state = State(False)
    state.set_value_after(True, 0.05)

    assert Check(state.get_value).as_waiting(0.2)

    state.value = False
    assert not Check(state.get_value).as_waiting(0.1)


def test_succeeds_within_check():
    state = State(False)
    state.set_value_after(True, 0.05)
    assert Check(state.get_value).succeeds_within(0.2)

    state.value = False
    assert not Check(state.get_value).succeeds_within(0.1)


def test_fails_within_check():
    state = State(True)
    state.set_value_after(False, 0.05)
    assert Check(state.get_value).fails_within(0.2)

    state.value = True
    assert not Check(state.get_value).fails_within(0.1)


def test_looping_checks():
    state = State(False)
    check = Check(state.get_value)

    # Test .sometimes() -> LoopingOrCheck
    sometimes = check.sometimes()
    assert not sometimes
    state.set_value_after(True, 0)
    time.sleep(0.1)  # Give thread time to update
    assert sometimes

    # Test .always() -> LoopingAndCheck
    state.set_value_after(True, 0)
    always = check.always()
    assert always
    state.set_value_after(False, 0)
    time.sleep(0.1)  # Give thread time to update
    assert not always


# --- Exception Tests ---


def test_raises_check():
    def raise_value_error():
        raise ValueError("Test error")

    def no_error():
        return True

    def raise_key_error():
        raise KeyError("Different error")

    assert Check(raise_value_error).raises(ValueError)
    assert not Check(no_error).raises(ValueError)

    # Make sure other exceptions are not caught and are propagated
    with pytest.raises(KeyError):
        Check(raise_key_error).raises(ValueError).check()


# --- Callback Tests ---


def test_on_success_callback():
    """Verify the on_success callback is triggered correctly."""
    tracker = []
    check = CHECK_TRUE.on_success(lambda: tracker.append("success"))
    assert check  # Evaluate the check
    assert tracker == ["success"]

    tracker.clear()
    check = CHECK_FALSE.on_success(lambda: tracker.append("success"))
    assert not check
    assert tracker == []


def test_on_failure_callback():
    """Verify the on_failure callback is triggered correctly."""
    tracker = []
    check = CHECK_FALSE.on_failure(lambda: tracker.append("failure"))
    assert not check
    assert tracker == ["failure"]

    tracker.clear()
    check = CHECK_TRUE.on_failure(lambda: tracker.append("failure"))
    assert check
    assert tracker == []


def test_callback_chaining():
    """Verify that callback methods can be chained."""
    tracker = []
    check = CHECK_TRUE.on_success(lambda: tracker.append("s")).on_failure(
        lambda: tracker.append("f")
    )
    assert check
    assert tracker == ["s"]

    tracker.clear()
    check = CHECK_FALSE.on_success(lambda: tracker.append("s")).on_failure(
        lambda: tracker.append("f")
    )
    assert not check
    assert tracker == ["f"]


def test_callbacks_with_raises_check():
    """Verify callbacks work with the RaisesCheck."""
    tracker = []

    def raise_error():
        raise ValueError()

    def no_error():
        return False

    check_success = (
        Check(raise_error)
        .raises(ValueError)
        .on_success(lambda: tracker.append("success"))
    )
    assert check_success
    assert tracker == ["success"]

    tracker.clear()
    check_fail = (
        Check(no_error).raises(ValueError).on_failure(lambda: tracker.append("failure"))
    )
    assert not check_fail
    assert tracker == ["failure"]


# --- Comparison Tests ---
@pytest.mark.parametrize(
    "left, right, expected", [(5, 5, True), (5, 10, False), ("a", "a", True)]
)
def test_is_equal_check(left, right, expected):
    assert IsEqualCheck(left, right).check() == expected


@pytest.mark.parametrize(
    "left, right, expected", [(5, 10, True), (5, 5, False), ("a", "b", True)]
)
def test_is_not_equal_check(left, right, expected):
    assert IsNotEqualCheck(left, right).check() == expected


@pytest.mark.parametrize(
    "left, right, expected", [(10, 5, True), (5, 10, False), (5, 5, False)]
)
def test_is_greater_than_check(left, right, expected):
    assert IsGreaterThanCheck(left, right).check() == expected


@pytest.mark.parametrize(
    "left, right, expected", [(5, 10, True), (10, 5, False), (5, 5, False)]
)
def test_is_less_than_check(left, right, expected):
    assert IsLessThanCheck(left, right).check() == expected


@pytest.mark.parametrize(
    "member, container, expected",
    [(2, [1, 2, 3], True), ("a", "abc", True), (4, [1, 2, 3], False)],
)
def test_is_in_check(member, container, expected):
    assert IsInCheck(member, container).check() == expected


@pytest.mark.parametrize(
    "obj, cls, expected",
    [(5, int, True), ("hi", str, True), (5, str, False), ("hi", (int, str), True)],
)
def test_is_instance_of_check(obj, cls, expected):
    assert IsInstanceOfCheck(obj, cls).check() == expected


# --- File System Tests ---


def test_file_exists_check(temp_file_system):
    assert FileExistsCheck(temp_file_system["file"])
    assert not FileExistsCheck(temp_file_system["non_existent_file"])


def test_directory_exists_check(temp_file_system):
    assert DirectoryExistsCheck(temp_file_system["dir"])
    assert not DirectoryExistsCheck(temp_file_system["file"])  # Path is a file


def test_file_contains_check(temp_file_system):
    assert FileContainsCheck(temp_file_system["file"], "fluent")
    assert not FileContainsCheck(temp_file_system["file"], "world")
    assert not FileContainsCheck(temp_file_system["non_existent_file"], "hello")


# --- Alias Tests ---


def test_eventually_alias():
    start_time = time.time()
    passing_check = Check(lambda: time.time() - start_time > 0.05)
    assert passing_check.eventually(timeout=0.2)

    failing_check = CHECK_FALSE
    assert not failing_check.eventually(timeout=0.1)
