#!/usr/bin/env fish

set -l DIRS src tests

echo "Running ruff formatter..."
ruff format $DIRS

echo "Running ruff linter (with auto-fix)..."
ruff check $DIRS --fix

echo "Formatting complete."