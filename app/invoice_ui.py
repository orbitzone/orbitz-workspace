"""Review a service invoice and explicitly export a private local PDF."""
from date_time_fields import attach_date_picker
from ui_language import ui
from invoice_messages import warning_message,warning_messages
from copy import deepcopy
from datetime import date
from pathlib import Path
from uuid import uuid4
import invoice
import invoice_profiles
import store
from invoice_period_ui import InvoicePeriodPicker
from workspace_ui import context_message


def check_external_destination(filename):
    """Keep user exports outside both lexical and resolved history boundaries."""
    try:
        import invoice_history
        root = Path(invoice_history.ROOT).expanduser().absolute()
        target = Path(filename).expanduser().absolute()
        managed = target.is_relative_to(root) or target.resolve().is_relative_to(root.resolve())
    except (ImportError, OSError, RuntimeError, TypeError, AttributeError):
        raise ui.exception(ValueError, 'workspace.invoice_ui.nao_foi_possivel_verificar_o_destino_do_pdf_escolha_uma_pasta_fora_do_historico_') from None
    if managed:
        raise ui.exception(ValueError, 'workspace.invoice_ui.escolha_uma_pasta_fora_do_historico_de_invoices_para_salvar_o_pdf')



class ReissueConfirmation(ValueError):
    def __init__(self, result):
        super().__init__(ui.tr('workspace.dialogs.invoice_ui.reissue_exception'))
        self.result = result


class InvoiceSession:
    """Keep a reviewed snapshot separate from editable fields and saved profiles."""
    def __init__(self, read_data=None):
        self.read_data = read_data or (lambda: store.modify({'action': 'get'}))
        self.snapshot = None
        self.profile = None
        self.sheet_id = None

    def invalidate(self):
        self.snapshot = None
        self.profile = None

    def prepare(self, sheet_id, values):
        self.invalidate()
        sheet = next((s for s in self.read_data().get('timesheets', []) if s['id'] == sheet_id), None)
        if sheet is None:
            raise ui.exception(ValueError, 'workspace.invoice_ui.esta_timesheet_nao_esta_mais_disponivel')
        snapshot = invoice.build_snapshot(sheet, issuer=values['issuer'], client=values['client'],
            rate=values['rate'], currency=values['currency'], language=values['language'],
            reference=values['reference'], issued_on=values['issued_on'],
            start=values.get('start'), end=values.get('end'))
        self.snapshot = deepcopy(snapshot)
        self.profile = deepcopy({key: values[key] for key in ('issuer', 'client', 'rate', 'currency', 'language')})
        self.sheet_id = sheet_id
        return deepcopy(snapshot)

    def duplicate_check(self):
        try:
            import invoice_history
            return invoice_history.possible_duplicates(deepcopy(self.snapshot))
        except Exception:
            return {'matches': [], 'warnings': [ui.tr('workspace.dialogs.invoice_ui.history_check_error')], 'incomplete': True}

    def export(self, filename, overwrite=False, confirmed_reissue=False):
        if self.snapshot is None:
            raise ui.exception(ValueError, 'workspace.invoice_ui.revise_a_previa_antes_de_salvar_o_pdf')
        check_external_destination(filename)
        duplicates = self.duplicate_check()
        if (duplicates['matches'] or duplicates['warnings'] or duplicates['incomplete']) and not confirmed_reissue:
            raise ReissueConfirmation(duplicates)
        try:
            import invoice_pdf
            path = invoice_pdf.write(deepcopy(self.snapshot), filename, overwrite=overwrite)
        except ImportError:
            raise ui.exception(ValueError, 'workspace.invoice_ui.a_exportacao_pdf_requer_reportlab_instale_a_dependencia_para_gerar_a_invoice') from None
        warnings = []
        try:
            import invoice_history
            invoice_history.record(deepcopy(self.snapshot), path)
        except Exception:
            warnings.append(ui.tr('workspace.dialogs.invoice_ui.archive_warning'))
        try:
            invoice_profiles.save(self.sheet_id, deepcopy(self.profile))
        except Exception:
            warnings.append(ui.tr('workspace.dialogs.invoice_ui.profile_warning'))
        return path, '\n'.join(warnings)


