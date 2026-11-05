"""Workspace navigation and today's read-only overview, independent of storage."""
from ui_language import ui
from datetime import date

AREAS = [('today', ui.msg('workspace.live.area_today')), ('events', ui.msg('workspace.live.area_events')), ('tasks', ui.msg('workspace.live.area_tasks')), ('hours', ui.msg('workspace.live.area_hours')), ('invoices', ui.msg('workspace.live.area_invoices'))]


def context_message(sheet):
    context = sheet.get('context', {})
    values = [sheet['name']]
    for key, title in [('client_name', ui.msg('workspace.live.context_client_name')), ('project_contract', ui.msg('workspace.live.context_project_contract')),
            ('department_costcenter', ui.msg('workspace.live.context_department_costcenter'))]:
        if context.get(key):
            values.append(title + ': ' + context[key])
    return ui.join(' · ',values)


def context_text(sheet):return str(context_message(sheet))


def today_message(data, events=(), today=None):
    today = today or date.today().isoformat()
    pending = [task for task in data.get('tasks', []) if not task.get('done')]
    due = [task for task in pending if task['date'] == today]
    overdue = sorted((task for task in pending if task['date'] < today), key=lambda task: task['date'])
    lines = [ui.msg('workspace.live.today_heading', date=ui.date_text(today)), '',
        ui.msg('workspace.live.today_events', count=len(events))]
    lines.extend('• ' + event.get('title', '') for event in events[:10])
    lines += ['', ui.msg('workspace.live.today_pending', pending=len(pending), due=len(due))]
    lines.extend('• ' + task['text'] for task in due[:10])
    lines += ['', ui.msg('workspace.live.today_overdue', count=len(overdue))]
    lines.extend('• ' + ui.date_text(task['date']) + ' · ' + task['text'] for task in overdue[:10])
    active = [sheet for sheet in data.get('timesheets', []) if sheet.get('timesheet_active')]
    lines += ['', ui.msg('workspace.live.today_timers', count=len(active))]
    for sheet in active:
        timer = sheet['timesheet_active']
        lines.append(ui.msg('workspace.live.today_active', name=sheet['name'], description=timer['description'], started=ui.date_text(timer['started'],'datetime')))
    return ui.join('\n',lines)


def today_text(data,events=(),today=None):return str(today_message(data,events,today))


class AgendaMount:
    """External calendar UI still mounts its page through the small existing API."""
    def __init__(self, container):
        self.container = container

    def append_page(self, page, _label):
        self.container.pack_start(page, True, True, 0)
        return 0


def add_navigation(container, window):
    from gi.repository import Gtk, Pango
    title = ui.widget(Gtk.Label,label=ui.msg('workspace.workspace_ui.orbitz_workspace'), xalign=0)
    title.get_style_context().add_class('title')
    subtitle = ui.widget(Gtk.Label,label=ui.msg('workspace.workspace_ui.agenda_tarefas_horas_e_faturamento'), xalign=0, wrap=True)
    container.pack_start(title, False, False, 0)
    container.pack_start(subtitle, False, False, 0)
    stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.NONE)
    switcher = Gtk.StackSwitcher(stack=stack, halign=Gtk.Align.START)
    ui.call(switcher.get_accessible(),'set_name',ui.msg('workspace.workspace_ui.areas_do_orbitz_workspace'))
    nav_scroll = Gtk.ScrolledWindow()
    nav_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
    nav_scroll.add(switcher)
    container.pack_start(nav_scroll, False, False, 0)
    context = Gtk.Label(xalign=0, wrap=True, selectable=True)
    context.set_max_width_chars(70)
    context.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
    container.pack_start(context, False, False, 0)
    container.pack_start(stack, True, True, 0)
    return stack, context


def flush_drafts(window, remove_source):
    for page in window.sheet_pages.values():
        if not page.readonly and not page.persist():
            return False
        if page.persist_timer:
            remove_source(page.persist_timer);page.persist_timer = 0
    return True


def quiesce(window, remove_source):
    # Drafts were flushed before inspect_backup; no write may follow its CAS token.
    window.restoring = True
    window.syncing_tabs = True
    for page in window.sheet_pages.values():
        page.readonly = True
        page.cleanup()
    if hasattr(window, 'external'):
        window.external.cleanup()
        window.external.executor.shutdown(wait=True, cancel_futures=True)
    if window.timer:
        remove_source(window.timer);window.timer = 0


def open_preferences(window):
    from gi.repository import Gtk
    import ui_state
    dialog = ui.widget(Gtk.Dialog,title=ui.msg('workspace.workspace_ui.preferencias_do_orbitz_workspace'), transient_for=window, modal=True)
    ui.buttons(dialog,ui.msg('workspace.workspace_ui.cancelar'), Gtk.ResponseType.CANCEL, ui.msg('workspace.workspace_ui.salvar'), Gtk.ResponseType.OK)
    dialog.set_default_size(960, 690)
    dialog.set_resizable(True)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin=18)
    scroll=Gtk.ScrolledWindow()
    scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC)
    dialog.get_content_area().pack_start(scroll,True,True,0)
    scroll.add(box)
    box.add(ui.widget(Gtk.Label,label=ui.msg('workspace.workspace_ui.area_inicial_do_workspace'), xalign=0))
    choice = Gtk.ComboBoxText()
    for key, title in AREAS:ui.combo_append(choice,key,title)
    choice.set_active_id(ui_state.get('workspace-start-area','today'))
    box.add(choice)
    box.add(ui.widget(Gtk.Label, label=ui.msg('workspace.preferences.language'), xalign=0))
    language = Gtk.ComboBoxText()
    language.append('pt-BR', 'Português (Brasil)')
    language.append('en-US', 'English (US)')
    language.set_active_id(ui.get_locale())
    box.add(language)
    box.add(ui.widget(Gtk.Label,label=ui.msg('workspace.reminders.open_app'),xalign=0,wrap=True,max_width_chars=48))
    from widget_preferences import WidgetPreferences
    import widget_control
    try:widget_settings=WidgetPreferences()
    except (ValueError,OSError) as error:
        dialog.destroy();ui.call(window.status,'set_text',ui.msg('workspace.widget.invalid',reason=str(error)));return
    box.add(widget_settings)
    def sync_widget_language(*_):
        widget_settings.fields['language'].set_active_id(language.get_active_id() or 'pt-BR')
    language.connect('changed',sync_widget_language)
    def resize_preferences(*_):
        dialog.resize(960 if widget_settings.enabled.get_active() else 520,
                      690 if widget_settings.enabled.get_active() else 400)
    widget_settings.enabled.connect('toggled',resize_preferences)
    if not widget_settings.enabled.get_active():dialog.set_default_size(520,400)
    error_label=Gtk.Label(xalign=0,wrap=True);box.add(error_label)
    dialog.show_all()
    try:
        while dialog.run() == Gtk.ResponseType.OK:
            try:config=widget_settings.value()
            except ValueError as error:
                ui.call(error_label,'set_text',ui.msg('workspace.widget.invalid',reason=str(error)));continue
            widget_control.apply(config)
            ui_state.set('workspace-start-area',choice.get_active_id() or 'today')
            ui_state.set('ui-language', language.get_active_id() or 'pt-BR')
            ui.refresh(language.get_active_id() or 'pt-BR')
            ui.call(window.status,'set_text',ui.msg('workspace.widget.saved'))
            break
    except Exception as failure:ui.call(window.status,'set_text',ui.error_message(failure))
    finally:dialog.destroy()
