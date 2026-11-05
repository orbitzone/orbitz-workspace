# Orbitz Workspace — independent application

Repository: https://github.com/orbitzone/orbitz-workspace

Current development checkout: `/home/felipe/Documents/Codex/projects/orbitz-workspace`.
Compatibility links at `/home/felipe/Documents/ChatGPT/orbitz-workspace` and
`/home/felipe/Documents/ChatGPT/Calendars, timesheets and invoices` point here.
Workspace and Widgets for GNOME are sibling repositories under `projects/`,
not nested checkouts.

## Source of truth

- Main application: `app/calendar-app.py`.
- Preferences: `app/workspace_ui.py`, `app/widget_preferences.py`.
- Desktop clock and weather: `app/desktop_widget.py` and `app/widget_*.py`.
- Launcher: `data/orbitz-workspace`.
- Desktop application ID: `io.orbitz.Workspace`.
- Local application data: `$XDG_DATA_HOME/orbitz-workspace`.
- User installation: `~/.local/share/orbitz-workspace`.

Calendar, tasks, timesheets, invoices, settings, weather and the desktop widget
are maintained here. No GNOME Shell extension is loaded or installed. GTK is a
runtime library; it does not require GNOME Shell as the desktop environment.
X11/Wayland placement differences remain documented in the README.

The original planner extraction is retained as provenance and license credit,
not as a runtime dependency. Do not implement Workspace changes in the old
`orbitz-widgets-for-gnome/extension/planner` checkout.

## Development

Run `./data/orbitz-workspace`, test with `make test`, and install with
`make install PREFIX="$HOME/.local"`. Credentials and personal application data
are excluded from version control. Public release packaging and validation are
separate from creating the independent source repository.
