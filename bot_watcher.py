#!/usr/bin/env python3
"""
Bot Auto-Restart Watcher
This script monitors bot.py for changes and automatically restarts it.
"""

import os
import sys
import time
import signal
import subprocess
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class BotRestartHandler(FileSystemEventHandler):
    def __init__(self, bot_script, bot_process=None):
        self.bot_script = bot_script
        self.bot_process = bot_process
        self.restart_pending = False
        
    def on_modified(self, event):
        if event.is_directory:
            return
            
        # Check if the modified file is our bot script
        if event.src_path.endswith('bot.py'):
            print(f"\n🔄 Detected change in {event.src_path}")
            if not self.restart_pending:
                self.restart_pending = True
                # Small delay to avoid multiple rapid restarts
                time.sleep(1)
                self.restart_bot()
                self.restart_pending = False
    
    def restart_bot(self):
        if self.bot_process and self.bot_process.poll() is None:
            print("🛑 Stopping bot to restart...")
            # Gracefully terminate the bot
            self.bot_process.terminate()
            try:
                self.bot_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                print("⚠️  Bot didn't stop gracefully, force killing...")
                self.bot_process.kill()
                self.bot_process.wait()
            # Wait an additional 3 seconds to ensure proper termination
            print("⏳ Waiting 3 seconds to ensure proper termination...")
            time.sleep(3)
        elif self.bot_process is None:
            print("🔄 Bot was already stopped, starting fresh...")
        else:
            print("🔄 Bot was already stopped, restarting...")
        
        print("🚀 Starting bot...")
        self.bot_process = subprocess.Popen([sys.executable, self.bot_script])
        print(f"✅ Bot started with PID {self.bot_process.pid}")
    
    def set_process(self, process):
        self.bot_process = process

def main():
    # Get the directory where this script is located
    script_dir = Path(__file__).parent.absolute()
    bot_script = script_dir / "bot.py"
    
    if not bot_script.exists():
        print(f"❌ Error: {bot_script} not found!")
        sys.exit(1)
    
    print(f"👀 Watching for changes in {script_dir}")
    print(f"🤖 Bot script: {bot_script}")
    print("Press Ctrl+C to stop the watcher\n")
    
    # Start the bot initially
    print("🚀 Starting bot for the first time...")
    bot_process = subprocess.Popen([sys.executable, str(bot_script)])
    print(f"✅ Bot started with PID {bot_process.pid}\n")
    
    # Set up file system watcher
    event_handler = BotRestartHandler(str(bot_script), bot_process)
    observer = Observer()
    observer.schedule(event_handler, str(script_dir), recursive=False)
    
    def signal_handler(signum, frame):
        print("\n🛑 Shutting down watcher...")
        observer.stop()
        if bot_process and bot_process.poll() is None:
            print("🛑 Stopping bot...")
            bot_process.terminate()
            try:
                bot_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                bot_process.kill()
                bot_process.wait()
        print("👋 Goodbye!")
        sys.exit(0)
    
    # Handle Ctrl+C gracefully
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Start watching
    observer.start()
    
    try:
        while True:
            time.sleep(1)
            # Check if bot process died unexpectedly (but don't restart)
            if bot_process and bot_process.poll() is not None:
                print("⚠️  Bot process died unexpectedly. Waiting for file changes to restart...")
                # Set bot_process to None so we know it's dead
                bot_process = None
                event_handler.set_process(None)
    except KeyboardInterrupt:
        signal_handler(signal.SIGINT, None)
    finally:
        observer.stop()
        observer.join()

if __name__ == "__main__":
    main()

