import pytest
import time
import datetime
import threading
from fluent_checks import (
    Check,
    AllCheck,
    AnyCheck,
    DeadlineException,
    FailsWithinCheck,
    SucceedsWithinCheck,
    TimeoutException,
)


# Helper for testing evaluation order and short-circuiting
def traceable_check(result: bool, tracker: list, name: str):
    def condition():
        tracker.append(name)
        return result

    return Check(condition)


def crash_check():
    def condition():
        pytest.fail("This check should not have been evaluated")

    return Check(condition)


def test_basic_check():
    assert Check(lambda: True).check()
    assert not Check(lambda: False).check()
    assert bool(Check(lambda: True))
    assert not bool(Check(lambda: False))


def test_invert_check():
    assert not bool(~Check(lambda: True))
    assert bool(~Check(lambda: False))


def test_and_check():
    check_true = Check(lambda: True)
    check_false = Check(lambda: False)
    assert bool(check_true and check_true)
    assert not bool(check_true and check_false)
    assert not bool(check_false and check_true)
    assert not bool(check_false and check_false)


def test_or_check():
    check_true = Check(lambda: True)
    check_false = Check(lambda: False)
    assert bool(check_true | check_true)
    assert bool(check_true | check_false)
    assert bool(check_false | check_true)
    assert not bool(check_false | check_false)


def test_and_short_circuiting_and_order():
    tracker = []
    c1 = traceable_check(True, tracker, "c1")
    c2 = traceable_check(False, tracker, "c2")
    c3 = traceable_check(True, tracker, "c3")  # Will not be called

    # Test short-circuiting
    assert not bool(c1 & c2 & c3)
    assert tracker == ["c1", "c2"]

    # Test that a False check short-circuits immediately
    assert not bool(Check(lambda: False) & crash_check())


def test_or_short_circuiting_and_order():
    tracker = []
    c1 = traceable_check(False, tracker, "c1")
    c2 = traceable_check(True, tracker, "c2")
    c3 = traceable_check(False, tracker, "c3")  # Will not be called

    # Test short-circuiting
    assert bool(c1 | c2 | c3)
    assert tracker == ["c1", "c2"]

    # Test that a True check short-circuits immediately
    assert bool(Check(lambda: True) | crash_check())


def test_all_check_short_circuiting():
    tracker = []
    c1 = traceable_check(True, tracker, "c1")
    c2 = traceable_check(False, tracker, "c2")
    c3 = traceable_check(True, tracker, "c3")  # Should not be evaluated

    check = AllCheck(c1, c2, c3)
    assert not bool(check)
    assert tracker == ["c1", "c2"]


def test_any_check_short_circuiting():
    tracker = []
    c1 = traceable_check(False, tracker, "c1")
    c2 = traceable_check(True, tracker, "c2")
    c3 = traceable_check(False, tracker, "c3")  # Should not be evaluated

    check = AnyCheck(c1, c2, c3)
    assert bool(check)
    assert tracker == ["c1", "c2"]


def test_delayed_check():
    delay = 0.1
    start_time = time.time()
    result = Check(lambda: True).with_delay(delay)
    assert bool(result)
    end_time = time.time()
    assert end_time - start_time >= delay


def test_repeating_and_check():
    # Test is_consistent_for
    counter = 0

    def condition_eventually_fails():
        nonlocal counter
        counter += 1
        return counter <= 3

    assert not bool(Check(condition_eventually_fails).is_consistent_for(5))

    counter = 0
    assert bool(Check(condition_eventually_fails).is_consistent_for(3))


def test_repeating_or_check():
    # Test succeeds_within
    counter = 0

    def condition_eventually_succeeds():
        nonlocal counter
        counter += 1
        return counter >= 3

    assert bool(Check(condition_eventually_succeeds).succeeds_in_attempts(5))

    counter = 0
    assert not bool(Check(condition_eventually_succeeds).succeeds_in_attempts(2))


