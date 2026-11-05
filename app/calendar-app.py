#!/usr/bin/python3
from date_time_fields import TimeField,attach_date_picker
"""Calendar and tasks in an independent native GTK window."""
from ui_language import ui
import sys
from pathlib import Path
from datetime import date
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,Gio,GLib,Pango
import store
import ui_state
import reminders
from day_activity import local_detail_messages
from datetime import timedelta
import planner_tools
import planner_menu
import task_timesheet_ui
import workspace_ui
import invoice_ui
import invoice_history_ui
import timesheet_context_ui
from external_ui import ExternalCalendars
from month_calendar import MonthCalendar
from timesheet_ui import Timesheet
import timesheet as timesheet_model

class CalendarWindow(Gtk.ApplicationWindow):
    def __init__(self,app):
        super().__init__(application=app,title=ui.tr('workspace.calendar_app.orbitz_workspace'))
        ui.set(self,'title',ui.msg('workspace.calendar_app.orbitz_workspace'))
        self.set_default_size(1100,1000);self.set_size_request(700,420)
        self.day=date.today().isoformat();self.data={'tasks':[]};self.timer=0;self.syncing_tabs=False
        self.last_tab='today';self.selected_sheet_id=None;self.restoring=False
        self.reminders=reminders.ReminderService(app.notify_reminder, ui_state)
        outer=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=14,margin=20)
        self.main_overlay=Gtk.Overlay();self.add(self.main_overlay);self.main_overlay.add(outer)
        row=Gtk.Box(spacing=22);outer.pack_start(row,True,True,0)
        left=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12);row.pack_start(left,False,False,0)
        self.calendar=MonthCalendar();left.pack_start(self.calendar,False,False,0)
        today=ui.widget(Gtk.Button,label=ui.msg('workspace.calendar_app.hoje'));today.connect('clicked',lambda *_:self.show_area('today',reset_day=True));left.pack_start(today,False,False,0)
        self.calendar.connect('day-selected',self.day_selected)
        self.calendar.connect('month-changed',lambda *_:self.mark_days())
        right=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12);row.pack_start(right,True,True,0)
        self.actions_menu=planner_menu.add_header(right,self)
        self.workspace,self.context_label=workspace_ui.add_navigation(right,self)
        task_page=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10)
        header=Gtk.Box(spacing=12);task_page.pack_start(header,False,False,0)
        add=ui.widget(Gtk.Button,label=ui.msg('workspace.calendar_app.nova_tarefa'));add.connect('clicked',lambda *_:self.edit());header.pack_end(add,False,False,0)
        scroll=Gtk.ScrolledWindow();scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC);task_page.pack_start(scroll,True,True,0)
        self.rows=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10);scroll.add(self.rows)
        events=Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        hours=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8)
        self.tabs=Gtk.Notebook();self.tabs.set_scrollable(True);hours.pack_start(self.tabs,True,True,0)
        self.sheet_pages={}
        plus=ui.widget(Gtk.Button,label=ui.msg('workspace.calendar_app.nova_timesheet'));plus.connect('clicked',self.new_sheet)
        hours.pack_start(plus,False,False,0);hours.reorder_child(plus,0);plus.show()
        self.hours_empty=ui.widget(Gtk.Label,label=ui.msg('workspace.calendar_app.crie_uma_timesheet_para_registrar_horas'),xalign=0,wrap=True)
        self.hours_empty.set_no_show_all(True)
        hours.pack_start(self.hours_empty,False,False,0)
        today_scroll=Gtk.ScrolledWindow();today_scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC)
        self.today_label=Gtk.Label(xalign=0,yalign=0,wrap=True,selectable=True)
        self.today_label.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR);self.today_label.set_max_width_chars(65)
        today_scroll.add(self.today_label)
        invoices=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10)
        generate=ui.widget(Gtk.Button,label=ui.msg('workspace.calendar_app.gerar_invoice_pdf'));generate.connect('clicked',lambda *_:invoice_ui.open_invoice(self))
        invoices.pack_start(generate,False,False,0)
        self.invoice_container=invoices;self.invoice_refresh=lambda:None
        areas={'today':today_scroll,'events':events,'tasks':task_page,'hours':hours,'invoices':invoices}
        for key,title in workspace_ui.AREAS:
            areas[key].page_id=key;ui.stack_page(self.workspace,areas[key],key,title)
        footer=Gtk.Box(spacing=8);outer.pack_end(footer,False,False,0)
        self.status=Gtk.Label(xalign=0,wrap=True);footer.pack_start(self.status,False,False,0)
        self.status.set_margin_end(100)
        from widget_footer import WorkspaceFooter
        self.brand_footer=WorkspaceFooter(self)
        self.main_overlay.add_overlay(self.brand_footer)
        self.main_overlay.set_overlay_pass_through(self.brand_footer,False)
        try:
            content,self.invoice_refresh=invoice_history_ui.create_history_content(self,self)
            invoices.pack_start(content,True,True,0)
        except Exception:
            invoices.pack_start(ui.widget(Gtk.Label,label=ui.msg('workspace.calendar_app.historico_indisponivel_reabra_o_workspace_para_tentar_novamente'),wrap=True),False,False,0)
        self.tabs.connect('switch-page',self.tab_switched)
        self.tabs.connect('page-reordered',self.tab_reordered)
        self.connect('delete-event',self.can_close)
        self.connect('focus-in-event',lambda *_:self.refresh() and False)
        self.connect('destroy',self.cleanup)
        self.external=ExternalCalendars(self,left,workspace_ui.AgendaMount(events))
        self.workspace.connect('notify::visible-child-name',self.area_changed)
        self.refresh();self.show_all();self.show_area('today')
        self.timer=GLib.timeout_add_seconds(5,self.refresh)

    def show_area(self,area,reset_day=False):
        if self.restoring:return
        self.workspace.set_visible_child_name(area)
        if reset_day:self.select(date.today().isoformat())
        self.area_changed()

    def area_changed(self,*_):
        if self.restoring:return
        area=self.workspace.get_visible_child_name()
        if area=='hours':
            page=self.tabs.get_nth_page(self.tabs.get_current_page())
            self.last_tab=getattr(page,'sheet_id','hours')
            if hasattr(page,'sheet_id'):self.selected_sheet_id=page.sheet_id
        else:self.last_tab=area
        if area=='invoices':self.invoice_refresh()
        self.update_context();self.update_today()

    def focus_sheet(self,identity):
        page=self.sheet_pages.get(identity)
        if page is not None:
            self.selected_sheet_id=identity;self.tabs.set_current_page(self.tabs.page_num(page));self.show_area('hours')

    def update_context(self):
        area=self.workspace.get_visible_child_name()
        title=dict(workspace_ui.AREAS).get(area,'Workspace')
        sheet=next((s for s in self.data.get('timesheets',[]) if s['id']==self.selected_sheet_id),None)
        context=workspace_ui.context_message(sheet) if sheet and area in ('hours','invoices') else ''
        if context and area=='invoices':context=ui.msg('workspace.live.new_invoice_context', context=context)
        context_day=date.today() if area=='today' else date.fromisoformat(self.day)
        ui.call(self.context_label,'set_text',title+' · '+ui.date_text(context_day)+(' · '+context if context else ''))

    def update_today(self):
        events=[]
        if hasattr(self,'external'):
            try:
                import apple_client
                _context,cache=self.external.selected_cache()
                events=[event for event in cache.get('events',[]) if apple_client.on_day(event,date.today())]
            except Exception:pass
        ui.call(self.today_label,'set_text',workspace_ui.today_message(self.data,events))

    def select(self,day):
        chosen=date.fromisoformat(day);self.day=day
        self.selecting_programmatically=True
        try:self.calendar.select_month(chosen.month-1,chosen.year);self.calendar.select_day(chosen.day)
        finally:self.selecting_programmatically=False
        self.render()

    def day_selected(self,*_):
        year,month,day=self.calendar.get_date();self.day=date(year,month+1,day).isoformat()
        if not getattr(self,'selecting_programmatically',False) and self.workspace.get_visible_child_name()=='today':self.show_area('events')
        self.render()

    def mark_days(self):
        self.calendar.clear_marks();year,month,_=self.calendar.get_date()
        details={};day=date(year,month+1,1)
        while day.year==year and day.month==month+1:
            activity=local_detail_messages(self.data,day)
            if activity:self.calendar.mark_day(day.day);details[day.day]=activity
            day+=timedelta(days=1)
        if hasattr(self,'external'):self.external.mark_days(details)
        else:self.calendar.finish_marks(details=details)

    def refresh(self):
        if self.restoring:return False
        try:
            latest=store.modify({'action':'get'})
            if latest!=self.data:self.data=latest;self.render()
            else:
                for page in self.sheet_pages.values():page.update_timer()
            self.update_today()
            import external_store
            self.reminders.poll(self.data, external_store.read())
            ui.call(self.status,'set_text',ui.msg('workspace.calendar_app.tarefas_e_horas_salvas_neste_computador'))
        except Exception as error:ui.call(self.status,'set_text',ui.error_message(error))
        return True

    def render(self):
        self.mark_days()
        for child in self.rows.get_children():child.destroy()
        ui.call(self.heading,'set_text',ui.date_text(self.day))
        tasks=sorted((t for t in self.data['tasks'] if t['date']==self.day),key=lambda t:(t['done'],t.get('time') or '99:99'))
        for task in tasks:
            row=Gtk.Box(spacing=8,margin_top=6,margin_bottom=6)
            check=Gtk.CheckButton();check.set_active(task['done']);ui.call(check,'set_tooltip_text',ui.msg('workspace.calendar_app.concluir_tarefa'))
            check.connect('toggled',lambda _,t=task:self.change({'action':'toggle','id':t['id']}));row.pack_start(check,False,False,0)
            detail=task['text']+'\n'+(task.get('time') or ui.msg('workspace.live.all_day'))
            linked=[s for s in self.data.get('timesheets',[]) if any(e.get('source_task_id')==task['id'] for e in s['timesheet'])]
            if linked:detail+='\n'+ui.msg('workspace.live.task_recorded_in', sheets=', '.join('TS - '+s['name'] for s in linked))
            if task.get('external_source'):detail+='\n'+ui.msg('workspace.live.task_origin', calendar=task['external_source']['calendar_name'])
            if task.get('time'):detail+=ui.msg('workspace.live.task_reminder', minutes=task.get('reminder',10))
            label=ui.widget(Gtk.Label,label=detail,xalign=0,wrap=True);label.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR);label.set_max_width_chars(45)
            label.set_hexpand(True)
            edit=Gtk.Button();edit.add(label);edit.set_relief(Gtk.ReliefStyle.NONE);edit.connect('clicked',lambda _,t=task:self.edit(t));row.pack_start(edit,True,True,0)
            delete=Gtk.Button.new_from_icon_name('edit-delete-symbolic',Gtk.IconSize.BUTTON);ui.call(delete,'set_tooltip_text',ui.msg('workspace.calendar_app.excluir_tarefa'));delete.connect('clicked',lambda _,t=task:self.remove(t));row.pack_end(delete,False,False,0)
            if linked:
                records=Gtk.Button.new_from_icon_name('go-jump-symbolic',Gtk.IconSize.BUTTON);ui.call(records,'set_tooltip_text',ui.msg('workspace.calendar_app.abrir_os_registros_desta_tarefa'))
                records.connect('clicked',lambda _,t=task:self.open_task_records(t));row.pack_start(records,False,False,0)
            if task['done']:
                register=ui.widget(Gtk.Button,label=ui.msg('workspace.calendar_app.registrar_horas'));ui.call(register,'set_tooltip_text',ui.msg('workspace.calendar_app.adicionar_esta_tarefa_concluida_a_uma_timesheet'))
                register.connect('clicked',lambda _,t=task:self.register_task(t));row.pack_start(register,False,False,0)
            self.rows.pack_start(row,False,False,0)
        if not tasks:self.rows.pack_start(ui.widget(Gtk.Label,label=ui.msg('workspace.calendar_app.nenhuma_tarefa_neste_dia'),xalign=0),False,False,0)
        self.rows.show_all()
        self.sync_sheets()
        if hasattr(self,'external'):self.external.render()
        self.update_context();self.update_today()

    def register_task(self,task):
        task_timesheet_ui.register_task(self,task)

    def sync_sheets(self):
        self.syncing_tabs=True
        active=[s for s in self.data.get('timesheets',[]) if not s['archived']]
        ids={s['id'] for s in active}
        for identity,page in list(self.sheet_pages.items()):
            if identity not in ids:
                self.tabs.remove_page(self.tabs.page_num(page));page.destroy();del self.sheet_pages[identity]
        for sheet in active:
            identity=sheet['id']
            if identity not in self.sheet_pages:
                page=Timesheet(self,identity);self.sheet_pages[identity]=page
                tab=Gtk.Label(label='TS - '+sheet['name']);tab.set_ellipsize(Pango.EllipsizeMode.END);tab.set_max_width_chars(22);tab.set_width_chars(min(22,len('TS - '+sheet['name'])))
                ui.call(tab,'set_tooltip_text','TS - '+sheet['name']);self.tabs.append_page(page,tab);self.tabs.set_tab_reorderable(page,True);page.show_all()
            page=self.sheet_pages[identity]
            label=self.tabs.get_tab_label(page);ui.call(label,'set_text','TS - '+sheet['name']);ui.call(label,'set_tooltip_text','TS - '+sheet['name']);label.set_width_chars(min(22,len('TS - '+sheet['name'])))
            self.tabs.reorder_child(page,active.index(sheet))
            page.render()
        planner_menu.update_archive_count(self)
        identity=self.last_tab if self.last_tab in self.sheet_pages else self.selected_sheet_id
        target=self.sheet_pages.get(identity)
        if target:self.tabs.set_current_page(self.tabs.page_num(target))
        elif active:self.selected_sheet_id=active[0]['id']
        else:self.selected_sheet_id=None
        self.hours_empty.set_visible(not active)
        self.syncing_tabs=False

    def tab_switched(self,tabs,page,index):
        if self.syncing_tabs:return
        self.selected_sheet_id=page.sheet_id
        if self.workspace.get_visible_child_name()=='hours':self.last_tab=page.sheet_id
        self.update_context()
        try:ui_state.set('active-tab',self.last_tab)
        except Exception as error:ui.call(self.status,'set_text',ui.error_message(error))

    def tab_reordered(self,*_):
        if self.syncing_tabs:return
        order=[self.tabs.get_nth_page(i).sheet_id for i in range(self.tabs.get_n_pages()) if hasattr(self.tabs.get_nth_page(i),'sheet_id')]
        self.change({'action':'sheet_reorder','order':order})

    def rename_sheet(self,page):
        timesheet_context_ui.edit_context(self,page.sheet_data())

    def open_task_records(self,task):
        self.refresh()
        linked=[s for s in self.data.get('timesheets',[]) if any(e.get('source_task_id')==task['id'] for e in s['timesheet'])]
        if not linked:ui.call(self.status,'set_text',ui.msg('workspace.calendar_app.nenhum_registro_vinculado_a_esta_tarefa'));return
        dialog=ui.widget(Gtk.Dialog,title=ui.msg('workspace.calendar_app.registros_da_tarefa'),transient_for=self,modal=True)
        ui.button(dialog,ui.msg('workspace.calendar_app.fechar'),Gtk.ResponseType.CLOSE);dialog.set_default_size(440,260)
        rows=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10,margin=16);dialog.get_content_area().add(rows)
        for index,sheet in enumerate(linked):
            button=ui.widget(Gtk.Button,label='TS - '+sheet['name']+(ui.msg('workspace.live.archived_suffix') if sheet['archived'] else ''))
            button.connect('clicked',lambda _,i=index:dialog.response(i+1));rows.add(button)
        dialog.show_all();response=dialog.run();dialog.destroy()
        if 1<=response<=len(linked):
            sheet=linked[response-1];entry=next(e for e in sheet['timesheet'] if e.get('source_task_id')==task['id'])
            self.select(entry['date'])
            if sheet['archived']:planner_tools.view_archive(self,sheet['id'])
            else:self.focus_sheet(sheet['id'])

    def open_source_task(self,identity):
        self.refresh();task=next((t for t in self.data['tasks'] if t['id']==identity),None)
        if task is None:ui.call(self.status,'set_text',ui.msg('workspace.calendar_app.a_tarefa_original_foi_removida_o_registro_de_horas_continua_preservado'));return
        self.select(task['date']);self.show_area('tasks');self.edit(task)

    def can_close(self,*_):
        if self.restoring:return False
        return any(page.can_close() for page in self.sheet_pages.values() if page.has_draft())

    def new_sheet(self,*_):
        timesheet_context_ui.edit_context(self)

    def archive_sheet(self,page):
        sheet=page.sheet_data()
        if sheet.get('timesheet_active'):
            ui.call(self.status,'set_text',ui.msg('workspace.calendar_app.encerre_a_atividade_em_andamento_antes_de_arquivar_esta_timesheet'));return
        text=ui.msg('workspace.live.archive_note')
        if page.has_draft():text+=ui.msg('workspace.live.archive_drafts')
        if page.ask(ui.msg('workspace.live.archive_sheet', name=sheet['name']),text):self.change({'action':'sheet_archive','sheet_id':page.sheet_id})

    def open_archived(self,*_):
        self.refresh()
        dialog=ui.widget(Gtk.Dialog,title=ui.msg('workspace.calendar_app.timesheets_arquivadas'),transient_for=self,modal=True)
        ui.button(dialog,ui.msg('workspace.calendar_app.fechar'),Gtk.ResponseType.CLOSE);dialog.set_default_size(560,360)
        scroll=Gtk.ScrolledWindow();scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC)
        dialog.get_content_area().pack_start(scroll,True,True,0)
        rows=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12,margin=16);scroll.add(rows)
        error=Gtk.Label(xalign=0,wrap=True);dialog.get_content_area().pack_end(error,False,False,8)
        def populate():
            for child in rows.get_children():child.destroy()
            archived=[s for s in self.data.get('timesheets',[]) if s['archived']]
            for sheet in archived:
                row=Gtk.Box(spacing=10);rows.pack_start(row,False,False,0)
                title=Gtk.Label(label='TS - '+sheet['name'],xalign=0);title.set_ellipsize(Pango.EllipsizeMode.END);title.set_max_width_chars(30)
                ui.call(title,'set_tooltip_text',sheet['name']);row.pack_start(title,True,True,0)
                view=ui.widget(Gtk.Button,label=ui.msg('workspace.calendar_app.consultar'));view.connect('clicked',lambda _,s=sheet:planner_tools.view_archive(self,s['id'],dialog));row.pack_start(view,False,False,0)
                restore=ui.widget(Gtk.Button,label=ui.msg('workspace.calendar_app.resgatar'));restore.connect('clicked',lambda _,s=sheet:act(s,False));row.pack_start(restore,False,False,0)
                delete=ui.widget(Gtk.Button,label=ui.msg('workspace.calendar_app.excluir'));delete.connect('clicked',lambda _,s=sheet:act(s,True));row.pack_start(delete,False,False,0)
            if not archived:rows.pack_start(ui.widget(Gtk.Label,label=ui.msg('workspace.calendar_app.nenhuma_timesheet_arquivada')),False,False,0)
            rows.show_all()
        def act(sheet,delete):
            if delete:
                confirm=ui.widget(Gtk.MessageDialog,transient_for=dialog,modal=True,message_type=Gtk.MessageType.WARNING,buttons=Gtk.ButtonsType.OK_CANCEL,text=ui.msg('workspace.live.delete_sheet_forever', name=sheet['name']))
                ui.call(confirm,'format_secondary_text',ui.msg('workspace.calendar_app.todos_os_registros_desta_timesheet_serao_removidos_esta_acao_nao_pode_ser_desfei'))
                answer=confirm.run();confirm.destroy()
                if answer!=Gtk.ResponseType.OK:return
            try:
                self.data=store.modify({'action':'sheet_delete' if delete else 'sheet_restore','sheet_id':sheet['id']});self.render();populate();ui.call(error,'set_text','')
                if delete:ui_state.set('draft:'+sheet['id'],None)
                if not delete:self.focus_sheet(sheet['id'])
            except Exception as failure:ui.call(error,'set_text',ui.error_message(failure))
        populate();dialog.show_all();dialog.run();dialog.destroy()

    def change(self,payload):
        try:self.data=store.modify(payload);self.render();ui.call(self.status,'set_text',ui.msg('workspace.calendar_app.tudo_salvo_neste_computador'));return True
        except Exception as error:ui.call(self.status,'set_text',ui.error_message(error));return False

    def remove(self,task):
        dialog=ui.widget(Gtk.MessageDialog,transient_for=self,modal=True,message_type=Gtk.MessageType.QUESTION,buttons=Gtk.ButtonsType.OK_CANCEL,text=ui.msg('workspace.calendar_app.excluir_esta_tarefa'))
        ui.call(dialog,'format_secondary_text',task['text'])
        answer=dialog.run();dialog.destroy()
        if answer==Gtk.ResponseType.OK:self.change({'action':'delete','id':task['id']})

    def edit(self,task=None):
        task=task or {}
        draft_key='task-draft:'+task.get('id','new:'+self.day)
        saved=ui_state.get(draft_key,{})
        draft_timer=[0]
        dialog=ui.widget(Gtk.Dialog,title=ui.msg('workspace.live.edit_task') if task else ui.msg('workspace.live.new_task'),transient_for=self,modal=True)
        ui.buttons(dialog,ui.msg('workspace.calendar_app.cancelar'),Gtk.ResponseType.CANCEL,ui.msg('workspace.calendar_app.salvar'),Gtk.ResponseType.OK)
        dialog.set_default_size(450,300)
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10,margin=18);dialog.get_content_area().add(box)
        fields={}
        for key,title,value in [('text',ui.msg('workspace.live.task'),task.get('text','')),('date',ui.msg('workspace.live.date_hint'),task.get('date',self.day)),('time',ui.msg('workspace.live.time_hint'),task.get('time','')),('reminder',ui.msg('workspace.live.reminder_minutes'),str(task.get('reminder',10)))]:
            box.pack_start(ui.widget(Gtk.Label,label=title,xalign=0),False,False,0);entry=TimeField(text=saved.get(key,value)) if key=='time' else Gtk.Entry(text=saved.get(key,value));
            if key=='date':attach_date_picker(entry)
            box.pack_start(entry,False,False,0);fields[key]=entry
        fields['text'].set_max_length(1000)
        error=Gtk.Label(xalign=0,wrap=True);box.pack_start(error,False,False,0)
        original_values={key:entry.get_text() for key,entry in fields.items()} if not saved else None
        def persist():
            draft_timer[0]=0
            try:
                values={key:entry.get_text() for key,entry in fields.items()}
                ui_state.set(draft_key,None if original_values is not None and values==original_values else values)
                if values!=original_values:ui.call(error,'set_text',ui.msg('workspace.calendar_app.rascunho_salvo_ainda_nao_e_uma_tarefa_registrada'))
            except Exception as failure:ui.call(error,'set_text',ui.msg('workspace.live.task_draft_error', error=ui.error_message(failure)))
            return False
        def changed(*_):
            if draft_timer[0]:GLib.source_remove(draft_timer[0])
            draft_timer[0]=GLib.timeout_add(350,persist)
        for entry in fields.values():entry.connect('changed',changed)
        if saved:ui.call(error,'set_text',ui.msg('workspace.calendar_app.rascunho_recuperado'))
        dialog.show_all();fields['text'].grab_focus()
        committed=False
        while dialog.run()==Gtk.ResponseType.OK:
            try:
                raw=fields['reminder'].get_text().strip()
                if not raw.isdigit():raise ui.exception(ValueError, 'workspace.calendar_app.informe_um_numero_inteiro_de_minutos')
                payload=dict(action='task',text=fields['text'].get_text(),date=fields['date'].get_text().strip(),time=fields['time'].get_text().strip(),reminder=int(raw))
                if task:payload['id']=task['id']
                self.data=store.modify(payload);self.select(payload['date']);ui.call(self.status,'set_text',ui.msg('workspace.calendar_app.tudo_salvo_neste_computador'));committed=True;break
            except Exception as failure:ui.call(error,'set_text',ui.error_message(failure))
        if draft_timer[0]:GLib.source_remove(draft_timer[0]);draft_timer[0]=0
        if committed:ui_state.set(draft_key,None)
        else:persist()
        dialog.destroy()

    def flush_workspace_drafts(self):
        if not workspace_ui.flush_drafts(self,GLib.source_remove):
            ui.call(self.status,'set_text',ui.msg('workspace.calendar_app.salve_ou_resolva_os_rascunhos_antes_de_continuar_com_o_backup'))
            return False
        return True

    def quiesce_for_restore(self):
        workspace_ui.quiesce(self,GLib.source_remove)

    def cleanup(self,*_):
        if hasattr(self,'external'):self.external.cleanup()
        if self.timer:GLib.source_remove(self.timer);self.timer=0

class CalendarApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='io.orbitz.Workspace',flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        GLib.set_application_name('Orbitz Workspace')
        Gtk.Window.set_default_icon_name('io.orbitz.Workspace')
        icon=Path(__file__).resolve().parents[1]/'data/io.orbitz.Workspace.png'
        if icon.is_file():Gtk.Window.set_default_icon_from_file(str(icon))
        self.connect('command-line',self.command)
        action=Gio.SimpleAction.new('open-reminder',GLib.VariantType.new('s'))
        action.connect('activate',self.open_reminder)
        self.add_action(action)
    def notify_reminder(self,item):
        notification=Gio.Notification.new(item['title'])
        notification.set_body(ui.tr('workspace.reminders.body',time=item['time']))
        notification.set_default_action_and_target('app.open-reminder',GLib.Variant('s',item['day']+'|'+item['area']))
        self.send_notification(item['id'],notification)
    def open_reminder(self,action,parameter):
        day,area=parameter.get_string().split('|',1)
        window=self.get_active_window() or CalendarWindow(self)
        window.select(day);window.show_area(area);window.present()
    def command(self,app,command):
        window=self.get_active_window() or CalendarWindow(self)
        initial=ui_state.get('workspace-start-area','today')
        if initial not in dict(workspace_ui.AREAS):initial='today'
        window.show_area(initial,reset_day=initial=='today')
        arguments=command.get_arguments()
        import widget_control
        try:widget_control.start()
        except (OSError,ValueError):pass
        if '--preferences' in arguments:
            GLib.idle_add(lambda: (workspace_ui.open_preferences(window), False)[1])
        if len(arguments)>1:
            try:window.select(date.fromisoformat(arguments[1]).isoformat());window.show_area('tasks')
            except ValueError:pass
        window.present();return 0

if __name__=='__main__':sys.exit(CalendarApp().run(sys.argv))
