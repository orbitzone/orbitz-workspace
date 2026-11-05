"""Read-only archive viewer and recoverable backup restoration UI."""
from ui_language import ui
from datetime import date
import hashlib
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk
import store,timesheet as model
from timesheet_ui import Timesheet

def view_archive(window,identity,parent=None):
    latest=store.modify({'action':'get'});sheet=model.get_sheet(latest,identity)
    dialog=ui.widget(Gtk.Dialog,title=ui.msg('workspace.dialogs.planner_tools.view_title', name=sheet['name']),transient_for=parent or window,modal=True)
    ui.button(dialog,ui.msg('workspace.dialogs.planner_tools.close'),Gtk.ResponseType.CLOSE);dialog.set_default_size(1050,650)
    dialog.data=latest;dialog.day=window.day;dialog.status=ui.widget(Gtk.Label,xalign=0)
    content=ui.widget(Gtk.Box,spacing=16,margin=16);dialog.get_content_area().pack_start(content,True,True,0)
    calendar=ui.widget(Gtk.Calendar,);chosen=date.fromisoformat(dialog.day)
    calendar.select_month(chosen.month-1,chosen.year);calendar.select_day(chosen.day)
    left=ui.widget(Gtk.Box,orientation=Gtk.Orientation.VERTICAL,spacing=10);left.pack_start(calendar,False,False,0)
    left.pack_start(ui.widget(Gtk.Label,label=ui.msg('workspace.dialogs.planner_tools.read_only'),xalign=0),False,False,0);content.pack_start(left,False,False,0)
    page=Timesheet(dialog,identity,readonly=True);content.pack_start(page,True,True,0)
    dialog.render=page.render
    def selected(*_):
        year,month,day=calendar.get_date();dialog.day=date(year,month+1,day).isoformat();page.render()
    calendar.connect('day-selected',selected)
    def source(identity):
        task=next((t for t in latest['tasks'] if t['id']==identity),None)
        info=ui.widget(Gtk.MessageDialog,transient_for=dialog,modal=True,message_type=Gtk.MessageType.INFO,buttons=Gtk.ButtonsType.CLOSE,text=ui.msg('workspace.dialogs.planner_tools.original_task'))
        ui.call(info, 'format_secondary_text', task['text'] + '\n' + task['date'] if task else ui.msg('workspace.dialogs.planner_tools.removed_task'))
        info.run();info.destroy()
    dialog.open_source_task=source;page.render();dialog.show_all();dialog.run();dialog.destroy()

def open_backups(window,*_):
    dialog=ui.widget(Gtk.Dialog,title=ui.msg('workspace.dialogs.planner_tools.restore'),transient_for=window,modal=True)
    ui.buttons(dialog,ui.msg('workspace.dialogs.planner_tools.close'),Gtk.ResponseType.CLOSE,ui.msg('workspace.dialogs.planner_tools.restore_selected'),Gtk.ResponseType.OK)
    dialog.set_default_size(720,520);dialog.set_default_response(Gtk.ResponseType.CLOSE)
    box=ui.widget(Gtk.Box,orientation=Gtk.Orientation.VERTICAL,spacing=12,margin=18);dialog.get_content_area().add(box)
    box.add(ui.widget(Gtk.Label,label=ui.msg('workspace.dialogs.planner_tools.restore_warning'),xalign=0,wrap=True))
    combo=ui.widget(Gtk.ComboBoxText,);box.pack_start(combo,False,False,0)
    for name in store.list_backups():combo.append(name,name.removesuffix('.json'))
    scroll=ui.widget(Gtk.ScrolledWindow,);scroll.set_policy(Gtk.PolicyType.AUTOMATIC,Gtk.PolicyType.AUTOMATIC);box.pack_start(scroll,True,True,0)
    preview=ui.widget(Gtk.TextView,editable=False,cursor_visible=False,wrap_mode=Gtk.WrapMode.WORD_CHAR);scroll.add(preview)
    error=ui.widget(Gtk.Label,xalign=0,wrap=True);box.pack_end(error,False,False,0);selection={}
    def changed(*_):
        selection.clear();dialog.set_response_sensitive(Gtk.ResponseType.OK,False)
        name=combo.get_active_id()
        if not name:ui.call(preview.get_buffer(), 'set_text', ui.msg('workspace.dialogs.planner_tools.none'));return
        try:
            current=store.modify({'action':'get'});path=store.backup_file(name);raw=path.read_bytes();backup=store.read(path)
            a,b=store.summary(current),store.summary(backup)
            lines=[ui.msg('workspace.dialogs.planner_tools.preview')]
            for key,title in [('tasks',ui.msg('workspace.dialogs.planner_tools.tasks')),('sheets',ui.msg('workspace.dialogs.planner_tools.sheets')),('entries',ui.msg('workspace.dialogs.planner_tools.entries')),('active',ui.msg('workspace.dialogs.planner_tools.timers'))]:lines.append(ui.msg('workspace.dialogs.planner_tools.count_change', title=title, before=a[key], after=b[key]))
            lines.append(ui.msg('workspace.dialogs.planner_tools.hours')+model.duration(a['minutes'])+' → '+model.duration(b['minutes']))
            lines.append(ui.msg('workspace.dialogs.planner_tools.note_count', before=a['notes'], after=b['notes']))
            lines.append(ui.msg('workspace.dialogs.planner_tools.sheets_heading'))
            for sheet in backup['timesheets']:
                lines.append('TS - '+sheet['name']+(ui.msg('workspace.dialogs.planner_tools.archived') if sheet['archived'] else '')+ui.msg('workspace.dialogs.planner_tools.entry_count', count=len(sheet['timesheet']))+model.duration(model.total(sheet['timesheet'])))
                for entry in sheet['timesheet'][:10]:lines.append(f"  {entry['date']} {entry['start']}–{entry['end']} · {entry['description']}")
            lines.append(ui.msg('workspace.dialogs.planner_tools.tasks_heading'))
            for task in backup['tasks'][:30]:lines.append(task['date']+' · '+task['text'])
            ui.call(preview.get_buffer(), 'set_text', ui.join('\n', lines))
            selection.update(name=name,expected=store.fingerprint(current),backup_hash=hashlib.sha256(raw).hexdigest())
            dialog.set_response_sensitive(Gtk.ResponseType.OK,True);ui.call(error, 'set_text', '')
        except Exception as failure:ui.call(error, 'set_text', ui.error_message(failure))
    combo.connect('changed',changed);combo.set_active(0);changed();dialog.show_all()
    while dialog.run()==Gtk.ResponseType.OK:
        if not selection:continue
        confirm=ui.widget(Gtk.MessageDialog,transient_for=dialog,modal=True,message_type=Gtk.MessageType.WARNING,buttons=Gtk.ButtonsType.OK_CANCEL,text=ui.msg('workspace.dialogs.planner_tools.restore_confirm'))
        confirm.set_default_response(Gtk.ResponseType.CANCEL)
        ui.call(confirm, 'format_secondary_text', ui.msg('workspace.dialogs.planner_tools.restore_detail'))
        answer=confirm.run();confirm.destroy()
        if answer!=Gtk.ResponseType.OK:continue
        try:
            window.data=store.modify(dict(action='backup_restore',**selection));window.render();ui.call(window.status, 'set_text', ui.msg('workspace.dialogs.planner_tools.restored'));break
        except Exception as failure:ui.call(error, 'set_text', ui.error_message(failure))
    dialog.destroy()
