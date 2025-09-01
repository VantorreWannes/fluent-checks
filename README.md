# Fluent Checks

A Python library for creating fluent, readable, and composable checks for your tests or application logic.

## Installation

Install the package using pip:

```bash
pip install fluent-checks
```

## Core Concepts

The core of the library is the abstract `Check` class. A `Check` is a simple wrapper around a function that returns a boolean (`Condition`). For custom logic, you use `CustomCheck`.
```python
from fluent_checks import CustomCheck

# Create a check from a lambda
is_even = CustomCheck(lambda: 2 % 2 == 0)

# The base class for all checks is `Check`.
# You can evaluate any check directly in a boolean context.
if is_even:
    print("It's even!")

# Or more explicitly
assert is_even.check() is True
```

## Usage
### Combining Checks

Checks can be combined using logical operators to create more complex conditions.
```python
from fluent_checks import CustomCheck

a = CustomCheck(lambda: True)
b = CustomCheck(lambda: False)

assert (a & b).check() is False  # And
assert (a | b).check() is True   # Or
assert (~b).check() is True      # Not
```

### Waiting for Conditions

You can wait for a condition to become true.
```python
import time
from datetime import timedelta
from fluent_checks import CustomCheck

start_time = time.time()
wait_check = CustomCheck(lambda: time.time() - start_time > 1)

# Block indefinitely until a check passes
wait_check.wait_until_true()
assert wait_check.check() is True

# Check if something becomes true within a timeout
passing_check = CustomCheck(lambda: True).with_delay(timedelta(seconds=1))
assert passing_check.succeeds_within_timeout(timedelta(seconds=2)) is True

failing_check = CustomCheck(lambda: True).with_delay(timedelta(seconds=2))
assert failing_check.succeeds_within_timeout(timedelta(seconds=1)) is False

# `eventually` is a convenient alias for succeeds_within_timeout
assert passing_check.eventually(timedelta(seconds=2)) is True
```

### Repeating Checks

You can verify that a condition holds true multiple times.
```python
import random
from fluent_checks import CustomCheck

# succeeds_within_attempts: True if the check passes at least once in 10 attempts
flaky_check = CustomCheck(lambda: random.random() > 0.8)
flaky_check.succeeds_within_attempts(10)

# is_true_for_attempts: True if the check passes 5 times in a row
stable_check = CustomCheck(lambda: True)
assert stable_check.is_true_for_attempts(5)
```

### Background Checks
You can run any check in a background thread.
```python
import time
from datetime import timedelta
from fluent_checks import CustomCheck

# Run a long-running check in the background
long_check = CustomCheck(lambda: True).with_delay(timedelta(seconds=1))
background_check = long_check.as_background()

# You can start it and check on it later
background_check.start()
assert background_check.is_finished().check() is False
time.sleep(1.1)
assert background_check.is_finished().check() is True
assert background_check.result() is True
```

### Checking for Exceptions

You can check that a piece of code raises a specific exception.
```python
from fluent_checks import CustomCheck

def might_fail():
    raise ValueError("Something went wrong")

check = CustomCheck(might_fail).raises(ValueError)

assert check.check() is True
```

### Callbacks
You can add callbacks to your checks that will be executed on success or on failure.
```python
from fluent_checks import CustomCheck

a = CustomCheck(lambda: True)
a.on_success(lambda: print("I've passed"))
a.on_failure(lambda: print("I've failed"))

a.check() # This will print "I've passed"
```

### File System Checks
You can use pre-built factory functions to check the file system.
```python
from pathlib import Path
from fluent_checks import file_exists, dir_exists, file_contains

# (Example using pytest's tmp_path fixture)
def test_fs(tmp_path: Path):
    # Check if a file exists
    my_file = tmp_path / "file.txt"
    my_file.touch()
    assert file_exists(my_file)

    # Check if a directory exists
    my_dir = tmp_path / "dir"
    my_dir.mkdir()
    assert dir_exists(my_dir)

    # Check if a file contains specific content
    my_file.write_text("hello")
    assert file_contains(my_file, b"hello")
```

### Comparison Checks
You can use factory functions to compare values.
```python
from fluent_checks import is_equal, is_not_equal, is_greater_than, is_less_than, is_in, is_instance_of

# Equality
assert is_equal(1, 1)
assert is_not_equal(1, 2)

# Comparison
assert is_greater_than(2, 1)
assert is_less_than(1, 2)

# Containment
assert is_in(1, [1, 2, 3])

# Instance
assert is_instance_of(1, int)
```

## API Overview

### Base `Check` Methods
| Method | Description |
| --- | --- |
| **`.check()`** | Evaluates the check and returns the boolean result. |
| **`&`, `\|`, `~`** | Operators for AND, OR, and NOT logic. |
| **`.on_success(callback)`** | Registers a callback to be executed when the check succeeds. |
| **`.on_failure(callback)`** | Registers a callback to be executed when the check fails. |
| **`.is_true_for_attempts(times)`** | Checks if the condition is met consecutively for a number of tries. |
| **`.succeeds_within_attempts(times)`** | Checks if the condition is met at least once within a number of tries. |
| **`.succeeds_before_deadline(deadline)`**| Checks if the condition becomes true before a specific datetime. |
| **`.succeeds_within_timeout(timeout)`** | Checks if the condition becomes true within a certain timedelta. |
| **`.eventually(timeout)`** | An alias for `succeeds_within_timeout`. |
| **`.wait_until_true()`** | Blocks indefinitely until the check returns `True`. |
| **`.raises(exception)`** | Checks if the condition raises a specific exception. |
| **`.with_delay(delay)`** | Returns a new check that waits for a delay before executing. |
| **`.as_background()`** | Returns a `BackgroundCheck` wrapper to run the check in a thread. |


### Filesystem Functions
| Function | Description |
| --- | --- |
| **`file_exists(path: Path)`** | Checks if a file exists at the given path. |
| **`dir_exists(path: Path)`** | Checks if a directory exists at the given path. |
| **`file_contains(path: Path, content: bytes)`**| Checks if a file contains the given bytes. |

### Comparison Functions
| Function | Description |
| --- | --- |
| **`is_equal(left, right)`** | Checks if `left == right`. |
| **`is_not_equal(left, right)`** | Checks if `left != right`. |
| **`is_greater_than(left, right)`** | Checks if `left > right`. |
| **`is_less_than(left, right)`** | Checks if `left < right`. |
| **`is_in(member, container)`** | Checks if `member in container`. |
| **`is_instance_of(obj, class_or_tuple)`**| Checks if `isinstance(obj, class_or_tuple)`. |


## License

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](LICENSE) file for details.