#!/bin/bash

# Ruff auto-fix script

echo "🔧 Auto-fixing linting issues..."
poetry run ruff check --fix .

echo ""
echo "🎨 Formatting code..."
poetry run ruff format .

echo ""
echo "🔍 Running final check..."
poetry run ruff check .

if [ $? -eq 0 ]; then
    echo "✅ All issues fixed!"
else
    echo "⚠️  Some issues may require manual attention."
fi 