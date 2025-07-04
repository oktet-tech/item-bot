#!/usr/bin/env python3
"""
Telegram Bot for Resource Allocation Management
"""

import sqlite3
import logging
import sys
import argparse
from datetime import datetime
from typing import Optional, List, Dict, Tuple
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# Try to import configuration
try:
    from config import BOT_TOKEN, ADMIN_USER_IDS

    # Optional config imports with defaults
    try:
        from config import DATABASE_PATH
    except ImportError:
        DATABASE_PATH = "resources.db"

    try:
        from config import LOG_LEVEL
    except ImportError:
        LOG_LEVEL = "INFO"

    try:
        from config import LOG_FILE
    except ImportError:
        LOG_FILE = None

except ImportError:
    print("❌ Error: config.py not found!")
    print("Please copy config.py.example to config.py and configure it:")
    print("  cp config.py.example config.py")
    print("  # Then edit config.py with your bot token and admin user IDs")
    sys.exit(1)


# Configure logging
log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
log_level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)

if LOG_FILE:
    logging.basicConfig(
        format=log_format,
        level=log_level,
        handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
    )
else:
    logging.basicConfig(format=log_format, level=log_level)

logger = logging.getLogger(__name__)

# Conversation states
(
    ADDING_ITEM,
    EDITING_ITEM,
    ADDING_TYPE,
    TAKING_ITEM,
    TAKING_PURPOSE,
    STEALING_ITEM,
    BATCH_PROCESSING,
    BATCH_CONFIRMING,
) = range(8)


