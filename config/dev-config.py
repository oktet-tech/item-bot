# Configuration for Dev Bot Instance
import os

# Telegram Bot Token (get from @BotFather)
BOT_TOKEN = os.getenv('DEV_BOT_TOKEN', 'your-dev-bot-token-here')

# Admin User IDs (get from @userinfobot)
ADMIN_USER_IDS = [
    int(os.getenv('DEV_ADMIN_1', '123456789')),
    int(os.getenv('DEV_ADMIN_2', '987654321')) if os.getenv('DEV_ADMIN_2') else None,
]
# Remove None values
ADMIN_USER_IDS = [uid for uid in ADMIN_USER_IDS if uid is not None]

# Database configuration
DATABASE_PATH = os.getenv('DATABASE_PATH', '/app/data/dev-resources.db')

# Logging configuration
LOG_LEVEL = os.getenv('LOG_LEVEL', 'DEBUG')  # More verbose for dev
LOG_FILE = os.getenv('LOG_FILE', '/app/logs/dev-bot.log')

# Instance-specific settings
BOT_NAME = os.getenv('BOT_NAME', 'dev-bot')
INSTANCE_ID = 'dev'
