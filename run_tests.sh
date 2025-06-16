#!/bin/bash

# Item Bot Test Runner
# Runs the comprehensive self-test suite using Poetry

set -e  # Exit on any error

echo "🚀 Item Bot Test Runner"
echo "======================="
echo

# Check if Poetry is installed
if ! command -v poetry &> /dev/null; then
    echo "❌ Poetry is not installed or not in PATH"
    echo "   Please install Poetry: https://python-poetry.org/docs/#installation"
    exit 1
fi

# Check if we're in the right directory
if [[ ! -f "pyproject.toml" ]]; then
    echo "❌ pyproject.toml not found"
    echo "   Please run this script from the bot directory"
    exit 1
fi

if [[ ! -f "selftest.py" ]]; then
    echo "❌ selftest.py not found"
    echo "   Please ensure the selftest script exists"
    exit 1
fi

echo "✅ Poetry found: $(poetry --version)"
echo "✅ Project files detected"
echo

# Install dependencies if needed
echo "📦 Ensuring dependencies are installed..."
poetry install --only=main
echo

# Check if user wants quick test or full test
if [[ "$1" == "quick" ]]; then
    echo "🧪 Running quick functionality test..."
    echo "   Using Poetry virtual environment"
    echo "   Production database is completely safe!"
    echo
    
    # Run the quick test using Poetry
    if poetry run python quick_test.py; then
        echo
        echo "🎉 Quick test completed successfully!"
        echo "   Your Item Bot core functionality is working!"
        exit 0
    else
        echo
        echo "❌ Quick test failed"
        echo "   Please review the output above for details"
        exit 1
    fi
else
    # Run the comprehensive tests
    echo "🧪 Running comprehensive self-tests..."
    echo "   Using Poetry virtual environment"
    echo "   Production database is completely safe!"
    echo "   Note: Database locking errors may occur but don't affect functionality"
    echo
    
    # Run the selftest using Poetry
    if poetry run python selftest.py; then
        echo
        echo "🎉 All tests completed successfully!"
        echo "   Your Item Bot is ready to use!"
        exit 0
    else
        echo
        echo "❌ Some tests failed"
        echo "   Please review the output above for details"
        echo "   Try running './run_tests.sh quick' for a simpler test"
        exit 1
    fi
fi 