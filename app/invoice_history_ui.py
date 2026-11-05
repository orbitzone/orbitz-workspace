"""Read, download and explicitly delete private invoice history copies."""
from ui_language import ui
from collections import OrderedDict
import importlib
import invoice_signatures_ui as signatures_ui


def group_records(records):
    """Group by stable identities, never by customer or company names alone."""
    companies = OrderedDict()
    for record in records:
        snapshot = record['snapshot']
        company = companies.setdefault(snapshot['sheet_id'], {
            'label': 'TS - ' + snapshot['sheet_name'], 'clients': OrderedDict()})
        client = company['clients'].setdefault(record['client_key'], {
            'label': snapshot['client']['name'] + ' · CPF/CNPJ ' + snapshot['client']['tax_id'],
            'months': OrderedDict()})
        period = (record['issued_year'], record['issued_month'])
        client['months'].setdefault(period, []).append(record)
    return companies


class HistorySession:
    def __init__(self, archive=None, payments=None):
        self.archive = archive or importlib.import_module('invoice_history')
        self.records = {}
        self.selected_id = None
        self.payments = payments

    def reload(self):
        self.records = {}
        self.selected_id = None
        result = self.archive.list_records()
        self.records = {record['id']: record for record in result['records']}
        return result

    def select(self, record_id):
        self.selected_id = record_id if record_id in self.records else None
        return self.records.get(self.selected_id)

    def _selected(self):
        if self.selected_id is None:
            raise ui.exception(ValueError, 'workspace.invoice_history_ui.selecione_uma_invoice_nao_um_cabecalho_do_historico')
        return self.selected_id

    def path(self):
        return self.archive.get_path(self._selected())

    def export(self, filename, overwrite=False):
        return self.archive.export_copy(self._selected(), filename, overwrite=overwrite)

    def payment(self):
        service = self.payments or importlib.import_module('invoice_payments')
        return service.get(self._selected())

    def report_paid(self, paid, confirmed=False):
        if not confirmed:
            return None
        service = self.payments or importlib.import_module('invoice_payments')
        return service.set_paid(self._selected(), paid)

    def delete(self, confirmed=False):
        if not confirmed:
            return False
        self.archive.delete(self._selected())
        self.selected_id = None
        return True


def describe_message(record,localized=True):
    snapshot=record['snapshot'];period=snapshot['period']
    return ui.msg('workspace.dialogs.invoice_history_ui.description', reference=snapshot['reference'], sheet=snapshot['sheet_name'], client=snapshot['client']['name'], tax=snapshot['client']['tax_id'], issued=ui.date_text(snapshot['issued_on']) if localized else snapshot['issued_on'], all_history=ui.msg('workspace.dialogs.invoice_history_ui.all_prefix') if period['all_history'] else '', start=ui.date_text(period['start']) if localized else period['start'], end=ui.date_text(period['end']) if localized else period['end'], hours=snapshot['hours'], currency=snapshot['currency'], total=snapshot['total'], language='Português' if snapshot['language']=='pt' else 'English', stored=ui.date_text(record['created_at'],'datetime') if localized else record['created_at'])


def describe(record):return str(describe_message(record,localized=False))


def feedback_message(records,errors):
    if not records:
        return ui.msg('workspace.dialogs.invoice_history_ui.none_readable', count=len(errors)) if errors else ui.msg('workspace.dialogs.invoice_history_ui.empty')
    return ui.msg('workspace.dialogs.invoice_history_ui.some_unreadable', count=len(errors)) if errors else ui.msg('workspace.dialogs.invoice_history_ui.available', count=len(records))


def list_feedback(records,errors):return str(feedback_message(records,errors))


