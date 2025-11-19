import asyncio
import os
import subprocess
import psutil
import sqlite3
import time
from pathlib import Path

# =============== CONFIGURATION ===============

# Define productive and distracting apps
whitelist = ["code", "libreoffice", "gedit", "google-docs", "gnome-terminal"]
blacklist = ["firefox", "chrome", "vlc", "spotify", "youtube"]

# Hosts file and blocked websites file
HOSTS_PATH = "/etc/hosts"
REDIRECT_IP = "127.0.0.1"
BLOCK_FILE = Path(__file__).parent / "blocked_sites.txt"

# Database file
DB_FILE = Path(__file__).parent / "focus_db.sqlite"

# =============== HELPER FUNCTIONS ===============

def get_active_app():
    """
    Detect currently active application.
    Uses xdotool + xprop primarily, falls back to psutil if fails.
    Returns app name as lowercase string.
    """
    try:
        # Try xdotool/xprop method first
        window_id = subprocess.check_output(["xdotool", "getactivewindow"], stderr=subprocess.DEVNULL).decode().strip()
        wm_class = subprocess.check_output(["xprop", "-id", window_id, "WM_CLASS"], stderr=subprocess.DEVNULL).decode().strip()
        # Extract only the app name (second string in WM_CLASS)
        app_name = wm_class.split(',')[-1].replace('"', '').strip().lower()
        return app_name
    except Exception:
        # Fallback: psutil method (detects active process with highest CPU)
        try:
            procs = [(p.info["name"].lower(), p.info["cpu_percent"]) for p in psutil.process_iter(["name", "cpu_percent"])]
            procs.sort(key=lambda x: x[1], reverse=True)
            if procs:
                return procs[0][0]
        except Exception:
            pass
    return "unknown"

def apply_focus_policies(mode):
    """Adjust system behavior based on mode."""
    try:
        if mode == "distracted":
            # Hide dock, mute sound, disable notifications
            subprocess.call(["gsettings", "set", "org.gnome.shell.extensions.dash-to-dock", "autohide", "true"])
            subprocess.call(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "1"])
            print("[ACTION] Dock hidden, audio muted.")
        elif mode == "productive":
            # Show dock, unmute sound
            subprocess.call(["gsettings", "set", "org.gnome.shell.extensions.dash-to-dock", "autohide", "false"])
            subprocess.call(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "0"])
            print("[ACTION] Dock visible, audio unmuted.")
    except Exception as e:
        print(f"[ERROR] Failed to apply focus policy: {e}")


def block_websites():
    """Add blocked sites to /etc/hosts."""
    try:
        with open(BLOCK_FILE, "r") as f:
            blocked = [line.strip() for line in f if line.strip()]

        with open(HOSTS_PATH, "r") as f:
            content = f.read()

        with open(HOSTS_PATH, "a") as f:
            for site in blocked:
                if site not in content:
                    f.write(f"{REDIRECT_IP} {site}\n")

        print("[INFO] Websites blocked successfully.")
    except PermissionError:
        print("[ERROR] Permission denied. Run this script with sudo.")
    except Exception as e:
        print(f"[ERROR] Failed to block websites: {e}")


def unblock_websites():
    """Remove blocked sites from /etc/hosts."""
    try:
        with open(BLOCK_FILE, "r") as f:
            blocked = [line.strip() for line in f if line.strip()]

        with open(HOSTS_PATH, "r") as f:
            lines = f.readlines()

        with open(HOSTS_PATH, "w") as f:
            for line in lines:
                if not any(site in line for site in blocked):
                    f.write(line)

        print("[INFO] Websites unblocked successfully.")
    except Exception as e:
        print(f"[ERROR] Failed to unblock websites: {e}")


def init_db():
    """Initialize SQLite DB for logging focus sessions."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS focus_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            app_name TEXT,
            mode TEXT,
            timestamp TEXT
        )
    """)
    conn.commit()
    conn.close()


def log_session(app_name, mode):
    """Insert a new session record."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO focus_log (app_name, mode, timestamp) VALUES (?, ?, ?)",
                   (app_name, mode, time.strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

# =============== MAIN ASYNC LOOP ===============

async def focus_daemon():
    """Main daemon loop: monitors active app and enforces focus policies."""
    print("[START] Focus Mode Daemon Running...\n")
    init_db()

    current_mode = None

    while True:
        app_name = get_active_app()
        print(f"[INFO] Active app: {app_name}")

        if any(name in app_name for name in blacklist):
            if current_mode != "distracted":
                print("[MODE] Distracting app detected — enforcing Focus Mode.")
                block_websites()
                apply_focus_policies("distracted")
                log_session(app_name, "distracted")
                current_mode = "distracted"

        elif any(name in app_name for name in whitelist):
            if current_mode != "productive":
                print("[MODE] Productive app detected — relaxing policies.")
                unblock_websites()
                apply_focus_policies("productive")
                log_session(app_name, "productive")
                current_mode = "productive"

        else:
            print("[MODE] Neutral app — no major policy change.")

        await asyncio.sleep(3)

# =============== ENTRY POINT ===============

if __name__ == "__main__":
    try:
        asyncio.run(focus_daemon())
    except KeyboardInterrupt:
        print("\n[STOP] Focus Mode Daemon Stopped.")
        unblock_websites()
        apply_focus_policies("productive")