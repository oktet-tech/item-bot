#!/bin/bash

# Ruff linting and formatting script

echo "🔍 Running ruff linter..."
poetry run ruff check .

if [ $? -ne 0 ]; then
    echo ""
    echo "❌ Linting issues found. Try running:"
    echo "   poetry run ruff check --fix ."
    echo ""
    exit 1
fi

echo "✅ Linting passed!"
echo ""

echo "🎨 Checking code formatting..."
poetry run ruff format --check .

if [ $? -ne 0 ]; then
    echo ""
    echo "❌ Formatting issues found. Try running:"
    echo "   poetry run ruff format ."
    echo ""
    exit 1
fi

echo "✅ Formatting is correct!"
echo ""
echo "🎉 All checks passed!" 