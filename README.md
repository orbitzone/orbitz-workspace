# Orbitz Workspace

![Orbitz Workspace icon](data/icons/hicolor/128x128/apps/io.orbitz.Workspace.png)

A native Linux workspace for calendars, tasks, time tracking and service invoices.
Orbitz Workspace is a standalone GTK application with its own repository:
[orbitzone/orbitz-workspace](https://github.com/orbitzone/orbitz-workspace).
It runs independently of GNOME Shell extensions.

This repository is the source of truth for the Workspace application, its
preferences and desktop widget. Development does not require a checkout or
installation of Widgets for GNOME.

- Browse external calendars and local activities together.
- Manage tasks and independent timesheets, including timers and archived records.
- Receive reminders for tasks and cached events while the app is open.
- Generate service invoice PDFs, track payments and retain invoice history.
- Export and restore Workspace backups.
- Switch between Brazilian Portuguese and English in preferences.
- Add a customizable desktop clock, date and weather widget without a GNOME Shell extension.

## Run

On Debian/Ubuntu, runtime dependencies are Python 3.10+, `python3-gi`,
`gir1.2-gtk-3.0`, `gir1.2-secret-1`, `python3-defusedxml`,
`python3-reportlab`, `python3-cairo`, `python3-gi-cairo`, `gir1.2-pango-1.0`,
`tzdata`, `python3-xlib`, and `fonts-dejavu-core`. A desktop Secret Service is required
for connected-account credentials. Calendar parsing libraries and their licenses
are bundled under `app/vendor`.

Run `./data/orbitz-workspace` from this checkout. Use `make test` for regression checks.
To install for your user, run `make install PREFIX="$HOME/.local"` and ensure
`$HOME/.local/bin` is on PATH. A graphical GTK session is required.

## Desktop widget

Open **Preferences → Add widget to desktop**. Content, appearance and placement
controls appear together with a live preview. Select a city from online search or
enter coordinates, choose °C/°F, PT/EN, a time zone, 12/24-hour time and date formats.
Customize visible weather details, fonts, sizes, colors, alpha transparency, border,
corners and widget dimensions. Save to apply; Cancel keeps the current configuration.

Click the clock/date to open Workspace; click weather for the seven-day forecast.
Hold Super and drag with the left mouse button to move the widget. With the pointer
over the widget, Ctrl+T shows a rounded resize frame with eight handles. Drag a
handle to scale all elements proportionally; Done, Esc or Ctrl+T confirms the size. Right-click also
provides forecast, resize, customization, refresh, lock and removal actions. The widget runs independently when the main window
closes. Starting it at login is optional and is enabled only by its dedicated checkbox.
Weather is refreshed in a background worker, with a labeled cached forecast when offline.
Preview weather is explicitly marked as example data.

The widget uses GTK and a normal, unpinned X11/XWayland window; it does not require GNOME
Shell or a Shell extension. It follows normal window stacking so its visible surface receives mouse input.
Native Wayland may ignore absolute positioning or sticky placement requests. Hover-scoped shortcuts and modifier-drag use X11/XWayland;
the right-click Resize action remains available on other backends. A compositor is needed for transparent backgrounds.
The native source runtime requires Python 3.10+ (Ubuntu 22.04 or newer is the initial
target); compatibility with every historical Ubuntu release is not claimed.

Weather data: [Open-Meteo](https://open-meteo.com/), CC BY 4.0;
location search: [GeoNames via Open-Meteo](https://open-meteo.com/en/docs/geocoding-api).
The configured coordinates are sent to the weather provider. City search sends your
search text only when you press Search. The free provider's non-commercial terms
must be reviewed before any commercial distribution.

## Existing Workspace data

The app stores its own data in `$XDG_DATA_HOME/orbitz-workspace` (default:
`~/.local/share/orbitz-workspace`). It does not modify the Widgets installation.
To transfer data, stop timers, export a Workspace backup in the old app, then
restore it through this app's backup menu after reviewing the preview. Credentials
are not included in backups. Reconnect accounts after restoring a backup from Widgets.
Credentials use dedicated Orbitz Workspace Secret Service schemas.
Local tasks and hours work offline.

Google authorization currently retains the inherited Desktop client configuration.
A separately owned OAuth client and provider review are release prerequisites.
Private client configuration belongs in `$XDG_CONFIG_HOME/orbitz-workspace/google-client.json`.
Never put credentials in the repository.

Service invoices are not electronic tax documents. This initial extraction is a
development version; public packaging and release validation are still pending.

## License and credits

Derived from the planner subsystem of Orbitz Widgets for GNOME.
The inherited GPL-3.0 license is preserved in `LICENSE`.
Bundled third-party notices and licenses remain in `app/vendor`.
