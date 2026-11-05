"""Presentation-only compatibility for Orbitz-owned historical warning fields."""
from ui_language import ui

WARNING_IDS=(
    'workspace.historical.active_timer',
    'workspace.historical.legacy_duplicates',
    'workspace.historical.unreadable_duplicates',
    'workspace.historical.version_directory',
    'workspace.historical.version_unavailable',
    'workspace.historical.history_interrupted',
    'workspace.historical.history_record_unavailable',
    'workspace.dialogs.invoice_ui.history_check_error',
    'workspace.dialogs.invoice_ui.archive_warning',
    'workspace.dialogs.invoice_ui.profile_warning',
)


def warning_message(value):return ui.known_lines(value,WARNING_IDS)


def warning_messages(values):return [warning_message(value) for value in values]
