"""Manual gov.br signing assistance; never uploads files or verifies signatures."""
from ui_language import ui
from datetime import date
import importlib

SIGN_URL = 'https://assinador.iti.br/'
VALIDATE_URL = 'https://validar.iti.gov.br/'
PENDING_LABEL = ui.tr('workspace.dialogs.invoice_signatures_ui.pending')


def version_message(version):
    return ui.msg('workspace.dialogs.invoice_signatures_ui.version', created=version['created_at'], id=version['id'][:8], status=ui.msg('workspace.dialogs.invoice_signatures_ui.pending'))


def version_label(version):return str(version_message(version))


def assist_sign(save_copy, launch):
    """Open only the fixed portal, and only after a confirmed copy succeeded."""
    saved = save_copy()
    if saved is None:
        return None, False
    try:
        if launch(SIGN_URL) is False:
            return saved, False
    except Exception:
        return saved, False
    return saved, True


def open_validator(launch):
    if launch(VALIDATE_URL) is False:
        raise ui.exception(ValueError, 'workspace.invoice_signatures_ui.nao_foi_possivel_abrir_o_portal_validar')


class SignatureSession:
    def __init__(self, invoice_id, archive=None, signatures=None):
        self.invoice_id = invoice_id
        self.archive = archive or importlib.import_module('invoice_history')
        self.signatures = signatures or importlib.import_module('invoice_signatures')
        self.versions = {}
        self.selected = None

    def reload(self):
        self.selected = None
        self.versions = {}
        result = self.signatures.list_versions(self.invoice_id)
        self.versions = {version['id']: version for version in result['versions']}
        return result

    def select(self, version_id):
        self.selected = version_id if version_id == 'original' or version_id in self.versions else None
        return self.selected is not None

    def path(self):
        if self.selected == 'original':
            return self.archive.get_path(self.invoice_id)
        if self.selected in self.versions:
            return self.signatures.resolve_pdf(self.invoice_id, self.selected)
        raise ui.exception(ValueError, 'workspace.invoice_signatures_ui.selecione_uma_versao_do_pdf')

    def export(self, target, overwrite=False):
        if self.selected == 'original':
            return self.archive.export_copy(self.invoice_id, target, overwrite=overwrite)
        if self.selected in self.versions:
            return self.signatures.export_copy(self.invoice_id, self.selected, target, overwrite=overwrite)
        raise ui.exception(ValueError, 'workspace.invoice_signatures_ui.selecione_uma_versao_do_pdf')

    def import_pdf(self, path, confirmed=False):
        if not confirmed:
            return None
        return self.signatures.import_version(self.invoice_id, path)


def save_copy(parent, exporter, title=ui.msg('workspace.dialogs.invoice_signatures_ui.save_copy')):
    import gi
    gi.require_version('Gtk', '3.0')
    from gi.repository import Gtk
    chooser = ui.widget(Gtk.FileChooserDialog,title=title, transient_for=parent, modal=True,
        action=Gtk.FileChooserAction.SAVE)
    ui.buttons(chooser,ui.msg('workspace.invoice_signatures_ui.cancelar'), Gtk.ResponseType.CANCEL, ui.msg('workspace.invoice_signatures_ui.salvar_copia'), Gtk.ResponseType.ACCEPT)
    chooser.set_current_name('invoice-' + date.today().isoformat() + '.pdf')
    chooser.set_do_overwrite_confirmation(True)
    allowed = [None]
    def confirm(file_chooser):
        allowed[0] = file_chooser.get_filename()
        return Gtk.FileChooserConfirmation.CONFIRM
    chooser.connect('confirm-overwrite', confirm)
    pdf_filter = ui.widget(Gtk.FileFilter,)
    ui.call(pdf_filter,'set_name',ui.msg('workspace.dialogs.invoice_signatures_ui.pdf_document'))
    pdf_filter.add_pattern('*.pdf')
    chooser.add_filter(pdf_filter)
    try:
        if chooser.run() != Gtk.ResponseType.ACCEPT:
            return None
        filename = chooser.get_filename()
        if not filename or not filename.lower().endswith('.pdf'):
            raise ui.exception(ValueError, 'workspace.invoice_signatures_ui.escolha_um_arquivo_local_terminado_em_pdf')
        return exporter(filename, overwrite=allowed[0] == filename)
    finally:
        chooser.destroy()


