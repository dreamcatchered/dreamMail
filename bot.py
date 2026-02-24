import subprocess
import sys
import time
import os
import signal

def run_process(script_name):
    # Use sys.executable to ensure we use the same python interpreter
    # cwd ensures we run in the script's directory
    return subprocess.Popen(
        [sys.executable, script_name], 
        cwd=os.path.dirname(os.path.abspath(__file__)),
        # On Windows, we might want to use creationflags to avoid new windows popping up if run from GUI,
        # but for terminal usage, default is fine.
    )

def main():
    print("🚀 Starting Mail System...")
    
    # Start App
    print("📝 Launching Web App (app.py)...")
    app_process = run_process('app.py')
    
    # Start Bot
    print("🤖 Launching Telegram Bot (bot1.py)...")
    bot_process = run_process('bot1.py')
    
    print("✅ System is running. Press Ctrl+C to stop.")
    
    try:
        while True:
            time.sleep(1)
            # Check if processes are still alive
            if app_process.poll() is not None:
                print(f"❌ app.py stopped unexpectedly with code {app_process.returncode}!")
                break
            if bot_process.poll() is not None:
                print(f"❌ bot1.py stopped unexpectedly with code {bot_process.returncode}!")
                break
    except KeyboardInterrupt:
        print("\n🛑 Stopping system...")
    finally:
        # Graceful shutdown
        print("Shutting down processes...")
        
        if app_process.poll() is None:
            app_process.terminate()
        
        if bot_process.poll() is None:
            bot_process.terminate()
            
        # Wait a bit for graceful exit
        try:
            app_process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            app_process.kill()
            
        try:
            bot_process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            bot_process.kill()
            
        print("👋 Goodbye!")

if __name__ == '__main__':
    main()
