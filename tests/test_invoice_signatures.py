"""INV-04: exact private PDF variants, explicitly without signature validation."""
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
import invoice_history as history
import invoice_signatures as signatures
from test_invoice_history import snapshot,PDF

VARIANT=b'%PDF-1.4\nPresented by user; this is not a real signed PDF.\n%%EOF\n'


class InvoiceSignatureTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.base=Path(self.temporary.name);self.root=self.base/'invoices'
        self.original_external=self.base/'original.pdf';self.original_external.write_bytes(PDF)
        self.external=self.base/'presented.pdf';self.external.write_bytes(VARIANT)
        self.original=history.record(snapshot(),self.original_external,root=self.root)
        self.identity=self.original['id']
        directory=self.root/self.identity
        self.original_bytes={name:(directory/name).read_bytes() for name in ('invoice.pdf','metadata.json')}

    def add(self):return signatures.import_version(self.identity,self.external,root=self.root)

    def assert_original(self):
        for name,value in self.original_bytes.items():self.assertEqual((self.root/self.identity/name).read_bytes(),value)
        self.assertEqual(history.get(self.identity,root=self.root),self.original)

    def test_multiple_exact_private_copies_no_signature_or_correspondence_claim(self):
        first=self.add();second=self.add()
        self.assertNotEqual(first['id'],second['id'])
        self.assertEqual(first['invoice_id'],self.identity)
        self.assertEqual(first['original_pdf_sha256'],self.original['pdf_sha256'])
        self.assertEqual(first['status'],'imported_pending_validation')
        self.assertEqual(first['status_label'],'Importada, validação pendente')
        self.assertNotIn(str(self.external),json.dumps(first))
        self.external.write_bytes(b'changed externally')
        self.assertEqual(signatures.resolve_pdf(self.identity,first['id'],root=self.root).read_bytes(),VARIANT)
        self.assertEqual(len(signatures.list_versions(self.identity,root=self.root)['versions']),2)
        directory=self.root/self.identity/'versions'
        self.assertEqual(stat.S_IMODE(directory.stat().st_mode),0o700)
        self.assertEqual(stat.S_IMODE((directory/first['id']).stat().st_mode),0o700)
        for name in ('invoice.pdf','metadata.json'):
            self.assertEqual(stat.S_IMODE((directory/first['id']/name).stat().st_mode),0o600)
        self.assert_original()

    def test_version1_invoice_without_versions_keeps_original_api(self):
        self.assertEqual(signatures.list_versions(self.identity,root=self.root),dict(versions=[],errors=[]))
        self.assertEqual(history.list_records(root=self.root)['records'],[self.original])
        self.assertFalse((self.root/self.identity/'versions').exists())
        self.assert_original()

    def test_version_corruption_isolated_from_other_versions_and_original(self):
        good=self.add();bad=self.add()
        metadata=self.root/self.identity/'versions'/bad['id']/'metadata.json'
        value=json.loads(metadata.read_text());value['status']='verified'
        metadata.write_text(json.dumps(value));damaged=metadata.read_bytes()
        scanned=signatures.list_versions(self.identity,root=self.root)
        self.assertEqual([item['id'] for item in scanned['versions']],[good['id']])
        self.assertEqual([item['id'] for item in scanned['errors']],[bad['id']])
        self.assertEqual(metadata.read_bytes(),damaged)
        with self.assertRaises(ValueError):signatures.get(self.identity,bad['id'],root=self.root)
        self.assert_original()
        self.assertEqual(history.list_records(root=self.root)['records'],[self.original])

    def test_version_list_never_reads_all_pdf_bytes_full_get_checks_hash(self):
        first=self.add();reader=history._read
        def only_metadata(path,limit):
            if path.name=='invoice.pdf':raise AssertionError('PDF read on listing')
            return reader(path,limit)
        with patch.object(history,'_read',side_effect=only_metadata):
            self.assertEqual(len(signatures.list_versions(self.identity,root=self.root)['versions']),1)
        pdf=self.root/self.identity/'versions'/first['id']/'invoice.pdf'
        pdf.write_bytes(VARIANT.replace(b'Presented',b'CORRUPTED'))
        self.assertEqual(len(pdf.read_bytes()),len(VARIANT))
        with self.assertRaises(ValueError):signatures.resolve_pdf(self.identity,first['id'],root=self.root)
        self.assert_original()

    def test_internal_source_traversal_and_symlink_refused_original_stays_accessible(self):
        with self.assertRaises(ValueError):signatures.import_version(self.identity,history.resolve_pdf(self.identity,root=self.root),root=self.root)
        for bad in ('../outside','a'*31,'A'*32,'a'*32+'/x'):
            with self.assertRaises(ValueError):signatures.import_version(bad,self.external,root=self.root)
            with self.assertRaises(ValueError):signatures.get(self.identity,bad,root=self.root)
        linked=self.base/'linked.pdf';linked.symlink_to(self.external)
        with self.assertRaises(OSError):signatures.import_version(self.identity,linked,root=self.root)
        versions=self.root/self.identity/'versions'
        outside=self.base/'outside';outside.mkdir();sentinel=outside/'sentinel';sentinel.write_text('unchanged')
        versions.symlink_to(outside)
        with self.assertRaises(ValueError):self.add()
        self.assertEqual(len(signatures.list_versions(self.identity,root=self.root)['errors']),1)
        with self.assertRaises(ValueError):history.delete(self.identity,root=self.root)
        self.assertEqual(sentinel.read_text(),'unchanged')
        self.assert_original()

    def test_failed_import_keeps_previous_version_and_both_external_files(self):
        first=self.add();writer=history._write
        def fail_metadata(path,value):
            if path.name=='metadata.json':raise OSError('synthetic failure')
            writer(path,value)
        with patch.object(history,'_write',side_effect=fail_metadata):
            with self.assertRaises(OSError):self.add()
        self.assertEqual([item['id'] for item in signatures.list_versions(self.identity,root=self.root)['versions']],[first['id']])
        self.assertEqual(self.external.read_bytes(),VARIANT)
        self.assertEqual(self.original_external.read_bytes(),PDF)
        self.assertEqual(list((self.root/self.identity/'versions').glob('.version-*')),[])
        self.assert_original()

    def test_export_version_exact_no_clobber_overwrite_and_managed_refusal(self):
        first=self.add();target=self.base/'download.pdf'
        signatures.export_copy(self.identity,first['id'],target,root=self.root)
        self.assertEqual(target.read_bytes(),VARIANT)
        self.assertEqual(stat.S_IMODE(target.stat().st_mode),0o600)
        target.write_bytes(b'user file')
        with self.assertRaises(FileExistsError):signatures.export_copy(self.identity,first['id'],target,root=self.root)
        self.assertEqual(target.read_bytes(),b'user file')
        signatures.export_copy(self.identity,first['id'],target,overwrite=True,root=self.root)
        self.assertEqual(target.read_bytes(),VARIANT)
        with self.assertRaises(ValueError):signatures.export_copy(self.identity,first['id'],self.root/self.identity/'invoice.pdf',overwrite=True,root=self.root)
        self.assert_original()

    def test_delete_one_version_and_whole_invoice_never_touches_external(self):
        first=self.add();second=self.add()
        signatures.delete(self.identity,first['id'],root=self.root)
        self.assertEqual([value['id'] for value in signatures.list_versions(self.identity,root=self.root)['versions']],[second['id']])
        self.assert_original()
        history.delete(self.identity,root=self.root)
        self.assertFalse((self.root/self.identity).exists())
        self.assertEqual(self.external.read_bytes(),VARIANT)
        self.assertEqual(self.original_external.read_bytes(),PDF)

    def test_prefix_limit_and_original_hash_link_are_conservative_not_verification(self):
        self.external.write_bytes(b'not a PDF')
        with self.assertRaises(ValueError):self.add()
        self.external.write_bytes(VARIANT)
        with patch.object(history,'MAX_PDF',len(VARIANT)-1):
            with self.assertRaises(ValueError):self.add()
        first=self.add()
        path=self.root/self.identity/'versions'/first['id']/'metadata.json'
        data=json.loads(path.read_text());data['original_pdf_sha256']='0'*64;path.write_text(json.dumps(data))
        with self.assertRaises(ValueError):signatures.get(self.identity,first['id'],root=self.root)
        self.assert_original()

    def test_concurrent_versions_keep_every_copy_and_original(self):
        jobs=[]
        script='import sys;sys.path.insert(0,sys.argv[1]);import invoice_signatures;invoice_signatures.import_version(sys.argv[2],sys.argv[3],root=sys.argv[4])'
        try:
            for _ in range(6):
                jobs.append(subprocess.Popen([sys.executable,'-c',script,str(ROOT/'app'),self.identity,str(self.external),str(self.root)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True))
            for job in jobs:
                stdout,stderr=job.communicate(timeout=10);self.assertEqual(job.returncode,0,stderr)
            scanned=signatures.list_versions(self.identity,root=self.root)
            self.assertEqual(len(scanned['versions']),6);self.assertEqual(scanned['errors'],[])
            self.assertEqual(len({version['id'] for version in scanned['versions']}),6)
            self.assert_original()
        finally:
            for job in jobs:
                if job.poll() is None:job.kill()
                job.communicate()


if __name__=='__main__':unittest.main()
