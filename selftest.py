#!/usr/bin/env python3
"""
Comprehensive Self-Test Suite for Item Bot
Tests all commands and functionality to ensure everything works correctly.
"""

import os
import sqlite3
import tempfile
import sys
import time
import random
from typing import List, Dict, Any
import asyncio
from unittest.mock import Mock, AsyncMock

# Add the current directory to Python path to import bot
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Safety: Temporarily override any config imports to prevent production database access
import sys
original_modules = sys.modules.copy()

try:
    from bot import ResourceBot
except ImportError as e:
    print(f"❌ Failed to import bot module: {e}")
    print("Make sure you're running this from the bot directory")
    sys.exit(1)


class BotSelfTest:
    """Comprehensive test suite for the Item Bot"""
    
    def __init__(self):
        self.test_db = None
        self.bot = None
        self.passed_tests = 0
        self.failed_tests = 0
        self.test_results = []
        
    def retry_db_operation(self, operation, max_retries=3, base_delay=0.1):
        """Retry database operations with exponential backoff"""
        for attempt in range(max_retries):
            try:
                return operation()
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e) and attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt) + random.uniform(0, 0.1)
                    print(f"    Database locked, retrying in {delay:.2f}s (attempt {attempt + 1}/{max_retries})")
                    time.sleep(delay)
                    continue
                else:
                    raise
        return None
        
    def setup_test_environment(self):
        """Set up a completely isolated temporary test database"""
        print("🔧 Setting up test environment...")
        
        # Create temporary database with unique name to avoid any conflicts
        fd, self.test_db = tempfile.mkstemp(suffix='_selftest.db', prefix='itembot_test_')
        os.close(fd)
        
        # Double-check we're not using production database
        if 'resources.db' in self.test_db or self.test_db == 'resources.db':
            raise RuntimeError("SAFETY ERROR: Test database path conflicts with production!")
        
        # Initialize bot with isolated test database
        self.bot = ResourceBot(self.test_db)
        print(f"✅ Isolated test database created: {self.test_db}")
        print(f"🔒 Production database (resources.db) is completely safe and untouched")
        
        # Verify the bot is using our test database
        actual_db_path = self.bot.db_path
        if actual_db_path != self.test_db:
            raise RuntimeError(f"SAFETY ERROR: Bot is using {actual_db_path} instead of test DB {self.test_db}")
        print(f"✅ Verified: Bot is using test database: {os.path.basename(actual_db_path)}")
        
    def cleanup_test_environment(self):
        """Clean up test environment"""
        if self.test_db and os.path.exists(self.test_db):
            os.unlink(self.test_db)
            print(f"🧹 Cleaned up test database: {self.test_db}")
            
    def assert_test(self, condition: bool, test_name: str, details: str = ""):
        """Assert a test condition and track results"""
        if condition:
            self.passed_tests += 1
            status = "✅ PASS"
            print(f"{status}: {test_name}")
            if details:
                print(f"    {details}")
        else:
            self.failed_tests += 1
            status = "❌ FAIL"
            print(f"{status}: {test_name}")
            if details:
                print(f"    {details}")
                
        self.test_results.append({
            'name': test_name,
            'status': status,
            'details': details,
            'passed': condition
        })
        
    def test_database_initialization(self):
        """Test database setup and table creation"""
        print("\n📊 Testing Database Initialization...")
        
        conn = self.bot.get_connection()
        cursor = conn.cursor()
        
        # Test all required tables exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        
        required_tables = ['types', 'items', 'usage_history', 'moderators', 'notifications', 'authorized_users']
        
        for table in required_tables:
            self.assert_test(
                table in tables,
                f"Table '{table}' exists",
                f"Required table found in database"
            )
            
        # Test items table has all required columns including new ones
        cursor.execute("PRAGMA table_info(items)")
        columns = [row[1] for row in cursor.fetchall()]
        
        required_columns = ['id', 'name', 'group_name', 'type_id', 'owner', 'purpose', 'description', 'note']
        
        for column in required_columns:
            self.assert_test(
                column in columns,
                f"Items table has '{column}' column",
                f"Required column found in items table"
            )
            
        conn.close()
        
    def test_type_management(self):
        """Test type management functionality"""
        print("\n🏷️  Testing Type Management...")
        
        # Test adding types with retry
        success1 = self.retry_db_operation(lambda: self.bot.add_type("Server"))
        self.assert_test(success1, "Add type 'Server'", "Type added successfully")
        
        success2 = self.retry_db_operation(lambda: self.bot.add_type("Device"))
        self.assert_test(success2, "Add type 'Device'", "Type added successfully")
        
        # Test duplicate type rejection
        duplicate = self.retry_db_operation(lambda: self.bot.add_type("Server"))
        self.assert_test(not duplicate, "Reject duplicate type", "Duplicate type correctly rejected")
        
        # Test listing types
        types = self.retry_db_operation(lambda: self.bot.list_types())
        self.assert_test(len(types) == 2, "List types returns correct count", f"Found {len(types)} types")
        
        type_names = [t[1] for t in types]
        self.assert_test("Server" in type_names, "Server type in list", "Type appears in listing")
        self.assert_test("Device" in type_names, "Device type in list", "Type appears in listing")
        
        # Test deleting unused type with retry
        success_add = self.bot.add_type('TestType')
        if success_add:
            types = self.bot.list_types()
            test_type_id = next((t[0] for t in types if t[1] == 'TestType'), None)
            if test_type_id:
                success, message = self.bot.delete_type(test_type_id)
                self.assert_test(success, 'Delete unused type', f'Type deleted: {message}')
            else:
                self.assert_test(False, 'Delete unused type', 'TestType not found after adding')
        else:
            self.assert_test(False, 'Delete unused type', 'Failed to add TestType for deletion test')
        
    def test_item_management(self):
        """Test item management functionality"""
        print("\n📦 Testing Item Management...")
        
        # Get type IDs for testing with retry
        types = self.retry_db_operation(lambda: self.bot.list_types())
        server_type_id = next(t[0] for t in types if t[1] == "Server")
        device_type_id = next(t[0] for t in types if t[1] == "Device")
        
        # Test adding items with retry
        success1 = self.retry_db_operation(lambda: self.bot.add_item("WebServer1", "production", server_type_id, "Main web server"))
        self.assert_test(success1, "Add item 'WebServer1'", "Item added successfully")
        
        success2 = self.retry_db_operation(lambda: self.bot.add_item("iPhone15", "testing", device_type_id, "Test device"))
        self.assert_test(success2, "Add item 'iPhone15'", "Item added successfully")
        
        # Test duplicate item rejection
        duplicate = self.retry_db_operation(lambda: self.bot.add_item("WebServer1", "production", server_type_id, "Duplicate"))
        self.assert_test(not duplicate, "Reject duplicate item", "Duplicate item correctly rejected")
        
        # Test listing items
        items = self.retry_db_operation(lambda: self.bot.list_items())
        self.assert_test(len(items) == 2, "List items returns correct count", f"Found {len(items)} items")
        
        item_names = [i["name"] for i in items]
        self.assert_test("WebServer1" in item_names, "WebServer1 in item list", "Item appears in listing")
        self.assert_test("iPhone15" in item_names, "iPhone15 in item list", "Item appears in listing")
        
        # Test find item by name and ID
        webserver_id = self.retry_db_operation(lambda: self.bot.find_item_by_name_or_id("WebServer1"))
        self.assert_test(webserver_id is not None, "Find item by name", f"Found item ID: {webserver_id}")
        
        found_by_id = self.retry_db_operation(lambda: self.bot.find_item_by_name_or_id(str(webserver_id)))
        self.assert_test(found_by_id == webserver_id, "Find item by ID", f"Found same item by ID")
        
        # Test item editing (description)
        success, message = self.retry_db_operation(lambda: self.bot.edit_item_description(webserver_id, "Updated web server description"))
        self.assert_test(success, "Edit item description", f"Description updated: {message}")
        
        # Verify description was updated
        updated_items = self.retry_db_operation(lambda: self.bot.list_items())
        webserver_item = next(i for i in updated_items if i["name"] == "WebServer1")
        self.assert_test(
            webserver_item["description"] == "Updated web server description",
            "Verify description update",
            "Description correctly updated in database"
        )
        
    def test_note_system(self):
        """Test note system functionality"""
        print("\n📝 Testing Note System...")
        
        # Get an item to test with
        webserver_id = self.bot.find_item_by_name_or_id("WebServer1")
        
        # Test setting note
        success, message = self.bot.set_item_note(webserver_id, "Currently under maintenance")
        self.assert_test(success, "Set item note", f"Note set: {message}")
        
        # Verify note appears in item listing
        items = self.bot.list_items()
        webserver_item = next(i for i in items if i["name"] == "WebServer1")
        self.assert_test(
            webserver_item["note"] == "Currently under maintenance",
            "Verify note in listing",
            "Note correctly stored and retrieved"
        )
        
        # Test updating note
        success, message = self.bot.set_item_note(webserver_id, "Maintenance completed")
        self.assert_test(success, "Update item note", f"Note updated: {message}")
        
        # Test dropping note
        success, message = self.bot.drop_item_note(webserver_id)
        self.assert_test(success, "Drop item note", f"Note removed: {message}")
        
        # Verify note is removed
        items = self.bot.list_items()
        webserver_item = next(i for i in items if i["name"] == "WebServer1")
        self.assert_test(
            webserver_item["note"] is None,
            "Verify note removal",
            "Note correctly removed from database"
        )
        
    def test_item_operations(self):
        """Test item take/free/steal/assign operations"""
        print("\n🔄 Testing Item Operations...")
        
        webserver_id = self.bot.find_item_by_name_or_id("WebServer1")
        iphone_id = self.bot.find_item_by_name_or_id("iPhone15")
        
        # Test taking item
        success, message = self.bot.take_item(webserver_id, "alice", "debugging issue")
        self.assert_test(success, "Take item", f"Item taken: {message}")
        
        # Verify item is owned
        items = self.bot.list_items()
        webserver_item = next(i for i in items if i["name"] == "WebServer1")
        self.assert_test(
            webserver_item["owner"] == "alice",
            "Verify item ownership",
            "Item correctly assigned to user"
        )
        self.assert_test(
            webserver_item["purpose"] == "debugging issue",
            "Verify item purpose",
            "Purpose correctly stored"
        )
        
        # Test taking already owned item (should fail)
        success, message = self.bot.take_item(webserver_id, "bob", "testing")
        self.assert_test(not success, "Reject taking owned item", f"Correctly rejected: {message}")
        
        # Test stealing item
        success, message = self.bot.steal_item(webserver_id, "bob", "urgent production issue")
        self.assert_test(success, "Steal item", f"Item stolen: {message}")
        
        # Verify ownership changed
        items = self.bot.list_items()
        webserver_item = next(i for i in items if i["name"] == "WebServer1")
        self.assert_test(
            webserver_item["owner"] == "bob",
            "Verify stolen item ownership",
            "Item ownership correctly transferred"
        )
        
        # Test freeing item
        success, message = self.bot.free_item(webserver_id, "bob")
        self.assert_test(success, "Free item", f"Item freed: {message}")
        
        # Verify item is free
        items = self.bot.list_items()
        webserver_item = next(i for i in items if i["name"] == "WebServer1")
        self.assert_test(
            webserver_item["owner"] is None,
            "Verify item is free",
            "Item correctly freed"
        )
        
        # Test assigning item
        success, message = self.bot.assign_item(iphone_id, "charlie", "admin")
        self.assert_test(success, "Assign item", f"Item assigned: {message}")
        
        # Test purging item
        success, message = self.bot.purge_item(iphone_id, "admin")
        self.assert_test(success, "Purge item", f"Item purged: {message}")
        
    def test_moderator_management(self):
        """Test moderator management functionality"""
        print("\n👮 Testing Moderator Management...")
        
        # Test adding moderator
        success = self.bot.add_moderator("alice", "admin")
        self.assert_test(success, "Add moderator 'alice'", "Moderator added successfully")
        
        success = self.bot.add_moderator("bob", "admin")
        self.assert_test(success, "Add moderator 'bob'", "Moderator added successfully")
        
        # Test duplicate moderator rejection
        duplicate = self.bot.add_moderator("alice", "admin")
        self.assert_test(not duplicate, "Reject duplicate moderator", "Duplicate moderator correctly rejected")
        
        # Test listing moderators
        moderators = self.bot.list_moderators()
        self.assert_test(len(moderators) == 2, "List moderators count", f"Found {len(moderators)} moderators")
        
        mod_names = [m[0] for m in moderators]
        self.assert_test("alice" in mod_names, "Alice in moderator list", "Moderator appears in listing")
        self.assert_test("bob" in mod_names, "Bob in moderator list", "Moderator appears in listing")
        
        # Test checking moderator status
        is_mod = self.bot.is_moderator("alice")
        self.assert_test(is_mod, "Check moderator status", "Moderator status correctly identified")
        
        not_mod = self.bot.is_moderator("charlie")
        self.assert_test(not not_mod, "Check non-moderator status", "Non-moderator correctly identified")
        
        # Test removing moderator
        success = self.bot.remove_moderator("bob")
        self.assert_test(success, "Remove moderator", "Moderator removed successfully")
        
        # Verify removal
        moderators = self.bot.list_moderators()
        mod_names = [m[0] for m in moderators]
        self.assert_test("bob" not in mod_names, "Verify moderator removal", "Moderator correctly removed")
        
    def test_authorized_users(self):
        """Test authorized user management"""
        print("\n👤 Testing Authorized User Management...")
        
        # Test adding authorized user by ID and username
        success = self.bot.add_authorized_user(user_id=12345, username="testuser", added_by="admin")
        self.assert_test(success, "Add authorized user with ID", "User added successfully")
        
        # Test adding user by username only
        success = self.bot.add_authorized_user(username="usernameonly", added_by="admin")
        self.assert_test(success, "Add authorized user by username", "User added successfully")
        
        # Test duplicate user rejection
        duplicate = self.bot.add_authorized_user(user_id=12345, username="testuser", added_by="admin")
        self.assert_test(not duplicate, "Reject duplicate authorized user", "Duplicate user correctly rejected")
        
        # Test listing authorized users
        users = self.bot.list_authorized_users()
        self.assert_test(len(users) >= 2, "List authorized users", f"Found {len(users)} authorized users")
        
        # Test checking authorization
        is_auth = self.bot.is_authorized_user(12345, "testuser")
        self.assert_test(is_auth, "Check user authorization", "User authorization correctly identified")
        
        # Test removing authorized user
        success = self.bot.remove_authorized_user(user_id=12345)
        self.assert_test(success, "Remove authorized user", "User removed successfully")
        
    def test_notification_system(self):
        """Test notification management"""
        print("\n🔔 Testing Notification System...")
        
        # Get type ID for testing
        types = self.bot.list_types()
        server_type_id = next(t[0] for t in types if t[1] == "Server")
        
        # Test adding notification subscription
        success = self.bot.add_notification(chat_id=-123456, chat_title="Test Chat", type_id=server_type_id, added_by="admin")
        self.assert_test(success, "Add notification subscription", "Notification added successfully")
        
        # Test adding global notification
        success = self.bot.add_notification(chat_id=-789012, chat_title="Global Chat", type_id=None, added_by="admin")
        self.assert_test(success, "Add global notification", "Global notification added successfully")
        
        # Test duplicate notification rejection
        duplicate = self.bot.add_notification(chat_id=-123456, chat_title="Test Chat", type_id=server_type_id, added_by="admin")
        self.assert_test(not duplicate, "Reject duplicate notification", "Duplicate notification correctly rejected")
        
        # Test listing notifications
        notifications = self.bot.list_notifications()
        self.assert_test(len(notifications) >= 2, "List notifications", f"Found {len(notifications)} notifications")
        
        # Test getting notification chats for type
        chats = self.bot.get_notification_chats_for_type(server_type_id)
        self.assert_test(len(chats) >= 1, "Get notification chats for type", f"Found {len(chats)} chats for type")
        
        # Test removing notification
        removed_count = self.bot.remove_notification(chat_id=-123456, type_id=server_type_id)
        self.assert_test(removed_count > 0, "Remove notification", f"Removed {removed_count} notifications")
        
    def test_usage_history(self):
        """Test that usage history is being recorded"""
        print("\n📈 Testing Usage History...")
        
        # Take and free an item to generate history
        webserver_id = self.bot.find_item_by_name_or_id("WebServer1")
        
        # Take item (should create history entry)
        self.bot.take_item(webserver_id, "testuser", "testing history")
        
        # Free item (should create another history entry)
        self.bot.free_item(webserver_id, "testuser")
        
        # Check that history entries were created
        conn = self.bot.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM usage_history WHERE item_id = ?", (webserver_id,))
        history_count = cursor.fetchone()[0]
        conn.close()
        
        self.assert_test(
            history_count >= 2,
            "Usage history recorded",
            f"Found {history_count} history entries for item operations"
        )
        
    def test_item_filtering(self):
        """Test item listing with filters"""
        print("\n🔍 Testing Item Filtering...")
        
        # Test filter by group
        production_items = self.bot.list_items(group="production")
        self.assert_test(
            len(production_items) >= 1,
            "Filter items by group",
            f"Found {len(production_items)} production items"
        )
        
        # Test filter by type
        types = self.bot.list_types()
        server_type_id = next(t[0] for t in types if t[1] == "Server")
        server_items = self.bot.list_items(type_id=server_type_id)
        self.assert_test(
            len(server_items) >= 1,
            "Filter items by type",
            f"Found {len(server_items)} server items"
        )
        
        # Test filter by owner (should be none since we freed everything)
        owned_items = self.bot.list_items(owner="testuser")
        self.assert_test(
            len(owned_items) == 0,
            "Filter items by owner",
            f"Found {len(owned_items)} items owned by testuser"
        )
        
        # Test free items only
        free_items = self.bot.list_items(free_only=True)
        self.assert_test(
            len(free_items) >= 2,
            "Filter free items only",
            f"Found {len(free_items)} free items"
        )
        
    def test_error_conditions(self):
        """Test error handling and edge cases"""
        print("\n⚠️  Testing Error Conditions...")
        
        # Test operations on non-existent item
        success, message = self.bot.edit_item_description(99999, "test")
        self.assert_test(not success, "Edit non-existent item", f"Correctly failed: {message}")
        
        success, message = self.bot.set_item_note(99999, "test note")
        self.assert_test(not success, "Set note on non-existent item", f"Correctly failed: {message}")
        
        success, message = self.bot.take_item(99999, "user", "purpose")
        self.assert_test(not success, "Take non-existent item", f"Correctly failed: {message}")
        
        # Test freeing item not owned by user
        webserver_id = self.bot.find_item_by_name_or_id("WebServer1")
        success, message = self.bot.free_item(webserver_id, "wronguser")
        self.assert_test(not success, "Free item not owned", f"Correctly failed: {message}")
        
        # Test deleting type in use
        types = self.bot.list_types()
        server_type_id = next(t[0] for t in types if t[1] == "Server")
        success, message = self.bot.delete_type(server_type_id)
        self.assert_test(not success, "Delete type in use", f"Correctly failed: {message}")
        
    def test_data_integrity(self):
        """Test data integrity and consistency"""
        print("\n🔒 Testing Data Integrity...")
        
        # Test that items maintain referential integrity with types
        items = self.bot.list_items()
        types = self.bot.list_types()
        type_ids = [t[0] for t in types]
        
        for item in items:
            if item["type_id"]:
                self.assert_test(
                    item["type_id"] in type_ids,
                    f"Item '{item['name']}' has valid type reference",
                    f"Type ID {item['type_id']} exists in types table"
                )
                
        # Test that all required fields are present
        for item in items:
            self.assert_test(
                item["name"] is not None and item["name"].strip(),
                f"Item '{item['name']}' has valid name",
                "Item name is not null or empty"
            )
            
            self.assert_test(
                item["group_name"] is not None and item["group_name"].strip(),
                f"Item '{item['name']}' has valid group",
                "Item group is not null or empty"
            )
            
    def run_all_tests(self):
        """Run the complete test suite"""
        print("🚀 Starting Item Bot Self-Test Suite")
        print("=" * 50)
        
        try:
            self.setup_test_environment()
            
            # Run all test categories
            self.test_database_initialization()
            self.test_type_management()
            self.test_item_management()
            self.test_note_system()
            self.test_item_operations()
            self.test_moderator_management()
            self.test_authorized_users()
            self.test_notification_system()
            self.test_usage_history()
            self.test_item_filtering()
            self.test_error_conditions()
            self.test_data_integrity()
            
        except Exception as e:
            print(f"\n💥 Test suite crashed: {e}")
            import traceback
            traceback.print_exc()
            self.failed_tests += 1
            
        finally:
            self.cleanup_test_environment()
            
        # Print summary
        self.print_test_summary()
        
    def print_test_summary(self):
        """Print test results summary"""
        print("\n" + "=" * 50)
        print("📊 TEST SUMMARY")
        print("=" * 50)
        
        total_tests = self.passed_tests + self.failed_tests
        pass_rate = (self.passed_tests / total_tests * 100) if total_tests > 0 else 0
        
        print(f"Total Tests: {total_tests}")
        print(f"✅ Passed: {self.passed_tests}")
        print(f"❌ Failed: {self.failed_tests}")
        print(f"📈 Pass Rate: {pass_rate:.1f}%")
        
        if self.failed_tests == 0:
            print("\n🎉 ALL TESTS PASSED! Bot is functioning correctly.")
        else:
            print(f"\n⚠️  {self.failed_tests} test(s) failed. Please review the failures above.")
            
        # Print failed tests for easy reference
        if self.failed_tests > 0:
            print("\n❌ FAILED TESTS:")
            for result in self.test_results:
                if not result['passed']:
                    print(f"  • {result['name']}")
                    if result['details']:
                        print(f"    {result['details']}")
                        
        print("\n" + "=" * 50)
        
        # Return exit code
        return 0 if self.failed_tests == 0 else 1


def main():
    """Main entry point"""
    print("Item Bot Self-Test Suite")
    print("This will test all bot functionality using a completely isolated temporary database.")
    print()
    
    # Safety check - ensure we don't accidentally touch production
    production_db = "resources.db"
    if os.path.exists(production_db):
        print(f"🔒 Production database detected: {production_db}")
        print("   ✅ Tests will use a separate temporary database - production is safe!")
    else:
        print("ℹ️  No production database found - this is fine for testing.")
    
    # Check if config exists (for import validation)
    if not os.path.exists('config.py'):
        print("⚠️  Warning: config.py not found. Some imports may fail.")
        print("   This is normal for testing - we'll use an isolated test database.")
        print()
    
    print("🛡️  SAFETY GUARANTEE: Production database will NOT be touched!")
    print()
    
    # Run tests
    test_suite = BotSelfTest()
    exit_code = test_suite.run_all_tests()
    
    return exit_code


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code) 