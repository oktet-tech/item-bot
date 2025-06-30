#!/bin/bash

# Item Bot Deployment Script for Debian-based systems

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PROJECT_NAME="item-bot"
DEPLOYMENT_DIR="/opt/item-bot"
SERVICE_USER="item-bot"

print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_root() {
    if [[ $EUID -ne 0 ]]; then
        print_error "This script must be run as root (use sudo)"
        exit 1
    fi
}

install_dependencies() {
    print_status "Installing system dependencies..."
    
    # Update package list
    apt-get update
    
    # Install Docker if not present
    if ! command -v docker &> /dev/null; then
        print_status "Installing Docker..."
        curl -fsSL https://get.docker.com -o get-docker.sh
        sh get-docker.sh
        rm get-docker.sh
        systemctl enable docker
        systemctl start docker
    fi
    
    # Install Docker Compose if not present
    if ! command -v docker-compose &> /dev/null; then
        print_status "Installing Docker Compose..."
        curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
        chmod +x /usr/local/bin/docker-compose
    fi
    
    # Install additional utilities
    apt-get install -y git curl wget nano htop
}

create_user() {
    print_status "Creating service user..."
    
    if ! id "$SERVICE_USER" &>/dev/null; then
        useradd -r -s /bin/bash -d "$DEPLOYMENT_DIR" -m "$SERVICE_USER"
        usermod -aG docker "$SERVICE_USER"
        print_success "Created user: $SERVICE_USER"
    else
        print_warning "User $SERVICE_USER already exists"
    fi
}

setup_directories() {
    print_status "Setting up directory structure..."
    
    # Create main directory
    mkdir -p "$DEPLOYMENT_DIR"
    mkdir -p "$DEPLOYMENT_DIR/config"
    mkdir -p "$DEPLOYMENT_DIR/data"
    mkdir -p "$DEPLOYMENT_DIR/logs"
    mkdir -p "$DEPLOYMENT_DIR/backups"
    
    # Set ownership
    chown -R "$SERVICE_USER:$SERVICE_USER" "$DEPLOYMENT_DIR"
    
    print_success "Directory structure created"
}

copy_files() {
    print_status "Copying application files..."
    
    # Copy application files (assuming script is run from project directory)
    cp -r . "$DEPLOYMENT_DIR/app"
    
    # Remove unnecessary files
    rm -rf "$DEPLOYMENT_DIR/app/.git"
    rm -f "$DEPLOYMENT_DIR/app/config.py"
    
    # Set ownership
    chown -R "$SERVICE_USER:$SERVICE_USER" "$DEPLOYMENT_DIR/app"
    
    print_success "Application files copied"
}

create_management_scripts() {
    print_status "Creating management scripts..."
    
    # Bot management script
    cat > "$DEPLOYMENT_DIR/manage-bots.sh" << 'EOF'
#!/bin/bash

DEPLOYMENT_DIR="/opt/item-bot"
cd "$DEPLOYMENT_DIR/app"

case "$1" in
    start)
        echo "Starting all bot instances..."
        docker-compose up -d
        ;;
    stop)
        echo "Stopping all bot instances..."
        docker-compose down
        ;;
    restart)
        echo "Restarting all bot instances..."
        docker-compose restart
        ;;
    status)
        echo "Bot instances status:"
        docker-compose ps
        ;;
    logs)
        if [ -n "$2" ]; then
            docker-compose logs -f "$2"
        else
            docker-compose logs -f
        fi
        ;;
    build)
        echo "Building bot images..."
        docker-compose build
        ;;
    update)
        echo "Updating and rebuilding..."
        docker-compose down
        docker-compose build --no-cache
        docker-compose up -d
        ;;
    backup)
        BACKUP_DIR="$DEPLOYMENT_DIR/backups/$(date +%Y%m%d_%H%M%S)"
        mkdir -p "$BACKUP_DIR"
        echo "Creating backup in $BACKUP_DIR..."
        
        # Backup databases
        docker-compose exec -T company-bot sqlite3 /app/data/company-resources.db .dump > "$BACKUP_DIR/company-db.sql" 2>/dev/null || true
        docker-compose exec -T dev-bot sqlite3 /app/data/dev-resources.db .dump > "$BACKUP_DIR/dev-db.sql" 2>/dev/null || true
        docker-compose exec -T qa-bot sqlite3 /app/data/qa-resources.db .dump > "$BACKUP_DIR/qa-db.sql" 2>/dev/null || true
        
        # Backup configs
        cp -r "$DEPLOYMENT_DIR/config" "$BACKUP_DIR/"
        
        echo "Backup completed: $BACKUP_DIR"
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs [service]|build|update|backup}"
        echo ""
        echo "Services: company-bot, dev-bot, qa-bot"
        echo ""
        echo "Examples:"
        echo "  $0 start          # Start all bots"
        echo "  $0 logs dev-bot   # Show logs for dev-bot"
        echo "  $0 status         # Show status of all bots"
        echo "  $0 backup         # Create backup of all data"
        exit 1
        ;;
esac
EOF

    chmod +x "$DEPLOYMENT_DIR/manage-bots.sh"
    chown "$SERVICE_USER:$SERVICE_USER" "$DEPLOYMENT_DIR/manage-bots.sh"
    
    # Create symlink for easy access
    ln -sf "$DEPLOYMENT_DIR/manage-bots.sh" /usr/local/bin/manage-bots
    
    print_success "Management scripts created"
}

create_systemd_service() {
    print_status "Creating systemd service..."
    
    cat > /etc/systemd/system/item-bot.service << EOF
[Unit]
Description=Item Bot Multi-Instance Manager
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$DEPLOYMENT_DIR/app
ExecStart=/usr/local/bin/docker-compose up -d
ExecStop=/usr/local/bin/docker-compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable item-bot.service
    
    print_success "Systemd service created and enabled"
}

setup_logrotate() {
    print_status "Setting up log rotation..."
    
    cat > /etc/logrotate.d/item-bot << EOF
$DEPLOYMENT_DIR/logs/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    copytruncate
    su $SERVICE_USER $SERVICE_USER
}
EOF

    print_success "Log rotation configured"
}

print_completion_info() {
    print_success "Deployment completed successfully!"
    echo ""
    print_status "Next steps:"
    echo "1. Configure your bot tokens and admin IDs in:"
    echo "   - $DEPLOYMENT_DIR/config/company-config.py"
    echo "   - $DEPLOYMENT_DIR/config/dev-config.py"
    echo "   - $DEPLOYMENT_DIR/config/qa-config.py"
    echo ""
    echo "2. Start the bots:"
    echo "   manage-bots start"
    echo ""
    echo "3. Check status:"
    echo "   manage-bots status"
    echo ""
    echo "4. View logs:"
    echo "   manage-bots logs [service-name]"
    echo ""
    print_status "Available management commands:"
    echo "   manage-bots {start|stop|restart|status|logs|build|update|backup}"
    echo ""
    print_status "Systemd service:"
    echo "   systemctl {start|stop|status} item-bot"
}

main() {
    print_status "Starting Item Bot deployment..."
    
    check_root
    install_dependencies
    create_user
    setup_directories
    copy_files
    create_management_scripts
    create_systemd_service
    setup_logrotate
    
    print_completion_info
}

# Run main function
main "$@"
