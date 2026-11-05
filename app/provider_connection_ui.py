"""Private provider connection dialogs; cancellation owns post-connect rollback."""
from ui_language import ui
import threading
import time
from urllib.parse import urlsplit


GOOGLE_PROGRESS = {
    'waiting_authorization': ui.msg('workspace.dialogs.provider_connection_ui.waiting_authorization'),
    'exchanging_token': ui.msg('workspace.dialogs.provider_connection_ui.exchanging_token'),
    'loading_calendars': ui.msg('workspace.dialogs.provider_connection_ui.loading_calendars'),
    'saving_credentials': ui.msg('workspace.dialogs.provider_connection_ui.saving_credentials'),
}


def launch_google_auth(url, launch):
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or parsed.hostname != 'accounts.google.com' or parsed.port not in (None,443) or parsed.username or parsed.password:
        raise ui.exception(ValueError, 'workspace.provider_connection_ui.o_endereco_de_autorizacao_google_foi_recusado')
    if launch(url) is False:
        raise ui.exception(ValueError, 'workspace.provider_connection_ui.nao_foi_possivel_abrir_o_navegador_para_autorizar_o_google')
    return True


class ConnectionAttempt:
    def __init__(self, service, provider, cancel_event=None):
        self.service, self.provider = service, provider
        self.cancelled = cancel_event or threading.Event()
        self.accepted = threading.Event()
        self.lock = threading.Lock()
        self.finished = False

    def accept(self):
        with self.lock:
            if not self.cancelled.is_set() and not self.finished:
                self.accepted.set();return True
            return False

    def connect(self, label, secret_or_path, deliver, open_browser=None, acknowledge_timeout=10, on_progress=None):
        if self.cancelled.is_set():return None
        if self.provider == 'google':
            options=dict(cancel_event=self.cancelled,open_browser=open_browser)
            if on_progress is not None:options['on_progress']=on_progress
            account = self.service.connect_google(None,label,**options)
        elif self.provider == 'calendly':
            account = self.service.connect_calendly(secret_or_path,label,cancel_event=self.cancelled)
        else:raise ui.exception(ValueError, 'workspace.provider_connection_ui.provedor_de_calendario_invalido')
        if account is None:return None
        committed = False
        try:
            if not self.cancelled.is_set():
                deliver(account)
                deadline = time.monotonic() + acknowledge_timeout
                while not self.accepted.wait(.05):
                    if self.cancelled.is_set() or time.monotonic() >= deadline:break
                with self.lock:
                    committed = self.accepted.is_set()
                    self.finished = True
                    if not committed:self.cancelled.set()
            return account if committed else None
        finally:
            if not committed:
                with self.lock:self.finished = True;self.cancelled.set()
                self.service.disconnect(account)


