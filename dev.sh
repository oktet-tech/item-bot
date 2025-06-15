#!/bin/bash

# Item Bot Development Script with Auto-restart

echo "🔧 Starting Item Bot in Development Mode..."

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

# Run the bot watcher for development
echo "🚀 Launching bot with auto-restart (development mode)..."
echo "📝 The bot will automatically restart when you modify bot.py"
echo "🛑 Press Ctrl+C to stop"
poetry run python bot_watcher.py 