def add_version(parent, record):
    import gi
    gi.require_version('Gtk', '3.0')
    from gi.repository import Gtk
    chooser = ui.widget(Gtk.FileChooserDialog,title=ui.msg('workspace.invoice_signatures_ui.adicionar_versao_assinada_importacao_manual'),
        transient_for=parent, modal=True, action=Gtk.FileChooserAction.OPEN)
    ui.buttons(chooser,ui.msg('workspace.invoice_signatures_ui.cancelar'), Gtk.ResponseType.CANCEL, ui.msg('workspace.invoice_signatures_ui.escolher_pdf'), Gtk.ResponseType.ACCEPT)
    pdf_filter = ui.widget(Gtk.FileFilter,)
    ui.call(pdf_filter,'set_name',ui.msg('workspace.dialogs.invoice_signatures_ui.pdf_document'))
    pdf_filter.add_pattern('*.pdf')
    chooser.add_filter(pdf_filter)
    try:
        if chooser.run() != Gtk.ResponseType.ACCEPT:
            return None
        filename = chooser.get_filename()
    finally:
        chooser.destroy()
    if not filename or not filename.lower().endswith('.pdf'):
        raise ui.exception(ValueError, 'workspace.invoice_signatures_ui.escolha_um_arquivo_pdf_local')
    snapshot = record['snapshot']
    period = snapshot['period']
    confirm = ui.widget(Gtk.MessageDialog,transient_for=parent, modal=True, message_type=Gtk.MessageType.QUESTION,
        buttons=Gtk.ButtonsType.OK_CANCEL, text=ui.msg('workspace.invoice_signatures_ui.vincular_este_pdf_a_invoice_selecionada'))
    confirm.set_default_response(Gtk.ResponseType.CANCEL)
    ui.call(confirm,'format_secondary_text',ui.msg('workspace.dialogs.invoice_signatures_ui.confirm_import', reference=snapshot['reference'], id=record['id'][:8], client=snapshot['client']['name'], start=ui.date_text(period['start']), end=ui.date_text(period['end'])))
    try:
        accepted = confirm.run() == Gtk.ResponseType.OK
    finally:
        confirm.destroy()
    return SignatureSession(record['id']).import_pdf(filename, confirmed=accepted) if accepted else None