def connect_provider(controller, provider):
    import calendar_accounts
    from gi.repository import Gtk, Gio, GLib, Pango
    google = provider == 'google'
    dialog = ui.widget(Gtk.Dialog,title=ui.msg('workspace.dialogs.provider_connection_ui.connect_google') if google else ui.msg('workspace.dialogs.provider_connection_ui.connect_calendly'),
        transient_for=controller.window,modal=True)
    ui.buttons(dialog,ui.msg('workspace.provider_connection_ui.cancelar'),Gtk.ResponseType.CANCEL,ui.msg('workspace.dialogs.provider_connection_ui.google_login') if google else ui.msg('workspace.dialogs.provider_connection_ui.connect'),Gtk.ResponseType.OK)
    dialog.set_default_size(560,300 if google else 360)
    box = ui.widget(Gtk.Box,orientation=Gtk.Orientation.VERTICAL,spacing=10,margin=18)
    dialog.get_content_area().add(box)
    info = ui.widget(Gtk.Label,label=(ui.msg('workspace.dialogs.provider_connection_ui.google_help')
        if google else ui.msg('workspace.dialogs.provider_connection_ui.calendly_help')),xalign=0,wrap=True)
    info.set_max_width_chars(58);info.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR);box.add(info)
    if google:
        help_label=ui.widget(Gtk.Label,label=ui.msg('workspace.provider_connection_ui.ajuda_para_o_mantenedor_responsavel_pelo_projeto_orbitz_ativar_a_api_se_o_google'),xalign=0,wrap=True)
        help_label.set_max_width_chars(58);box.add(help_label)
        link=ui.widget(Gtk.LinkButton,uri='https://console.cloud.google.com/apis/library/calendar-json.googleapis.com?project=227612761270',label=ui.msg('workspace.provider_connection_ui.ativar_api_do_projeto_orbitz'))
        box.add(link)
    box.add(ui.widget(Gtk.Label,label=ui.msg('workspace.provider_connection_ui.nome_da_conexao'),xalign=0))
    name = ui.widget(Gtk.Entry,text=ui.tr('workspace.dialogs.provider_connection_ui.default_name') if google else '');name.set_max_length(100);ui.call(name.get_accessible(),'set_name',ui.msg('workspace.provider_connection_ui.nome_da_conexao'));box.add(name)
    credential = None
    if not google:
        credential = ui.widget(Gtk.Entry,visibility=False)
        credential.set_input_purpose(Gtk.InputPurpose.PASSWORD)
        credential.set_max_length(8192);ui.call(credential.get_accessible(),'set_name',ui.msg('workspace.provider_connection_ui.personal_access_token_do_calendly'));box.add(credential)
    status=ui.widget(Gtk.Label,xalign=0,wrap=True,selectable=google);status.set_max_width_chars(58);status.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR);box.add(status)
    pending=[None];result=[None]

    def alive():return controller.alive and dialog.get_visible()
    def complete(attempt, account):
        if alive() and pending[0] is attempt and attempt.accept():
            result[0]=account;dialog.response(Gtk.ResponseType.ACCEPT)
        else:attempt.cancelled.set()
        return False
    def progress(attempt, stage):
        message=GOOGLE_PROGRESS.get(stage)
        if message and alive() and pending[0] is attempt and not attempt.cancelled.is_set() and not attempt.accepted.is_set():
            ui.call(status,'set_text',message)
        return False
    def failed(attempt, error):
        if alive() and pending[0] is attempt:
            pending[0]=None
            ui.call(status,'set_text',ui.error_message(error) if isinstance(error,ValueError) else ui.msg('workspace.dialogs.provider_connection_ui.failed'))
            name.set_sensitive(True)
            if credential is not None:credential.set_sensitive(True)
            dialog.set_response_sensitive(Gtk.ResponseType.OK,True)
        return False
    def start(label,value):
        attempt=ConnectionAttempt(calendar_accounts,provider)
        pending[0]=attempt;controller.cancel_events.append(attempt.cancelled)
        def worker():
            try:
                connected=attempt.connect(label,value,lambda account:GLib.idle_add(complete,attempt,account),
                    open_browser=lambda url:launch_google_auth(url,lambda target:Gio.AppInfo.launch_default_for_uri(target,None)),
                    on_progress=(lambda stage:GLib.idle_add(progress,attempt,stage)) if google else None)
                if connected is None:GLib.idle_add(failed,attempt,ui.exception(ValueError, 'workspace.provider_connection_ui.a_conexao_nao_foi_concluida_tente_novamente_ou_cancele'))
            except Exception as error:GLib.idle_add(failed,attempt,error)
        try:controller.executor.submit(worker)
        except RuntimeError:
            attempt.cancelled.set()
            GLib.idle_add(failed,attempt,ui.exception(ValueError, 'workspace.provider_connection_ui.o_servico_de_conexao_foi_encerrado_reabra_o_workspace_para_tentar_novamente'))

    dialog.show_all();name.grab_focus()
    try:
        while True:
            response=dialog.run()
            if response==Gtk.ResponseType.ACCEPT:break
            if response!=Gtk.ResponseType.OK:break
            if pending[0] is not None:continue
            label=name.get_text().strip() or (ui.tr('workspace.dialogs.provider_connection_ui.default_name') if google else '')
            value=None if google else credential.get_text().strip()
            if not google:
                ui.call(credential,'set_text','')
                if not label or not value:
                    ui.call(status,'set_text',ui.msg('workspace.provider_connection_ui.informe_o_nome_e_o_token_privado'));continue
            name.set_sensitive(False)
            if credential is not None:credential.set_sensitive(False)
            dialog.set_response_sensitive(Gtk.ResponseType.OK,False)
            ui.call(status,'set_text',ui.msg('workspace.dialogs.provider_connection_ui.authorize') if google else ui.msg('workspace.dialogs.provider_connection_ui.connecting'))
            start(label,value)
    finally:
        if pending[0] is not None and not pending[0].accepted.is_set():pending[0].cancelled.set()
        if not google:ui.call(credential,'set_text','')
        dialog.destroy()
    if result[0]:
        account=result[0]
        if account.get('calendars'):
            controller.populate(account['id']+'|'+account['calendars'][0]['id'])
        else:controller.populate()
        controller.selection_changed();controller.window.show_area('events')
