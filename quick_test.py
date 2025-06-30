#!/usr/bin/env python3
"""
Quick Test Suite for Item Bot
A simplified test that validates core functionality without database locking issues
"""

import os
import sys
import tempfile

# Add the current directory to Python path to import bot
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from bot import ResourceBot
except ImportError as e:
    print(f"❌ Failed to import bot module: {e}")
    print("Make sure you're running this from the bot directory")
    sys.exit(1)


def test_basic_functionality():
    """Test basic bot functionality without complex concurrent operations"""
    print("🚀 Item Bot Quick Test")
    print("=====================")
    print()

    # Create temporary database
    fd, test_db = tempfile.mkstemp(suffix="_quicktest.db", prefix="itembot_quick_")
    os.close(fd)

    try:
        print(f"🔧 Using test database: {os.path.basename(test_db)}")
        print("🔒 Production database is completely safe!")
        print()

        # Initialize bot
        bot = ResourceBot(test_db)

        # Test 1: Database initialization
        print("📊 Testing database initialization...")
        conn = bot.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()

        required_tables = ["types", "items", "usage_history", "moderators", "notifications", "authorized_users"]
        missing_tables = [t for t in required_tables if t not in tables]

        if missing_tables:
            print(f"❌ Missing tables: {missing_tables}")
            return False
        else:
            print("✅ All required tables exist")

        # Test 2: Type management
        print("\n🏷️ Testing type management...")

        # Add types
        if not bot.add_type("Server"):
            print("❌ Failed to add Server type")
            return False
        print("✅ Added Server type")

        if not bot.add_type("Device"):
            print("❌ Failed to add Device type")
            return False
        print("✅ Added Device type")

        # List types
        types = bot.list_types()
        if len(types) != 2:
            print(f"❌ Expected 2 types, got {len(types)}")
            return False
        print(f"✅ Listed {len(types)} types correctly")

        # Test 3: Item management
        print("\n📦 Testing item management...")

        server_type_id = next(t[0] for t in types if t[1] == "Server")
        device_type_id = next(t[0] for t in types if t[1] == "Device")

        # Add items
        if not bot.add_item("WebServer1", "production", server_type_id, "Main web server"):
            print("❌ Failed to add WebServer1")
            return False
        print("✅ Added WebServer1")

        if not bot.add_item("iPhone15", "testing", device_type_id, "Test device"):
            print("❌ Failed to add iPhone15")
            return False
        print("✅ Added iPhone15")

        # List items
        items = bot.list_items()
        if len(items) != 2:
            print(f"❌ Expected 2 items, got {len(items)}")
            return False
        print(f"✅ Listed {len(items)} items correctly")

        # Test 4: Item operations
        print("\n🔄 Testing item operations...")

        webserver_id = bot.find_item_by_name_or_id("WebServer1")
        if not webserver_id:
            print("❌ Failed to find WebServer1")
            return False
        print("✅ Found WebServer1 by name")

        # Take item
        success, message = bot.take_item(webserver_id, "testuser", "testing")
        if not success:
            print(f"❌ Failed to take item: {message}")
            return False
        print("✅ Successfully took item")

        # Free item
        success, message = bot.free_item(webserver_id, "testuser")
        if not success:
            print(f"❌ Failed to free item: {message}")
            return False
        print("✅ Successfully freed item")

        # Test 5: New features (edit description and notes)
        print("\n📝 Testing new features...")

        # Edit description
        success, message = bot.edit_item_description(webserver_id, "Updated description")
        if not success:
            print(f"❌ Failed to edit description: {message}")
            return False
        print("✅ Successfully edited item description")

        # Set note
        success, message = bot.set_item_note(webserver_id, "Test note")
        if not success:
            print(f"❌ Failed to set note: {message}")
            return False
        print("✅ Successfully set item note")

        # Verify note in listing
        items = bot.list_items()
        webserver_item = next(i for i in items if i["name"] == "WebServer1")
        if webserver_item["note"] != "Test note":
            print(f"❌ Note not found in listing: {webserver_item['note']}")
            return False
        print("✅ Note appears correctly in item listing")

        # Drop note
        success, message = bot.drop_item_note(webserver_id)
        if not success:
            print(f"❌ Failed to drop note: {message}")
            return False
        print("✅ Successfully dropped item note")

        # Test 6: User management
        print("\n👤 Testing user management...")

        # Add authorized user
        if not bot.add_authorized_user(user_id=12345, username="testuser", added_by="admin"):
            print("❌ Failed to add authorized user")
            return False
        print("✅ Added authorized user")

        # Check authorization
        if not bot.is_authorized_user(12345, "testuser"):
            print("❌ User authorization check failed")
            return False
        print("✅ User authorization verified")

        # Test 7: Moderator management
        print("\n👮 Testing moderator management...")

        # Add moderator
        if not bot.add_moderator("testmod", "admin"):
            print("❌ Failed to add moderator")
            return False
        print("✅ Added moderator")

        # Check moderator status
        if not bot.is_moderator("testmod"):
            print("❌ Moderator status check failed")
            return False
        print("✅ Moderator status verified")

        print("\n🎉 All core functionality tests passed!")
        print("✅ Your Item Bot is working correctly!")
        return True

    except Exception as e:
        print(f"\n💥 Test failed with error: {e}")
        import traceback

        traceback.print_exc()
        return False

    finally:
        # Clean up
        if os.path.exists(test_db):
            os.unlink(test_db)
            print("\n🧹 Cleaned up test database")


def main():
    """Main entry point"""
    print("Item Bot Quick Test Suite")
    print("Tests core functionality without database locking issues")
    print()

    # Safety check
    production_db = "resources.db"
    if os.path.exists(production_db):
        print(f"🔒 Production database detected: {production_db}")
        print("   ✅ Quick test will use a separate temporary database - production is safe!")

    print()

    success = test_basic_functionality()

    if success:
        print("\n🎉 QUICK TEST PASSED!")
        print("All essential bot features are working correctly.")
        return 0
    else:
        print("\n❌ QUICK TEST FAILED!")
        print("Some core functionality is not working properly.")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
