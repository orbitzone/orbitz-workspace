# Workspace / Widgets for GNOME integration boundary

## Checkouts

Both repositories live under `/home/felipe/Documents/Codex/projects/`:

| Folder | Repository | Responsibility |
| --- | --- | --- |
| `orbitz-workspace` | `orbitzone/orbitz-workspace` | Independent GTK application, calendars, tasks, hours, invoices and its own desktop widget |
| `orbitz-widgets-for-gnome` | `orbitzone/orbitz-widgets-for-gnome` | GNOME Shell extension, GSettings, Shell widgets, collectors and Shell panels |

The older `extension/planner` copy is historical source, not the current
Workspace application. Workspace now includes the Content/Appearance/Position
preferences with preview. The migration map in the GNOME checkout describes
that checkout; its statements about not finding the independent app predate
this folder alignment.

## Invariants for upcoming integration

- Each project keeps its own Git history, launcher, installation and data ownership.
- Workspace must start and run without the extension, its schema or its source tree.
- Do not directly import GJS/St/Clutter modules into the GTK app.
- Define explicit, versioned messages or adapters before sharing runtime behavior.
- Do not give both processes write access to the same settings/financial store.
- Transfer user settings through a reviewed migration with backup and validation;
  do not overwrite either application's live data during source migration.
- Integration must fail gracefully if the other application is absent or stopped.
- Validate Workspace alone, Widgets alone and then both together. X11/Wayland
  behavior must be tested separately; folder alignment is not runtime validation.

No new cross-application protocol or data migration is introduced by this setup.
The GNOME checkout currently contains uncommitted changes and is left untouched.

## Paths and installation

Old ChatGPT paths remain symlinks for existing chats and scripts. Use canonical
`projects/orbitz-workspace` paths for new work. The installed app remains at
`~/.local/share/orbitz-workspace`; the user launcher and data paths do not change.