def test_timeout_check():
    # Test with_timeout. This now returns a LoopingCheck that should be used as a context manager.
    check_false = Check(lambda: False).with_timeout(0.1)
    with pytest.raises(TimeoutException):
        with check_false:  # Starts the background polling
            # Loop until the check's internal deadline is hit, which raises TimeoutException
            while True:
                bool(check_false)
                time.sleep(0.01)

    # Test that it passes if condition is True before timeout
    check_true = Check(lambda: True).with_timeout(1)
    with check_true:
        time.sleep(0.05)  # Allow thread to run and update result
        assert bool(check_true)


def test_deadline_check():
    # Test with_deadline, which is now a LoopingCheck
    deadline = datetime.datetime.now() + datetime.timedelta(seconds=0.1)
    check_false = Check(lambda: False).with_deadline(deadline)
    with pytest.raises(DeadlineException):
        with check_false:
            while True:
                bool(check_false)
                time.sleep(0.01)

    deadline_true = datetime.datetime.now() + datetime.timedelta(seconds=1)
    check_true = Check(lambda: True).with_deadline(deadline_true)
    with check_true:
        time.sleep(0.05)
        assert bool(check_true)


def test_waiting_check():
    # Test as_waiting, which replaced wait_for
    state = False

    def condition_changes():
        return state

    def change_state_later(delay):
        time.sleep(delay)
        nonlocal state
        state = True

    threading.Thread(target=change_state_later, args=(0.05,)).start()

    assert bool(Check(condition_changes).as_waiting(0.2))

    state = False
    assert not bool(Check(condition_changes).as_waiting(0.1))


def test_looping_check_start_stop():
    class State:
        value = False

    state = State()
    check = Check(lambda: state.value).sometimes()  # LoopingOrCheck

    assert not bool(check)  # Thread not started, initial value is False

    check.start()
    try:
        assert not bool(check)  # Thread started, but state is still False
        state.value = True
        time.sleep(0.05)  # Give thread time to update the result
        assert bool(check)
    finally:
        check.stop()

    # Check that the result is latched after stopping
    state.value = False
    time.sleep(0.05)
    assert bool(check)  # Result should not change after stop() is called


def test_looping_or_check():
    # Test sometimes
    class State:
        value = False

    state = State()

    with Check(lambda: state.value).sometimes() as check:
        assert not bool(check)
        time.sleep(0.05)
        assert not bool(check)
        state.value = True
        time.sleep(0.05)  # Give loop time to catch up
        assert bool(check)


def test_looping_and_check():
    # Test always
    class State:
        value = True

    state = State()

    with Check(lambda: state.value).always() as check:
        assert bool(check)
        time.sleep(0.05)
        assert bool(check)
        state.value = False
        time.sleep(0.05)  # Give loop time to catch up
        assert not bool(check)


def test_raises_check():
    def raise_value_error():
        raise ValueError("Test error")

    def no_error():
        return True

    def raise_key_error():
        raise KeyError("Different error")

    assert bool(Check(raise_value_error).raises(ValueError))
    assert not bool(Check(no_error).raises(ValueError))

    # Ensure it doesn't catch other exceptions
    with pytest.raises(KeyError):
        bool(Check(raise_key_error).raises(ValueError))


def test_SucceedsWithin_class():
    state = False

    def condition():
        return state

    def change_state_later(delay):
        time.sleep(delay)
        nonlocal state
        state = True

    check = Check(condition)

    # Succeeds
    state = False
    t = threading.Thread(target=change_state_later, args=(0.05,))
    t.start()
    assert bool(SucceedsWithinCheck(check, 0.2))
    t.join()

    # Fails
    state = False
    assert not bool(SucceedsWithinCheck(check, 0.1))


def test_FailsWithin_class():
    state = True

    def condition():
        return state

    def change_state_later(delay):
        time.sleep(delay)
        nonlocal state
        state = False

    check = Check(condition)

    # "Fails" (i.e. condition becomes False) within timeout -> succeeds
    state = True
    t = threading.Thread(target=change_state_later, args=(0.05,))
    t.start()
    assert bool(FailsWithinCheck(check, 0.2))
    t.join()

    # Stays True -> fails
    state = True
    assert not bool(FailsWithinCheck(check, 0.1))
