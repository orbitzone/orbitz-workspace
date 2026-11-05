"""Explicit full Workspace backup and quiescent restore; no credential scope."""
from ui_language import ui
from datetime import date
import importlib

SCOPE_TEXT = (ui.msg('workspace.dialogs.workspace_backup_ui.scope'))


def apply_restore(service, filename, preview, quiesce, confirmed=False):
    if not confirmed:
        return None
    if preview['current_active_timer']:
        raise ui.exception(ValueError, 'workspace.workspace_backup_ui.encerre_os_cronometros_antes_de_restaurar_o_workspace')
    quiesce()
    return service.restore_backup(filename, confirmed=True, expected=preview['token'], quiescent=True)


def export_backup(window):
    from gi.repository import Gtk
    try:backend = importlib.import_module('workspace_backup')
    except ImportError:
        ui.call(window.status,'set_text',ui.msg('workspace.workspace_backup_ui.o_servico_de_backup_completo_nao_esta_disponivel_nesta_instalacao'));return
    confirm=ui.widget(Gtk.MessageDialog,transient_for=window,modal=True,message_type=Gtk.MessageType.INFO,
        buttons=Gtk.ButtonsType.OK_CANCEL,text=ui.msg('workspace.workspace_backup_ui.exportar_backup_completo_do_workspace'))
    confirm.set_default_response(Gtk.ResponseType.CANCEL)
    ui.call(confirm,'format_secondary_text',SCOPE_TEXT+ui.msg('workspace.dialogs.workspace_backup_ui.private'))
    accepted=confirm.run()==Gtk.ResponseType.OK;confirm.destroy()
    if not accepted:return
    if not window.flush_workspace_drafts():return
    chooser = ui.widget(Gtk.FileChooserDialog,title=ui.msg('workspace.dialogs.workspace_backup_ui.export'), transient_for=window,
        modal=True, action=Gtk.FileChooserAction.SAVE)
    ui.buttons(chooser,ui.msg('workspace.workspace_backup_ui.cancelar'),Gtk.ResponseType.CANCEL,ui.msg('workspace.workspace_backup_ui.exportar_backup'),Gtk.ResponseType.ACCEPT)
    chooser.set_current_name('orbitz-workspace-'+date.today().isoformat()+'.zip')
    chooser.set_do_overwrite_confirmation(True)
    confirmed=[None]
    def overwrite(widget):
        confirmed[0]=widget.get_filename()
        return Gtk.FileChooserConfirmation.CONFIRM
    chooser.connect('confirm-overwrite',overwrite)
    try:
        if chooser.run()!=Gtk.ResponseType.ACCEPT:return
        filename=chooser.get_filename()
        if not filename or not filename.lower().endswith('.zip'):raise ui.exception(ValueError, 'workspace.workspace_backup_ui.escolha_um_arquivo_local_zip')
        backend.export_backup(filename,overwrite=filename==confirmed[0])
        ui.call(window.status,'set_text',ui.msg('workspace.workspace_backup_ui.backup_completo_do_workspace_exportado_guarde_o_em_local_privado'))
    except Exception as failure:ui.call(window.status,'set_text',ui.error_message(failure))
    finally:chooser.destroy()


def restore_backup(window):
    from gi.repository import Gtk
    try:backend = importlib.import_module('workspace_backup')
    except ImportError:
        ui.call(window.status,'set_text',ui.msg('workspace.workspace_backup_ui.o_servico_de_backup_completo_nao_esta_disponivel_nesta_instalacao'));return
    chooser = ui.widget(Gtk.FileChooserDialog,title=ui.msg('workspace.workspace_backup_ui.escolher_backup_completo_do_workspace'), transient_for=window,
        modal=True, action=Gtk.FileChooserAction.OPEN)
    ui.buttons(chooser,ui.msg('workspace.workspace_backup_ui.cancelar'),Gtk.ResponseType.CANCEL,ui.msg('workspace.workspace_backup_ui.revisar_backup'),Gtk.ResponseType.ACCEPT)
    try:
        if chooser.run()!=Gtk.ResponseType.ACCEPT:return
        filename=chooser.get_filename()
    finally:chooser.destroy()
    quiesced=False
    app=None
    try:
        if not filename:raise ui.exception(ValueError, 'workspace.workspace_backup_ui.escolha_um_arquivo_de_backup_local')
        if not window.flush_workspace_drafts():return
        preview=backend.inspect_backup(filename)
        if preview['current_active_timer']:
            raise ui.exception(ValueError, 'workspace.workspace_backup_ui.encerre_os_cronometros_antes_de_restaurar_o_workspace')
        confirm=ui.widget(Gtk.MessageDialog,transient_for=window,modal=True,message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.OK_CANCEL,text=ui.msg('workspace.workspace_backup_ui.restaurar_o_backup_completo_e_fechar_o_workspace'))
        confirm.set_default_response(Gtk.ResponseType.CANCEL)
        ui.call(confirm,'format_secondary_text',SCOPE_TEXT + ui.msg('workspace.dialogs.workspace_backup_ui.size', files=preview['files'], bytes=preview['bytes']) +
            ui.msg('workspace.dialogs.workspace_backup_ui.restore_notice'))
        accepted=confirm.run()==Gtk.ResponseType.OK;confirm.destroy()
        if not accepted:return
        app=window.get_application()
        quiesced=True
        message=''
        try:
            result=apply_restore(backend,filename,preview,window.quiesce_for_restore,confirmed=True)
            message=ui.msg('workspace.dialogs.workspace_backup_ui.restored', path=str(result['previous_backup']))
        except Exception as failure:
            message=ui.msg('workspace.dialogs.workspace_backup_ui.restore_failed', error=ui.error_message(failure))
        info=ui.widget(Gtk.MessageDialog,transient_for=window,modal=True,message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.CLOSE,text=message)
        info.run();info.destroy()
    except Exception as failure:ui.call(window.status,'set_text',ui.error_message(failure))
    finally:
        if quiesced:
            window.destroy()
            if app:app.quit()
