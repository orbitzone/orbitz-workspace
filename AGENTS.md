# Orbitz Workspace

This is the independent Orbitz Workspace repository, not the planner copy inside
Widgets for GNOME. Start with README.md and docs/standalone-project.md.

Canonical checkout: `/home/felipe/Documents/Codex/projects/orbitz-workspace`.
Sibling integration source: `../orbitz-widgets-for-gnome` (separate Git repository).
Old ChatGPT folder names are compatibility symlinks, not separate copies.

Keep changes for Workspace here. Do not silently edit, commit, reset or overwrite
work in the sibling repository. Preserve its uncommitted changes. Integration
must keep Workspace runnable without GNOME Shell and keep credentials and
personal application data out of either repository.

Run `make test` for regression checks. Relevant graphical checks are in tools/qa-*.py
and use disposable data. Read docs/integration-boundary.md before cross-project work.
