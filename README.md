# Fluent Checks

A Python library for creating fluent, readable, and composable checks for your tests or application logic.

## Installation

Install the package using pip:

```bash
pip install fluent-checks
```

## Core Idea: Everything Is a `Check`

The entire library rests on a single primitive:

```python
type Condition = Callable[[], bool]
```

A `Check` wraps a `Condition` and exposes one method, `check()`, which calls it. Every other check in the library — logical, temporal, repetition, filesystem, comparison — is just a `Check` built from a lambda that composes other checks. Complex behaviour **emerges** from composing a handful of primitives with fluent combinators, rather than from a deep class hierarchy.

```python
from fluent_checks import Check, CustomCheck

# `Check` and `CustomCheck` are interchangeable: both wrap a Condition.
is_even = Check(lambda: 2 % 2 == 0)

# Evaluate directly in a boolean context...
if is_even:
    print("It's even!")

# ...or explicitly.
assert is_even.check() is True
```

Because every combinator returns a full `Check`, you can chain anything together:

```python
from datetime import timedelta
from fluent_checks import Check

# timing + repetition + inversion + callbacks, all composed freely
Check(lambda: ready()).any_attempt(10).within(timedelta(seconds=2)).on_success(log)
```

## Usage

### Combining Checks

Checks compose with `&`, `|`, and `~`. These short-circuit, just like the underlying Python operators.

```python
from fluent_checks import Check

a = Check(lambda: True)
b = Check(lambda: False)

assert (a & b).check() is False  # AND
assert (a | b).check() is True   # OR
assert (~b).check() is True      # NOT
```

For more than two checks, use `AllCheck` (all must pass) and `AnyCheck` (at least one must pass):

```python
from fluent_checks import AllCheck, AnyCheck, Check

assert AllCheck(Check(lambda: True), Check(lambda: True)).check()
assert AnyCheck(Check(lambda: False), Check(lambda: True)).check()
```

### Waiting for Conditions

`.wait()` blocks indefinitely until a check passes. `.within(timeout)` / `.eventually(timeout)` race the check against a timeout. `.before(deadline)` does the same against an absolute `datetime`.

```python
import time
from datetime import timedelta
from fluent_checks import Check

start = time.time()
becomes_true = Check(lambda: time.time() - start > 1)

# Block until true
becomes_true.wait().check()

# True if it becomes true within the timeout
delayed = Check(lambda: True).with_delay(timedelta(seconds=1))
assert delayed.within(timedelta(seconds=2)).check() is True
```

### Repeating Checks

`.all_attempts(n)` requires the check to pass `n` consecutive times; `.any_attempt(n)` requires it to pass at least once in `n` tries.

```python
import random
from fluent_checks import Check

flaky = Check(lambda: random.random() > 0.8)
flaky.any_attempt(10)        # True if it passes at least once in 10 tries

stable = Check(lambda: True)
assert stable.all_attempts(5)  # True if it passes 5 times in a row
```

### Background Checks

`.background()` runs a check in a daemon thread. `start()` launches it, `is_finished()` polls, `result()` retrieves the outcome, and `check()` blocks until it completes.

```python
import time
from datetime import timedelta
from fluent_checks import Check

long_check = Check(lambda: True).with_delay(timedelta(seconds=1))
bg = long_check.background()

bg.start()
assert bg.is_finished().check() is False
time.sleep(1.1)
assert bg.is_finished().check() is True
assert bg.result() is True
```

`BackgroundCheck` also works as a context manager (`with check.background() as bg: ...`).

### Checking for Exceptions

`.raises(exc)` returns a check that passes iff the wrapped check raises `exc`.

```python
from fluent_checks import Check

def might_fail():
    raise ValueError("Something went wrong")

assert Check(might_fail).raises(ValueError).check() is True
```

### Callbacks

`.on_success(cb)` and `.on_failure(cb)` fire `cb` when the check passes or fails, respectively, without changing the result.

```python
from fluent_checks import Check

a = Check(lambda: True).on_success(lambda: print("passed"))
a.check()  # prints "passed"
```

