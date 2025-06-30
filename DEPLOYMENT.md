# Item Bot Deployment Guide

This guide covers deploying the Item Bot on Debian-based systems with support for multiple bot instances.

## Overview

The deployment uses Docker containers to provide:
- Complete isolation between bot instances
- Easy scaling and management
- Consistent deployment across environments
- Built-in process management and health checks

## Prerequisites

- Debian-based Linux system (Ubuntu, Debian, etc.)
- Root or sudo access
- Internet connectivity for downloading dependencies

## Quick Start

1. **Clone the repository**
   ```bash
   git clone <your-repo-url>
   cd item-bot
   ```

2. **Make deployment script executable**
   ```bash
   chmod +x deploy.sh
   ```

3. **Run deployment script**
   ```bash
   sudo ./deploy.sh
   ```

4. **Configure bot tokens**
   ```bash
   sudo nano /opt/item-bot/config/company-config.py
   sudo nano /opt/item-bot/config/dev-config.py
   sudo nano /opt/item-bot/config/qa-config.py
   ```

5. **Start the bots**
   ```bash
   manage-bots start
   ```

## Configuration

### Bot Tokens

Each bot instance needs its own Telegram bot token:

1. Create bots via [@BotFather](https://t.me/BotFather)
2. Use `/newbot` command for each bot
3. Save the tokens in respective config files

### Admin Users

Get your Telegram user ID from [@userinfobot](https://t.me/userinfobot) and add to the `ADMIN_USER_IDS` list in each config file.

### Environment Variables

You can also use environment variables by copying `.env.example` to `.env`:

```bash
cp .env.example .env
# Edit .env with your values
```

## Management Commands

The deployment creates a `manage-bots` command for easy management:

### Basic Operations
```bash
manage-bots start      # Start all bot instances
manage-bots stop       # Stop all bot instances  
manage-bots restart    # Restart all bot instances
manage-bots status     # Show status of all instances
```

### Monitoring
```bash
manage-bots logs                 # Show logs from all bots
manage-bots logs company-bot     # Show logs from specific bot
manage-bots logs dev-bot         # Show logs from dev bot
```

### Maintenance
```bash
manage-bots build      # Rebuild Docker images
manage-bots update     # Update and rebuild (for code changes)
manage-bots backup     # Create backup of databases and configs
```

## Directory Structure

```
/opt/item-bot/
├── app/                    # Application code
│   ├── bot.py
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── ...
├── config/                 # Configuration files
│   ├── company-config.py
│   ├── dev-config.py
│   └── qa-config.py
├── data/                   # Persistent data (Docker volumes)
├── logs/                   # Log files
├── backups/               # Database backups
└── manage-bots.sh         # Management script
```

## Multiple Instances

The setup supports multiple bot instances by default:

### Adding New Instances

1. **Create new config file**
   ```bash
   sudo cp /opt/item-bot/config/company-config.py /opt/item-bot/config/newteam-config.py
   ```

2. **Edit the config with new bot token and settings**
   ```bash
   sudo nano /opt/item-bot/config/newteam-config.py
   ```

3. **Add service to docker-compose.yml**
   ```yaml
   newteam-bot:
     build: .
     container_name: item-bot-newteam
     restart: unless-stopped
     environment:
       - BOT_NAME=newteam-bot
       - DATABASE_PATH=/app/data/newteam-resources.db
       - LOG_FILE=/app/logs/newteam-bot.log
     volumes:
       - ./config/newteam-config.py:/app/config.py:ro
       - newteam-bot-data:/app/data
       - newteam-bot-logs:/app/logs
     networks:
       - bot-network
   ```

4. **Add corresponding volumes**
   ```yaml
   volumes:
     newteam-bot-data:
       driver: local
     newteam-bot-logs:
       driver: local
   ```

5. **Restart the deployment**
   ```bash
   manage-bots update
   ```

## Systemd Integration

The deployment creates a systemd service for automatic startup:

```bash
# Control via systemd
sudo systemctl start item-bot
sudo systemctl stop item-bot
sudo systemctl status item-bot

# Enable/disable auto-start
sudo systemctl enable item-bot
sudo systemctl disable item-bot
```

## Monitoring and Logs

### Log Files
- Application logs: `/opt/item-bot/logs/`
- Docker logs: `manage-bots logs [service]`
- System logs: `journalctl -u item-bot`

### Log Rotation
Logs are automatically rotated daily and kept for 30 days.

### Health Checks
Each container includes health checks that monitor database connectivity.

## Backup and Recovery

### Automatic Backups
```bash
manage-bots backup
```

This creates timestamped backups in `/opt/item-bot/backups/` containing:
- Database dumps (SQL format)
- Configuration files

### Manual Database Operations
```bash
# Access database directly
docker exec -it item-bot-company sqlite3 /app/data/company-resources.db

# Export database
docker exec item-bot-company sqlite3 /app/data/company-resources.db .dump > backup.sql

# Import database
cat backup.sql | docker exec -i item-bot-company sqlite3 /app/data/company-resources.db
```

## Security Considerations

1. **File Permissions**: All files are owned by the `item-bot` user
2. **Network Isolation**: Bots run in an isolated Docker network
3. **Non-root Containers**: Containers run as non-root user
4. **Config File Security**: Configuration files are read-only in containers

## Troubleshooting

### Common Issues

1. **Bots not starting**
   ```bash
   manage-bots logs
   # Check for configuration errors or missing tokens
   ```

2. **Permission errors**
   ```bash
   sudo chown -R item-bot:item-bot /opt/item-bot
   ```

3. **Database corruption**
   ```bash
   manage-bots stop
   # Remove corrupted database
   sudo rm /opt/item-bot/data/[instance]-resources.db
   manage-bots start
   ```

4. **Docker issues**
   ```bash
   # Restart Docker service
   sudo systemctl restart docker
   
   # Clean up Docker
   docker system prune -f
   ```

### Getting Help

Check logs in this order:
1. `manage-bots logs [service]` - Application logs
2. `manage-bots status` - Container status
3. `journalctl -u item-bot` - System service logs
4. `docker ps -a` - Container status

## Updating the Application

To update the bot code:

1. **Pull latest changes**
   ```bash
   cd /opt/item-bot/app
   sudo -u item-bot git pull
   ```

2. **Update deployment**
   ```bash
   manage-bots update
   ```

This will rebuild the containers with the new code and restart all services.

## Performance Tuning

For high-load deployments:

1. **Resource Limits**: Add resource limits to docker-compose.yml
2. **Database Optimization**: Consider PostgreSQL for high-traffic bots
3. **Load Balancing**: Use nginx for webhook-based deployments
4. **Monitoring**: Add Prometheus/Grafana for metrics

## Alternative Deployment Methods

While Docker is recommended, you can also deploy using:

### Systemd Services (Traditional)
Create individual systemd services for each bot instance.

### Process Managers
Use PM2 or Supervisor for process management.

### Virtual Environments
Deploy each bot in separate Python virtual environments.

See individual deployment scripts in the `deployment/` directory for these alternatives.