def create_history_content(window, parent=None):
    import gi
    gi.require_version('Gtk', '3.0')
    from gi.repository import Gtk, Gio, Pango

    session = HistorySession()
    dialog = parent or window
    box = ui.widget(Gtk.Box,orientation=Gtk.Orientation.VERTICAL, spacing=10, margin=16)
    note = ui.widget(Gtk.Label,label=ui.msg('workspace.invoice_history_ui.empresa_cliente_ano_mes_de_emissao_invoice_somente_pdfs_gerados_e_guardados_desd'),
        xalign=0, wrap=True)
    note.set_max_width_chars(68)
    box.pack_start(note, False, False, 0)
    tree_model = ui.widget(Gtk.TreeStore,str, str)
    tree = ui.widget(Gtk.TreeView,model=tree_model, headers_visible=True)
    ui.call(tree.get_accessible(),'set_name',ui.msg('workspace.invoice_history_ui.invoices_por_empresa_cliente_e_mes_de_emissao'))
    renderer = ui.widget(Gtk.CellRendererText,wrap_mode=Pango.WrapMode.WORD_CHAR, wrap_width=420)
    column = ui.tree_column(Gtk,ui.msg('workspace.dialogs.invoice_history_ui.column'), renderer, text=0)
    column.set_expand(True)
    tree.append_column(column)
    scroll = ui.widget(Gtk.ScrolledWindow,)
    scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    scroll.add(tree)
    box.pack_start(scroll, True, True, 0)
    details = ui.widget(Gtk.Label,label=ui.msg('workspace.invoice_history_ui.selecione_uma_invoice_para_consultar_os_detalhes_e_as_acoes'), xalign=0,
        wrap=True, selectable=True)
    details.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
    details.set_max_width_chars(68)
    detail_scroll = ui.widget(Gtk.ScrolledWindow,)
    detail_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    detail_scroll.set_min_content_height(100)
    detail_scroll.set_max_content_height(190)
    detail_scroll.add(details)
    box.pack_start(detail_scroll, False, True, 0)
    actions = ui.widget(Gtk.FlowBox,)
    actions.set_selection_mode(Gtk.SelectionMode.NONE)
    actions.set_min_children_per_line(1)
    actions.set_max_children_per_line(4)
    actions.set_row_spacing(6)
    actions.set_column_spacing(8)
    box.pack_start(actions, False, False, 0)
    buttons = {}
    for key, label in [('view', ui.msg('workspace.dialogs.invoice_history_ui.view')), ('copy', ui.msg('workspace.dialogs.invoice_history_ui.copy')),
            ('sign', ui.msg('workspace.dialogs.invoice_history_ui.sign')), ('import', ui.msg('workspace.dialogs.invoice_history_ui.import')),
            ('versions', ui.msg('workspace.dialogs.invoice_history_ui.versions')), ('payment', ui.msg('workspace.dialogs.invoice_history_ui.payment')), ('delete', ui.msg('workspace.dialogs.invoice_history_ui.delete'))]:
        button = ui.widget(Gtk.Button,label=label, sensitive=False)
        ui.call(button.get_accessible(),'set_name',ui.transform(label,'replace','…',''))
        actions.add(button)
        buttons[key] = button
    refresh = ui.widget(Gtk.Button,label=ui.msg('workspace.invoice_history_ui.atualizar'))
    actions.add(refresh)
    feedback = ui.widget(Gtk.Label,xalign=0, wrap=True, selectable=True)
    feedback.set_max_width_chars(68)
    box.pack_start(feedback, False, False, 0)

    def set_enabled(enabled):
        for button in buttons.values():
            button.set_sensitive(enabled)

    def selected(*_):
        model, row = tree.get_selection().get_selected()
        record = session.select(model[row][1] if row is not None else None)
        set_enabled(record is not None)
        text = describe_message(record) if record else ui.msg('workspace.dialogs.invoice_history_ui.select')
        if record:
            try:
                payment = session.payment()
                text += ui.msg('workspace.dialogs.invoice_history_ui.payment_prefix') + (ui.msg('workspace.dialogs.invoice_history_ui.manual_paid') if payment['status'] == 'reported_paid' else ui.msg('workspace.dialogs.invoice_history_ui.not_reported'))
            except Exception:text += ui.msg('workspace.dialogs.invoice_history_ui.payment_na')
        ui.call(details,'set_text',text)

    def reload(*_):
        set_enabled(False)
        ui.model_clear(tree_model,tree)
        ui.call(details,'set_text',ui.msg('workspace.invoice_history_ui.selecione_uma_invoice_para_consultar_os_detalhes_e_as_acoes'))
        try:
            result = session.reload()
            for company in group_records(result['records']).values():
                company_row = ui.model_append(tree_model,[company['label'], ''],tree=True,owner=tree)
                for client in company['clients'].values():
                    client_row = ui.model_append(tree_model,[client['label'], ''],parent=company_row,tree=True,owner=tree)
                    for (year, month), records in sorted(client['months'].items(), reverse=True):
                        month_row = ui.model_append(tree_model,[ui.msg('workspace.dialogs.invoice_history_ui.issue_month', year=f'{year:04d}', month=f'{month:02d}'), ''],parent=client_row,tree=True,owner=tree)
                        for record in records:
                            snapshot = record['snapshot']
                            label = ui.msg('workspace.dialogs.invoice_history_ui.record_label', reference=snapshot['reference'], currency=snapshot['currency'], total=snapshot['total'], id=record['id'][:8])
                            ui.model_append(tree_model,[label, record['id']],parent=month_row,tree=True,owner=tree)
            ui.call(feedback,'set_text',feedback_message(result['records'], result['errors']))
        except Exception:
            session.records = {}
            session.selected_id = None
            ui.call(feedback,'set_text',ui.msg('workspace.invoice_history_ui.nao_foi_possivel_carregar_o_historico_os_arquivos_foram_preservados'))

    def show_error(message):
        ui.call(feedback,'set_text',message)
        feedback.grab_focus()

    def view(*_):
        try:
            uri = Gio.File.new_for_path(str(session.path())).get_uri()
            Gio.AppInfo.launch_default_for_uri(uri, None)
        except Exception:
            show_error(ui.msg('workspace.dialogs.invoice_history_ui.open_error'))

    def copy(*_):
        if session.selected_id is None:
            return
        try:
            if signatures_ui.save_copy(dialog, session.export) is None:
                buttons['copy'].grab_focus()
                return
            ui.call(feedback,'set_text',ui.msg('workspace.invoice_history_ui.copia_do_pdf_salva_o_historico_permanece_intacto'))
        except Exception:
            show_error(ui.msg('workspace.dialogs.invoice_history_ui.copy_error'))
        feedback.grab_focus()

    def sign(*_):
        if session.selected_id is None:
            return
        try:
            saved, opened = signatures_ui.sign_invoice(dialog, session.export)
            if saved is None:
                ui.call(feedback,'set_text',ui.msg('workspace.invoice_history_ui.acao_cancelada_nenhum_portal_foi_aberto'))
            elif opened:
                ui.call(feedback,'set_text',ui.msg('workspace.invoice_history_ui.copia_salva_e_portal_gov_br_aberto_envie_e_assine_manualmente_depois_importe_a_v'))
            else:
                ui.call(feedback,'set_text',ui.msg('workspace.invoice_history_ui.copia_salva_mas_nao_foi_possivel_abrir_o_portal_gov_br_nenhum_pdf_foi_enviado'))
        except Exception:
            show_error(ui.msg('workspace.dialogs.invoice_history_ui.sign_error'))
        feedback.grab_focus()

    def import_version(*_):
        record = session.records.get(session.selected_id)
        if record is None:
            return
        try:
            if signatures_ui.add_version(dialog, record) is not None:
                ui.call(feedback,'set_text',ui.msg('workspace.invoice_history_ui.versao_importada_validacao_pendente_o_original_e_as_versoes_anteriores_foram_pre'))
        except Exception:
            show_error(ui.msg('workspace.dialogs.invoice_history_ui.import_error'))
        feedback.grab_focus()

    def versions(*_):
        record = session.records.get(session.selected_id)
        if record is None:
            return
        try:
            signatures_ui.show_versions(dialog, record)
        except Exception:
            show_error(ui.msg('workspace.dialogs.invoice_history_ui.versions_error'))

    def payment(*_):
        record = session.records.get(session.selected_id)
        if not record:return
        snapshot = record['snapshot']
        confirm = ui.widget(Gtk.MessageDialog,transient_for=dialog, modal=True, message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.NONE, text=ui.msg('workspace.invoice_history_ui.informacao_manual_de_pagamento'))
        ui.buttons(confirm,ui.msg('workspace.invoice_history_ui.cancelar'), Gtk.ResponseType.CANCEL, ui.msg('workspace.invoice_history_ui.informar_como_pago'), 1, ui.msg('workspace.invoice_history_ui.remover_informacao'), 2)
        confirm.set_default_response(Gtk.ResponseType.CANCEL)
        ui.call(confirm,'format_secondary_text',ui.msg('workspace.dialogs.invoice_history_ui.payment_confirm', reference=snapshot['reference'], id=record['id'][:8], client=snapshot['client']['name'], issued=ui.date_text(snapshot['issued_on']), currency=snapshot['currency'], total=snapshot['total']))
        answer = confirm.run();confirm.destroy()
        if answer not in (1,2):return
        try:
            session.report_paid(answer == 1, confirmed=True)
            selected()
            ui.call(feedback,'set_text',ui.msg('workspace.invoice_history_ui.pagamento_informado_manualmente_pdf_e_estado_de_assinatura_preservados'))
        except Exception:show_error(ui.msg('workspace.dialogs.invoice_history_ui.payment_error'))

    def delete(*_):
        record = session.records.get(session.selected_id)
        if record is None:
            return
        snapshot = record['snapshot']
        confirm = ui.widget(Gtk.MessageDialog,transient_for=dialog, modal=True, message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.OK_CANCEL, text=ui.msg('workspace.invoice_history_ui.excluir_esta_invoice_do_historico'))
        confirm.set_default_response(Gtk.ResponseType.CANCEL)
        ui.call(confirm,'format_secondary_text',ui.msg('workspace.dialogs.invoice_history_ui.delete_confirm', reference=snapshot['reference'], client=snapshot['client']['name'], issued=ui.date_text(snapshot['issued_on']), id=record['id'][:8], stored=ui.date_text(record['created_at'],'datetime')))
        answer = confirm.run()
        confirm.destroy()
        if answer != Gtk.ResponseType.OK:
            return
        try:
            session.delete(confirmed=True)
            reload()
            previous = feedback.get_text()
            ui.call(feedback,'set_text',ui.msg('workspace.dialogs.invoice_history_ui.deleted') +
                ('\n' + previous if previous else ''))
        except Exception as failure:
            reload()
            show_error(ui.msg('workspace.dialogs.invoice_history_ui.delete_error', error=ui.error_message(failure,limit=300)))

    def resized(_tree, allocation):
        width = max(180, allocation.width - 80)
        if renderer.get_property('wrap-width') != width:
            renderer.set_property('wrap-width', width)

    tree.connect('size-allocate', resized)
    def activated(_tree, path, _column):
        if tree_model[path][1]:
            tree.get_selection().select_path(path)
            view()

    tree.connect('row-activated', activated)
    tree.get_selection().connect('changed', selected)
    buttons['view'].connect('clicked', view)
    buttons['copy'].connect('clicked', copy)
    buttons['sign'].connect('clicked', sign)
    buttons['import'].connect('clicked', import_version)
    buttons['versions'].connect('clicked', versions)
    buttons['payment'].connect('clicked', payment)
    buttons['delete'].connect('clicked', delete)
    refresh.connect('clicked', reload)
    reload()
    return box, reload


def open_history(window):
    from gi.repository import Gtk
    dialog = ui.widget(Gtk.Dialog,title=ui.msg('workspace.invoice_history_ui.historico_de_invoices'), transient_for=window, modal=True)
    ui.button(dialog,ui.msg('workspace.invoice_history_ui.fechar'), Gtk.ResponseType.CLOSE)
    dialog.set_default_size(820, 620)
    dialog.set_size_request(420, 300)
    try:
        content, _refresh = create_history_content(window, dialog)
        dialog.get_content_area().pack_start(content, True, True, 0)
        dialog.show_all()
        dialog.run()
    except Exception:
        ui.call(window.status,'set_text',ui.msg('workspace.invoice_history_ui.nao_foi_possivel_abrir_o_historico_de_invoices_os_arquivos_foram_preservados'))
    finally:
        dialog.destroy()