class ResourceBot:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or DATABASE_PATH
        self.init_database()

    def init_database(self):
        """Initialize SQLite database with required tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Create types table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS types (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            )
        """
        )

        # Create items table
        cursor.execute(
            """
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
        """
        )

        # Create usage history table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS usage_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER,
                user TEXT,
                action TEXT,
                purpose TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (item_id) REFERENCES items(id)
            )
        """
        )

        # Create moderators table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS moderators (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                added_by TEXT,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Create notifications table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                chat_title TEXT,
                type_id INTEGER,
                added_by TEXT,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (type_id) REFERENCES types(id),
                UNIQUE(chat_id, type_id)
            )
        """
        )

        # Create authorized users table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS authorized_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                added_by TEXT,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Add purpose column if it doesn't exist (migration for existing databases)
        try:
            cursor.execute("ALTER TABLE items ADD COLUMN purpose TEXT")
        except sqlite3.OperationalError:
            # Column already exists, ignore
            pass

        # Add note column if it doesn't exist (migration for existing databases)
        try:
            cursor.execute("ALTER TABLE items ADD COLUMN note TEXT")
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
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()

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
                (name, group, type_id, description),
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()

    def edit_item(self, item_id: int, type_id: Optional[int] = None, group: Optional[str] = None) -> bool:
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

    def edit_item_description(self, item_id: int, description: str) -> Tuple[bool, str]:
        """Edit item description"""
        conn = self.get_connection()
        cursor = conn.cursor()

        # Check if item exists
        cursor.execute("SELECT name FROM items WHERE id = ?", (item_id,))
        result = cursor.fetchone()

        if not result:
            conn.close()
            return False, "Item not found"

        item_name = result[0]

        # Update description
        cursor.execute("UPDATE items SET description = ? WHERE id = ?", (description, item_id))
        conn.commit()
        conn.close()
        return True, f"Description updated for '{item_name}'"

    def set_item_note(self, item_id: int, note: str) -> Tuple[bool, str]:
        """Set or update item note"""
        conn = self.get_connection()
        cursor = conn.cursor()

        # Check if item exists
        cursor.execute("SELECT name FROM items WHERE id = ?", (item_id,))
        result = cursor.fetchone()

        if not result:
            conn.close()
            return False, "Item not found"

        item_name = result[0]

        # Update note
        cursor.execute("UPDATE items SET note = ? WHERE id = ?", (note, item_id))
        conn.commit()
        conn.close()
        return True, f"Note set for '{item_name}'"

    def drop_item_note(self, item_id: int) -> Tuple[bool, str]:
        """Remove item note"""
        conn = self.get_connection()
        cursor = conn.cursor()

        # Check if item exists
        cursor.execute("SELECT name FROM items WHERE id = ?", (item_id,))
        result = cursor.fetchone()

        if not result:
            conn.close()
            return False, "Item not found"

        item_name = result[0]

        # Remove note
        cursor.execute("UPDATE items SET note = NULL WHERE id = ?", (item_id,))
        conn.commit()
        conn.close()
        return True, f"Note removed from '{item_name}'"

    def delete_item(self, item_id: int) -> bool:
        """Delete an item"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM items WHERE id = ?", (item_id,))
        conn.commit()
        success = cursor.rowcount > 0
        conn.close()
        return success

    def list_items(
        self,
        group: Optional[str] = None,
        type_id: Optional[int] = None,
        owner: Optional[str] = None,
        free_only: bool = False,
    ) -> List[Dict]:
        """List items with optional filters

        Args:
            group: Filter by group name
            type_id: Filter by type ID
            owner: Filter by owner username (None means no filter)
            free_only: If True, only show items with no owner
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        query = """
            SELECT i.id, i.name, i.group_name, i.type_id, t.name as type_name,
                   i.owner, i.purpose, i.description, i.note
            FROM items i
            LEFT JOIN types t ON i.type_id = t.id
            WHERE 1=1
        """
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
        elif free_only:
            query += " AND i.owner IS NULL"

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
        cursor.execute(
            "UPDATE items SET owner = ?, purpose = ? WHERE id = ?",
            (user, purpose, item_id),
        )

        # Log the action
        cursor.execute(
            "INSERT INTO usage_history (item_id, user, action, purpose) VALUES (?, ?, ?, ?)",
            (item_id, user, "take", purpose),
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
            (item_id, user, "free"),
        )

        conn.commit()
        conn.close()
        return True, f"'{item_name}' is now free"

    def purge_item(self, item_id: int, moderator: str) -> Tuple[bool, str]:
        """Force-free an item (moderator only)"""
        conn = self.get_connection()
        cursor = conn.cursor()

        # Check if item exists
        cursor.execute("SELECT name, owner FROM items WHERE id = ?", (item_id,))
        result = cursor.fetchone()

        if not result:
            conn.close()
            return False, "Item not found"

        item_name, current_owner = result

        if not current_owner:
            conn.close()
            return False, f"'{item_name}' is already free"

        # Force-free the item
        cursor.execute("UPDATE items SET owner = NULL, purpose = NULL WHERE id = ?", (item_id,))

        # Log the action
        cursor.execute(
            "INSERT INTO usage_history (item_id, user, action, purpose) VALUES (?, ?, ?, ?)",
            (item_id, moderator, "purge", f"force-freed from {current_owner}"),
        )

        conn.commit()
        conn.close()
        return True, f"'{item_name}' force-freed from {current_owner}"

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
        cursor.execute(
            "UPDATE items SET owner = ?, purpose = NULL WHERE id = ?",
            (to_user, item_id),
        )

        # Log the action
        cursor.execute(
            "INSERT INTO usage_history (item_id, user, action, purpose) VALUES (?, ?, ?, ?)",
            (item_id, by_user, "assign", f"assigned to {to_user}"),
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
        cursor.execute(
            "UPDATE items SET owner = ?, purpose = ? WHERE id = ?",
            (user, purpose, item_id),
        )

        # Log the action
        cursor.execute(
            "INSERT INTO usage_history (item_id, user, action, purpose) VALUES (?, ?, ?, ?)",
            (
                item_id,
                user,
                "steal",
                f"from {current_owner}" + (f": {purpose}" if purpose else ""),
            ),
        )

        conn.commit()
        conn.close()
        return True, f"You have stolen '{item_name}' from {current_owner}"

    # Moderator management methods
    def add_moderator(self, username: str, added_by: str) -> bool:
        """Add a moderator"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO moderators (username, added_by) VALUES (?, ?)",
                (username, added_by),
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()

    def remove_moderator(self, username: str) -> bool:
        """Remove a moderator"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM moderators WHERE username = ?", (username,))
        success = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return success

    def list_moderators(self) -> List[Tuple[str, str, str]]:
        """List all moderators"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT username, added_by, added_at FROM moderators ORDER BY added_at")
        moderators = cursor.fetchall()
        conn.close()
        return moderators

    def is_moderator(self, username: str) -> bool:
        """Check if user is a moderator"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM moderators WHERE username = ?", (username,))
        result = cursor.fetchone()
        conn.close()
        return result is not None

    # Notification management methods
    def add_notification(self, chat_id: int, chat_title: str, type_id: Optional[int], added_by: str) -> bool:
        """Add a notification subscription"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO notifications (chat_id, chat_title, type_id, added_by) VALUES (?, ?, ?, ?)",
                (chat_id, chat_title, type_id, added_by),
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()

    def remove_notification(self, chat_id: int, type_id: Optional[int] = None) -> int:
        """Remove notification subscription(s). Returns number of removed records"""
        conn = self.get_connection()
        cursor = conn.cursor()

        if type_id is None:
            # Remove all notifications for this chat
            cursor.execute("DELETE FROM notifications WHERE chat_id = ?", (chat_id,))
        else:
            # Remove specific type notification for this chat
            cursor.execute(
                "DELETE FROM notifications WHERE chat_id = ? AND type_id = ?",
                (chat_id, type_id),
            )

        removed_count = cursor.rowcount
        conn.commit()
        conn.close()
        return removed_count

    def list_notifications(
        self,
    ) -> List[Tuple[int, str, Optional[int], Optional[str], str, str]]:
        """List all notification subscriptions"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT n.chat_id, n.chat_title, n.type_id, t.name as type_name, n.added_by, n.added_at
            FROM notifications n
            LEFT JOIN types t ON n.type_id = t.id
            ORDER BY n.chat_title, t.name
        """
        )
        notifications = cursor.fetchall()
        conn.close()
        return notifications

    def get_notification_chats_for_type(self, type_id: int) -> List[Tuple[int, str]]:
        """Get all chats that should be notified for a specific item type"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT DISTINCT chat_id, chat_title
            FROM notifications
            WHERE type_id = ? OR type_id IS NULL
        """,
            (type_id,),
        )
        chats = cursor.fetchall()
        conn.close()
        return chats

    # Authorized users management methods
    def add_authorized_user(self, user_id: int = None, username: str = None, added_by: str = None) -> bool:
        """Add an authorized user by user_id or username"""
        if not user_id and not username:
            return False

        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            # If we have user_id, use it directly
            if user_id:
                cursor.execute(
                    "INSERT INTO authorized_users (user_id, username, added_by) VALUES (?, ?, ?)",
                    (user_id, username, added_by),
                )
            else:
                # Check if username already exists
                cursor.execute(
                    "SELECT 1 FROM authorized_users WHERE username = ? COLLATE NOCASE",
                    (username,),
                )
                if cursor.fetchone():
                    return False  # Username already exists

                # Generate a unique negative user_id for username-only entries
                cursor.execute("SELECT MIN(user_id) FROM authorized_users WHERE user_id < 0")
                min_id = cursor.fetchone()[0]
                placeholder_id = (min_id - 1) if min_id else -1

                cursor.execute(
                    "INSERT INTO authorized_users (user_id, username, added_by) VALUES (?, ?, ?)",
                    (placeholder_id, username, added_by),
                )

            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()

    def remove_authorized_user(self, user_id: int = None, username: str = None) -> bool:
        """Remove an authorized user by user_id or username"""
        if not user_id and not username:
            return False

        conn = self.get_connection()
        cursor = conn.cursor()

        if user_id:
            cursor.execute("DELETE FROM authorized_users WHERE user_id = ?", (user_id,))
        else:
            cursor.execute(
                "DELETE FROM authorized_users WHERE username = ? COLLATE NOCASE",
                (username,),
            )

        success = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return success

    def list_authorized_users(self) -> List[Tuple[int, str, str, str]]:
        """List all authorized users"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, username, added_by, added_at FROM authorized_users ORDER BY added_at")
        users = cursor.fetchall()
        conn.close()
        return users

    def is_authorized_user(self, user_id: int, username: str = None) -> bool:
        """Check if user is authorized by user_id or username"""
        conn = self.get_connection()
        cursor = conn.cursor()

        # Check by user_id first
        cursor.execute("SELECT 1 FROM authorized_users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()

        # If not found by user_id and we have a username, check by username
        if not result and username:
            cursor.execute(
                "SELECT 1 FROM authorized_users WHERE username = ? COLLATE NOCASE",
                (username,),
            )
            result = cursor.fetchone()

            # If found by username, update the record with the actual user_id
            if result:
                cursor.execute(
                    "UPDATE authorized_users SET user_id = ? WHERE username = ? COLLATE NOCASE AND user_id < 0",
                    (user_id, username),
                )
                conn.commit()

        conn.close()
        return result is not None


# Bot instance
bot = ResourceBot()


# Notification functions
async def send_notification_to_chats(application, chats: List[Tuple[int, str]], message: str):
    """Send notification message to multiple chats"""
    for chat_id, chat_title in chats:
        try:
            await application.bot.send_message(chat_id=chat_id, text=message, parse_mode="HTML")
            logger.info(f"Sent notification to '{chat_title}' ({chat_id})")
        except Exception as e:
            logger.error(f"Failed to send notification to '{chat_title}' ({chat_id}): {e}")


async def notify_item_action(
    application,
    item_name: str,
    item_type_id: int,
    action: str,
    user: str,
    purpose: str = None,
    from_user: str = None,
):
    """Send notification when an item action occurs"""
    chats = bot.get_notification_chats_for_type(item_type_id)
    if not chats:
        return

    # Create appropriate message based on action
    if action == "take":
        emoji = "📍"
        purpose_text = f" for <i>{purpose}</i>" if purpose else ""
        message = f"{emoji} <b>{item_name}</b> taken by {user}{purpose_text}"
    elif action == "free":
        emoji = "✅"
        message = f"{emoji} <b>{item_name}</b> freed by {user}"
    elif action == "steal":
        emoji = "⚠️"
        purpose_text = f" for <i>{purpose}</i>" if purpose else ""
        message = f"{emoji} <b>{item_name}</b> stolen by {user} from @{from_user}{purpose_text}"
    elif action == "assign":
        emoji = "👑"
        message = (
            f"{emoji} <b>{item_name}</b> assigned to @{purpose} by @{user}"  # purpose contains target user for assign
        )
    elif action == "purge":
        emoji = "🧹"
        message = f"{emoji} <b>{item_name}</b> force-freed by moderator @{user} from @{from_user}"
    else:
        return

    await send_notification_to_chats(application, chats, message)


# Helper functions
def is_admin(user_id: int) -> bool:
    """Check if user is admin"""
    return user_id in ADMIN_USER_IDS


def is_moderator_or_admin(user_id: int, username: str) -> bool:
    """Check if user is moderator or admin"""
    if is_admin(user_id):
        return True
    if username:
        return bot.is_moderator(username)
    return False


def is_user_authorized(user_id: int, username: str) -> bool:
    """Check if user is authorized to use the bot (admin, moderator, or whitelisted)"""
    # Admins and moderators are always authorized
    if is_moderator_or_admin(user_id, username):
        return True
    # Check if user is in authorized users list
    return bot.is_authorized_user(user_id, username)


def require_authorization(func):
    """Decorator to require user authorization for command handlers"""

    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if not is_user_authorized(user.id, user.username):
            await update.message.reply_text(
                "❌ You are not authorized to use this bot. Please contact an administrator."
            )
            return
        return await func(update, context)

    return wrapper


def log_command(func):
    """Decorator to log all command usage"""
    
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            # Safely extract information with fallbacks
            user = update.effective_user
            user_info = f"{user.username or 'No username'} (ID: {user.id})" if user else "Unknown user"
            
            command = update.message.text.strip() if update.message and update.message.text else "No text"
            
            chat = update.effective_chat
            if chat:
                chat_type = chat.type
                chat_id = chat.id
                chat_title = getattr(chat, 'title', 'Private Chat')
            else:
                chat_type = 'unknown'
                chat_id = 'unknown'
                chat_title = 'Unknown'
            
            # Log command details
            logger.info(
                f"COMMAND: {command} | "
                f"User: {user_info} | "
                f"Chat: {chat_title} ({chat_type}, ID: {chat_id})"
            )
            
        except Exception as e:
            # Log the error but don't prevent command execution
            logger.error(f"Error in log_command decorator: {e}")
            logger.info(f"COMMAND: {update.message.text if update.message and update.message.text else 'Unknown'} | User: Unknown | Chat: Unknown")
        
        return await func(update, context)
    
    return wrapper


def format_item_list(items: List[Dict]) -> str:
    """Format items list for display as HTML list"""
    if not items:
        return "No items found."

    # Group items by group_name for better organization
    groups = {}
    for item in items:
        group_name = item["group_name"]
        if group_name not in groups:
            groups[group_name] = []
        groups[group_name].append(item)

    text = ""

    for group_name, group_items in groups.items():
        # Group header
        text += f"<b>📁 {group_name.upper()}</b>\n\n"

        for item in group_items:
            # Status icon and owner
            if not item["owner"]:
                icon = "✅"  # Free (same as free action)
                owner_text = "-"
            else:
                icon = "📍"  # Taken (same as take action)
                owner_text = f"{item['owner']}"
                if item["purpose"] and item["purpose"].strip():
                    owner_text += f": {item['purpose']}"

            # Main item line: - <icon> item name #id: owner
            text += f"• {icon} <b><code>{item['name']}</code></b> : {owner_text}\n"

            # Type and description on same line
            type_desc = f"{item['type_name'] or 'No type'}"
            if item["description"]:
                type_desc += f" : {item['description']}"
            text += f"   • <i>{type_desc}</i>\n"

            # Add note if present
            if item.get("note") and item["note"].strip():
                text += f"   📝 <i>{item['note']}</i>\n"

            text += "\n"

        text += "\n"

    return text


# Command handlers
@require_authorization
@log_command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /start is issued."""
    user = update.effective_user
    user_id = user.id
    username = user.username

    text = f"👋 Welcome {user.mention_html()}!\n\n"
    text += "🤖 I'm your <b>Item Bot</b> - I help teams manage shared items like servers, devices, and accounts.\n\n"

    text += "🚀 <b>Quick Start:</b>\n"
    text += "• <code>/list</code> - See all available items\n"
    text += "• <code>/take ItemName</code> - Take a free item\n"
    text += "• <code>/free ItemName</code> - Release your item\n"
    text += "• <code>/help</code> - Get detailed help & examples\n\n"

    text += "🔧 <b>All User Commands:</b>\n"
    text += "• <code>/list</code> - List all items (with filters)\n"
    text += "• <code>/take</code> - Take a free item\n"
    text += "• <code>/free</code> - Free an item you own\n"
    text += "• <code>/steal</code> - Steal an item (urgent situations)\n"
    text += "• <code>/noteset</code> - Add note to any item\n"
    text += "• <code>/notedrop</code> - Remove note from any item\n\n"

    if is_moderator_or_admin(user_id, username):
        text += "🛡️ <b>Your Moderator Commands:</b>\n"
        text += "• <code>/additem &lt;name&gt; &lt;group&gt; &lt;type&gt; &lt;description&gt;</code> - Add a new item\n"
        text += "• <code>/delitem</code> - Delete an item\n"
        text += "• <code>/edititem</code> - Edit item description\n"
        text += "• <code>/assign</code> - Assign item to user\n"
        text += "• <code>/purge</code> - Force-free any item\n"
        text += "• <code>/addnotify</code> - Enable notifications\n"
        text += "• <code>/delnotify</code> - Disable notifications\n"
        text += "• <code>/listnotify</code> - List notifications\n"
        text += "• <code>/help mod</code> - Moderator help guide\n\n"

    if is_admin(user_id):
        text += "👑 <b>Your Admin Commands:</b>\n"
        text += "• <code>/addtype</code> - Add item type\n"
        text += "• <code>/listtypes</code> - List all types\n"
        text += "• <code>/deltype</code> - Delete a type\n"
        text += "• <code>/addmod</code> - Add moderator\n"
        text += "• <code>/delmod</code> - Remove moderator\n"
        text += "• <code>/listmod</code> - List moderators\n"
        text += "• <code>/adduser</code> - Add authorized user\n"
        text += "• <code>/deluser</code> - Remove authorized user\n"
        text += "• <code>/listuser</code> - List authorized users\n"
        text += "• <code>/listhist</code> - View usage history\n"
        text += "• <code>/help admin</code> - Admin setup guide\n\n"

        text += "🗄️ <b>Database Management (Admin):</b>\n"
        text += "• <code>/dbdump</code> - Export database as commands\n"
        text += "• <code>/batch</code> - Import commands from file or chat\n"
        text += "• <code>/dbwipe</code> - Reset database (dangerous!)\n\n"

    text += "💡 <b>Pro Tips:</b>\n"
    text += "• Always specify a purpose when taking items\n"
    text += "• Free items promptly when you're done\n"
    text += "• Use <code>/list owner yourusername</code> to see your items\n\n"

    text += "❓ Need help? Use <code>/help</code> for detailed examples!\n\n"
    
    # Debug info
    text += f"🔧 <b>Debug Info:</b>\n"
    text += f"Your ID: <code>{user_id}</code>\n"
    text += f"Your username: <code>{username or 'None'}</code>\n"
    text += f"Admin: {'✅' if is_admin(user_id) else '❌'}\n"
    text += f"Moderator: {'✅' if is_moderator_or_admin(user_id, username) else '❌'}\n"
    text += f"Authorized: {'✅' if is_user_authorized(user_id, username) else '❌'}"

    await update.message.reply_html(text)


@require_authorization
@log_command
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send detailed help with examples"""
    user = update.effective_user
    user_id = user.id
    username = user.username

    # Check what type of help to show
    help_type = None
    if context.args:
        help_type = context.args[0].lower()

    text = "🤖 <b>Item Bot Help</b>\n\n"

    # Determine which sections to show
    show_user = help_type in [None, "full"]
    show_mod = help_type in ["mod", "full"] and is_moderator_or_admin(user_id, username)
    show_admin = help_type in ["admin", "full"] and is_admin(user_id)

    if help_type == "full":
        text += "📚 <b>Complete Bot Help Guide</b>\n\n"

    # User section
    if show_user:
        if help_type == "full":
            text += "👤 <b>USER COMMANDS</b>\n\n"

        text += "This bot helps manage shared items (servers, devices, accounts, etc.) in your team.\n\n"

        text += "📋 <b>How to Use:</b>\n\n"
        text += "<b>1. See available items:</b>\n"
        text += "<code>/list</code> → Shows all items with their status (✅ free, 📍 taken)\n"
        text += "<code>/list group production</code> → Shows only production items\n"
        text += "<code>/list owner alice</code> → Shows items owned by alice\n\n"

        text += "<b>2. Take a free item:</b>\n"
        text += "<code>/take WebServer1 debugging issue</code> → Take with purpose immediately\n"
        text += "<code>/take WebServer1</code> → Bot asks for purpose\n"
        text += "✅ Result: WebServer1 is now owned by you\n\n"

        text += "<b>3. Free your item when done:</b>\n"
        text += "<code>/free WebServer1</code> → Releases WebServer1 back to free pool\n"
        text += "✅ Result: WebServer1 is now available for others\n\n"

        text += "<b>4. Steal an item (urgent situations only):</b>\n"
        text += "<code>/steal</code> → Shows owned items → Enter: <code>iPhone15 critical production bug</code>\n"
        text += "⚠️ Result: You steal iPhone15 from current owner\n\n"

        text += "🔧 <b>User Commands:</b>\n"
        text += "<code>/list</code> - List all items (add filters: group, type, owner)\n"
        text += "<code>/take &lt;item_name&gt; [purpose]</code> - Take a free item\n"
        text += "<code>/free &lt;item_id&gt;</code> - Free an item you own\n"
        text += "<code>/steal</code> - Steal an item from someone (use responsibly!)\n"
        text += "<code>/noteset &lt;item_name&gt; &lt;note&gt;</code> - Add note to any item\n"
        text += "<code>/notedrop &lt;item_name&gt;</code> - Remove note from any item\n\n"

        text += "💡 <b>Tips:</b>\n"
        text += "• Always provide a purpose when taking/stealing items\n"
        text += "• Free items promptly when done\n"
        text += "• Use groups to organize items (production, testing, dev)\n"
        text += "• Stealing should be used only for urgent situations\n"
        text += "• Check <code>/list owner yourusername</code> to see your items\n\n"

    # Moderator section
    if show_mod:
        if help_type == "full":
            text += "🛡️ <b>MODERATOR COMMANDS</b>\n\n"
        else:
            text += "🛡️ <b>Moderator Commands & Guide</b>\n\n"

        text += "As a moderator, you can manage items and assignments:\n\n"

        text += "<b>Adding Items:</b>\n"
        text += "<code>/additem WebServer1 production Server Main web server</code>\n"
        text += "Format: <code>/additem &lt;name&gt; &lt;group&gt; &lt;type&gt; &lt;multi-word description&gt;</code>\n\n"

        text += "<b>Managing Items:</b>\n"
        text += "<code>/delitem WebServer1</code> → Delete an item\n"
        text += "<code>/edititem WebServer1 Updated production server with new specs</code> → Edit description\n"
        text += "<code>/assign iPhone15 alice</code> → Force assign item to user\n"
        text += "<code>/purge iPhone15</code> → Force-free item from current owner\n\n"

        text += "<b>Adding Notes (All Users):</b>\n"
        text += "<code>/noteset WebServer1 Currently running maintenance</code> → Add note to item\n"
        text += "<code>/notedrop WebServer1</code> → Remove note from item\n"
        text += "<i>💡 Notes are visible in /list and help track item status</i>\n\n"

        text += "🛡️ <b>Moderator Commands:</b>\n"
        text += "<code>/additem &lt;name&gt; &lt;group&gt; &lt;type&gt; &lt;multi-word description&gt;</code> - Add new item\n"
        text += "<code>/delitem &lt;item_id_or_name&gt;</code> - Delete an item\n"
        text += "<code>/edititem &lt;item_id_or_name&gt; &lt;new_description&gt;</code> - Edit item description\n"
        text += "<code>/assign &lt;item_id_or_name&gt; &lt;username&gt;</code> - Force assign item to user\n"
        text += "<code>/purge &lt;item_id_or_name&gt;</code> - Force-free any item (removes from current owner)\n\n"

        text += "<code>/addnotify [type_name]</code> - Enable notifications (all types if no arg)\n"
        text += "<code>/delnotify [type_name]</code> - Disable notifications (all types if no arg)\n"
        text += "<code>/listnotify</code> - List all notification subscriptions\n\n"

    # Admin section
    if show_admin:
        if help_type == "full":
            text += "👑 <b>ADMIN COMMANDS</b>\n\n"
        else:
            text += "👑 <b>Admin Commands & Setup Guide</b>\n\n"

        text += "As an admin, you can set up the entire system:\n\n"

        text += "<b>1. Set up item types:</b>\n"
        text += "<code>/addtype</code> → Enter: <code>Server</code>\n"
        text += "<code>/addtype</code> → Enter: <code>Test Device</code>\n\n"

        text += "<b>2. Manage moderators:</b>\n"
        text += "<code>/addmod alice</code> → Add alice as moderator\n"
        text += "<code>/listmod</code> → See all moderators\n"
        text += "<code>/delmod bob</code> → Remove bob from moderators\n\n"

        text += "<b>3. Manage authorized users:</b>\n"
        text += "<code>/adduser @alice</code> → Add user by username\n"
        text += "<code>/adduser 123456789 alice</code> → Add user by ID and username\n"
        text += "<code>/deluser @alice</code> → Remove user by username\n"
        text += "<code>/listuser</code> → See all authorized users\n"
        text += "<i>💡 Reply to any message with /adduser or /deluser</i>\n\n"

        text += "<b>4. Manage types:</b>\n"
        text += "<code>/listtypes</code> → See all item types\n"
        text += "<code>/deltype 1</code> → Delete unused type\n\n"

        text += "👑 <b>Admin Commands:</b>\n"
        text += "<code>/addtype [type_name]</code> - Add type with optional inline arg\n"
        text += "<code>/listtypes</code> - Show all available types\n"
        text += "<code>/deltype &lt;type_id&gt;</code> - Delete a type (if unused)\n\n"

        text += "<code>/addmod &lt;username&gt;</code> - Add moderator\n"
        text += "<code>/delmod &lt;username&gt;</code> - Remove moderator\n"
        text += "<code>/listmod</code> - List all moderators\n\n"

        text += "<code>/adduser &lt;@username|user_id&gt;</code> - Add authorized user\n"
        text += "<code>/deluser &lt;user_id|@username&gt;</code> - Remove authorized user\n"
        text += "<code>/listuser</code> - List all authorized users\n"
        text += "<i>💡 Tip: Reply to any user's message with /adduser or /deluser</i>\n"
        text += "<code>/listhist [N]</code> - View latest N usage history entries (default: 10)\n\n"

        text += "🗄️ <b>Database Management:</b>\n"
        text += "<code>/dbdump</code> - Export database as bot commands for backup/migration\n"
        text += "<code>/batch</code> - Import and execute commands from file or direct text input\n"
        text += "<code>/dbwipe confirm</code> - Reset database (deletes everything!)\n\n"

    # Add role-specific help hints
    if help_type != "mod" and is_moderator_or_admin(user_id, username):
        text += "🛡️ <b>Moderator?</b> Use <code>/help mod</code> for moderator commands.\n"

    if help_type != "admin" and is_admin(user_id):
        text += "👑 <b>Admin?</b> Use <code>/help admin</code> for admin commands and setup guide.\n"

    if help_type not in ["mod", "admin", "full"]:
        text += "\n❓ <b>Need help?</b> Contact an admin or use <code>/start</code> for quick command list.\n"
        text += "📖 Use <code>/help full</code> to see all available commands at once."

    await update.message.reply_html(text)


@require_authorization
@log_command
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
@require_authorization
@log_command
async def add_item_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add a new item with inline arguments"""
    user_id = update.effective_user.id
    username = update.effective_user.username

    if not is_moderator_or_admin(user_id, username):
        await update.message.reply_text("You don't have permission to use this command.")
        return

    types = bot.list_types()
    if not types:
        await update.message.reply_text("No types available. Please add types first using /addtype")
        return

    # Check if item details provided as arguments
    if not context.args or len(context.args) < 4:
        available_types = ", ".join([f"'{t[1]}'" for t in types])
        await update.message.reply_text(
            f"❌ Invalid usage. Command format:\n\n"
            f"<code>/additem &lt;name&gt; &lt;group&gt; &lt;type&gt; &lt;multi-word description&gt;</code>\n\n"
            f"Available types: {available_types}\n\n"
            f"Example: <code>/additem WebServer1 production Server Main production web server</code>",
            parse_mode='HTML'
        )
        return

    # Parse inline arguments: /additem name group type description
    name = context.args[0]
    group = context.args[1]
    type_arg = context.args[2]
    description = " ".join(context.args[3:])

    # Try to parse type as integer first, then as string (type name)
    type_id = None

    try:
        # Try as integer (type ID)
        type_id = int(type_arg)
        if not any(t[0] == type_id for t in types):
            available_types = "\n".join([f"ID {t[0]}: {t[1]}" for t in types])
            await update.message.reply_text(f"Type ID {type_id} not found. Available types:\n{available_types}")
            return
    except ValueError:
        # Try as string (type name)
        type_name_lower = type_arg.lower()
        for t_id, t_name in types:
            if t_name.lower() == type_name_lower:
                type_id = t_id
                break

        if type_id is None:
            available_types = ", ".join([f"'{t[1]}'" for t in types])
            await update.message.reply_text(
                f"Type '{type_arg}' not found. Available types: {available_types}\n"
                f"Use /addtype {type_arg} to create it first, or use /listtypes to see all types."
            )
            return

    success = bot.add_item(name, group, type_id, description)

    if success:
        await update.message.reply_text(f"Item '{name}' added successfully!")
    else:
        await update.message.reply_text("Failed to add item. Name might already exist.")





@require_authorization
@log_command
async def add_type_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start adding a new type"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("You don't have permission to use this command.")
        return ConversationHandler.END

    # Check if type name provided as argument
    if context.args:
        type_name = " ".join(context.args).strip()
        logger.info(f"Admin attempting to add type: '{type_name}'")
        success = bot.add_type(type_name)

        if success:
            logger.info(f"Type '{type_name}' added successfully")
            await update.message.reply_text(f"Type '{type_name}' added successfully!")
        else:
            logger.warning(f"Failed to add type '{type_name}' - might already exist")
            await update.message.reply_text("Failed to add type. Name might already exist.")

        return ConversationHandler.END

    await update.message.reply_text("Please enter the name for the new type:")
    return ADDING_TYPE


@require_authorization
@log_command
async def add_type_finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Finish adding a new type"""
    type_name = update.message.text.strip()

    success = bot.add_type(type_name)

    if success:
        await update.message.reply_text(f"Type '{type_name}' added successfully!")
    else:
        await update.message.reply_text("Failed to add type. Name might already exist.")

    return ConversationHandler.END


@require_authorization
@log_command
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


@require_authorization
@log_command
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


@require_authorization
@log_command
async def delete_item_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Delete an item"""
    user_id = update.effective_user.id
    username = update.effective_user.username

    if not is_moderator_or_admin(user_id, username):
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
@require_authorization
@log_command
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
    item = next((i for i in items if i["id"] == item_id), None)
    if not item:
        await update.message.reply_text("Item not found.")
        return ConversationHandler.END

    if item["owner"]:
        await update.message.reply_text(f"Item '{item['name']}' is already owned by {item['owner']}.")
        return ConversationHandler.END

    # If purpose provided, take immediately
    if len(args) > 1:
        purpose = " ".join(args[1:])
        user = update.effective_user.username or str(update.effective_user.id)
        success, message = bot.take_item(item_id, user, purpose)
        await update.message.reply_text(message)

        # Send notifications
        if success:
            await notify_item_action(
                context.application,
                item["name"],
                item["type_id"],
                "take",
                user,
                purpose,
            )

        return ConversationHandler.END

    # If no purpose, ask for it
    context.user_data["take_item_id"] = item_id
    context.user_data["take_item_name"] = item["name"]
    await update.message.reply_text(f"What is the purpose for taking <b>{item['name']}</b>?", parse_mode="HTML")
    return TAKING_PURPOSE


@require_authorization
@log_command
async def take_purpose_finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Finish taking item after purpose is provided"""
    purpose = update.message.text.strip()
    item_id = context.user_data.get("take_item_id")

    if not item_id:
        await update.message.reply_text("Error: Lost track of which item you wanted to take.")
        return ConversationHandler.END

    user = update.effective_user.username or str(update.effective_user.id)
    success, message = bot.take_item(item_id, user, purpose)
    await update.message.reply_text(message)

    # Send notifications
    if success:
        # Get item details for notification
        items = bot.list_items()
        item = next((i for i in items if i["id"] == item_id), None)
        if item:
            await notify_item_action(
                context.application,
                item["name"],
                item["type_id"],
                "take",
                user,
                purpose,
            )

    # Clean up context data
    context.user_data.pop("take_item_id", None)
    context.user_data.pop("take_item_name", None)

    return ConversationHandler.END


@require_authorization
@log_command
async def take_item_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start taking an item"""
    # Show available free items
    items = bot.list_items(free_only=True)

    if not items:
        await update.message.reply_text("No free items available.")
        return ConversationHandler.END

    text = "<b>Available Free Items:</b>\n\n" + format_item_list(items)
    text += "\nPlease enter the item ID or name you want to take, optionally with purpose:\n"
    text += "Format: <code>&lt;item_id_or_name&gt; [purpose]</code>\n"
    text += "Examples: <code>5 for testing</code> or <code>ItemName debugging</code>"

    await update.message.reply_html(text)
    return TAKING_ITEM


@require_authorization
@log_command
async def take_item_finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Finish taking an item"""
    text = update.message.text.strip()
    parts = text.split(" ", 1)

    # Find item by name or ID
    item_id = bot.find_item_by_name_or_id(parts[0])
    if item_id is None:
        await update.message.reply_text("Item not found. Please enter a valid item ID or name.")
        return TAKING_ITEM

    purpose = parts[1] if len(parts) > 1 else None
    user = update.effective_user.username or str(update.effective_user.id)

    success, message = bot.take_item(item_id, user, purpose)
    await update.message.reply_text(message)

    # Send notifications
    if success:
        # Get item details for notification
        items = bot.list_items()
        item = next((i for i in items if i["id"] == item_id), None)
        if item:
            await notify_item_action(
                context.application,
                item["name"],
                item["type_id"],
                "take",
                user,
                purpose,
            )

    return ConversationHandler.END


@require_authorization
@log_command
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

    # Send notifications
    if success:
        # Get item details for notification
        items = bot.list_items()
        item = next((i for i in items if i["id"] == item_id), None)
        if item:
            await notify_item_action(context.application, item["name"], item["type_id"], "free", user)


@require_authorization
@log_command
async def steal_item_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start stealing an item"""
    user = update.effective_user.username or str(update.effective_user.id)

    # Show all owned items except user's own
    items = [item for item in bot.list_items() if item["owner"] and item["owner"] != user]

    if not items:
        await update.message.reply_text("No items available to steal.")
        return ConversationHandler.END

    text = "<b>Items You Can Steal:</b>\n\n" + format_item_list(items)
    text += "\nPlease enter the item ID or name you want to steal, optionally with purpose:\n"
    text += "Format: <code>&lt;item_id_or_name&gt; [purpose]</code>\n"
    text += "Examples: <code>5 urgent issue</code> or <code>iPhone15 critical bug</code>"

    await update.message.reply_html(text)
    return STEALING_ITEM


@require_authorization
@log_command
async def steal_item_finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Finish stealing an item"""
    text = update.message.text.strip()
    parts = text.split(" ", 1)

    # Find item by name or ID
    item_id = bot.find_item_by_name_or_id(parts[0])
    if item_id is None:
        await update.message.reply_text("Item not found. Please enter a valid item ID or name.")
        return STEALING_ITEM

    purpose = parts[1] if len(parts) > 1 else None
    user = update.effective_user.username or str(update.effective_user.id)

    # Get item details before stealing for notification
    items = bot.list_items()
    item = next((i for i in items if i["id"] == item_id), None)
    previous_owner = item["owner"] if item else None

    success, message = bot.steal_item(item_id, user, purpose)
    await update.message.reply_text(message)

    # Send notifications
    if success and item and previous_owner:
        await notify_item_action(
            context.application,
            item["name"],
            item["type_id"],
            "steal",
            user,
            purpose,
            previous_owner,
        )

    return ConversationHandler.END


@require_authorization
@log_command
async def assign_item_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Assign an item to a user (moderator/admin only)"""
    user_id = update.effective_user.id
    username = update.effective_user.username

    if not is_moderator_or_admin(user_id, username):
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

    # Send notifications
    if success:
        # Get item details for notification
        items = bot.list_items()
        item = next((i for i in items if i["id"] == item_id), None)
        if item:
            await notify_item_action(
                context.application,
                item["name"],
                item["type_id"],
                "assign",
                by_user,
                to_user,
            )


@require_authorization
@log_command
async def purge_item_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Force-free an item (moderator/admin only)"""
    user_id = update.effective_user.id
    username = update.effective_user.username

    if not is_moderator_or_admin(user_id, username):
        await update.message.reply_text("You don't have permission to use this command.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /purge <item_id_or_name>")
        return

    item_identifier = context.args[0]

    # Find item by name or ID
    item_id = bot.find_item_by_name_or_id(item_identifier)
    if item_id is None:
        await update.message.reply_text("Item not found. Please enter a valid item ID or name.")
        return

    moderator = update.effective_user.username or str(update.effective_user.id)

    # Get item details before purging for notification
    items = bot.list_items()
    item = next((i for i in items if i["id"] == item_id), None)
    previous_owner = item["owner"] if item else None

    success, message = bot.purge_item(item_id, moderator)
    await update.message.reply_text(message)

    # Send notifications
    if success and item and previous_owner:
        await notify_item_action(
            context.application,
            item["name"],
            item["type_id"],
            "purge",
            moderator,
            None,
            previous_owner,
        )


@require_authorization
@log_command
async def edit_item_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Edit item description (moderator/admin only)"""
    user_id = update.effective_user.id
    username = update.effective_user.username

    if not is_moderator_or_admin(user_id, username):
        await update.message.reply_text("You don't have permission to use this command.")
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "Usage: /edititem <item_id_or_name> <new_description>\n\n"
            "Example: /edititem WebServer1 Updated web server for production use"
        )
        return

    # Find item by name or ID
    item_id = bot.find_item_by_name_or_id(context.args[0])
    if item_id is None:
        await update.message.reply_text("Item not found. Please enter a valid item ID or name.")
        return

    # Get new description (join all remaining args)
    new_description = " ".join(context.args[1:])

    success, message = bot.edit_item_description(item_id, new_description)
    await update.message.reply_text(message)


@require_authorization
@log_command
async def note_set_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set item note (any authorized user)"""
    if len(context.args) < 2:
        await update.message.reply_text(
            "Usage: /noteset <item_id_or_name> <note_text>\n\n"
            "Example: /noteset WebServer1 Currently running maintenance scripts"
        )
        return

    # Find item by name or ID
    item_id = bot.find_item_by_name_or_id(context.args[0])
    if item_id is None:
        await update.message.reply_text("Item not found. Please enter a valid item ID or name.")
        return

    # Get note text (join all remaining args)
    note_text = " ".join(context.args[1:])

    success, message = bot.set_item_note(item_id, note_text)
    await update.message.reply_text(message)


@require_authorization
@log_command
async def note_drop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove item note (any authorized user)"""
    if not context.args:
        await update.message.reply_text("Usage: /notedrop <item_id_or_name>\n\n" "Example: /notedrop WebServer1")
        return

    # Find item by name or ID
    item_id = bot.find_item_by_name_or_id(context.args[0])
    if item_id is None:
        await update.message.reply_text("Item not found. Please enter a valid item ID or name.")
        return

    success, message = bot.drop_item_note(item_id)
    await update.message.reply_text(message)


@require_authorization
@log_command
async def add_moderator_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add a moderator (admin only)"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("You don't have permission to use this command.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /addmod <username>")
        return

    username = context.args[0].lstrip("@")  # Remove @ if present
    added_by = update.effective_user.username or str(update.effective_user.id)

    success = bot.add_moderator(username, added_by)

    if success:
        await update.message.reply_text(f"✅ @{username} has been added as a moderator.")
    else:
        await update.message.reply_text(f"❌ @{username} is already a moderator.")


@require_authorization
@log_command
async def remove_moderator_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove a moderator (admin only)"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("You don't have permission to use this command.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /delmod <username>")
        return

    username = context.args[0].lstrip("@")  # Remove @ if present
    success = bot.remove_moderator(username)

    if success:
        await update.message.reply_text(f"✅ @{username} has been removed from moderators.")
    else:
        await update.message.reply_text(f"❌ @{username} was not a moderator.")


@require_authorization
@log_command
async def list_moderators_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all moderators (admin only)"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("You don't have permission to use this command.")
        return

    moderators = bot.list_moderators()

    if not moderators:
        await update.message.reply_text("No moderators configured.")
        return

    text = "<b>Moderators:</b>\n\n"
    for username, added_by, added_at in moderators:
        text += f"• @{username}\n"
        text += f"  Added by: {added_by or 'N/A'}\n"
        text += f"  Added: {added_at}\n\n"

    await update.message.reply_html(text)


@require_authorization
@log_command
async def add_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add an authorized user (admin only)"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("You don't have permission to use this command.")
        return

    # Check if this is a reply to another user's message
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        target_user = update.message.reply_to_message.from_user
        user_id = target_user.id
        username = target_user.username
        added_by = update.effective_user.username or str(update.effective_user.id)

        success = bot.add_authorized_user(user_id=user_id, username=username, added_by=added_by)

        if success:
            user_display = f"@{username}" if username else f"User ID {user_id}"
            await update.message.reply_text(f"✅ {user_display} has been authorized to use the bot.")
        else:
            await update.message.reply_text(f"❌ User {user_display} is already authorized.")
        return

    if not context.args:
        await update.message.reply_text(
            "Usage:\n"
            "• /adduser @username - Add by username\n"
            "• /adduser <user_id> [username] - Add by numeric ID\n"
            "• Reply to a user's message with /adduser - Add that user"
        )
        return

    identifier = context.args[0]
    user_id = None
    username = None

    # Check if it's a username (starts with @)
    if identifier.startswith("@"):
        username = identifier[1:]  # Remove @ prefix
        added_by = update.effective_user.username or str(update.effective_user.id)

        success = bot.add_authorized_user(username=username, added_by=added_by)

        if success:
            await update.message.reply_text(
                f"✅ @{username} has been authorized to use the bot.\n"
                f"<i>Note: Authorization will take effect when they next interact with the bot.</i>",
                parse_mode="HTML",
            )
        else:
            await update.message.reply_text(f"❌ @{username} is already authorized.")
        return
    else:
        # Try to parse as numeric user ID
        try:
            user_id = int(identifier)
            username = context.args[1] if len(context.args) > 1 else None
        except ValueError:
            await update.message.reply_text(
                "Invalid format. Use:\n"
                "• /adduser @username\n"
                "• /adduser 123456789 [username]\n"
                "• Reply to a user's message with /adduser"
            )
            return

    added_by = update.effective_user.username or str(update.effective_user.id)

    success = bot.add_authorized_user(user_id=user_id, username=username, added_by=added_by)

    if success:
        user_display = f"@{username}" if username else f"User ID {user_id}"
        await update.message.reply_text(f"✅ {user_display} has been authorized to use the bot.")
    else:
        await update.message.reply_text(f"❌ User ID {user_id} is already authorized.")


@require_authorization
@log_command
async def remove_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove an authorized user (admin only)"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("You don't have permission to use this command.")
        return

    # Check if this is a reply to another user's message
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        target_user = update.message.reply_to_message.from_user
        user_id = target_user.id
        username = target_user.username

        success = bot.remove_authorized_user(user_id=user_id)

        if success:
            user_display = f"@{username}" if username else f"User ID {user_id}"
            await update.message.reply_text(f"✅ {user_display} has been removed from authorized users.")
        else:
            user_display = f"@{username}" if username else f"User ID {user_id}"
            await update.message.reply_text(f"❌ {user_display} was not found in authorized users.")
        return

    if not context.args:
        await update.message.reply_text(
            "Usage:\n"
            "• /deluser <user_id> - Remove by numeric ID\n"
            "• /deluser @username - Remove by username (searches authorized users)\n"
            "• Reply to a user's message with /deluser - Remove that user"
        )
        return

    identifier = context.args[0]
    user_id = None

    # Check if it's a username (starts with @)
    if identifier.startswith("@"):
        username = identifier[1:]  # Remove @ prefix

        # Search for user in authorized users list by username
        authorized_users = bot.list_authorized_users()
        found_user = None
        for uid, uname, added_by, added_at in authorized_users:
            if uname and uname.lower() == username.lower():
                found_user = (uid, uname)
                break

        if not found_user:
            await update.message.reply_text(f"❌ @{username} not found in authorized users list.")
            return

        success = bot.remove_authorized_user(username=username)

        if success:
            await update.message.reply_text(f"✅ @{username} has been removed from authorized users.")
        else:
            await update.message.reply_text(f"❌ Failed to remove @{username} from authorized users.")
        return
    else:
        # Try to parse as numeric user ID
        try:
            user_id = int(identifier)
        except ValueError:
            await update.message.reply_text(
                "Invalid format. Use:\n"
                "• /deluser 123456789\n"
                "• /deluser @username\n"
                "• Reply to a user's message with /deluser"
            )
            return

    success = bot.remove_authorized_user(user_id=user_id)

    if success:
        await update.message.reply_text(f"✅ User ID {user_id} has been removed from authorized users.")
    else:
        await update.message.reply_text(f"❌ User ID {user_id} was not found in authorized users.")


@require_authorization
@log_command
async def list_users_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all authorized users (admin only)"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("You don't have permission to use this command.")
        return

    users = bot.list_authorized_users()

    if not users:
        await update.message.reply_text(
            "No authorized users configured.\n\n<i>Note: Admins and moderators are automatically authorized.</i>",
            parse_mode="HTML",
        )
        return

    text = "<b>Authorized Users:</b>\n\n"
    for user_id, username, added_by, added_at in users:
        user_display = f"{username}" if username else f"User ID {user_id}"
        text += f"• {user_display} (ID: {user_id})\n"
        text += f"  Added by: {added_by or 'N/A'}\n"
        text += f"  Added: {added_at}\n\n"

    text += "<i>Note: Admins and moderators are automatically authorized and not shown here.</i>"

    await update.message.reply_html(text)


@require_authorization
@log_command
async def add_notify_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add notification subscription (moderator/admin only)"""
    user_id = update.effective_user.id
    username = update.effective_user.username

    if not is_moderator_or_admin(user_id, username):
        await update.message.reply_text("You don't have permission to use this command.")
        return

    chat_id = update.effective_chat.id
    chat_title = getattr(update.effective_chat, "title", "Private Chat")
    added_by = username or str(user_id)

    # Parse type argument
    type_id = None
    type_name = None

    if context.args:
        type_arg = context.args[0]
        # Try to find type by name or ID
        types = bot.list_types()

        # Try as integer first (type ID)
        try:
            type_id = int(type_arg)
            type_name = next((t[1] for t in types if t[0] == type_id), None)
            if not type_name:
                await update.message.reply_text(f"Type ID {type_id} not found.")
                return
        except ValueError:
            # Try as string (type name)
            for t_id, t_name in types:
                if t_name.lower() == type_arg.lower():
                    type_id = t_id
                    type_name = t_name
                    break

            if type_id is None:
                await update.message.reply_text(f"Type '{type_arg}' not found.")
                return

    success = bot.add_notification(chat_id, chat_title, type_id, added_by)

    if success:
        if type_id:
            await update.message.reply_html(f"✅ Notifications enabled for <b>{type_name}</b> items in this chat.")
        else:
            await update.message.reply_html("✅ Notifications enabled for <b>all item types</b> in this chat.")
    else:
        if type_id:
            await update.message.reply_html(
                f"❌ Notifications for <b>{type_name}</b> are already enabled in this chat."
            )
        else:
            await update.message.reply_html(
                "❌ Notifications for <b>all item types</b> are already enabled in this chat."
            )


@require_authorization
@log_command
async def remove_notify_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove notification subscription (moderator/admin only)"""
    user_id = update.effective_user.id
    username = update.effective_user.username

    if not is_moderator_or_admin(user_id, username):
        await update.message.reply_text("You don't have permission to use this command.")
        return

    chat_id = update.effective_chat.id

    # Parse type argument
    type_id = None
    type_name = None

    if context.args:
        type_arg = context.args[0]
        # Try to find type by name or ID
        types = bot.list_types()

        # Try as integer first (type ID)
        try:
            type_id = int(type_arg)
            type_name = next((t[1] for t in types if t[0] == type_id), None)
            if not type_name:
                await update.message.reply_text(f"Type ID {type_id} not found.")
                return
        except ValueError:
            # Try as string (type name)
            for t_id, t_name in types:
                if t_name.lower() == type_arg.lower():
                    type_id = t_id
                    type_name = t_name
                    break

            if type_id is None:
                await update.message.reply_text(f"Type '{type_arg}' not found.")
                return

    removed_count = bot.remove_notification(chat_id, type_id)

    if removed_count > 0:
        if type_id:
            await update.message.reply_text(f"✅ Notifications for <b>{type_name}</b> removed from this chat.")
        else:
            await update.message.reply_text(f"✅ Removed {removed_count} notification subscription(s) from this chat.")
    else:
        if type_id:
            await update.message.reply_text(f"❌ No notifications for <b>{type_name}</b> found in this chat.")
        else:
            await update.message.reply_text("❌ No notification subscriptions found in this chat.")


@require_authorization
@log_command
async def list_notify_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all notification subscriptions (moderator/admin only)"""
    user_id = update.effective_user.id
    username = update.effective_user.username

    if not is_moderator_or_admin(user_id, username):
        await update.message.reply_text("You don't have permission to use this command.")
        return

    notifications = bot.list_notifications()

    # Log the notification listing
    logger.info(f"User {username or user_id} requested notification list")

    if not notifications:
        logger.info("No notification subscriptions configured")
        await update.message.reply_text("No notification subscriptions configured.")
        return

    # Log each notification's details
    logger.info(f"Found {len(notifications)} notification subscriptions:")
    for chat_id, chat_title, type_id, type_name, added_by, added_at in notifications:
        logger.info(
            f"  - Chat: '{chat_title}' (ID: {chat_id}), Type: {type_name or 'ALL'}, Added by: {added_by}, Added: {added_at}"
        )

    text = "<b>📢 Notification Subscriptions:</b>\n\n"

    # Group by chat for better readability
    current_chat = None
    for chat_id, chat_title, type_id, type_name, added_by, added_at in notifications:
        if current_chat != chat_title:
            if current_chat is not None:
                text += "\n"
            text += f"<b>💬 {chat_title or 'Unknown Chat'}</b>\n"
            text += f"   ID: <code>{chat_id}</code>\n"
            current_chat = chat_title

        type_display = type_name or "ALL TYPES"
        text += f"   • {type_display}\n"
        text += f"     Added by: {added_by or 'N/A'} on {added_at}\n"

    await update.message.reply_html(text)


@require_authorization
@log_command
async def list_history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List usage history (admin only)"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("You don't have permission to use this command.")
        return

    # Parse limit argument
    limit = 10  # default
    if context.args:
        try:
            limit = int(context.args[0])
            if limit <= 0 or limit > 100:
                await update.message.reply_text("Please provide a number between 1 and 100.")
                return
        except ValueError:
            await update.message.reply_text("Please provide a valid number.")
            return

    # Get history from database
    conn = bot.get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT h.timestamp, h.user, h.action, h.purpose, i.name as item_name, t.name as type_name
        FROM usage_history h
        LEFT JOIN items i ON h.item_id = i.id
        LEFT JOIN types t ON i.type_id = t.id
        ORDER BY h.timestamp DESC
        LIMIT ?
    """,
        (limit,),
    )

    history = cursor.fetchall()
    conn.close()

    admin_user = update.effective_user.username or str(update.effective_user.id)
    logger.info(f"Admin {admin_user} requested {limit} latest history entries")

    if not history:
        await update.message.reply_text("No usage history found.")
        return

    text = f"📊 <b>Latest {len(history)} Actions:</b>\n\n"

    for timestamp, user, action, purpose, item_name, type_name in history:
        # Format timestamp
        try:
            dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            time_str = dt.strftime("%m/%d %H:%M")
        except (ValueError, TypeError):
            time_str = timestamp[:16]  # fallback

        # Choose emoji based on action
        if action == "take":
            emoji = "📍"
        elif action == "free":
            emoji = "✅"
        elif action == "steal":
            emoji = "⚠️"
        elif action == "assign":
            emoji = "👑"
        else:
            emoji = "🔄"

        # Format the entry
        text += f"{emoji} <code>{time_str}</code> - <b>{item_name or 'Unknown'}</b>\n"
        text += f"   {action.title()} by {user}"

        if purpose:
            if action == "assign":
                text += f" ({purpose})"
            else:
                text += f" - <i>{purpose}</i>"

        if type_name:
            text += f" [{type_name}]"

        text += "\n\n"

    # Log the history details
    logger.info(f"Returned {len(history)} history entries to admin {admin_user}")

    await update.message.reply_html(text)


@require_authorization
@log_command
async def batch_command_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start batch command processing (admin only)"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("You don't have permission to use this command.")
        return ConversationHandler.END

    await update.message.reply_html(
        "📄 <b>Batch Command Processing</b>\n\n"
        "You can provide commands in two ways:\n\n"
        "📎 <b>Option 1:</b> Upload a text file containing bot commands\n"
        "💬 <b>Option 2:</b> Paste commands directly in chat\n\n"
        "• Lines starting with <code>#</code> will be ignored\n"
        "• Empty lines will be skipped\n"
        "• Commands will be executed in order\n"
        "• Process will stop on first error\n\n"
        "Send the file or paste commands now, or use /cancel to abort."
    )
    return BATCH_PROCESSING


@require_authorization
@log_command
async def batch_command_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process uploaded batch file or text input"""
    content = None

    try:
        if update.message.document:
            # Handle file upload
            file = await context.bot.get_file(update.message.document.file_id)
            file_content = await file.download_as_bytearray()

            # Decode content
            try:
                content = file_content.decode("utf-8")
            except UnicodeDecodeError:
                await update.message.reply_text("❌ File must be a text file with UTF-8 encoding.")
                return ConversationHandler.END

        elif update.message.text:
            # Handle direct text input
            content = update.message.text.strip()

        else:
            await update.message.reply_text(
                "Please upload a text file or paste commands directly, or use /cancel to abort."
            )
            return BATCH_PROCESSING

        # Parse commands
        lines = content.split("\n")
        commands = []

        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            # Skip empty lines and comments
            if not line or line.startswith("#"):
                continue

            # Validate it looks like a bot command
            if not line.startswith("/"):
                await update.message.reply_text(f"❌ Invalid command on line {line_num}: {line[:50]}...")
                return ConversationHandler.END

            commands.append((line_num, line))

        if not commands:
            await update.message.reply_text("❌ No valid commands found in file.")
            return ConversationHandler.END

        # Show preview and ask for confirmation
        preview_lines = []
        for i, (line_num, cmd) in enumerate(commands[:10]):  # Show first 10
            preview_lines.append(f"{i+1}. {cmd}")

        preview_text = "\n".join(preview_lines)
        if len(commands) > 10:
            preview_text += f"\n... and {len(commands) - 10} more commands"

        await update.message.reply_html(
            f"📋 <b>Found {len(commands)} commands to execute:</b>\n\n"
            f"<code>{preview_text}</code>\n\n"
            "⚠️ <b>Warning:</b> This will execute all commands immediately!\n\n"
            "Reply with <code>EXECUTE</code> to proceed, or anything else to cancel."
        )

        # Store commands in context for confirmation
        context.user_data["batch_commands"] = commands
        return BATCH_CONFIRMING

    except Exception as e:
        logger.error(f"Failed to process batch file: {e}")
        await update.message.reply_text(f"❌ Failed to process file: {str(e)}")
        return ConversationHandler.END


@require_authorization
@log_command
async def batch_command_execute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Execute confirmed batch commands"""
    if update.message.text.strip().upper() != "EXECUTE":
        await update.message.reply_text("❌ Batch processing cancelled.")
        return ConversationHandler.END

    commands = context.user_data.get("batch_commands", [])
    if not commands:
        await update.message.reply_text("❌ No commands to execute.")
        return ConversationHandler.END

    admin_user = update.effective_user.username or str(update.effective_user.id)
    logger.warning(f"Admin {admin_user} starting batch execution of {len(commands)} commands")

    await update.message.reply_text(f"🔄 Executing {len(commands)} commands...")

    executed = 0
    failed = 0
    results = []

    for line_num, command in commands:
        try:
            # Parse command and arguments
            parts = command.split()
            cmd = parts[0][1:]  # Remove leading /
            args = parts[1:] if len(parts) > 1 else []

            # Execute based on command type
            success = False
            message = ""

            if cmd == "addtype" and len(args) >= 1:
                type_name = " ".join(args)
                success = bot.add_type(type_name)
                message = f"Type '{type_name}' {'added' if success else 'failed (may already exist)'}"

            elif cmd == "additem" and len(args) >= 4:
                name, group, type_arg, *desc_parts = args
                description = " ".join(desc_parts)

                # Find type ID
                types = bot.list_types()
                type_id = None

                try:
                    type_id = int(type_arg)
                    if not any(t[0] == type_id for t in types):
                        type_id = None
                except ValueError:
                    type_name_lower = type_arg.lower()
                    for t_id, t_name in types:
                        if t_name.lower() == type_name_lower:
                            type_id = t_id
                            break

                if type_id:
                    success = bot.add_item(name, group, type_id, description)
                    message = f"Item '{name}' {'added' if success else 'failed (may already exist)'}"
                else:
                    message = f"Invalid type '{type_arg}' for item '{name}'"

            elif cmd == "addmod" and len(args) >= 1:
                username = args[0]
                success = bot.add_moderator(username, admin_user)
                message = f"Moderator '{username}' {'added' if success else 'failed (may already exist)'}"

            else:
                message = f"Unsupported or invalid command: {command}"

            if success or "failed" not in message.lower():
                executed += 1
                results.append(f"✅ Line {line_num}: {message}")
            else:
                failed += 1
                results.append(f"❌ Line {line_num}: {message}")

        except Exception as e:
            failed += 1
            results.append(f"❌ Line {line_num}: Error executing '{command}': {str(e)}")
            logger.error(f"Batch command error on line {line_num}: {e}")

    # Send results
    summary = "📊 <b>Batch Execution Complete</b>\n\n"
    summary += f"✅ Executed: {executed}\n"
    summary += f"❌ Failed: {failed}\n"
    summary += f"📋 Total: {len(commands)}\n\n"

    # Send summary first
    await update.message.reply_html(summary)

    # Send detailed results if not too long
    if results:
        results_text = "\n".join(results)
        if len(results_text) > 4000:
            # Send as file if too long
            import io

            file_content = results_text.encode("utf-8")
            file_obj = io.BytesIO(file_content)
            file_obj.name = "batch_results.txt"

            await update.message.reply_document(
                document=file_obj,
                filename="batch_results.txt",
                caption="📄 Detailed batch execution results",
            )
        else:
            await update.message.reply_html(f"<b>Detailed Results:</b>\n\n<code>{results_text}</code>")

    logger.warning(f"Admin {admin_user} completed batch execution: {executed} success, {failed} failed")
    return ConversationHandler.END


@require_authorization
@log_command
async def wipe_database_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Wipe and bootstrap the database (admin only)"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("You don't have permission to use this command.")
        return

    admin_user = update.effective_user.username or str(update.effective_user.id)

    # Confirmation check
    if not context.args or context.args[0].lower() != "confirm":
        await update.message.reply_html(
            "⚠️ <b>WARNING:</b> This will delete ALL data!\n\n"
            "This includes:\n"
            "• All item types\n"
            "• All items\n"
            "• All usage history\n"
            "• All moderators\n"
            "• All notification subscriptions\n\n"
            "To confirm, use: <code>/dbwipe confirm</code>"
        )
        return

    try:
        # Drop all tables and recreate
        conn = bot.get_connection()
        cursor = conn.cursor()

        # Drop tables in reverse dependency order
        cursor.execute("DROP TABLE IF EXISTS notifications")
        cursor.execute("DROP TABLE IF EXISTS usage_history")
        cursor.execute("DROP TABLE IF EXISTS moderators")
        cursor.execute("DROP TABLE IF EXISTS items")
        cursor.execute("DROP TABLE IF EXISTS types")

        conn.commit()
        conn.close()

        # Reinitialize database
        bot.init_database()

        logger.warning(f"Database wiped by admin {admin_user}")
        await update.message.reply_text("✅ Database wiped and reinitialized successfully!")

    except Exception as e:
        logger.error(f"Failed to wipe database: {e}")
        await update.message.reply_text(f"❌ Failed to wipe database: {str(e)}")


@require_authorization
@log_command
async def dump_database_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Dump database as bot commands (admin only)"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("You don't have permission to use this command.")
        return

    admin_user = update.effective_user.username or str(update.effective_user.id)
    logger.info(f"Admin {admin_user} requested database dump")

    try:
        conn = bot.get_connection()
        cursor = conn.cursor()

        dump_lines = []
        dump_lines.append("# Database dump - Bot commands to recreate data")
        dump_lines.append("# Generated by /dbdump command")
        dump_lines.append("")

        # Dump types
        cursor.execute("SELECT id, name FROM types ORDER BY id")
        types = cursor.fetchall()

        if types:
            dump_lines.append("# Item Types")
            for type_id, type_name in types:
                dump_lines.append(f"/addtype {type_name}")
            dump_lines.append("")

        # Dump items
        cursor.execute(
            """
            SELECT i.name, i.group_name, t.name as type_name, i.description
            FROM items i
            LEFT JOIN types t ON i.type_id = t.id
            ORDER BY i.id
        """
        )
        items = cursor.fetchall()

        if items:
            dump_lines.append("# Items")
            for item_name, group_name, type_name, description in items:
                # Escape any special characters and format for inline command
                safe_name = item_name.replace(" ", "_") if " " in item_name else item_name
                safe_group = group_name.replace(" ", "_") if " " in group_name else group_name
                safe_type = type_name.replace(" ", "_") if type_name and " " in type_name else type_name
                safe_desc = description.replace("\n", " ").replace("|", "-") if description else "No description"

                dump_lines.append(f"/additem {safe_name} {safe_group} {safe_type or 'Unknown'} {safe_desc}")
            dump_lines.append("")

        # Dump moderators
        cursor.execute("SELECT username FROM moderators ORDER BY added_at")
        moderators = cursor.fetchall()

        if moderators:
            dump_lines.append("# Moderators")
            for (username,) in moderators:
                dump_lines.append(f"/addmod {username}")
            dump_lines.append("")

        conn.close()

        if len(dump_lines) <= 3:  # Only headers
            await update.message.reply_text("No data to dump - database is empty.")
            return

        # Create dump text
        dump_text = "\n".join(dump_lines)

        # Send as file if too long, otherwise as message
        if len(dump_text) > 4000:
            # Create a file
            import io

            file_content = dump_text.encode("utf-8")
            file_obj = io.BytesIO(file_content)
            file_obj.name = "database_dump.txt"

            await update.message.reply_document(
                document=file_obj,
                filename="database_dump.txt",
                caption="📄 Database dump as bot commands",
            )
        else:
            await update.message.reply_text(f"```\n{dump_text}\n```", parse_mode="MarkdownV2")

        logger.info(f"Database dump completed for admin {admin_user}")

    except Exception as e:
        logger.error(f"Failed to dump database: {e}")
        await update.message.reply_text(f"❌ Failed to dump database: {str(e)}")


@require_authorization
@log_command
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel the current operation"""
    await update.message.reply_text("Operation cancelled.")
    return ConversationHandler.END


def main():
    """Start the bot"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Telegram Bot for Resource Allocation Management')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    args = parser.parse_args()

    # Configure logging based on debug flag
    if args.debug:
        log_level = logging.DEBUG
        print("🔍 Debug logging enabled")
        # Reconfigure logging with debug level
        if LOG_FILE:
            logging.basicConfig(
                format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                level=log_level,
                handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
            )
        else:
            logging.basicConfig(
                format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                level=log_level
            )

    # Create the Application with timeout configuration
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .read_timeout(30)
        .write_timeout(30)
        .connect_timeout(30)
        .pool_timeout(30)
        .build()
    )

    # Conversation handlers

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

    batch_handler = ConversationHandler(
        entry_points=[CommandHandler("batch", batch_command_start)],
        states={
            BATCH_PROCESSING: [
                MessageHandler(filters.Document.ALL, batch_command_process),
                MessageHandler(filters.TEXT & ~filters.COMMAND, batch_command_process),
            ],
            BATCH_CONFIRMING: [MessageHandler(filters.TEXT & ~filters.COMMAND, batch_command_execute)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # Register handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("list", list_items_command))
    application.add_handler(CommandHandler("additem", add_item_command))
    application.add_handler(add_type_handler)
    application.add_handler(CommandHandler("listtypes", list_types_command))
    application.add_handler(CommandHandler("deltype", delete_type_command))
    application.add_handler(CommandHandler("delitem", delete_item_command))
    application.add_handler(take_item_handler)
    application.add_handler(CommandHandler("free", free_item_command))
    application.add_handler(steal_item_handler)
    application.add_handler(CommandHandler("assign", assign_item_command))
    application.add_handler(CommandHandler("purge", purge_item_command))
    application.add_handler(CommandHandler("edititem", edit_item_command))
    application.add_handler(CommandHandler("noteset", note_set_command))
    application.add_handler(CommandHandler("notedrop", note_drop_command))
    application.add_handler(CommandHandler("addmod", add_moderator_command))
    application.add_handler(CommandHandler("delmod", remove_moderator_command))
    application.add_handler(CommandHandler("listmod", list_moderators_command))
    application.add_handler(CommandHandler("adduser", add_user_command))
    application.add_handler(CommandHandler("deluser", remove_user_command))
    application.add_handler(CommandHandler("listuser", list_users_command))
    application.add_handler(CommandHandler("addnotify", add_notify_command))
    application.add_handler(CommandHandler("delnotify", remove_notify_command))
    application.add_handler(CommandHandler("listnotify", list_notify_command))
    application.add_handler(CommandHandler("listhist", list_history_command))
    application.add_handler(CommandHandler("dbwipe", wipe_database_command))
    application.add_handler(CommandHandler("dbdump", dump_database_command))
    application.add_handler(batch_handler)

    # Set debug logging for telegram library only if debug flag is enabled
    if args.debug:
        logging.getLogger("telegram").setLevel(logging.DEBUG)
        logging.getLogger("telegram.vendor.ptb_urllib3.urllib3").setLevel(logging.DEBUG)
        logging.getLogger("urllib3").setLevel(logging.DEBUG)

    # Run the bot with improved error handling
    try:
        logger.info("Starting bot...")
        application.run_polling(drop_pending_updates=True)
    except Exception as e:
        logger.error(f"Bot crashed: {e}")
        raise


if __name__ == "__main__":
    main()