def open_invoice(window):
    import gi
    gi.require_version('Gtk', '3.0')
    from gi.repository import Gtk, Pango

    try:
        data = store.modify({'action': 'get'})
        sheets = data.get('timesheets', [])
        if not sheets:
            ui.call(window.status,'set_text',ui.msg('workspace.invoice_ui.crie_uma_timesheet_para_gerar_uma_invoice_de_servicos'))
            return
        session = InvoiceSession()
        preferred = getattr(window, 'selected_sheet_id', None) or window.last_tab
        first = next((s['id'] for s in sheets if s['id'] == preferred), sheets[0]['id'])
        first_sheet = next(s for s in sheets if s['id'] == first)
        initial = invoice_profiles.load(first, context=first_sheet.get('context', {}))
    except Exception:
        ui.call(window.status,'set_text',ui.msg('workspace.invoice_ui.nao_foi_possivel_carregar_os_dados_da_invoice_os_dados_locais_foram_preservados'))
        return

    dialog = ui.widget(Gtk.Dialog,title=ui.msg('workspace.invoice_ui.gerar_invoice_de_servicos_pdf'), transient_for=window, modal=True)
    ui.buttons(dialog,ui.msg('workspace.invoice_ui.cancelar'), Gtk.ResponseType.CANCEL, ui.msg('workspace.invoice_ui.revisar_previa'), Gtk.ResponseType.APPLY,
        ui.msg('workspace.invoice_ui.salvar_pdf'), Gtk.ResponseType.OK)
    width, height = 640, 680
    parent_window = window.get_window()
    monitor = window.get_display().get_monitor_at_window(parent_window) if parent_window else None
    if monitor:
        area = monitor.get_workarea()
        width, height = min(width, max(360, area.width - 48)), min(height, max(280, area.height - 64))
    dialog.set_default_size(width, height)
    dialog.set_size_request(360, 280)
    dialog.set_default_response(Gtk.ResponseType.APPLY)
    dialog.set_response_sensitive(Gtk.ResponseType.OK, False)
    scroll = ui.widget(Gtk.ScrolledWindow,)
    scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    dialog.get_content_area().pack_start(scroll, True, True, 0)
    form = ui.widget(Gtk.Box,orientation=Gtk.Orientation.VERTICAL, spacing=10, margin=16)
    scroll.add(form)
    fields = {}

    def caption(text, widget):
        label = ui.mnemonic_label(Gtk,text)
        label.set_xalign(0)
        label.set_line_wrap(True)
        label.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        label.set_max_width_chars(58)
        label.set_mnemonic_widget(widget)
        form.pack_start(label, False, False, 0)
        ui.call(widget.get_accessible(),'set_name',ui.transform(text,'replace','_',''))

    def field(key, title, value='', maximum=200):
        entry = ui.widget(Gtk.Entry,text=value, hexpand=True)
        if key=='issued_on':attach_date_picker(entry)
        entry.set_max_length(maximum)
        caption(title, entry)
        form.pack_start(entry, False, False, 0)
        fields[key] = entry
        return entry

    sheet_choice = ui.widget(Gtk.ComboBoxText,hexpand=True)
    for renderer in sheet_choice.get_cells():
        renderer.set_property('ellipsize', Pango.EllipsizeMode.END)
        renderer.set_property('max-width-chars', 36)
    for sheet in sheets:
        ui.combo_append(sheet_choice,sheet['id'], 'TS - ' + sheet['name'] + (ui.msg('workspace.dialogs.invoice_ui.archived') if sheet['archived'] else ''))
    caption(ui.msg('workspace.dialogs.invoice_ui.sheet_caption'), sheet_choice)
    form.add(sheet_choice)
    sheet_context = ui.widget(Gtk.Label,xalign=0, wrap=True, selectable=True)
    sheet_context.set_max_width_chars(58);sheet_context.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR);form.add(sheet_context)
    field('reference', ui.msg('workspace.dialogs.invoice_ui.reference'), 'INV-' + date.today().strftime('%Y%m%d') + '-' + uuid4().hex[:8], 80)
    field('issued_on', ui.msg('workspace.dialogs.invoice_ui.issue_date'), date.today().isoformat(), 10)
    field('issuer_name', ui.msg('workspace.dialogs.invoice_ui.issuer_name'), initial.get('issuer', {}).get('name', ''))
    field('issuer_tax_id', ui.msg('workspace.dialogs.invoice_ui.issuer_tax'), initial.get('issuer', {}).get('tax_id', ''), 30)
    field('client_name', ui.msg('workspace.dialogs.invoice_ui.client_name'))
    field('client_tax_id', ui.msg('workspace.dialogs.invoice_ui.client_tax'), maximum=30)
    address = ui.widget(Gtk.TextView,wrap_mode=Gtk.WrapMode.WORD_CHAR)
    address.set_accepts_tab(False)
    address_scroll = ui.widget(Gtk.ScrolledWindow,)
    address_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    address_scroll.set_min_content_height(74)
    address_scroll.set_max_content_height(130)
    address_scroll.add(address)
    caption(ui.msg('workspace.dialogs.invoice_ui.address'), address)
    form.pack_start(address_scroll, False, False, 0)
    field('rate', ui.msg('workspace.dialogs.invoice_ui.rate'), maximum=24)
    field('currency', ui.msg('workspace.dialogs.invoice_ui.currency'), 'BRL', 3)
    language = ui.widget(Gtk.ComboBoxText,)
    language.append('pt', 'Português')
    language.append('en', 'English')
    language.set_active_id(initial.get('language', 'pt'))
    caption(ui.msg('workspace.dialogs.invoice_ui.language'), language)
    form.add(language)
    notice = ui.widget(Gtk.Label,label=ui.msg('workspace.invoice_ui.fatura_de_servicos_sem_emissao_de_nota_fiscal_eletronica_o_cronometro_em_andamen'), xalign=0, wrap=True)
    notice.set_max_width_chars(58)
    notice.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
    form.add(notice)
    preview = ui.widget(Gtk.Label,label=ui.msg('workspace.invoice_ui.preencha_os_dados_e_revise_a_previa'), xalign=0, wrap=True, selectable=True)
    preview.set_max_width_chars(58)
    preview.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
    form.add(preview)
    error = ui.widget(Gtk.Label,xalign=0, wrap=True, selectable=True)
    error.set_max_width_chars(58)
    error.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
    dialog.get_content_area().pack_end(error, False, False, 8)
    drafts = {}
    selected = [None]
    loading = [False]

    def invalidate(*_):
        if loading[0]:
            return
        session.invalidate()
        dialog.set_response_sensitive(Gtk.ResponseType.OK, False)
        ui.call(preview,'set_text',ui.msg('workspace.invoice_ui.dados_alterados_revise_novamente_antes_de_salvar'))
        ui.call(error,'set_text','')
        dialog.set_response_sensitive(Gtk.ResponseType.APPLY, period.model.ready)

    def client_values():
        buffer = address.get_buffer()
        return {'name': fields['client_name'].get_text(), 'tax_id': fields['client_tax_id'].get_text(),
            'address': buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True)}

    def change_sheet(*_):
        if getattr(sheet_choice,'_orbitz_language_updating',False):return
        previous = selected[0]
        if previous:
            drafts[previous] = {'client': client_values(), 'rate': fields['rate'].get_text(),
                'currency': fields['currency'].get_text()}
        identity = sheet_choice.get_active_id()
        current = next((sheet for sheet in sheets if sheet['id'] == identity), None)
        ui.call(sheet_choice,'set_tooltip_text',current['name'] if current else '')
        ui.call(sheet_context,'set_text',context_message(current) if current else '')
        try:
            profile = drafts.get(identity) or invoice_profiles.load(identity, context=current.get('context', {}) if current else {})
        except Exception:
            ui.call(error,'set_text',ui.msg('workspace.invoice_ui.nao_foi_possivel_carregar_o_perfil_desta_timesheet'))
            session.invalidate()
            dialog.set_response_sensitive(Gtk.ResponseType.OK, False)
            return
        loading[0] = True
        client = profile.get('client', {})
        ui.call(fields['client_name'],'set_text',client.get('name', ''))
        ui.call(fields['client_tax_id'],'set_text',client.get('tax_id', ''))
        ui.call(address.get_buffer(),'set_text',client.get('address', ''))
        ui.call(fields['rate'],'set_text',profile.get('rate', ''))
        ui.call(fields['currency'],'set_text',profile.get('currency', 'BRL'))
        selected[0] = identity
        loading[0] = False
        invalidate()

    period = InvoicePeriodPicker(getattr(window, 'day', None), invalidate)
    form.pack_start(period.widget, False, False, 0)
    form.reorder_child(period.widget, form.get_children().index(notice))

    def values():
        start, end = period.model.bounds()
        return {'issuer': {'name': fields['issuer_name'].get_text(), 'tax_id': fields['issuer_tax_id'].get_text()},
            'client': client_values(), 'rate': fields['rate'].get_text(), 'currency': fields['currency'].get_text(),
            'language': language.get_active_id(), 'reference': fields['reference'].get_text(),
            'issued_on': fields['issued_on'].get_text(),
            'start': start, 'end': end}

    for entry in fields.values():
        entry.connect('changed', invalidate)
    address.get_buffer().connect('changed', invalidate)
    language.connect('changed', invalidate)
    sheet_choice.connect('changed', change_sheet)
    sheet_choice.set_active_id(first)
    invalidate()
    dialog.show_all()
    fields['issuer_name'].grab_focus()
    try:
        while True:
            response = dialog.run()
            if response not in (Gtk.ResponseType.APPLY, Gtk.ResponseType.OK):
                break
            if response == Gtk.ResponseType.APPLY:
                dialog.set_response_sensitive(Gtk.ResponseType.OK, False)
                ui.call(preview,'set_text',ui.msg('workspace.invoice_ui.validando_os_dados_da_previa'))
                try:
                    if selected[0] != sheet_choice.get_active_id():
                        raise ui.exception(ValueError, 'workspace.invoice_ui.selecione_novamente_a_timesheet_para_carregar_os_dados')
                    snapshot = session.prepare(sheet_choice.get_active_id(), values())
                    duplicate_result = session.duplicate_check()
                    ui.call(preview,'set_text',ui.msg('workspace.dialogs.invoice_ui.preview', context=context_message({'name':snapshot['sheet_name'],'context':snapshot.get('context',{})}), all_history=ui.msg('workspace.dialogs.invoice_ui.all_history') if snapshot['period']['all_history'] else '', start=ui.date_text(snapshot['period']['start']), end=ui.date_text(snapshot['period']['end']), hours=snapshot['hours'], minutes=snapshot['minutes'], currency=snapshot['currency'], rate=invoice.format_money(snapshot['rate'],'pt'), total=invoice.format_money(snapshot['total'],'pt')) +
                        ('\n' + ui.join('\n',warning_messages(snapshot['warnings'])) if snapshot.get('warnings') else '') +
                        (ui.msg('workspace.dialogs.invoice_ui.duplicate_warning')
                         if duplicate_result['matches'] or duplicate_result['warnings'] or duplicate_result['incomplete'] else ''))
                    dialog.set_response_sensitive(Gtk.ResponseType.OK, True)
                    ui.call(error,'set_text','')
                    preview.grab_focus()
                except Exception as failure:
                    session.invalidate()
                    dialog.set_response_sensitive(Gtk.ResponseType.OK, False)
                    ui.call(preview,'set_text',ui.msg('workspace.invoice_ui.previa_indisponivel_corrija_os_dados_e_revise_novamente'))
                    ui.call(error,'set_text',ui.error_message(failure))
                    error.grab_focus()
                continue
            chooser = ui.widget(Gtk.FileChooserDialog,title=ui.msg('workspace.invoice_ui.salvar_invoice_em_pdf'), transient_for=dialog,
                modal=True, action=Gtk.FileChooserAction.SAVE)
            ui.buttons(chooser,ui.msg('workspace.invoice_ui.cancelar'), Gtk.ResponseType.CANCEL, ui.msg('workspace.dialogs.invoice_ui.save_pdf'), Gtk.ResponseType.ACCEPT)
            chooser.set_do_overwrite_confirmation(True)
            overwrite_target = [None]
            def confirm_overwrite(file_chooser):
                overwrite_target[0] = file_chooser.get_filename()
                return Gtk.FileChooserConfirmation.CONFIRM
            chooser.connect('confirm-overwrite', confirm_overwrite)
            chooser.set_current_name('invoice-' + date.today().isoformat() + '.pdf')
            pdf_filter = ui.widget(Gtk.FileFilter,)
            ui.call(pdf_filter,'set_name',ui.msg('workspace.dialogs.invoice_ui.pdf_document'))
            pdf_filter.add_pattern('*.pdf')
            chooser.add_filter(pdf_filter)
            try:
                if chooser.run() != Gtk.ResponseType.ACCEPT:
                    continue
                filename = chooser.get_filename()
                if not filename or not filename.lower().endswith('.pdf'):
                    raise ui.exception(ValueError, 'workspace.invoice_ui.escolha_um_arquivo_local_com_nome_terminado_em_pdf')
                try:
                    result, warning = session.export(filename, overwrite=overwrite_target[0] == filename)
                except ReissueConfirmation as duplicate:
                    confirm = ui.widget(Gtk.MessageDialog,transient_for=chooser, modal=True, message_type=Gtk.MessageType.WARNING,
                        buttons=Gtk.ButtonsType.YES_NO, text=ui.msg('workspace.invoice_ui.reemitir_estas_horas_intencionalmente'))
                    confirm.set_default_response(Gtk.ResponseType.NO)
                    matches = duplicate.result['matches']
                    reasons={'entry_id_and_time':ui.msg('workspace.dialogs.invoice_ui.same_records'),'time_overlap_legacy':ui.msg('workspace.dialogs.invoice_ui.legacy_overlap'),'time_overlap':ui.msg('workspace.dialogs.invoice_ui.overlap')}
                    lines = [ui.msg('workspace.dialogs.invoice_ui.duplicate_line', reference=item['reference'], minutes=item['minutes'], reason=reasons.get(item['basis'],ui.msg('workspace.dialogs.invoice_ui.review_hours'))) for item in matches[:12]]
                    lines += warning_messages(duplicate.result['warnings'])
                    ui.call(confirm,'format_secondary_text',ui.join('\n',lines) + ui.msg('workspace.dialogs.invoice_ui.reissue_notice'))
                    accepted = confirm.run() == Gtk.ResponseType.YES;confirm.destroy()
                    if not accepted:continue
                    result, warning = session.export(filename, overwrite=overwrite_target[0] == filename, confirmed_reissue=True)
                ui.call(window.status,'set_text',warning_message(warning) if warning else ui.msg('workspace.dialogs.invoice_ui.saved'))
                if warning:
                    info = ui.widget(Gtk.MessageDialog,transient_for=dialog, modal=True,
                        message_type=Gtk.MessageType.WARNING, buttons=Gtk.ButtonsType.CLOSE,
                        text=warning_message(warning))
                    info.run()
                    info.destroy()
                break
            except Exception as failure:
                ui.call(error,'set_text',ui.error_message(failure))
            finally:
                chooser.destroy()
            error.grab_focus()
    finally:
        dialog.destroy()
