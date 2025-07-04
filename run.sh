#!/bin/bash

# Item Bot Startup Script

# Parse command line arguments
DEBUG_MODE=false
while [[ $# -gt 0 ]]; do
    case $1 in
        --debug)
            DEBUG_MODE=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--debug]"
            exit 1
            ;;
    esac
done

if [ "$DEBUG_MODE" = true ]; then
    echo "🤖 Starting Item Bot in DEBUG mode..."
else
    echo "🤖 Starting Item Bot..."
fi

# Check if Poetry is installed
if ! command -v poetry &> /dev/null; then
    echo "❌ Poetry is not installed. Please install Poetry first:"
    echo "   curl -sSL https://install.python-poetry.org | python3 -"
    exit 1
fi

# Check if dependencies are installed
if [ ! -d ".venv" ] && [ ! -f "poetry.lock" ]; then
    echo "📦 Installing dependencies..."
    poetry install
fi

# Check if config.py exists
if [ ! -f "config.py" ]; then
    echo "⚠️  config.py not found. Please copy config.py.example to config.py and configure it."
    echo "   cp config.py.example config.py"
    echo "   # Then edit config.py with your bot token and admin user IDs"
    exit 1
fi

# Run the bot
echo "🚀 Launching bot..."
if [ "$DEBUG_MODE" = true ]; then
    poetry run python bot.py --debug
else
    poetry run python bot.py
fi 