def show_versions(parent, record):
    import gi
    gi.require_version('Gtk', '3.0')
    from gi.repository import Gtk, Gio, Pango
    session = SignatureSession(record['id'])
    dialog = ui.widget(Gtk.Dialog,title=ui.msg('workspace.dialogs.invoice_signatures_ui.title', reference=record['snapshot']['reference']),
        transient_for=parent, modal=True)
    ui.button(dialog,ui.msg('workspace.invoice_signatures_ui.fechar'), Gtk.ResponseType.CLOSE)
    width, height = 680, 480
    if parent.get_window():
        monitor = parent.get_display().get_monitor_at_window(parent.get_window())
        if monitor:
            area = monitor.get_workarea()
            width, height = min(width, max(400, area.width - 48)), min(height, max(280, area.height - 64))
    dialog.set_default_size(width, height)
    dialog.set_size_request(400, 280)
    box = ui.widget(Gtk.Box,orientation=Gtk.Orientation.VERTICAL, spacing=10, margin=16)
    dialog.get_content_area().pack_start(box, True, True, 0)
    note = ui.widget(Gtk.Label,label=ui.msg('workspace.invoice_signatures_ui.importacao_nao_comprova_assinatura_nem_correspondencia_com_o_original_use_o_vali'), xalign=0, wrap=True)
    note.set_max_width_chars(60)
    box.add(note)
    model = ui.widget(Gtk.ListStore,str, str)
    tree = ui.widget(Gtk.TreeView,model=model)
    ui.call(tree.get_accessible(),'set_name',ui.msg('workspace.invoice_signatures_ui.original_e_versoes_importadas_da_invoice'))
    renderer = ui.widget(Gtk.CellRendererText,wrap_mode=Pango.WrapMode.WORD_CHAR, wrap_width=500)
    tree.append_column(ui.tree_column(Gtk,ui.msg('workspace.dialogs.invoice_signatures_ui.column'), renderer, text=0))
    scroll = ui.widget(Gtk.ScrolledWindow,)
    scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    scroll.add(tree)
    box.pack_start(scroll, True, True, 0)
    actions = ui.widget(Gtk.FlowBox,)
    actions.set_selection_mode(Gtk.SelectionMode.NONE)
    actions.set_min_children_per_line(1)
    actions.set_max_children_per_line(3)
    box.add(actions)
    view = ui.widget(Gtk.Button,label=ui.msg('workspace.invoice_signatures_ui.consultar_pdf'), sensitive=False)
    copy = ui.widget(Gtk.Button,label=ui.msg('workspace.dialogs.invoice_signatures_ui.copy'), sensitive=False)
    validate = ui.widget(Gtk.Button,label=ui.msg('workspace.invoice_signatures_ui.verificar_no_validar'), sensitive=False)
    for button in (view, copy, validate):
        actions.add(button)
    feedback = ui.widget(Gtk.Label,xalign=0, wrap=True, selectable=True)
    feedback.set_max_width_chars(60)
    box.add(feedback)
    def selected(*_):
        current, row = tree.get_selection().get_selected()
        enabled = session.select(current[row][1] if row is not None else None)
        for button in (view, copy, validate):
            button.set_sensitive(enabled)
    def consult(*_):
        try:
            uri = Gio.File.new_for_path(str(session.path())).get_uri()
            Gio.AppInfo.launch_default_for_uri(uri, None)
        except Exception:
            ui.call(feedback,'set_text',ui.msg('workspace.invoice_signatures_ui.nao_foi_possivel_abrir_esta_versao_os_arquivos_foram_preservados'))
            feedback.grab_focus()
    def download(*_):
        try:
            if save_copy(dialog, session.export) is None:
                copy.grab_focus()
                return
            ui.call(feedback,'set_text',ui.msg('workspace.invoice_signatures_ui.copia_salva_sem_alterar_os_bytes_da_versao_guardada'))
        except Exception:
            ui.call(feedback,'set_text',ui.msg('workspace.invoice_signatures_ui.nao_foi_possivel_concluir_a_copia_confira_o_destino_a_versao_guardada_foi_preser'))
        feedback.grab_focus()
    def validator(*_):
        try:
            open_validator(lambda url: Gio.AppInfo.launch_default_for_uri(url, None))
            ui.call(feedback,'set_text',ui.msg('workspace.invoice_signatures_ui.envie_o_pdf_manualmente_no_validar_o_status_local_permanece_sem_validacao'))
        except Exception:
            ui.call(feedback,'set_text',ui.msg('workspace.invoice_signatures_ui.nao_foi_possivel_abrir_o_validar_nenhum_arquivo_foi_enviado'))
        feedback.grab_focus()
    def resized(_tree, allocation):
        width = max(180, allocation.width - 24)
        if renderer.get_property('wrap-width') != width:
            renderer.set_property('wrap-width', width)

    tree.connect('size-allocate', resized)
    tree.get_selection().connect('changed', selected)
    view.connect('clicked', consult)
    copy.connect('clicked', download)
    validate.connect('clicked', validator)
    try:
        result = session.reload()
        ui.model_append(model,[ui.msg('workspace.dialogs.invoice_signatures_ui.original'), 'original'],owner=tree)
        for version in result['versions']:
            ui.model_append(model,[version_message(version), version['id']],owner=tree)
        if result['errors']:
            ui.call(feedback,'set_text',ui.msg('workspace.dialogs.invoice_signatures_ui.unreadable', count=len(result['errors'])))
        dialog.show_all()
        dialog.run()
    finally:
        dialog.destroy()


def sign_invoice(parent, exporter):
    import gi
    gi.require_version('Gtk', '3.0')
    from gi.repository import Gtk, Gio
    instructions = ui.widget(Gtk.MessageDialog,transient_for=parent, modal=True,
        message_type=Gtk.MessageType.INFO, buttons=Gtk.ButtonsType.OK_CANCEL,
        text=ui.msg('workspace.invoice_signatures_ui.salvar_uma_copia_e_continuar_no_assinador_gov_br'))
    instructions.set_default_response(Gtk.ResponseType.CANCEL)
    ui.call(instructions,'format_secondary_text',ui.msg('workspace.invoice_signatures_ui.1_salve_uma_copia_do_pdf_2_no_portal_oficial_entre_com_sua_conta_gov_br_prata_ou'))
    try:
        accepted = instructions.run() == Gtk.ResponseType.OK
    finally:
        instructions.destroy()
    if not accepted:
        return None, False
    return assist_sign(lambda: save_copy(parent, exporter, ui.msg('workspace.dialogs.invoice_signatures_ui.sign_copy')),
        lambda url: Gio.AppInfo.launch_default_for_uri(url, None))
