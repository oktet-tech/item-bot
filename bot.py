#!/usr/bin/env python3
"""
Telegram Bot for Resource Allocation Management
"""

import sqlite3
import logging
from datetime import datetime
from typing import Optional, List, Dict, Tuple
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters
)

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration
BOT_TOKEN = "7636903842:AAFriRggH2EjFBz267cpiLBMrhciUawpqeM"
ADMIN_USER_IDS = [79700973]  # Replace with actual admin user IDs

# Conversation states
ADDING_ITEM = range(1)
EDITING_ITEM = range(1)
ADDING_TYPE = range(1)
TAKING_ITEM = range(1)
TAKING_PURPOSE = range(1)
STEALING_ITEM = range(1)

class ResourceBot:
    def __init__(self, db_path: str = "resources.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize SQLite database with required tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create types table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS types (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            )
        ''')
        
        # Create items table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                group_name TEXT DEFAULT 'default',
                type_id INTEGER,
                owner TEXT,
                purpose TEXT,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (type_id) REFERENCES types(id)
            )
        ''')
        
        # Create usage history table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS usage_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER,
                user TEXT,
                action TEXT,
                purpose TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (item_id) REFERENCES items(id)
            )
        ''')
        
        # Add purpose column if it doesn't exist (migration for existing databases)
        try:
            cursor.execute("ALTER TABLE items ADD COLUMN purpose TEXT")
        except sqlite3.OperationalError:
            # Column already exists, ignore
            pass
        
        conn.commit()
        conn.close()
    
    def get_connection(self):
        """Get database connection"""
        return sqlite3.connect(self.db_path)
    
    # Type management methods
    def add_type(self, type_name: str) -> bool:
        """Add a new item type"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("INSERT INTO types (name) VALUES (?)", (type_name,))
            conn.commit()
            conn.close()
            return True
        except sqlite3.IntegrityError:
            return False
    
    def list_types(self) -> List[Tuple[int, str]]:
        """List all item types"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM types ORDER BY name")
        types = cursor.fetchall()
        conn.close()
        return types
    
    def delete_type(self, type_id: int) -> Tuple[bool, str]:
        """Delete an item type if not in use"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Check if type is in use
        cursor.execute("SELECT COUNT(*) FROM items WHERE type_id = ?", (type_id,))
        count = cursor.fetchone()[0]
        
        if count > 0:
            conn.close()
            return False, f"Cannot delete: {count} items are using this type"
        
        cursor.execute("DELETE FROM types WHERE id = ?", (type_id,))
        conn.commit()
        conn.close()
        return True, "Type deleted successfully"
    
    # Item management methods
    def add_item(self, name: str, group: str, type_id: int, description: str) -> bool:
        """Add a new item"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO items (name, group_name, type_id, description) VALUES (?, ?, ?, ?)",
                (name, group, type_id, description)
            )
            conn.commit()
            conn.close()
            return True
        except sqlite3.IntegrityError:
            return False
    
    def edit_item(self, item_id: int, type_id: Optional[int] = None, 
                  group: Optional[str] = None) -> bool:
        """Edit an existing item"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        updates = []
        params = []
        
        if type_id is not None:
            updates.append("type_id = ?")
            params.append(type_id)
        
        if group is not None:
            updates.append("group_name = ?")
            params.append(group)
        
        if not updates:
            conn.close()
            return False
        
        params.append(item_id)
        query = f"UPDATE items SET {', '.join(updates)} WHERE id = ?"
        cursor.execute(query, params)
        conn.commit()
        success = cursor.rowcount > 0
        conn.close()
        return success
    
    def delete_item(self, item_id: int) -> bool:
        """Delete an item"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM items WHERE id = ?", (item_id,))
        conn.commit()
        success = cursor.rowcount > 0
        conn.close()
        return success
    
    def list_items(self, group: Optional[str] = None, type_id: Optional[int] = None,
                   owner: Optional[str] = None) -> List[Dict]:
        """List items with optional filters"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        query = '''
            SELECT i.id, i.name, i.group_name, t.name as type_name, 
                   i.owner, i.purpose, i.description
            FROM items i
            LEFT JOIN types t ON i.type_id = t.id
            WHERE 1=1
        '''
        params = []
        
        if group:
            query += " AND i.group_name = ?"
            params.append(group)
        
        if type_id:
            query += " AND i.type_id = ?"
            params.append(type_id)
        
        if owner:
            query += " AND i.owner = ?"
            params.append(owner)
        
        query += " ORDER BY i.group_name, i.name"
        
        cursor.execute(query, params)
        columns = [description[0] for description in cursor.description]
        items = []
        for row in cursor.fetchall():
            items.append(dict(zip(columns, row)))
        
        conn.close()
        return items
    
    def take_item(self, item_id: int, user: str, purpose: Optional[str] = None) -> Tuple[bool, str]:
        """Take a free item"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Check if item exists and is free
        cursor.execute("SELECT name, owner FROM items WHERE id = ?", (item_id,))
        result = cursor.fetchone()
        
        if not result:
            conn.close()
            return False, "Item not found"
        
        item_name, current_owner = result
        
        if current_owner:
            conn.close()
            return False, f"Item is already owned by {current_owner}"
        
        # Take the item
        cursor.execute("UPDATE items SET owner = ?, purpose = ? WHERE id = ?", (user, purpose, item_id))
        
        # Log the action
        cursor.execute(
            "INSERT INTO usage_history (item_id, user, action, purpose) VALUES (?, ?, ?, ?)",
            (item_id, user, 'take', purpose)
        )
        
        conn.commit()
        conn.close()
        return True, f"You have taken '{item_name}'"
    
    def free_item(self, item_id: int, user: str) -> Tuple[bool, str]:
        """Free an item owned by the user"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Check ownership
        cursor.execute("SELECT name, owner FROM items WHERE id = ?", (item_id,))
        result = cursor.fetchone()
        
        if not result:
            conn.close()
            return False, "Item not found"
        
        item_name, current_owner = result
        
        if current_owner != user:
            conn.close()
            return False, "You don't own this item"
        
        # Free the item
        cursor.execute("UPDATE items SET owner = NULL, purpose = NULL WHERE id = ?", (item_id,))
        
        # Log the action
        cursor.execute(
            "INSERT INTO usage_history (item_id, user, action) VALUES (?, ?, ?)",
            (item_id, user, 'free')
        )
        
        conn.commit()
        conn.close()
        return True, f"'{item_name}' is now free"
    
    def assign_item(self, item_id: int, to_user: str, by_user: str) -> Tuple[bool, str]:
        """Assign an item to a user (admin only)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Check if item exists
        cursor.execute("SELECT name, owner FROM items WHERE id = ?", (item_id,))
        result = cursor.fetchone()
        
        if not result:
            conn.close()
            return False, "Item not found"
        
        item_name, current_owner = result
        
        # Assign the item (clear purpose since it's admin assigned)
        cursor.execute("UPDATE items SET owner = ?, purpose = NULL WHERE id = ?", (to_user, item_id))
        
        # Log the action
        cursor.execute(
            "INSERT INTO usage_history (item_id, user, action, purpose) VALUES (?, ?, ?, ?)",
            (item_id, by_user, 'assign', f"assigned to {to_user}")
        )
        
        conn.commit()
        conn.close()
        return True, f"'{item_name}' assigned to {to_user}"
    
    def find_item_by_name_or_id(self, identifier: str) -> Optional[int]:
        """Find item ID by name or ID string"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Try as integer first (item ID)
        try:
            item_id = int(identifier)
            cursor.execute("SELECT id FROM items WHERE id = ?", (item_id,))
            result = cursor.fetchone()
            conn.close()
            return item_id if result else None
        except ValueError:
            # Try as string (item name)
            cursor.execute("SELECT id FROM items WHERE name = ?", (identifier,))
            result = cursor.fetchone()
            conn.close()
            return result[0] if result else None
    
    def steal_item(self, item_id: int, user: str, purpose: Optional[str] = None) -> Tuple[bool, str]:
        """Steal an item from another user"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Check if item exists and is owned
        cursor.execute("SELECT name, owner FROM items WHERE id = ?", (item_id,))
        result = cursor.fetchone()
        
        if not result:
            conn.close()
            return False, "Item not found"
        
        item_name, current_owner = result
        
        if not current_owner:
            conn.close()
            return False, "Item is not owned by anyone"
        
        if current_owner == user:
            conn.close()
            return False, "You already own this item"
        
        # Steal the item
        cursor.execute("UPDATE items SET owner = ?, purpose = ? WHERE id = ?", (user, purpose, item_id))
        
        # Log the action
        cursor.execute(
            "INSERT INTO usage_history (item_id, user, action, purpose) VALUES (?, ?, ?, ?)",
            (item_id, user, 'steal', f"from {current_owner}" + (f": {purpose}" if purpose else ""))
        )
        
        conn.commit()
        conn.close()
        return True, f"You have stolen '{item_name}' from {current_owner}"

# Bot instance
bot = ResourceBot()

# Helper functions
def is_admin(user_id: int) -> bool:
    """Check if user is admin"""
    return user_id in ADMIN_USER_IDS

def format_item_list(items: List[Dict]) -> str:
    """Format items list for display as HTML list"""
    if not items:
        return "No items found."
    
    # Group items by group_name for better organization
    groups = {}
    for item in items:
        group_name = item['group_name']
        if group_name not in groups:
            groups[group_name] = []
        groups[group_name].append(item)
    
    text = ""
    
    for group_name, group_items in groups.items():
        # Group header
        text += f"<b>📁 {group_name.upper()}</b>\n\n"
        
        for item in group_items:
            # Status bubble and owner
            if not item['owner']:
                bubble = '🟢'
                owner_text = '-'
            else:
                bubble = '🔴'
                owner_text = f"@{item['owner']}"
                if item['purpose'] and item['purpose'].strip():
                    owner_text += f": {item['purpose']}"
            
            # Main item line: - <bubble> item name #id: owner
            text += f"• {bubble} <b><code>{item['name']}</code></b> : {owner_text}\n"
            
            # Type and description on same line
            type_desc = f"{item['type_name'] or 'No type'}"
            if item['description']:
                type_desc += f" : {item['description']}"
            text += f"   • <i>{type_desc}</i>\n\n"
        
        text += "\n"
    
    return text

# Command handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /start is issued."""
    user = update.effective_user
    text = f"Hi {user.mention_html()}! I'm a resource allocation bot.\n\n"
    text += "Available commands:\n"
    text += "/help - Get detailed help with examples\n"
    text += "/list - List all items\n"
    text += "/take - Take a free item\n"
    text += "/free - Free an item you own\n"
    text += "/steal - Steal an item from someone\n"
    
    if is_admin(user.id):
        text += "\nAdmin commands:\n"
        text += "/additem - Add a new item\n"
        text += "/edititem - Edit an item\n"
        text += "/delitem - Delete an item\n"
        text += "/addtype - Add a new item type\n"
        text += "/listtypes - List all types\n"
        text += "/deltype - Delete a type\n"
        text += "/assign - Assign item to user\n"
    
    await update.message.reply_html(text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send detailed help with examples"""
    user = update.effective_user
    
    text = f"🤖 <b>Resource Allocation Bot Help</b>\n\n"
    text += "This bot helps manage shared resources (servers, devices, accounts, etc.) in your team.\n\n"
    
    text += "📋 <b>Item Lifecycle Example:</b>\n\n"
    text += "<b>1. Admin sets up item types:</b>\n"
    text += "<code>/addtype</code> → Enter: <code>Server</code>\n"
    text += "<code>/addtype</code> → Enter: <code>Test Device</code>\n\n"
    
    text += "<b>2. Admin adds items:</b>\n"
    text += "<code>/additem</code> → Enter: <code>ItemName | production | 1 | Main web server</code>\n"
    text += "<code>/additem</code> → Enter: <code>iPhone15 | testing | 2 | iOS testing device</code>\n\n"
    
    text += "<b>3. Users can see available items:</b>\n"
    text += "<code>/list</code> → Shows all items with their status (free/owned)\n"
    text += "<code>/list group production</code> → Shows only production items\n"
    text += "<code>/list owner alice</code> → Shows items owned by alice\n\n"
    
    text += "<b>4. Taking a free item:</b>\n"
    text += "<code>/take ItemName debugging issue</code> → Take with purpose immediately\n"
    text += "<code>/take ItemName</code> → Bot asks for purpose\n"
    text += "✅ Result: ItemName is now owned by you\n\n"
    
    text += "<b>5. Freeing your item:</b>\n"
    text += "<code>/free 1</code> → Releases ItemName back to free pool\n"
    text += "✅ Result: ItemName is now available for others\n\n"
    
    text += "<b>6. Stealing an item (when urgent):</b>\n"
    text += "<code>/steal</code> → Shows owned items → Enter: <code>2 critical production bug</code>\n"
    text += "⚠️ Result: You steal iPhone15 from current owner\n\n"
    
    text += "🔧 <b>User Commands:</b>\n"
    text += "<code>/list</code> - List all items (add filters: group, type, owner)\n"
    text += "<code>/take &lt;item_name&gt; [purpose]</code> - Take a free item\n"
    text += "<code>/free &lt;item_id&gt;</code> - Free an item you own\n"
    text += "<code>/steal</code> - Steal an item from someone (use responsibly!)\n\n"
    
    if is_admin(user.id):
        text += "👑 <b>Admin Commands:</b>\n"
        text += "<code>/addtype</code> - Add new item type (e.g., 'Server', 'Device')\n"
        text += "<code>/listtypes</code> - Show all available types\n"
        text += "<code>/deltype &lt;type_id&gt;</code> - Delete a type (if unused)\n\n"
        
        text += "<code>/additem</code> - Add new item (format: name | group | type_id_or_name | description)\n"
        text += "<code>/delitem &lt;item_id_or_name&gt;</code> - Delete an item\n"
        text += "<code>/assign &lt;item_id_or_name&gt; &lt;username&gt;</code> - Force assign item to user\n\n"
    
    text += "💡 <b>Tips:</b>\n"
    text += "• Always provide a purpose when taking/stealing items\n"
    text += "• Free items promptly when done\n"
    text += "• Use groups to organize items (production, testing, dev)\n"
    text += "• Stealing should be used only for urgent situations\n"
    text += "• Check <code>/list owner yourusername</code> to see your items\n\n"
    
    text += "❓ <b>Need help?</b> Contact an admin or use <code>/start</code> for quick command list."
    
    await update.message.reply_html(text)

async def list_items_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all items with optional filters"""
    # Parse filters from command arguments
    args = context.args
    group = None
    type_name = None
    owner = None
    
    # Simple argument parsing (could be improved)
    for i, arg in enumerate(args):
        if arg == "group" and i + 1 < len(args):
            group = args[i + 1]
        elif arg == "type" and i + 1 < len(args):
            type_name = args[i + 1]
        elif arg == "owner" and i + 1 < len(args):
            owner = args[i + 1]
    
    # Get type_id from type_name if provided
    type_id = None
    if type_name:
        types = bot.list_types()
        for t_id, t_name in types:
            if t_name.lower() == type_name.lower():
                type_id = t_id
                break
    
    items = bot.list_items(group=group, type_id=type_id, owner=owner)
    
    # Add header with filter info
    header = "📋 <b>Item List</b>\n\n"
    if group or type_name or owner:
        filters = []
        if group:
            filters.append(f"Group: <code>{group}</code>")
        if type_name:
            filters.append(f"Type: <code>{type_name}</code>")
        if owner:
            filters.append(f"Owner: <code>{owner}</code>")
        header += f"🔍 Filters: {' | '.join(filters)}\n\n"
    
    text = header + format_item_list(items)
    
    await update.message.reply_html(text)

# Admin command handlers
async def add_item_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start adding a new item"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("You don't have permission to use this command.")
        return ConversationHandler.END
    
    types = bot.list_types()
    if not types:
        await update.message.reply_text("No types available. Please add types first using /addtype")
        return ConversationHandler.END
    
    # Store types in context for later use
    context.user_data['types'] = types
    
    await update.message.reply_text(
        "Let's add a new item. Please send the details in this format:\n"
        "name | group | type_id | description\n\n"
        "Available types:\n" + 
        "\n".join([f"{t_id}: {t_name}" for t_id, t_name in types]) +
        "\n\nExample: Server1 | production | 1 | Main production server"
    )
    
    return ADDING_ITEM

async def add_item_finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Finish adding a new item"""
    text = update.message.text.strip()
    parts = [p.strip() for p in text.split('|')]
    
    if len(parts) != 4:
        await update.message.reply_text(
            "Invalid format. Please use: name | group | type_id_or_name | description"
        )
        return ADDING_ITEM
    
    name, group, type_id_str, description = parts
    
    # Try to parse as integer first, then as string (type name)
    type_id = None
    types = context.user_data.get('types', [])
    
    try:
        # Try as integer (type ID)
        type_id = int(type_id_str)
        if not any(t[0] == type_id for t in types):
            await update.message.reply_text(f"Invalid type ID: {type_id}")
            return ADDING_ITEM
    except ValueError:
        # Try as string (type name)
        type_name_lower = type_id_str.lower()
        for t_id, t_name in types:
            if t_name.lower() == type_name_lower:
                type_id = t_id
                break
        
        if type_id is None:
            await update.message.reply_text(f"Invalid type name: '{type_id_str}'. Use type ID or exact type name.")
            return ADDING_ITEM
    
    success = bot.add_item(name, group, type_id, description)
    
    if success:
        await update.message.reply_text(f"Item '{name}' added successfully!")
    else:
        await update.message.reply_text("Failed to add item. Name might already exist.")
    
    return ConversationHandler.END

async def add_type_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start adding a new type"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("You don't have permission to use this command.")
        return ConversationHandler.END
    
    await update.message.reply_text("Please enter the name for the new type:")
    return ADDING_TYPE

async def add_type_finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Finish adding a new type"""
    type_name = update.message.text.strip()
    
    success = bot.add_type(type_name)
    
    if success:
        await update.message.reply_text(f"Type '{type_name}' added successfully!")
    else:
        await update.message.reply_text("Failed to add type. Name might already exist.")
    
    return ConversationHandler.END

async def list_types_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all types"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("You don't have permission to use this command.")
        return
    
    types = bot.list_types()
    
    if not types:
        await update.message.reply_text("No types available.")
        return
    
    text = "Available types:\n"
    for type_id, type_name in types:
        text += f"• {type_id}: {type_name}\n"
    
    await update.message.reply_text(text)

async def delete_type_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Delete a type"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("You don't have permission to use this command.")
        return
    
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /deltype <type_id>")
        return
    
    type_id = int(context.args[0])
    success, message = bot.delete_type(type_id)
    
    await update.message.reply_text(message)

async def delete_item_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Delete an item"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("You don't have permission to use this command.")
        return
    
    if not context.args:
        await update.message.reply_text("Usage: /delitem <item_id_or_name>")
        return
    
    # Find item by name or ID
    item_id = bot.find_item_by_name_or_id(context.args[0])
    if item_id is None:
        await update.message.reply_text("Item not found. Please enter a valid item ID or name.")
        return
    
    success = bot.delete_item(item_id)
    
    if success:
        await update.message.reply_text("Item deleted successfully!")
    else:
        await update.message.reply_text("Failed to delete item. Item might not exist.")

# User command handlers
async def take_item_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Take an item with new syntax: /take <item_name> [purpose]"""
    args = context.args
    
    # If no arguments, show available items (old behavior)
    if not args:
        return await take_item_start(update, context)
    
    # Get item name (first argument)
    item_identifier = args[0]
    
    # Find item by name or ID
    item_id = bot.find_item_by_name_or_id(item_identifier)
    if item_id is None:
        await update.message.reply_text(f"Item '{item_identifier}' not found.")
        return ConversationHandler.END
    
    # Check if item is available
    items = bot.list_items()
    item = next((i for i in items if i['id'] == item_id), None)
    if not item:
        await update.message.reply_text("Item not found.")
        return ConversationHandler.END
    
    if item['owner']:
        await update.message.reply_text(f"Item '{item['name']}' is already owned by @{item['owner']}.")
        return ConversationHandler.END
    
    # If purpose provided, take immediately
    if len(args) > 1:
        purpose = ' '.join(args[1:])
        user = update.effective_user.username or str(update.effective_user.id)
        success, message = bot.take_item(item_id, user, purpose)
        await update.message.reply_text(message)
        return ConversationHandler.END
    
    # If no purpose, ask for it
    context.user_data['take_item_id'] = item_id
    context.user_data['take_item_name'] = item['name']
    await update.message.reply_text(f"What is the purpose for taking <b>{item['name']}</b>?", parse_mode='HTML')
    return TAKING_PURPOSE

async def take_purpose_finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Finish taking item after purpose is provided"""
    purpose = update.message.text.strip()
    item_id = context.user_data.get('take_item_id')
    item_name = context.user_data.get('take_item_name')
    
    if not item_id:
        await update.message.reply_text("Error: Lost track of which item you wanted to take.")
        return ConversationHandler.END
    
    user = update.effective_user.username or str(update.effective_user.id)
    success, message = bot.take_item(item_id, user, purpose)
    await update.message.reply_text(message)
    
    # Clean up context data
    context.user_data.pop('take_item_id', None)
    context.user_data.pop('take_item_name', None)
    
    return ConversationHandler.END

async def take_item_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start taking an item"""
    # Show available free items
    items = bot.list_items(owner=None)
    
    if not items:
        await update.message.reply_text('No free items available.')
        return ConversationHandler.END
    
    text = "<b>Available Free Items:</b>\n\n" + format_item_list(items)
    text += "\nPlease enter the item ID or name you want to take, optionally with purpose:\n"
    text += "Format: <code>&lt;item_id_or_name&gt; [purpose]</code>\n"
    text += "Examples: <code>5 for testing</code> or <code>ItemName debugging</code>"
    
    await update.message.reply_html(text)
    return TAKING_ITEM
async def take_item_finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Finish taking an item"""
    text = update.message.text.strip()
    parts = text.split(' ', 1)
    
    # Find item by name or ID
    item_id = bot.find_item_by_name_or_id(parts[0])
    if item_id is None:
        await update.message.reply_text("Item not found. Please enter a valid item ID or name.")
        return TAKING_ITEM
    
    purpose = parts[1] if len(parts) > 1 else None
    user = update.effective_user.username or str(update.effective_user.id)
    
    success, message = bot.take_item(item_id, user, purpose)
    await update.message.reply_text(message)
    
    return ConversationHandler.END

async def free_item_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Free an item owned by the user"""
    user = update.effective_user.username or str(update.effective_user.id)
    
    if not context.args:
        # Show user's items
        items = bot.list_items(owner=user)
        if not items:
            await update.message.reply_text("You don't own any items.")
            return
        
        text = "<b>Your Items:</b>\n\n" + format_item_list(items)
        text += "\n<b>Usage:</b> <code>/free &lt;item_id_or_name&gt;</code>"
        await update.message.reply_html(text)
        return
    
    # Find item by name or ID
    item_id = bot.find_item_by_name_or_id(context.args[0])
    if item_id is None:
        await update.message.reply_text("Item not found. Please enter a valid item ID or name.")
        return
    success, message = bot.free_item(item_id, user)
    await update.message.reply_text(message)

async def steal_item_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start stealing an item"""
    user = update.effective_user.username or str(update.effective_user.id)
    
    # Show all owned items except user's own
    items = [item for item in bot.list_items() if item['owner'] and item['owner'] != user]
    
    if not items:
        await update.message.reply_text("No items available to steal.")
        return ConversationHandler.END
    
    text = "<b>Items You Can Steal:</b>\n\n" + format_item_list(items)
    text += "\nPlease enter the item ID or name you want to steal, optionally with purpose:\n"
    text += "Format: <code>&lt;item_id_or_name&gt; [purpose]</code>\n"
    text += "Examples: <code>5 urgent issue</code> or <code>iPhone15 critical bug</code>"
    
    await update.message.reply_html(text)
    return STEALING_ITEM

async def steal_item_finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Finish stealing an item"""
    text = update.message.text.strip()
    parts = text.split(' ', 1)
    
    # Find item by name or ID
    item_id = bot.find_item_by_name_or_id(parts[0])
    if item_id is None:
        await update.message.reply_text("Item not found. Please enter a valid item ID or name.")
        return STEALING_ITEM
    
    purpose = parts[1] if len(parts) > 1 else None
    user = update.effective_user.username or str(update.effective_user.id)
    
    success, message = bot.steal_item(item_id, user, purpose)
    await update.message.reply_text(message)
    
    return ConversationHandler.END

async def assign_item_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Assign an item to a user (admin only)"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("You don't have permission to use this command.")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /assign <item_id_or_name> <username>")
        return
    
    # Find item by name or ID
    item_id = bot.find_item_by_name_or_id(context.args[0])
    if item_id is None:
        await update.message.reply_text("Item not found. Please enter a valid item ID or name.")
        return
    
    to_user = context.args[1]
    by_user = update.effective_user.username or str(update.effective_user.id)
    
    success, message = bot.assign_item(item_id, to_user, by_user)
    await update.message.reply_text(message)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel the current operation"""
    await update.message.reply_text("Operation cancelled.")
    return ConversationHandler.END

def main():
    """Start the bot"""
    # Create the Application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Conversation handlers
    add_item_handler = ConversationHandler(
        entry_points=[CommandHandler("additem", add_item_start)],
        states={
            ADDING_ITEM: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_item_finish)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    add_type_handler = ConversationHandler(
        entry_points=[CommandHandler("addtype", add_type_start)],
        states={
            ADDING_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_type_finish)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    take_item_handler = ConversationHandler(
        entry_points=[CommandHandler("take", take_item_command)],
        states={
            TAKING_ITEM: [MessageHandler(filters.TEXT & ~filters.COMMAND, take_item_finish)],
            TAKING_PURPOSE: [MessageHandler(filters.TEXT & ~filters.COMMAND, take_purpose_finish)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    steal_item_handler = ConversationHandler(
        entry_points=[CommandHandler("steal", steal_item_start)],
        states={
            STEALING_ITEM: [MessageHandler(filters.TEXT & ~filters.COMMAND, steal_item_finish)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    # Register handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("list", list_items_command))
    application.add_handler(add_item_handler)
    application.add_handler(add_type_handler)
    application.add_handler(CommandHandler("listtypes", list_types_command))
    application.add_handler(CommandHandler("deltype", delete_type_command))
    application.add_handler(CommandHandler("delitem", delete_item_command))
    application.add_handler(take_item_handler)
    application.add_handler(CommandHandler("free", free_item_command))
    application.add_handler(steal_item_handler)
    application.add_handler(CommandHandler("assign", assign_item_command))
    
    # Run the bot
    application.run_polling()

if __name__ == '__main__':
    main()