#!/usr/bin/python3
"""Exercise real GTK screens with disposable data; capture screenshots and a report.

Run with a graphical display (or a private Broadway session). Never uses real accounts.
"""
import argparse
from contextlib import ExitStack
from datetime import date, datetime, timedelta
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve();output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='orbitz-workspace-qa-') as folder:
        os.environ.update(XDG_DATA_HOME=folder+'/data', XDG_CONFIG_HOME=folder+'/config',
                          XDG_CACHE_HOME=folder+'/cache', GSETTINGS_BACKEND='memory', ORBITZ_LOCALE='pt-BR')
        sys.path.insert(0, str(ROOT/'app'))
        import gi
        gi.require_version('Gtk', '3.0')
        from gi.repository import Gtk, GLib, Gio
        import cairo
        import external_ui, workspace_ui, planner_tools, workspace_backup_ui
        import invoice_ui, invoice_history, invoice_signatures_ui, timesheet_context_ui
        import store, ui_state, timesheet, invoice_payments, external_store, ics_client, calendar_events
        from ui_language import ui
        errors=[];screens=[];queue=[]
        original_hook = sys.excepthook
        def exception_hook(typ, value, tb):
            errors.append(f'{typ.__name__}: {value}')
            original_hook(typ, value, tb)
        sys.excepthook = exception_hook
        def pump():
            context=GLib.MainContext.default()
            while context.pending():context.iteration(False)
        def widgets(widget, kind):
            result=[widget] if isinstance(widget,kind) else []
            if isinstance(widget,Gtk.Container):
                children=widget.get_children()
                if isinstance(widget,Gtk.Grid):
                    children.sort(key=lambda c:(widget.child_get_property(c,'top-attach'),widget.child_get_property(c,'left-attach')))
                for child in children:result.extend(widgets(child,kind))
            return result
        def shot(widget,name):
            pump()
            widget.check_resize()
            pump()
            width,height=widget.get_allocated_width(),widget.get_allocated_height()
            surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,width,height)
            widget.draw(cairo.Context(surface))
            surface.write_to_png(str(output/(name+'.png')))
            screens.append({'screen':name,'size':[width,height]})
        original_run=Gtk.Dialog.run
        def run(dialog):
            if not queue:raise AssertionError('Unexpected dialog: '+str(dialog.get_title()))
            name,action,response=queue.pop(0)
            def respond():
                try:
                    if action:action(dialog)
                    shot(dialog,name)
                    dialog.response(response)
                except Exception as error:
                    errors.append(name+': '+repr(error));dialog.response(Gtk.ResponseType.CANCEL)
                return False
            GLib.timeout_add(120,respond)
            return original_run(dialog)
        def modal(callback,name,action=None,response=Gtk.ResponseType.CANCEL):
            queue.append((name,action,response));callback();pump()
            assert not queue, 'Dialog did not open: '+name
        def choose(dialog,path):
            path=Path(path)
            dialog.set_current_folder(str(path.parent))
            if dialog.get_action()==Gtk.FileChooserAction.SAVE:
                dialog.set_current_name(path.name)
            else:dialog.set_filename(str(path))
            loop=GLib.MainLoop();GLib.timeout_add(150,lambda:(loop.quit(),False)[1]);loop.run()
        def entries(dialog,values):
            from date_time_fields import TimeField
            fields=widgets(dialog.get_content_area(),(Gtk.Entry,TimeField))
            assert len(fields)==len(values),(len(fields),values)
            for field,value in zip(fields,values):field.set_text(value)
        with ExitStack() as stack:
            # Networking has separate synthetic provider tests. No real account or request here.
            stack.enter_context(patch.object(external_ui.ExternalCalendars,'sync',return_value=None))
            stack.enter_context(patch.object(external_ui.ExternalCalendars,'run',return_value=None))
            stack.enter_context(patch.object(Gtk.Dialog,'run',run))
            spec=importlib.util.spec_from_file_location('workspace_app',ROOT/'app/calendar-app.py')
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            app=module.CalendarApp();app.set_flags(app.get_flags()|Gio.ApplicationFlags.NON_UNIQUE);assert app.register(None)
            notifications=stack.enter_context(patch.object(app,'send_notification',return_value=None))
            window=module.CalendarWindow(app);pump()
            brand=window.brand_footer
            assert brand.trigger.get_label()=='ORBITZ'
            brand.trigger.clicked();pump();assert not brand.active
            brand.entered(brand.panel);assert not brand.active
            brand.entered(brand.trigger);pump();assert brand.panel.get_mapped()
            bx,by=brand.translate_coordinates(window,0,0)
            bounds=brand.get_allocation()
            assert bx>=0 and by>=0 and bx+bounds.width<=window.get_allocated_width() and by+bounds.height<=window.get_allocated_height()
            assert not brand.paypal.get_sensitive()
            shot(window,'workspace-orbitz-footer')
            with patch('widget_footer.Gtk.show_uri_on_window') as launch:
                brand.github.clicked()
                assert launch.call_args.args[1]=='https://github.com/orbitzone'
            assert not brand.active

            app.notify_reminder(dict(id='qa-reminder',title='Lembrete QA',time='12:00',day=date.today().isoformat(),area='tasks'))
            assert notifications.call_args.args[0]=='qa-reminder'
            app.activate_action('open-reminder',GLib.Variant('s',date.today().isoformat()+'|tasks'))
            assert window.workspace.get_visible_child_name()=='tasks'
            try:
                for area in ('today','events','tasks','hours','invoices'):
                    window.show_area(area);pump();shot(window,'empty-'+area)
                    assert window.workspace.get_visible_child_name()==area
                modal(window.edit,'task-create',lambda d:entries(d,['Preparar entrega QA',date.today().isoformat(),'09:00','10']),Gtk.ResponseType.OK)
                assert len(window.data['tasks'])==1,window.status.get_text()
                task=window.data['tasks'][0]
                modal(lambda:window.edit(task),'task-edit',lambda d:entries(d,['Revisar entrega QA',date.today().isoformat(),'09:00','10']),Gtk.ResponseType.OK)
                assert window.data['tasks'][0]['text']=='Revisar entrega QA'
                modal(window.new_sheet,'sheet-create',lambda d:entries(d,['Projeto QA','Cliente fictício','Contrato QA','Produto']),Gtk.ResponseType.OK)
                sheet_id=next(s['id'] for s in window.data['timesheets'] if s['name']=='Projeto QA')
                page=window.sheet_pages[sheet_id]
                modal(lambda:window.rename_sheet(page),'sheet-context',response=Gtk.ResponseType.CANCEL)
                for key,value in [('description','Implementação QA'),('start','09:00'),('end','10:30')]:page.fields[key].set_text(value)
                page.save();assert len(page.sheet_data()['timesheet'])==1,page.message.get_text()
                entry=page.sheet_data()['timesheet'][0]
                fields=page.inline_widgets[entry['id']]
                fields['description'].set_text('Implementação e revisão QA');fields['description'].emit('activate')
                assert page.sheet_data()['timesheet'][0]['description']=='Implementação e revisão QA'
                for period in ('day','week','month'):
                    page.period.set_active_id(period);shot(window,'hours-'+period)
                page.fields['description'].set_text('Cronômetro QA')
                modal(page.timer_click,'timer-start',lambda d:entries(d,['Cronômetro QA']),Gtk.ResponseType.OK)
                assert page.sheet_data()['timesheet_active'],page.message.get_text()
                page.timer_click()
                if page.sheet_data()['timesheet_active']:
                    assert 'minuto' in page.message.get_text()
                real_modify=timesheet.modify_entries
                with patch.object(timesheet,'modify_entries',side_effect=lambda data,request,now=None:real_modify(data,request,now=datetime.now()+timedelta(minutes=2))):
                    page.timer_click()
                assert not page.sheet_data()['timesheet_active'],page.message.get_text()
                assert window.change({'action':'toggle','id':task['id']})
                task=window.data['tasks'][0]
                def register_hours(dialog):
                    widgets(dialog.get_content_area(),Gtk.ComboBoxText)[0].set_active_id(sheet_id)
                    entries(dialog,['11:00','12:00'])
                modal(lambda:window.register_task(task),'task-register-hours',register_hours,Gtk.ResponseType.OK)
                assert any(e.get('source_task_id')==task['id'] for e in page.sheet_data()['timesheet'])
                modal(lambda:window.open_task_records(task),'task-linked-records')
                window.show_area('tasks');shot(window,'tasks-populated')
                window.focus_sheet(sheet_id)
                queue.extend([('csv-period',None,Gtk.ResponseType.OK),
                              ('csv-save',lambda d:choose(d,Path(folder)/'hours.csv'),Gtk.ResponseType.OK)])
                page.export();assert not queue
                assert (Path(folder)/'hours.csv').read_text(encoding='utf-8-sig').find('Implementação e revisão QA')>=0
                # A synthetic cached calendar exercises agenda rendering without HTTP or credentials.
                account=ics_client.account('Calendário QA','https://example.test/qa.ics')
                external_store.add_account(account);calendar=account['calendars'][0]
                day=date.today();stamp=day.strftime('%Y%m%d')
                raw=f'BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:qa-event\r\nDTSTART:{stamp}T160000\r\nDTEND:{stamp}T170000\r\nSUMMARY:Reunião QA\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n'.encode()
                events=calendar_events.normalize_events(raw,account['id'],calendar['id'],day,day+timedelta(days=1))
                external_store.put_cache(account['id'],calendar,day.strftime('%Y-%m'),events,datetime.now().astimezone().isoformat())
                window.external.populate(account['id']+'|'+calendar['id']);window.external.selection_changed()
                window.show_area('events');shot(window,'calendar-cached-event')
                assert any('Reunião QA' in label.get_text() for label in widgets(window.external.rows,Gtk.Label))
                modal(lambda:window.external.import_task(events[0],account,calendar),'calendar-import-task',response=Gtk.ResponseType.OK)
                assert any(task.get('external_source') for task in window.data['tasks'])
                window.focus_sheet(sheet_id)
                def invoice_fields(dialog):
                    values={'reference':'QA-001','issued_on':date.today().isoformat(),'issuer_name':'Emitente QA','issuer_tax_id':'00000000000','client_name':'Cliente QA','client_tax_id':'00000000000','rate':'100','currency':'BRL'}
                    # Use the real dialog's field captions through its accessible names.
                    for field in widgets(dialog.get_content_area(),Gtk.Entry):
                        name=field.get_accessible().get_name() or ''
                        mapping={'Referência':'reference','Data de emissão':'issued_on','Nome do emitente':'issuer_name','CPF/CNPJ do emitente':'issuer_tax_id','Nome do destinatário':'client_name','CPF/CNPJ do destinatário':'client_tax_id','Valor por hora':'rate','Moeda':'currency'}
                        for label,key in mapping.items():
                            if label.casefold() in name.casefold():field.set_text(values[key]);break
                    # Stable order of invoice text entries (before the period year spin button).
                    fields=[f for f in widgets(dialog.get_content_area(),Gtk.Entry) if not isinstance(f,Gtk.SpinButton)]
                    for field,value in zip(fields,values.values()):field.set_text(value)
                    widgets(dialog.get_content_area(),Gtk.TextView)[0].get_buffer().set_text('Endereço QA')
                queue.extend([('invoice-form',invoice_fields,Gtk.ResponseType.APPLY),
                              ('invoice-preview',lambda d: (_ for _ in ()).throw(AssertionError('Preview unavailable')) if not d.get_widget_for_response(Gtk.ResponseType.OK).get_sensitive() else None,Gtk.ResponseType.OK),
                              ('invoice-save',lambda d:choose(d,Path(folder)/'invoice.pdf'),Gtk.ResponseType.ACCEPT)])
                invoice_ui.open_invoice(window);assert not queue
                assert (Path(folder)/'invoice.pdf').read_bytes().startswith(b'%PDF')
                window.show_area('invoices');window.invoice_refresh();shot(window,'invoices-history')
                history=invoice_history.list_records();records=history['records'];assert records and not history['errors']
                tree=widgets(window.invoice_container,Gtk.TreeView)[0]
                tree.expand_all();tree.get_selection().select_path(Gtk.TreePath.new_from_string('0:0:0:0'))
                def history_button(key):
                    label=ui.tr('workspace.dialogs.invoice_history_ui.'+key)
                    return next(b for b in widgets(window.invoice_container,Gtk.Button) if b.get_label()==label)
                modal(history_button('payment').clicked,'invoice-payment',response=1)
                assert invoice_payments.get(records[0]['id'])['status']=='reported_paid'
                shot(window,'invoice-paid')
                modal(lambda:invoice_signatures_ui.show_versions(window,records[0]),'invoice-versions')
                modal(lambda:invoice_signatures_ui.add_version(window,records[0]),'invoice-import-signed')
                modal(lambda:invoice_signatures_ui.sign_invoice(window,lambda *a,**k:None),'invoice-sign')
                modal(window.external.connect_apple,'connect-icloud')
                modal(window.external.connect_google,'connect-google')
                modal(window.external.connect_calendly,'connect-calendly')
                modal(window.external.connect_subscription,'connect-ics')
                modal(window.external.manage,'manage-connections')
                def preferences(dialog):
                    combos=widgets(dialog.get_content_area(),Gtk.ComboBoxText)
                    combos[0].set_active_id('hours');combos[1].set_active_id('en-US')
                modal(lambda:workspace_ui.open_preferences(window),'preferences',preferences,Gtk.ResponseType.OK)
                assert ui_state.get('workspace-start-area')=='hours'
                assert ui.get_locale()=='en-US'
                window.show_area('today');shot(window,'today-english')
                ui.refresh('pt-BR')
                queue.extend([('backup-export-confirm',None,Gtk.ResponseType.OK),
                              ('backup-export-save',lambda d:choose(d,Path(folder)/'workspace.zip'),Gtk.ResponseType.ACCEPT)])
                workspace_backup_ui.export_backup(window);assert not queue
                assert (Path(folder)/'workspace.zip').is_file(),window.status.get_text()
                queue.extend([('backup-restore-file',lambda d:choose(d,Path(folder)/'workspace.zip'),Gtk.ResponseType.ACCEPT),
                              ('backup-restore-preview',None,Gtk.ResponseType.CANCEL)])
                workspace_backup_ui.restore_backup(window);assert not queue
                modal(lambda:workspace_backup_ui.restore_backup(window),'backup-restore-choose')
                modal(lambda:planner_tools.open_backups(window),'backup-legacy')
                modal(lambda:window.archive_sheet(page),'sheet-archive-confirm',response=Gtk.ResponseType.YES)
                assert sheet_id not in window.sheet_pages
                modal(window.open_archived,'sheet-archive-list')
                # Delete confirmation must also render correctly; cancel preserves the record.
                window.show_area('invoices');window.invoice_refresh()
                tree.expand_all();tree.get_selection().select_path(Gtk.TreePath.new_from_string('0:0:0:0'))
                modal(history_button('delete').clicked,'invoice-delete-confirm')
                assert invoice_history.list_records()['records']
                modal(lambda:planner_tools.view_archive(window,sheet_id),'sheet-archive-view')
                for area in ('today','events','hours','invoices'):
                    window.show_area(area);shot(window,'final-'+area)
                # Restore the exported state through the real UI; the application closes by design.
                before_tasks=len(window.data['tasks'])
                window.change({'action':'task','text':'Alteração posterior ao backup','date':date.today().isoformat()})
                assert len(window.data['tasks'])==before_tasks+1
                queue.extend([('backup-restore-apply-file',lambda d:choose(d,Path(folder)/'workspace.zip'),Gtk.ResponseType.ACCEPT),
                              ('backup-restore-apply-confirm',None,Gtk.ResponseType.OK),
                              ('backup-restore-result',None,Gtk.ResponseType.CLOSE)])
                workspace_backup_ui.restore_backup(window);assert not queue
                assert len(store.modify({'action':'get'})['tasks'])==before_tasks
                assert not errors,errors
            finally:
                window.external.executor.shutdown(wait=True,cancel_futures=True)
                window.destroy();pump()
        report={'application':'Orbitz Workspace','screens':screens,'errors':errors,'scope':'Real GTK widgets with temporary local data; network and external services excluded.'}
        (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps({'screens':len(screens),'errors':errors,'report':str(output/'report.json')}))

if __name__=='__main__':main()
