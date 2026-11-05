"""Calendar header actions, sharing the existing archive and backup callbacks."""
from ui_language import ui
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
import planner_tools
import workspace_backup_ui
import workspace_ui


def add_header(container, window):
    header = ui.widget(Gtk.Box,spacing=8)
    window.heading = ui.widget(Gtk.Label,xalign=0, hexpand=True)
    header.pack_start(window.heading, True, True, 0)
    button = ui.widget(Gtk.MenuButton,)
    button.add(Gtk.Image.new_from_icon_name('open-menu-symbolic', Gtk.IconSize.BUTTON))
    ui.call(button,'set_tooltip_text',ui.msg('workspace.planner_menu.mais_acoes_do_workspace'))
    ui.call(button.get_accessible(),'set_name',ui.msg('workspace.planner_menu.mais_acoes_do_workspace'))
    menu = ui.widget(Gtk.Menu,)
    actions = [
        (ui.msg('workspace.dialogs.planner_menu.archive'), window.open_archived),
        (ui.msg('workspace.dialogs.planner_menu.export'), lambda *_: workspace_backup_ui.export_backup(window)),
        (ui.msg('workspace.dialogs.planner_menu.restore'), lambda *_: workspace_backup_ui.restore_backup(window)),
        (ui.msg('workspace.dialogs.planner_menu.legacy'), lambda *_: planner_tools.open_backups(window)),
        (ui.msg('workspace.dialogs.planner_menu.preferences'), lambda *_: workspace_ui.open_preferences(window)),
    ]
    for label, callback in actions:
        item = ui.widget(Gtk.MenuItem,label=label)
        item.connect('activate', callback)
        menu.append(item)
        if callback == window.open_archived:
            window.archived_button = item
    menu.show_all()
    button.set_popup(menu)
    header.pack_end(button, False, False, 0)
    container.pack_start(header, False, False, 0)
    return button


def update_archive_count(window):
    count = sum(bool(sheet['archived']) for sheet in window.data.get('timesheets', []))
    label = ui.msg('workspace.dialogs.planner_menu.archive_count', count=count)
    ui.call(window.archived_button,'set_label',label)
    ui.call(window.archived_button.get_accessible(),'set_name',label)
