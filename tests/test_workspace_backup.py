"""WSP-01 backup/recovery whitelist, locks, limits and byte-preserving failure tests."""
import io
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch
import fcntl

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
import store,invoice_profiles,invoice_history,invoice_signatures,invoice_payments
import workspace_backup as backup
from test_invoice_backend import PROFILE
from test_invoice_history import snapshot,PDF


class WorkspaceBackupTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.base=Path(self.temporary.name);self.data=self.base/'data';self.data.mkdir()
        store.modify(dict(action='task',text='Tarefa sintética',date='2026-10-19'),self.data/'notes.json')
        invoice_profiles.save('sheet',PROFILE,self.data/'invoice-profiles.json')
        (self.data/'planner-ui.json').write_text(json.dumps({'draft':'synthetic'}))
        self.external=self.base/'source.pdf';self.external.write_bytes(PDF)
        self.record=invoice_history.record(snapshot(),self.external,root=self.data/'invoices')
        invoice_signatures.import_version(self.record['id'],self.external,root=self.data/'invoices')
        invoice_payments.set_paid(self.record['id'],True,root=self.data/'invoices')
        for name in ('external-calendars.json','credentials.json','notes.sqlite3'):(self.data/name).write_bytes(b'outside-whitelist-private')
        self.archive=self.base/'workspace.zip'

    def export(self):return backup.export_backup(self.archive,data_dir=self.data)
    def preview(self):return backup.inspect_backup(self.archive,data_dir=self.data)
    def restore(self,preview=None):return backup.restore_backup(self.archive,confirmed=True,quiescent=True,expected=(preview or self.preview())['token'],data_dir=self.data)

    def test_export_private_manifest_whitelist_and_roundtrip_preserves_lock_inode(self):
        original=backup._collect(self.data);self.export()
        self.assertEqual(self.archive.stat().st_mode & 0o777,0o600)
        with zipfile.ZipFile(self.archive) as archive:
            names=set(archive.namelist())
            self.assertIn('manifest.json',names)
            self.assertTrue(any('/versions/' in name for name in names))
            self.assertTrue(any(name.endswith('/payment.json') for name in names))
            for forbidden in ('external-calendars.json','credentials.json','notes.sqlite3'):self.assertNotIn(forbidden,names)
        store.modify(dict(action='notes',notes='Estado posterior'),self.data/'notes.json')
        invoice_history.record(snapshot('11111111111'),self.external,root=self.data/'invoices')
        invoice_payments.set_paid(self.record['id'],False,root=self.data/'invoices')
        before_restore=backup._collect(self.data)
        inode=(self.data/'invoices/.lock').stat().st_ino
        result=self.restore()
        self.assertTrue(result['restored']);self.assertEqual(backup._collect(self.data),original)
        self.assertEqual((self.data/'invoices/.lock').stat().st_ino,inode)
        previous=Path(result['previous_backup'])
        self.assertEqual(previous.stat().st_mode & 0o777,0o600)
        self.assertEqual(previous.parent.stat().st_mode & 0o777,0o700)
        for forbidden in ('external-calendars.json','credentials.json','notes.sqlite3'):self.assertEqual((self.data/forbidden).read_bytes(),b'outside-whitelist-private')
        preview=backup.inspect_backup(previous,data_dir=self.data)
        backup.restore_backup(previous,confirmed=True,quiescent=True,expected=preview['token'],data_dir=self.data)
        self.assertEqual(backup._collect(self.data),before_restore)

    def test_restore_requires_confirmation_quiescence_and_current_preview_cas(self):
        self.export();preview=self.preview();before=backup._collect(self.data)
        for options in [dict(confirmed=False,quiescent=True),dict(confirmed=True,quiescent=False)]:
            with self.assertRaises(ValueError):backup.restore_backup(self.archive,expected=preview['token'],data_dir=self.data,**options)
        self.assertEqual(backup._collect(self.data),before)
        (self.data/'planner-ui.json').write_text('{"draft":"changed"}')
        changed=backup._collect(self.data)
        with self.assertRaisesRegex(ValueError,'mudaram'):self.restore(preview)
        self.assertEqual(backup._collect(self.data),changed)

    def test_timer_and_busy_existing_lock_are_refused(self):
        self.export()
        store.modify(dict(action='timesheet_start',description='Timer'),self.data/'notes.json')
        self.assertTrue(self.preview()['current_active_timer'])
        with self.assertRaisesRegex(ValueError,'cronômetros'):backup.export_backup(self.base/'timer.zip',data_dir=self.data)
        with self.assertRaisesRegex(ValueError,'cronômetros'):self.restore()
        notes=json.loads((self.data/'notes.json').read_text());notes['timesheets'][0]['timesheet_active']=None
        (self.data/'notes.json').write_text(json.dumps(notes))
        preview=self.preview()
        with (self.data/'notes.json.lock').open('r+') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaisesRegex(ValueError,'andamento'):self.restore(preview)

    def test_failure_during_apply_rolls_back_every_byte_and_keeps_prebackup(self):
        self.export()
        store.modify(dict(action='notes',notes='Before restore'),self.data/'notes.json')
        before=backup._collect(self.data);preview=self.preview();real_put=backup._put;failed=[False]
        def fail_once(path,value):
            if path==self.data/'notes.json' and not failed[0]:
                failed[0]=True;raise OSError('synthetic apply failure')
            return real_put(path,value)
        with patch.object(backup,'_put',side_effect=fail_once):
            with self.assertRaisesRegex(RuntimeError,'rollback verificado'):self.restore(preview)
        self.assertTrue(failed[0]);self.assertEqual(backup._collect(self.data),before)
        folder=next((self.data/'workspace-backups').iterdir())
        journal=json.loads((folder/'recovery.json').read_text())
        self.assertEqual(journal['state'],'rolled-back')
        prior,_=backup._read_archive(folder/'before.zip');self.assertEqual(prior,before)

    def test_interrupted_restore_can_recover_partial_invoice_without_stale_ui(self):
        self.export()
        store.modify(dict(action='notes',notes='Estado anterior completo'),self.data/'notes.json')
        before=backup._collect(self.data);preview=self.preview()
        def interruption(directory,old,new):
            (directory/'invoices'/self.record['id']/'invoice.pdf').unlink()
            raise KeyboardInterrupt('synthetic interruption')
        with patch.object(backup,'_apply',side_effect=interruption):
            with self.assertRaises(KeyboardInterrupt):self.restore(preview)
        folder=next((self.data/'workspace-backups').iterdir())
        self.assertEqual(json.loads((folder/'recovery.json').read_text())['state'],'prepared')
        backup.rollback_restore(folder,confirmed=True,quiescent=True,data_dir=self.data)
        self.assertEqual(backup._collect(self.data),before)
        self.assertEqual(invoice_history.get(self.record['id'],root=self.data/'invoices')['id'],self.record['id'])

    def test_recovery_preserves_unexpected_edits_after_interruption(self):
        self.export();preview=self.preview()
        def interruption(directory,old,new):raise KeyboardInterrupt('synthetic interruption')
        with patch.object(backup,'_apply',side_effect=interruption):
            with self.assertRaises(KeyboardInterrupt):self.restore(preview)
        folder=next((self.data/'workspace-backups').iterdir())
        (self.data/'planner-ui.json').write_text('{"later":"keep"}')
        before=backup._collect(self.data)
        with self.assertRaisesRegex(ValueError,'mudaram'):backup.rollback_restore(folder,confirmed=True,quiescent=True,data_dir=self.data)
        self.assertEqual(backup._collect(self.data),before)

    def test_hash_tamper_archive_change_and_overwrite_are_refused(self):
        self.export();preview=self.preview();before=backup._collect(self.data)
        with self.assertRaises(FileExistsError):self.export()
        original=self.archive.read_bytes()
        with zipfile.ZipFile(io.BytesIO(original)) as archive:
            contents={name:archive.read(name) for name in archive.namelist()}
        contents['planner-ui.json']=b'{"different":true}'
        with zipfile.ZipFile(self.archive,'w') as archive:
            for name,value in contents.items():archive.writestr(name,value)
        with self.assertRaisesRegex(ValueError,'Hash'):self.restore(preview)
        self.assertEqual(backup._collect(self.data),before)
        self.archive.write_bytes(original)
        backup.export_backup(self.archive,overwrite=True,data_dir=self.data)
        with self.assertRaisesRegex(ValueError,'mudaram'):self.restore(preview)

    def test_traversal_outside_whitelist_symlink_and_zipbomb_refused(self):
        before=backup._collect(self.data)
        for name in ('../notes.json','/notes.json','external-calendars.json','invoices/../../notes.json','notes.sqlite3'):
            with self.subTest(name=name):
                with zipfile.ZipFile(self.archive,'w') as archive:
                    archive.writestr('manifest.json','{}');archive.writestr(name,b'x')
                with self.assertRaises(ValueError):backup.inspect_backup(self.archive,data_dir=self.data)
        symlink=zipfile.ZipInfo('notes.json');symlink.external_attr=(stat.S_IFLNK|0o777)<<16
        with zipfile.ZipFile(self.archive,'w') as archive:
            archive.writestr('manifest.json','{}');archive.writestr(symlink,b'outside')
        with self.assertRaises(ValueError):self.preview()
        with zipfile.ZipFile(self.archive,'w',compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('manifest.json','{}');archive.writestr('planner-ui.json',b'0'*(2*1024*1024))
        with self.assertRaisesRegex(ValueError,'comprimido'):self.preview()
        self.assertEqual(backup._collect(self.data),before)

    def test_live_filesystem_symlink_and_size_limits_refused(self):
        notes=self.data/'notes.json';value=notes.read_bytes();notes.unlink();notes.symlink_to(self.external)
        with self.assertRaises(OSError):self.export()
        self.assertEqual(self.external.read_bytes(),PDF)
        notes.unlink();notes.write_bytes(value)
        linked=self.base/'linked';linked.symlink_to(self.data)
        with self.assertRaises(ValueError):backup.export_backup(self.archive,data_dir=linked)
        with patch.object(backup,'MAX_TOTAL',2):
            with self.assertRaisesRegex(ValueError,'limite'):self.export()
        self.assertFalse(self.archive.exists())


if __name__=='__main__':unittest.main()