### File System Checks

Factory functions for common filesystem assertions:

```python
from pathlib import Path
from fluent_checks import file_exists, dir_exists, file_contains

def test_fs(tmp_path: Path):
    my_file = tmp_path / "file.txt"
    my_file.touch()
    assert file_exists(my_file).check()

    my_dir = tmp_path / "dir"
    my_dir.mkdir()
    assert dir_exists(my_dir).check()

    my_file.write_text("hello")
    assert file_contains(my_file, b"hello").check()
```

### Comparison Checks

Factory functions for value comparisons:

```python
from fluent_checks import is_equal, is_not_equal, is_greater_than, is_less_than, is_in, is_instance_of

assert is_equal(1, 1).check()
assert is_not_equal(1, 2).check()
assert is_greater_than(2, 1).check()
assert is_less_than(1, 2).check()
assert is_in(1, [1, 2, 3]).check()
assert is_instance_of(1, int).check()
```

## How It Works

There is one real type, `Check`, which stores a `Condition` and implements `check()` once:

```python
class Check:
    def __init__(self, condition: Condition) -> None:
        self._condition = condition
    def check(self) -> bool:
        return self._condition()
    # ... fluent combinators, all returning Check subclasses
```

Every named check (`AndCheck`, `DelayedCheck`, `IsTrueBeforeTimeoutCheck`, `FileContainsCheck`, …) is a `Check` whose `__init__` builds a lambda composing other checks and passes it to `super().__init__`. They do not override `check()`. The named subclasses exist so that `isinstance` checks and readable `repr`s keep working, but they carry no custom logic of their own.

This means any combinator can follow any other — timing, repetition, inversion, callbacks, exception handling, and background execution all compose without writing a new class.

## API Overview

### Base `Check` Methods

| Method                      | Description                                                  |
| --------------------------- | ------------------------------------------------------------ |
| **`.check()`**              | Evaluates the check and returns the boolean result.          |
| **`&`, `\|`, `~`**          | Operators for AND, OR, and NOT logic (short-circuiting).     |
| **`.on_success(callback)`** | Runs `callback` when the check succeeds.                     |
| **`.on_failure(callback)`** | Runs `callback` when the check fails.                        |
| **`.all_attempts(times)`**  | True if the check passes `times` consecutive times.          |
| **`.any_attempt(times)`**   | True if the check passes at least once in `times` tries.     |
| **`.before(deadline)`**     | True if the check becomes true before a specific `datetime`. |
| **`.within(timeout)`**      | True if the check becomes true within a `timedelta`.         |
| **`.eventually(timeout)`**  | Alias for `within`.                                          |
| **`.wait()`**               | Blocks indefinitely until the check returns `True`.          |
| **`.raises(exception)`**    | True if the check raises the given exception type.           |
| **`.with_delay(delay)`**    | Returns a check that sleeps for `delay` before running.      |
| **`.invert()`**             | Logical negation (same as `~`).                              |
| **`.background()`**         | Returns a `BackgroundCheck` running in a daemon thread.      |

### Filesystem Functions

| Function                           | Description                                     |
| ---------------------------------- | ----------------------------------------------- |
| **`file_exists(path)`**            | Checks if a file exists at the given path.      |
| **`dir_exists(path)`**             | Checks if a directory exists at the given path. |
| **`file_contains(path, content)`** | Checks if a file contains the given bytes.      |

### Comparison Functions

| Function                                  | Description                                  |
| ----------------------------------------- | -------------------------------------------- |
| **`is_equal(left, right)`**               | Checks if `left == right`.                   |
| **`is_not_equal(left, right)`**           | Checks if `left != right`.                   |
| **`is_greater_than(left, right)`**        | Checks if `left > right`.                    |
| **`is_less_than(left, right)`**           | Checks if `left < right`.                    |
| **`is_in(member, container)`**            | Checks if `member in container`.             |
| **`is_instance_of(obj, class_or_tuple)`** | Checks if `isinstance(obj, class_or_tuple)`. |

## License

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](LICENSE) file for details.
