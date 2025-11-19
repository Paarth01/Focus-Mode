import asyncio
import os
import subprocess
import psutil
import fcntl
import sqlite3
import time
import threading
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

# Threading primitives for GUI/start-stop control
_daemon_thread = None
_daemon_lock = threading.Lock()
_stop_event = None

# =============== HELPER FUNCTIONS ===============

def _quiet_run(command):
    """Run a shell command while suppressing stdout/stderr noise."""
    subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


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
            procs = []
            for proc in psutil.process_iter(["name", "cpu_percent"]):
                name = proc.info.get("name")
                if not name:
                    continue
                cpu = proc.info.get("cpu_percent") or 0
                procs.append((name.lower(), cpu))

            procs.sort(key=lambda x: x[1], reverse=True)
            if procs:
                return procs[0][0]
        except Exception:
            pass
    return "unknown"


def terminate_app(app_keyword):
    """Stop any running process whose name contains app_keyword."""
    killed = False
    for proc in psutil.process_iter(["name"]):
        name = proc.info.get("name")
        if not name:
            continue
        if app_keyword in name.lower():
            try:
                proc.terminate()
                killed = True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

    if killed:
        print(f"[ACTION] Terminated processes containing '{app_keyword}'.")

def apply_focus_policies(mode):
    """Adjust system behavior based on mode."""
    try:
        if mode == "distracted":
            # Hide dock, mute sound, disable notifications
            _quiet_run(["gsettings", "set", "org.gnome.shell.extensions.dash-to-dock", "autohide", "true"])
            _quiet_run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "1"])
            print("[ACTION] Dock hidden, audio muted.")
        elif mode == "productive":
            # Show dock, unmute sound
            _quiet_run(["gsettings", "set", "org.gnome.shell.extensions.dash-to-dock", "autohide", "false"])
            _quiet_run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "0"])
            print("[ACTION] Dock visible, audio unmuted.")
    except Exception as e:
        print(f"[ERROR] Failed to apply focus policy: {e}")


def block_websites():
    """Add blocked sites to /etc/hosts to redirect them to localhost."""
    try:
        if not BLOCK_FILE.exists():
            BLOCK_FILE.touch()

        with open(BLOCK_FILE, "r") as bf:
            blocked_sites = [line.strip() for line in bf if line.strip() and not line.startswith("#")]

        if not blocked_sites:
            print("[INFO] No websites listed in blocked_sites.txt — skipping.")
            return

        with open(HOSTS_PATH, "r+") as f:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                existing_lines = {line.strip() for line in f.readlines()}
                f.seek(0, os.SEEK_END)

                for site in blocked_sites:
                    entry = f"{REDIRECT_IP} {site}"
                    if entry not in existing_lines:
                        f.write(entry + "\n")
                        print(f"[BLOCK] {site} -> {REDIRECT_IP}")
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    except PermissionError:
        print("[ERROR] Run with sudo or use user-space DNS blocking")
    except Exception as e:
        print(f"[ERROR] Failed to block websites: {e}")


def unblock_websites():
    """Remove blocked sites from /etc/hosts."""
    try:
        if not BLOCK_FILE.exists():
            print("[INFO] No blocked_sites.txt found — nothing to unblock.")
            return

        with open(BLOCK_FILE, "r") as f:
            blocked = [line.strip() for line in f if line.strip() and not line.startswith("#")]

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

async def focus_daemon(stop_event=None):
    """Main daemon loop: monitors active app and enforces focus policies."""
    print("[START] Focus Mode Daemon Running...\n")
    init_db()

    current_mode = None

    try:
        while True:
            if stop_event and stop_event.is_set():
                print("[STOP] Focus Mode stop requested.")
                break

            app_name = get_active_app()
            print(f"[INFO] Active app: {app_name}")

            if any(name in app_name for name in blacklist):
                for name in blacklist:
                    if name in app_name:
                        terminate_app(name)
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
    finally:
        unblock_websites()
        apply_focus_policies("productive")
        print("[CLEANUP] Focus Mode policies reset.")


def _run_daemon(stop_event):
    asyncio.run(focus_daemon(stop_event))


def start_focus_mode():
    """Start the focus daemon in a background thread."""
    global _daemon_thread, _stop_event

    with _daemon_lock:
        if _daemon_thread and _daemon_thread.is_alive():
            return False

        _stop_event = threading.Event()
        _daemon_thread = threading.Thread(target=_run_daemon, args=(_stop_event,), daemon=True)
        _daemon_thread.start()
        return True


def stop_focus_mode():
    """Signal the focus daemon to stop and wait for cleanup."""
    global _daemon_thread, _stop_event

    with _daemon_lock:
        if not _daemon_thread or not _daemon_thread.is_alive():
            return False

        _stop_event.set()
        _daemon_thread.join()
        _daemon_thread = None
        _stop_event = None
        return True


def is_focus_mode_running():
    """Return True if the background focus daemon is active."""
    return _daemon_thread is not None and _daemon_thread.is_alive()

# =============== ENTRY POINT ===============

if __name__ == "__main__":
    try:
        asyncio.run(focus_daemon())
    except KeyboardInterrupt:
        print("\n[STOP] Focus Mode Daemon Stopped.")
