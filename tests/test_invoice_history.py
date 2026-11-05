"""Private invoice history contracts; synthetic bytes and temporary XDG only."""
import copy
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
import invoice
import invoice_history as history

PDF=b'%PDF-1.4\nsynthetic invoice bytes\n%%EOF\n'


def snapshot(tax_id='000.000.000-00',issued_on='2026-10-19'):
    return invoice.build_snapshot(dict(id='company-a',name='Empresa sintética',timesheet=[dict(id='1',description='Serviço sintético',date='2026-09-01',start='09:00',end='10:00')]),issuer=dict(name='Emitente teste',tax_id='00.000.000/0000-00'),client=dict(name='Cliente homônimo',tax_id=tax_id,address='Rua teste, 1'),rate='100.00',reference='REF-REPETIDA',issued_on=issued_on)


class InvoiceHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.base=Path(self.temporary.name)
        self.root=self.base/'data/invoices'
        self.external=self.base/'external.pdf';self.external.write_bytes(PDF)

    def record(self,value=None):return history.record(value or snapshot(),self.external,root=self.root)

    def test_empty_list_does_not_create_storage(self):
        self.assertEqual(history.list_records(root=self.root),dict(records=[],errors=[]))
        self.assertFalse(self.root.exists())

    def test_immutable_bytes_snapshot_permissions_and_duplicate_references(self):
        source=snapshot();original=copy.deepcopy(source)
        first=self.record(source);second=self.record(source)
        self.assertNotEqual(first['id'],second['id'])
        self.assertRegex(first['id'],'^[0-9a-f]{32}$')
        self.assertEqual(first['snapshot'],original)
        self.assertEqual(first['pdf_sha256'],hashlib.sha256(PDF).hexdigest())
        self.assertEqual(stat.S_IMODE(self.root.stat().st_mode),0o700)
        directory=self.root/first['id']
        self.assertEqual(stat.S_IMODE(directory.stat().st_mode),0o700)
        for name in ('invoice.pdf','metadata.json'):
            self.assertEqual(stat.S_IMODE((directory/name).stat().st_mode),0o600)
        self.external.write_bytes(b'changed externally')
        source['client']['name']='Future profile name'
        self.assertEqual(history.resolve_pdf(first['id'],root=self.root).read_bytes(),PDF)
        self.assertEqual(history.get(first['id'],root=self.root)['client_name'],'Cliente homônimo')
        raw=(directory/'metadata.json').read_text()
        self.assertNotIn(str(self.external),raw)
        self.assertEqual({path.name for path in directory.iterdir()},{'metadata.json','invoice.pdf'})

    def test_client_identity_normalization_and_issue_month_not_service_month(self):
        a=self.record(snapshot('000.000.000-00'))
        b=self.record(snapshot('00000000000'))
        c=self.record(snapshot('11111111111',issued_on='2026-11-01'))
        self.assertEqual(a['client_key'],b['client_key'])
        self.assertNotEqual(a['client_key'],c['client_key'])
        self.assertEqual(a['client_name'],c['client_name'])
        self.assertEqual((a['issued_year'],a['issued_month']),(2026,10))
        self.assertEqual(a['period']['start'],'2026-09-01')
        self.assertEqual(history.list_records(root=self.root)['records'][0]['id'],c['id'])
        d=self.record(snapshot('AB.CDE.123/F45G-00'))
        e=self.record(snapshot('abcde123f45g00'))
        self.assertEqual(d['client_key'],e['client_key'])

    def test_corruption_isolated_no_existing_files_modified(self):
        good=self.record();bad=self.record()
        corrupt=self.root/bad['id']/'invoice.pdf';corrupt.write_bytes(b'%PDF-tampered')
        before=corrupt.read_bytes()
        scanned=history.list_records(root=self.root)
        self.assertEqual([value['id'] for value in scanned['records']],[good['id']])
        self.assertEqual(scanned['errors'][0]['id'],bad['id'])
        self.assertNotIn('000',scanned['errors'][0]['message'])
        for action in [lambda:history.get(bad['id'],root=self.root),lambda:history.export_copy(bad['id'],self.base/'bad-copy.pdf',root=self.root),lambda:history.delete(bad['id'],root=self.root)]:
            with self.assertRaises(ValueError):action()
        self.assertEqual(corrupt.read_bytes(),before)
        self.assertFalse((self.base/'bad-copy.pdf').exists())

    def test_malformed_activity_metadata_is_isolated_and_preserved(self):
        good=self.record();bad=self.record()
        path=self.root/bad['id']/'metadata.json'
        metadata=json.loads(path.read_text())
        metadata['snapshot']['entries']=[None]
        path.write_text(json.dumps(metadata))
        damaged=path.read_bytes()
        scanned=history.list_records(root=self.root)
        self.assertEqual([value['id'] for value in scanned['records']],[good['id']])
        self.assertEqual([error['id'] for error in scanned['errors']],[bad['id']])
        self.assertEqual(path.read_bytes(),damaged)
        self.assertEqual(history.get(good['id'],root=self.root)['id'],good['id'])
        with self.assertRaises(ValueError):history.get(bad['id'],root=self.root)
        invalid=snapshot();invalid['entries']=[None]
        with self.assertRaises(ValueError):self.record(invalid)
        self.assertEqual(self.external.read_bytes(),PDF)

    def test_listing_reads_metadata_only_full_hash_checked_on_open(self):
        first=self.record()
        read=history._read
        def metadata_only(path,limit):
            if path.name=='invoice.pdf':raise AssertionError('PDF read while browsing')
            return read(path,limit)
        with patch.object(history,'_read',side_effect=metadata_only):
            self.assertEqual(len(history.list_records(root=self.root)['records']),1)
        pdf=self.root/first['id']/'invoice.pdf'
        pdf.write_bytes(PDF.replace(b'synthetic',b'modified!'))
        self.assertEqual(len(pdf.read_bytes()),len(PDF))
        self.assertEqual(len(history.list_records(root=self.root)['records']),1)
        with self.assertRaises(ValueError):history.resolve_pdf(first['id'],root=self.root)

    def test_failed_archive_preserves_external_and_prior_record(self):
        first=self.record()
        original_write=history._write
        def failing(path,value):
            if path.name=='metadata.json':raise OSError('synthetic metadata failure')
            original_write(path,value)
        with patch.object(history,'_write',side_effect=failing):
            with self.assertRaises(OSError):self.record()
        self.assertEqual(self.external.read_bytes(),PDF)
        self.assertEqual([value['id'] for value in history.list_records(root=self.root)['records']],[first['id']])
        self.assertEqual(list(self.root.glob('.record-*')),[])

    def test_path_traversal_symlink_and_invalid_source_rejected(self):
        first=self.record()
        for identity in ['../outside','/tmp/anything','a'*31,'A'*32,'a'*32+'/x']:
            for function in [history.get,history.resolve_pdf,history.delete]:
                with self.subTest(identity=identity,function=function),self.assertRaises(ValueError):function(identity,root=self.root)
        symlink=self.base/'source-link.pdf';symlink.symlink_to(self.external)
        with self.assertRaises(OSError):history.record(snapshot(),symlink,root=self.root)
        pdf=self.root/first['id']/'invoice.pdf';pdf.unlink();pdf.symlink_to(self.external)
        with self.assertRaises(OSError):history.get(first['id'],root=self.root)
        self.assertEqual(self.external.read_bytes(),PDF)
        linkedroot=self.base/'root-link';linkedroot.symlink_to(self.root)
        with self.assertRaises(ValueError):history.list_records(root=linkedroot)

    def test_export_no_clobber_private_exact_bytes_and_managed_destination_refused(self):
        first=self.record();target=self.base/'download.pdf'
        history.export_copy(first['id'],target,root=self.root)
        self.assertEqual(target.read_bytes(),PDF)
        self.assertEqual(stat.S_IMODE(target.stat().st_mode),0o600)
        target.write_bytes(b'existing user file')
        with self.assertRaises(FileExistsError):history.export_copy(first['id'],target,root=self.root)
        self.assertEqual(target.read_bytes(),b'existing user file')
        history.export_copy(first['id'],target,overwrite=True,root=self.root)
        self.assertEqual(target.read_bytes(),PDF)
        with self.assertRaises(ValueError):history.export_copy(first['id'],self.root/'unexpected.pdf',root=self.root)
        real_link=history.os.link
        raced=self.base/'race.pdf'
        def racing_link(source,destination):
            Path(destination).write_bytes(b'concurrent file')
            return real_link(source,destination)
        with patch.object(history.os,'link',side_effect=racing_link):
            with self.assertRaises(FileExistsError):history.export_copy(first['id'],raced,root=self.root)
        self.assertEqual(raced.read_bytes(),b'concurrent file')
        self.assertEqual(list(self.base.glob('.invoice-copy-*')),[])

    def test_delete_only_managed_record_keeps_external_download_and_other_data(self):
        first=self.record();second=self.record()
        target=self.base/'download.pdf';history.export_copy(first['id'],target,root=self.root)
        for name in ('notes.json','invoice-profiles.json'):(self.base/name).write_text('unchanged')
        history.delete(first['id'],root=self.root)
        self.assertFalse((self.root/first['id']).exists())
        self.assertEqual(history.get(second['id'],root=self.root)['id'],second['id'])
        self.assertEqual(self.external.read_bytes(),PDF);self.assertEqual(target.read_bytes(),PDF)
        for name in ('notes.json','invoice-profiles.json'):self.assertEqual((self.base/name).read_text(),'unchanged')

    def test_concurrent_records_distinct_ids_keep_all_copies(self):
        jobs=[]
        script='import sys,json;sys.path.insert(0,sys.argv[1]);import invoice_history;invoice_history.record(json.loads(sys.argv[2]),sys.argv[3])'
        environment={**os.environ,'XDG_DATA_HOME':str(self.base/'xdg')}
        try:
            for _ in range(6):
                jobs.append(subprocess.Popen([sys.executable,'-c',script,str(ROOT/'app'),json.dumps(snapshot()),str(self.external)],env=environment,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True))
            for job in jobs:
                stdout,stderr=job.communicate(timeout=10);self.assertEqual(job.returncode,0,stderr)
            scanned=history.list_records(root=self.base/'xdg/orbitz-workspace/invoices')
            self.assertEqual(len(scanned['records']),6);self.assertEqual(scanned['errors'],[])
            self.assertEqual(len({value['id'] for value in scanned['records']}),6)
        finally:
            for job in jobs:
                if job.poll() is None:job.kill()
                job.communicate()


if __name__=='__main__':unittest.main()
