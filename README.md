# Fluent Checks

[![PyPI version](https://badge.fury.io/py/fluent-checks.svg)](https://badge.fury.io/py/fluent-checks)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A Python library for creating readable, composable, and chainable conditions for tests or application logic.

## Installation

```bash
pip install fluent-checks
```

## Quickstart

`fluent-checks` helps you turn complex, imperative conditional logic into a clean, fluent API.

**Instead of this:**
```python
# Imperative style
start_time = time.time()
file_created = False
while time.time() - start_time < 5:
    if os.path.exists("my_file.txt"):
        file_created = True
        break
if not file_created:
    raise AssertionError("File not created in 5 seconds")
```

**You can write this:**
```python
from fluent_checks import Check
import os

# Fluent style
file_exists = Check(lambda: os.path.exists("my_file.txt"))

# This line will block until the file exists or raise a TimeoutException after 5s
file_exists.with_timeout(5).wait_for()
```

## Core Features

### 1. Combine Checks
Use standard logical operators to combine checks.
```python
from fluent_checks import Check

is_ready = Check(lambda: service.status == "ready")
is_healthy = Check(lambda: service.health > 0.9)

# This will block until the service is both ready AND healthy
(is_ready & is_healthy).wait_for()
```

### 2. Add Modifiers
Chain methods to add conditions like timeouts, retries, or exception checks.

-   **Time-Based**:
    -   `.with_timeout(seconds)`: Fails if the check doesn't pass within a time limit.
    -   `.with_delay(seconds)`: Waits a fixed duration before checking.
    -   `.with_deadline(datetime)`: Fails if the check doesn't pass by a specific time.

-   **Repetition**:
    -   `.succeeds_within(attempts)`: Checks multiple times, succeeding if it passes at least once.
    -   `.is_consistent_for(attempts)`: Succeeds only if the check passes on every attempt.

-   **Exception Handling**:
    -   `.raises(ExceptionType)`: Succeeds if the wrapped function raises the specified exception.

**Example with multiple modifiers:**
```python
import random

# A check for a flaky API that should eventually return True
flaky_api_call = Check(lambda: random.choice([True, False]))

# Succeeds if the API returns True within 3 tries, waiting 0.5s between each try.
check = flaky_api_call.with_delay(0.5).succeeds_within(3)

if check:
    print("API call succeeded!")
```

## Contributing

Contributions are welcome! Please open an issue to discuss your ideas.

## License

This project is licensed under the GNU GENERAL PUBLIC LICENSE.