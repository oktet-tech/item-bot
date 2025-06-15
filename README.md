# Item Bot

A Telegram bot for managing shared items (servers, devices, accounts, etc.)
in teams. Built with Python and the python-telegram-bot library.

## Key Features
- **SQLite database**: Lightweight, file-based storage
- **Auto-migration**: Database schema updates automatically
- **Permission system**: Admin > Moderator > User hierarchy
- **Conversation handlers**: Multi-step command workflows
- **Error handling**: Comprehensive logging and user feedback
- **Mobile-optimized**: HTML formatting for better mobile display

### Details

#### 🔧 User Features

- **List Items**: View all available items with status (✅ free, 📍 taken)
- **Take Items**: Reserve items with purpose tracking
- **Free Items**: Release items back to the pool
- **Steal Items**: Emergency takeover of items (with notifications)
- **Filtering**: Filter by group, type, or owner

#### 🛡️ Moderator Features

- **Item Management**: Add, delete, and assign items
- **Notification Management**: Subscribe to item type notifications
- **Inline Commands**: Quick item creation with command arguments

#### 👑 Admin Features

- **Type Management**: Create and manage item types
- **Moderator Management**: Add/remove moderators
- **Usage History**: Track all item actions
- **Database Management**: Export, import, and reset database
- **Batch Operations**: Import multiple commands from files or text

#### 🔔 Notification System

- **Type-specific notifications**: Subscribe to specific item types
- **Real-time alerts**: Get notified when items are taken, freed, or stolen
- **Group notifications**: Notify entire teams about resource changes

## Installation

### Prerequisites

- Python 3.8 or higher
- Poetry (for dependency management)
- A Telegram Bot Token (from @BotFather)

### Setup

1. **Clone the repository**

   ```bash
   git clone <repository-url>
   cd item-bot
   ```

2. **Install Poetry** (if not already installed)

You can use your package manager or install it manually:

   ```bash
   curl -sSL https://install.python-poetry.org | python3 -
   ```

3. **Install dependencies**

   ```bash
   poetry install
   ```

4. **Configure the bot**

   Copy the example configuration and edit it:
   
   ```bash
   cp config.py.example config.py
   # Edit config.py with your bot token and admin user IDs
   ```

   **Important**: The bot will not start without a valid `config.py` file!
   
   To get your Telegram user ID, message @userinfobot on Telegram.

5. **Run the bot**

   ```bash
   poetry run python bot.py
   ```

   Or use the Poetry script:

   ```bash
   poetry run bot
   ```

### Development Mode with Auto-restart

For development, you can use the bot watcher that automatically restarts the bot when files change:

```bash
poetry run bot-watcher
```

## Usage

See `/help full` for all available commands.

## Development

### Code Style

The project uses Black for code formatting and Flake8 for linting:

```bash
# Format code
poetry run black .

# Check linting
poetry run flake8 .
```

## Configuration

### Database Location
By default, the database is stored as `resources.db` in the current directory. You can change this in `config.py`:

```python
DATABASE_PATH = "custom_path/resources.db"
```

## Troubleshooting

### Common Issues

1. **Bot doesn't respond**
   - Check if the bot token is correct
   - Ensure the bot is started (@BotFather)
   - Check console for error messages

2. **Permission denied errors**
   - Verify your user ID is in ADMIN_USER_IDS
   - Check if you're added as a moderator for mod commands

3. **Database errors**
   - Ensure write permissions in the bot directory
   - Check if the database file is corrupted (delete and restart)

4. **Import/Export issues**
   - Ensure file encoding is UTF-8
   - Check command format matches expected syntax

### Logs
The bot logs important events to the console. For production, consider redirecting logs to a file:

```bash
poetry run bot 2>&1 | tee bot.log
```

## License

Apache 2.0

## Contributing

Issues and pull requests are welcome.

## Support

Bot authors are not responsible for any damage caused by the bot or any GDPR or
other personal data protection laws violations. You're on your own.
