# Fluent Checks

A Python library for creating fluent, readable, and composable checks for your tests or application logic.

## Installation

Install the package using pip:

```bash
pip install fluent-checks
```

## Core Concepts

The core of the library is the `Check` class. A `Check` is a simple wrapper around a function that returns a boolean (a `Condition`).
```python
from fluent_checks import Check

# Create a check from a lambda
is_even = Check(lambda: 2 % 2 == 0)

# Evaluate the check
if is_even:
    print("It's even!")

# Or more explicitly
assert bool(is_even) is True
```

## Usage
### Combining Checks

Checks can be combined using logical operators to create more complex conditions.
```python
a = Check(lambda: True)
b = Check(lambda: False)

assert bool(a & b) is False  # And
assert bool(a | b) is True   # Or
assert bool(~b) is True      # Not
```

### Waiting for Conditions

You can wait for a condition to become true.
```python
import time

start_time = time.time()
flaky_check = Check(lambda: time.time() - start_time > 2)

# as_waiting will block until the check is true, or the timeout is reached.
assert flaky_check.as_waiting(timeout=3) is True
assert flaky_check.as_waiting(timeout=1) is False
```

### Timeouts and Deadlines

You can enforce time limits on checks.

```python
from datetime import datetime, timedelta

# This check will raise a TimeoutException if it takes longer than 1 second
slow_check = Check(lambda: time.sleep(2) or True)
failing_check = slow_check.with_timeout(1)

try:
    bool(failing_check)
except TimeoutException:
    print("Caught expected timeout!")

# You can also use a specific deadline
deadline = datetime.now() + timedelta(seconds=1)
check_with_deadline = slow_check.with_deadline(deadline)
```

### Repeating Checks

You can verify that a condition holds true multiple times.

```python
# succeeds_in_attempts: True if the check passes at least once in 5 attempts
flaky_check = Check(lambda: random.random() > 0.5)
assert flaky_check.succeeds_in_attempts(5)

# is_consistent_for: True if the check passes 5 times in a row
stable_check = Check(lambda: True)
assert stable_check.is_consistent_for(5)
```

### Looping Checks
The `sometimes` and `always` checks will run in a background thread until they are explicitly stopped.
```python
# The 'sometimes' check will pass if the condition is met at least once.
check = Check(lambda: random.random() > 0.8).sometimes()
time.sleep(1) # Give it some time to run
assert bool(check) is True
check.stop()

# The 'always' check will only pass if the condition is met every single time.
check = Check(lambda: random.random() > 0.2).always()
time.sleep(1) # Give it some time to run
assert bool(check) is False
check.stop()
```

### Checking for Exceptions

You can check that a piece of code raises a specific exception.

```python
def might_fail():
    raise ValueError("Something went wrong")

check = Check(might_fail).raises(ValueError)

assert bool(check) is True
```

### Callbacks
You can add callbacks to your checks, that will be executed on success or on failure.
```python
a = Check(lambda: True)
a.on_success(lambda: print("I've passed"))
a.on_failure(lambda: print("I've failed"))

bool(a) # This will print "I've passed"
```

### File System Checks
You can check for files and directories.
```python
# Check if a file exists
assert FileExistsCheck("path/to/file")

# Check if a directory exists
assert DirectoryExistsCheck("path/to/dir")

# Check if a file contains specific content
assert FileContainsCheck("path/to/file", "content")
```

### Comparison Checks
You can compare values.
```python
# Equality
assert IsEqualCheck(1, 1)
assert IsNotEqualCheck(1, 2)

# Comparison
assert IsGreaterThanCheck(2, 1)
assert IsLessThanCheck(1, 2)

# Containment
assert IsInCheck(1, [1, 2, 3])

# Instance
assert IsInstanceOfCheck(1, int)
```

## API Overview

### Base Class
| Class/Method | Description |
| --- | --- |
| **`Check(condition: Callable[[], bool])`** | The base class for all checks. |
| **`&`, `\|`, `~`** | Operators for AND, OR, and NOT logic. |
| **`bool(check)`, `check.check()`** | Evaluates the check and returns the boolean result. |

### Waiting and Timeouts
| Class/Method | Description |
| --- | --- |
| **`as_waiting(timeout: float) -> WaitingCheck`** | Blocks until the check is `True` or the timeout expires. |
| **`with_timeout(timeout: float) -> TimeoutCheck`** | Returns a new check that will raise a `TimeoutException` if it doesn't complete within the timeout. |
| **`with_deadline(deadline: datetime) -> DeadlineCheck`** | Similar to `with_timeout` but uses an absolute deadline. |
| **`succeeds_within(timeout: float) -> SucceedsWithinCheck`** | Checks if the condition is met at least once within a time limit. `eventually` is an alias for this. |
| **`fails_within(timeout: float) -> FailsWithinCheck`** | Checks if the condition fails at least once within a time limit. |

### Repeating and Looping
| Class/Method | Description |
| --- | --- |
| **`succeeds_in_attempts(times: int) -> RepeatingOrCheck`** | Checks if the condition is met at least once within a number of tries. |
| **`is_consistent_for(times: int) -> RepeatingAndCheck`** | Checks if the condition is met consecutively for a number of tries. |
| **`sometimes() -> LoopingOrCheck`** | Runs the check in a background thread and succeeds if the condition is met at least once. Remember to call `stop()`.|
| **`always() -> LoopingAndCheck`** | Runs the check in a background thread and succeeds only if the condition is always met. Remember to call `stop()`.|

### Exceptions and Callbacks
| Class/Method | Description |
| --- | --- |
| **`raises(exception: type[Exception]) -> RaisesCheck`** | Checks if the condition raises a specific exception. |
| **`on_success(callback: Callable[[], None]) -> Check`** | Registers a callback to be executed when the check succeeds. |
| **`on_failure(callback: Callable[[], None]) -> Check`** | Registers a callback to be executed when the check fails. |

### File System
| Class/Method | Description |
| --- | --- |
| **`FileExistsCheck(path: str)`** | Checks if a file exists at the given path. |
| **`DirectoryExistsCheck(path: str)`** | Checks if a directory exists at the given path. |
| **`FileContainsCheck(path: str, content: str)`** | Checks if a file at the given path contains the given content. |

### Comparisons
| Class/Method | Description |
| --- | --- |
| **`IsEqualCheck(left, right)`** | Checks if `left == right`. |
| **`IsNotEqualCheck(left, right)`** | Checks if `left != right`. |
| **`IsGreaterThanCheck(left, right)`** | Checks if `left > right`. |
| **`IsLessThanCheck(left, right)`** | Checks if `left < right`. |
| **`IsInCheck(member, container)`** | Checks if `member in container`. |
| **`IsInstanceOfCheck(obj, class_or_tuple)`** | Checks if `isinstance(obj, class_or_tuple)`. |


## License

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](LICENSE) file for details.

