# Configuration Guide

The bot supports two configuration methods that work together:

## Configuration Priority (Highest to Lowest)

1. **Environment Variables** (highest priority)
2. **Config file values** (fallback)

## Method 1: Environment Variables (Recommended for Production)

Create a `.env` file in your project root:

```bash
# Copy the example file
cp .env.example .env

# Edit with your values
nano .env
```

Example `.env` file:
```bash
# Company Bot
COMPANY_BOT_TOKEN=1234567890:ABCDEF...
COMPANY_ADMIN_1=123456789
COMPANY_ADMIN_2=987654321

# Dev Bot  
DEV_BOT_TOKEN=9876543210:ZYXWVU...
DEV_ADMIN_1=123456789

# QA Bot
QA_BOT_TOKEN=5555555555:QWERTY...
QA_ADMIN_1=123456789

# Global settings
LOG_LEVEL=INFO
```

## Method 2: Config Files (Good for Development)

Edit the config files directly:

```bash
# Edit each bot's config
nano config/company-config.py
nano config/dev-config.py  
nano config/qa-config.py
```

Example config file:
```python
# config/company-config.py
BOT_TOKEN = "1234567890:ABCDEF..."
ADMIN_USER_IDS = [123456789, 987654321]
DATABASE_PATH = "/app/data/company-resources.db"
LOG_LEVEL = "INFO"
```

## How They Work Together

Each config file uses `os.getenv()` to check environment variables first:

```python
# This line checks for COMPANY_BOT_TOKEN environment variable first
# If not found, uses the fallback value
BOT_TOKEN = os.getenv('COMPANY_BOT_TOKEN', 'your-fallback-token-here')

# For admin IDs, it converts env vars to integers
ADMIN_USER_IDS = [
    int(os.getenv('COMPANY_ADMIN_1', '123456789')),
    int(os.getenv('COMPANY_ADMIN_2', '987654321')) if os.getenv('COMPANY_ADMIN_2') else None,
]
```

## Docker Integration

In Docker deployment:

1. **docker-compose.yml** reads from `.env` file automatically
2. Environment variables are passed to containers  
3. Each container mounts its specific config file as `/app/config.py`
4. The bot code imports from `config.py` which uses `os.getenv()`

## Configuration Flow

```
.env file → Docker Compose → Container Environment → config.py → bot.py
```

## Examples

### Scenario 1: Using .env file (Production)
```bash
# .env file
COMPANY_BOT_TOKEN=real-token-123
COMPANY_ADMIN_1=123456789

# config/company-config.py
BOT_TOKEN = os.getenv('COMPANY_BOT_TOKEN', 'fallback-token')  # Uses real-token-123
```

### Scenario 2: No .env file (Development)
```bash
# No .env file

# config/company-config.py  
BOT_TOKEN = os.getenv('COMPANY_BOT_TOKEN', 'dev-token-456')  # Uses dev-token-456
```

### Scenario 3: Mixed approach
```bash
# .env file (only some variables)
COMPANY_BOT_TOKEN=prod-token-789

# config/company-config.py
BOT_TOKEN = os.getenv('COMPANY_BOT_TOKEN', 'fallback')     # Uses prod-token-789
LOG_LEVEL = os.getenv('LOG_LEVEL', 'DEBUG')               # Uses DEBUG (fallback)
```

## Best Practices

### For Production
- Use `.env` file for sensitive data (tokens, user IDs)
- Keep config files with sensible defaults
- Never commit `.env` files to git

### For Development  
- Use config files for quick testing
- Set different log levels per environment
- Use environment variables for secrets

### For Multiple Instances
- Each instance gets its own config file
- Use environment variable prefixes (COMPANY_, DEV_, QA_)
- Separate databases and log files per instance

## Security Notes

1. **Never commit tokens** to git repositories
2. **Use .env files** for production secrets
3. **Set proper file permissions** on config files:
   ```bash
   chmod 600 .env
   chmod 644 config/*.py
   ```

## Troubleshooting

### Bot not starting?
1. Check if config file exists and is readable
2. Verify BOT_TOKEN is set (either in env var or config file)
3. Check ADMIN_USER_IDS format (must be integers)

### Wrong configuration values?
1. Check environment variable names (case sensitive)
2. Verify .env file is in the correct location
3. Remember: environment variables override config file values

### Docker issues?
1. Verify .env file is in same directory as docker-compose.yml
2. Check container logs: `manage-bots logs company-bot`
3. Ensure config files are mounted correctly in docker-compose.yml
