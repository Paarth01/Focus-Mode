# Focus Mode

Focus Mode is a productivity daemon for Ubuntu desktops that keeps you on task by watching the active window, blocking distracting websites/apps, and logging your focus habits. The project now includes both the original CLI daemon and a Tkinter desktop GUI that sits on top of the same core logic.

---

## Features

- **Active App Monitoring**: Detects the current foreground application via `xdotool`/`xprop` (with a psutil fallback) and categorises it as productive, distracting, or neutral.
- **Automatic Enforcement**: Terminates blacklisted apps, toggles GNOME shell docks, mutes audio, and updates `/etc/hosts` with entries from `blocked_sites.txt` to block websites.
- **Session Logging**: Records mode transitions to `focus_db.sqlite` for later analytics.
- **GUI Command Center**: Tkinter UI (Home / Session Settings / Logs) to start/stop Focus Mode, edit durations, manage blocked sites, and review recent sessions.
- **Configurable Lists**: `config.yaml` controls productive/distracting apps; `blocked_sites.txt` lists hostnames to redirect.

---

## Requirements

- Ubuntu with Xorg (Wayland not yet supported).
- Python 3.10+ (recommended).
- System tools: `xdotool`, `xprop`, `gsettings`, `pactl` (already available on standard Ubuntu desktops).
- Permissions to edit `/etc/hosts` (run with sudo if needed).

Python dependencies come from the standard library (`asyncio`, `tkinter`, `sqlite3`, etc.) plus `psutil`. Install them via:

```bash
python3 -m pip install psutil
```

---

## Project Structure

```
Focus-Mode-main/
├── main.py              # core daemon and exported start/stop helpers
├── gui/
│   ├── gui.py           # Tkinter GUI entrypoint
│   └── __init__.py
├── blocked_sites.txt    # newline-separated hostnames to block
├── config.yaml          # productive/distracting app configuration
├── focus_db.sqlite      # SQLite log (auto-created)
└── README.md
```

---

## Setup

1. Clone or copy the repository to your Ubuntu machine.
2. (Optional) Create a virtual environment and install `psutil`.
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install psutil
   ```
3. Ensure `blocked_sites.txt` and `config.yaml` contain the apps/sites you care about.
4. The first run of the daemon or GUI auto-creates `focus_db.sqlite`.

---

## Running the CLI Daemon

```bash
python3 main.py
```

The daemon will:

- Loop every ~3 seconds, checking the active app.
- Apply blocking/unblocking policies depending on whether the app matches the whitelist or blacklist.
- Log transitions into the SQLite database.

Stop the daemon with `Ctrl+C`. Cleanup runs automatically (websites unblocked, policies reset).

> **Note:** Writing to `/etc/hosts` requires elevated permissions. Run `sudo python3 main.py` if you see permission errors when blocking websites.

---

## Running the GUI

```bash
python3 gui/gui.py
```

### Home Screen
- **Start Focus Mode / Stop Focus Mode** buttons wrap the daemon’s exported `start_focus_mode()` and `stop_focus_mode()` helpers.
- **Session Overview** shows the current status, blocking mode, elapsed time, and a progress bar that moves toward the configured focus duration.

### Session Settings
- **Focus Duration** input writes to `config.yaml` (`focus_duration` key) and updates the home screen goal.
- **Blocked Websites** listbox is backed by `blocked_sites.txt`. Add/remove entries and save to persist.

### Logs & Analytics
- Displays last recorded session timestamp, total productive time today, and completed productive sessions.
- Shows the 10 most recent entries from `focus_db.sqlite`.
- Includes a `Refresh Logs` button in case you start/stop sessions while the window stays open.

> The GUI dynamically imports the functions from `main.py` and doesn’t reimplement blocking logic, so behaviour stays consistent between CLI and GUI.

---

## Configuration Files

- `config.yaml`
  ```yaml
  focus_duration: 25        # minutes, used by the GUI progress indicator
  productive_apps:
    - code
    - libreoffice
  distracting_apps:
    - youtube
    - spotify
  ```

- `blocked_sites.txt`

  Each non-empty, non-comment line is written into `/etc/hosts` while Focus Mode is in the “distracted” state. Example:
  ```
  youtube.com
  www.youtube.com
  ```

Changes take effect immediately when the daemon next evaluates state.

---

## Data & Analytics

- `focus_db.sqlite` table `focus_log` keeps `(app_name, mode, timestamp)` rows.
- The GUI calculates:
  - **Last session timestamp** (latest entry).
  - **Total focus time today** (aggregating productive spans).
  - **Sessions completed** (count of productive entries).

Feel free to open the DB with any SQLite viewer for custom analysis.

---

## Troubleshooting

| Issue | Possible Fix |
| ----- | ------------ |
| `ModuleNotFoundError: No module named 'main'` when running GUI | Ensure you launch from the project root (`python3 gui/gui.py`). The GUI prepends the root to `sys.path`, but running from a different directory can break it. |
| “Permission denied” editing `/etc/hosts` | Run the daemon/GUI with elevated privileges or adjust your blocking strategy. |
| GUI does not launch | Confirm you are on an Xorg session. Tkinter requires an X display. |
| No logs showing | Ensure `focus_db.sqlite` is writable; delete it to reset if corrupted. |

---

## Contributing

1. Fork or branch the repository.
2. Make changes, keeping the core blocking logic inside `main.py`.
3. Run linting/tests (if available) and update this README if behaviour changes.
4. Submit a PR with a clear description.

---

## License

See `LICENSE` for details. Feel free to adapt Focus Mode for personal productivity setups. Contributions are welcome!*** End Patch

