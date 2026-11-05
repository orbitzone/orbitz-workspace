"""Editable timesheet work context, independent of fiscal invoice recipients."""
from ui_language import ui
import store

CONTEXT_FIELDS = [('client_name', ui.msg('workspace.live.context_client')),
    ('project_contract', ui.msg('workspace.live.context_project')),
    ('department_costcenter', ui.msg('workspace.live.context_department'))]


def context_payload(name, values, identity=None):
    context = {key: values.get(key, '').strip() for key, _title in CONTEXT_FIELDS}
    payload = {'action': 'sheet_update' if identity else 'sheet_create', 'name': name.strip(), 'context': context}
    if identity:
        payload['sheet_id'] = identity
    return payload


def edit_context(window, sheet=None):
    from gi.repository import Gtk
    sheet = sheet or {}
    dialog = ui.widget(Gtk.Dialog,title=ui.msg('workspace.live.edit_context') if sheet else ui.msg('workspace.live.new_timesheet'), transient_for=window, modal=True)
    ui.buttons(dialog,ui.msg('workspace.timesheet_context_ui.cancelar'), Gtk.ResponseType.CANCEL, ui.msg('workspace.timesheet_context_ui.salvar'), Gtk.ResponseType.OK)
    dialog.set_default_size(540, 420)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin=18)
    dialog.get_content_area().add(box)
    fields = {}
    for key, title, value, limit in [('name', ui.msg('workspace.live.sheet_name'), sheet.get('name', ''), 80),
            *[(key, title, sheet.get('context', {}).get(key, ''), 200) for key, title in CONTEXT_FIELDS]]:
        label = ui.widget(Gtk.Label,label=title, xalign=0, wrap=True)
        entry = Gtk.Entry(text=value, hexpand=True)
        entry.set_max_length(limit)
        ui.call(entry.get_accessible(),'set_name',title)
        box.add(label);box.add(entry);fields[key] = entry
    box.add(ui.widget(Gtk.Label,label=ui.msg('workspace.timesheet_context_ui.este_contexto_identifica_o_trabalho_os_dados_fiscais_do_destinatario_sao_revisad'),
        xalign=0, wrap=True))
    error = Gtk.Label(xalign=0, wrap=True)
    box.add(error)
    dialog.show_all();fields['name'].grab_focus()
    try:
        while dialog.run() == Gtk.ResponseType.OK:
            try:
                before = {value['id'] for value in window.data.get('timesheets', [])}
                window.data = store.modify(context_payload(fields['name'].get_text(),
                    {key: fields[key].get_text() for key, _title in CONTEXT_FIELDS}, sheet.get('id')))
                identity = sheet.get('id') or next(value['id'] for value in window.data['timesheets'] if value['id'] not in before)
                window.render();window.focus_sheet(identity)
                ui.call(window.status,'set_text',ui.msg('workspace.timesheet_context_ui.contexto_da_timesheet_salvo_neste_computador'))
                break
            except Exception as failure:
                ui.call(error,'set_text',ui.error_message(failure))
    finally:
        dialog.destroy()
