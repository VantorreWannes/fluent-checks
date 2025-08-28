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
assert is_even.as_bool() is True
```

## Usage
### Combining Checks

Checks can be combined using logical operators to create more complex conditions.
```python
a = Check(lambda: True)
b = Check(lambda: False)

assert (a & b).as_bool() is False  # And
assert (a | b).as_bool() is True   # Or
assert (~b).as_bool() is True      # Not
```

### Waiting for Conditions

You can wait for a condition to become true.
```python
import time

start_time = time.time()
flaky_check = Check(lambda: time.time() - start_time > 2)

# wait_for will block until the check is true, or the timeout is reached.
assert flaky_check.wait_for(timeout=3) is True
assert flaky_check.wait_for(timeout=1) is False
```

### Timeouts and Deadlines

You can enforce time limits on checks.

```python
from datetime import datetime, timedelta

# This check will raise a TimeoutException if it takes longer than 1 second
slow_check = Check(lambda: time.sleep(2) or True)
failing_check = slow_check.with_timeout(1)

try:
    failing_check.as_bool()
except TimeoutException:
    print("Caught expected timeout!")

# You can also use a specific deadline
deadline = datetime.now() + timedelta(seconds=1)
check_with_deadline = slow_check.with_deadline(deadline)
```

### Repeating Checks

You can verify that a condition holds true multiple times.

```python
# succeeds_within: True if the check passes at least once in 5 attempts
flaky_check = Check(lambda: random.random() > 0.5)
assert flaky_check.succeeds_within(5)

# is_consistent_for: True if the check passes 5 times in a row
stable_check = Check(lambda: True)
assert stable_check.is_consistent_for(5)
```

### Checking for Exceptions

You can check that a piece of code raises a specific exception.

```python
def might_fail():
    raise ValueError("Something went wrong")

check = Check(might_fail).raises(ValueError)

assert check.as_bool() is True
```

## API Overview

-   **`Check(condition: Callable[[], bool])`**: The base class for all checks.
-   **`&`, `|`, `~`**: Operators for AND, OR, and NOT logic.
-   **`as_bool() -> bool`**: Evaluates the check and returns the boolean result.
-   **`wait_for(timeout: float) -> bool`**: Blocks until the check is `True` or the timeout expires.
-   **`with_timeout(timeout: float) -> TimeoutCheck`**: Returns a new check that will raise a `TimeoutException` if it doesn't complete within the timeout.
-   **`with_deadline(deadline: datetime) -> DeadlineCheck`**: Similar to `with_timeout` but uses an absolute deadline.
-   **`succeeds_within(times: int) -> RepeatingOrCheck`**: Checks if the condition is met at least once within a number of tries.
-   **`is_consistent_for(times: int) -> RepeatingAndCheck`**: Checks if the condition is met consecutively for a number of tries.
-   **`raises(exception: type[Exception]) -> RaisesCheck`**: Checks if the condition raises a specific exception.
## License

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](LICENSE) file for details.
