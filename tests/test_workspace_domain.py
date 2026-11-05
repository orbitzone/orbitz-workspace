"""WSP-01 context, invoice compatibility, overlap evidence and manual payment."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
import invoice,invoice_profiles,invoice_pdf,invoice_history,invoice_payments,store,timesheet
from test_invoice_backend import PROFILE,entry
from test_invoice_history import PDF

CONTEXT=dict(client_name='Cliente de contexto',project_contract='Projeto <Ação> & contrato',department_costcenter='Centro / Departamento 42')


def document(entries=None,context=True):
    sheet=dict(id='sheet',name='Projeto interno',timesheet=entries or [entry()],context=CONTEXT if context else {})
    return invoice.build_snapshot(sheet,reference='WSP-TEST',issued_on='2026-10-19',**PROFILE)


class WorkspaceDomainTests(unittest.TestCase):
    def test_sheet_create_update_context_preserves_legacy_hours_ids_and_archive(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'notes.json'
            data=store.modify(dict(action='sheet_create',name='projeto interno',context=CONTEXT),path)
            sheet=data['timesheets'][-1];identity=sheet['id']
            activity=entry();activity.pop('id')
            data=store.modify(dict(action='timesheet',sheet_id=identity,**activity),path)
            before=copy.deepcopy(data['timesheets'][-1]['timesheet'])
            data=store.modify(dict(action='sheet_update',sheet_id=identity,name='Centro de custos',context={**CONTEXT,'client_name':'Outro'}),path)
            sheet=data['timesheets'][-1]
            self.assertEqual(sheet['timesheet'],before);self.assertEqual(sheet['id'],identity)
            self.assertEqual(sheet['context']['client_name'],'Outro')
            data=store.modify(dict(action='sheet_rename',sheet_id=identity,name='Renomeada'),path)
            self.assertEqual(data['timesheets'][-1]['context']['client_name'],'Outro')
            for request in [dict(action='sheet_create',name=''),dict(action='sheet_update',sheet_id=identity,context={'client_name':'x'*201}),dict(action='sheet_update',sheet_id=identity,context={'unknown':'x'})]:
                raw=path.read_bytes()
                with self.assertRaises(ValueError):store.modify(request,path)
                self.assertEqual(path.read_bytes(),raw)
        legacy=dict(notes='',tasks=[],timesheets=[dict(id='old',name='Legacy',archived=True,timesheet=[],timesheet_trash=[],timesheet_active=None)])
        before=copy.deepcopy(legacy);timesheet.migrate(legacy);self.assertEqual(legacy,before)

    def test_profile_prefill_only_unsaved_never_overwrites_fiscal_client(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'profiles.json'
            profile=invoice_profiles.load('sheet',path,context=CONTEXT)
            self.assertEqual(profile['client']['name'],CONTEXT['client_name'])
            self.assertFalse(path.exists())
            invoice_profiles.save('sheet',PROFILE,path)
            self.assertEqual(invoice_profiles.load('sheet',path,context=CONTEXT)['client'],PROFILE['client'])

    def test_invoice_context_and_provenance_optional_old_snapshots_remain_valid(self):
        current=document()
        self.assertEqual(current['context'],CONTEXT)
        self.assertEqual(current['client'],PROFILE['client'])
        self.assertEqual(current['source_entries'][0]['id'],'synthetic')
        self.assertEqual(invoice.validate_snapshot(current),current)
        legacy=copy.deepcopy(current);legacy.pop('context');legacy.pop('source_entries')
        self.assertEqual(invoice.validate_snapshot(legacy),legacy)
        invalid=copy.deepcopy(current);invalid['source_entries'][0]['start']='01:00'
        with self.assertRaises(ValueError):invoice.validate_snapshot(invalid)

    def test_context_labels_pdf_pt_en_escaped_without_fiscal_replacement(self):
        with tempfile.TemporaryDirectory() as temporary:
            for language,label in [('pt','Contrato / projeto'),('en','Contract / project')]:
                result=document();result['language']=language
                path=invoice_pdf.write(result,Path(temporary)/(language+'.pdf'))
                text=subprocess.run(['/usr/bin/pdftotext',str(path),'-'],capture_output=True,text=True,check=True).stdout
                self.assertIn(label,text);self.assertIn('Projeto <Ação> & contrato',text)
                self.assertIn(PROFILE['client']['name'],text);self.assertIn(CONTEXT['client_name'],text)

    def test_duplicate_actual_intervals_not_just_period_legacy_corrupt_and_deleted(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)/'invoices';pdf=Path(temporary)/'source.pdf';pdf.write_bytes(PDF)
            first=invoice_history.record(document(),pdf,root=root)
            result=invoice_history.possible_duplicates(document(),root=root)
            self.assertEqual(result['matches'][0]['minutes'],60)
            self.assertEqual(result['matches'][0]['basis'],'entry_id_and_time')
            other=document([entry(start='11:00',end='12:00')])
            self.assertEqual(invoice_history.possible_duplicates(other,root=root)['matches'],[])
            # Partial overlaps are unioned, not counted more than once.
            partial=document([entry(start='09:30',end='10:30'),entry(start='09:45',end='10:00')])
            self.assertEqual(invoice_history.possible_duplicates(partial,root=root)['matches'][0]['minutes'],30)
            invoice_history.delete(first['id'],root=root)
            self.assertEqual(invoice_history.possible_duplicates(document(),root=root)['matches'],[])
            legacy=document();legacy.pop('source_entries')
            archived=invoice_history.record(legacy,pdf,root=root)
            self.assertTrue(invoice_history.possible_duplicates(document(),root=root)['incomplete'])
            (root/archived['id']/'metadata.json').write_text('corrupt')
            result=invoice_history.possible_duplicates(document(),root=root)
            self.assertEqual(result['matches'],[]);self.assertTrue(result['incomplete'])

    def test_zero_currency_total_still_compares_actual_minutes_and_new_ids(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)/'invoices';pdf=Path(temporary)/'source.pdf';pdf.write_bytes(PDF)
            sheet=dict(id='sheet',name='Minuto',timesheet=[entry(start='09:00',end='09:01')])
            value=invoice.build_snapshot(sheet,reference='ZERO',issued_on='2026-10-19',**{**PROFILE,'rate':'0.10'})
            self.assertEqual(value['total'],'0.00')
            invoice_history.record(value,pdf,root=root)
            newer=copy.deepcopy(value);newer['source_entries'][0]['id']='different-id'
            result=invoice_history.possible_duplicates(newer,root=root)
            self.assertEqual(result['matches'][0]['minutes'],1)
            self.assertEqual(result['matches'][0]['basis'],'time_overlap')

    def test_manual_payment_separate_immutable_original_and_signatures(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)/'invoices';pdf=Path(temporary)/'source.pdf';pdf.write_bytes(PDF)
            record=invoice_history.record(document(),pdf,root=root);identity=record['id']
            original={name:(root/identity/name).read_bytes() for name in ('metadata.json','invoice.pdf')}
            self.assertEqual(invoice_payments.get(identity,root=root),dict(status='not_reported',updated_at=None))
            paid=invoice_history.set_payment(identity,'reported_paid',root=root)
            self.assertEqual(paid['status'],'reported_paid');self.assertTrue(paid['updated_at'])
            self.assertEqual(invoice_history.get(identity,root=root),record)
            self.assertEqual(invoice_history.get_payment(identity,root=root),paid)
            for name,value in original.items():self.assertEqual((root/identity/name).read_bytes(),value)
            self.assertEqual(invoice_payments.set_paid(identity,False,root=root)['status'],'not_reported')
            path=root/identity/'payment.json';self.assertEqual(path.stat().st_mode & 0o777,0o600)
            path.write_text('damaged')
            with self.assertRaises(ValueError):invoice_payments.set_paid(identity,True,root=root)
            self.assertEqual(path.read_text(),'damaged');self.assertEqual(invoice_history.get(identity,root=root),record)


if __name__=='__main__':unittest.main()
