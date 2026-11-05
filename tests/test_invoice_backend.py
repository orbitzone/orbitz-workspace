"""INV-01 domain/profile/PDF contracts with synthetic identities and temporary files."""
import copy
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
import invoice
import invoice_profiles
import invoice_pdf

PROFILE = dict(issuer=dict(name='João Ação <emitente> & Cia',tax_id='000.000.000-00'),client=dict(name='Clínica Sintética',tax_id='00.000.000/0000-00',address='Rua Sintética, 42\nBrasília - DF'),rate='123,45',currency='BRL',language='pt')


def entry(day='2026-10-18', start='09:00', end='10:00', description='Ação <tag> & revisão'):
    return dict(date=day,start=start,end=end,description=description,id='synthetic')


def snapshot(entries=None,**kwargs):
    return invoice.build_snapshot(dict(id='sheet-a',name='Empresa de testes',archived=True,timesheet=entries if entries is not None else [entry()]),reference='INV-TEST-1',issued_on='2026-10-18',**{**PROFILE,**kwargs})


class InvoiceDomainTests(unittest.TestCase):
    def test_decimal_final_rounding_and_integer_minutes(self):
        entries = [entry(start='09:00',end='09:01'),entry(start='09:01',end='09:02'),entry(start='09:02',end='09:03')]
        result = snapshot(entries,rate='0.10')
        self.assertEqual((result['minutes'],result['hours'],result['total']),(3,'00:03','0.01'))
        self.assertEqual(snapshot(entries[:1],rate='0.30')['total'],'0.01')
        self.assertEqual(snapshot(entries[:1],rate='0.10')['total'],'0.00')
        self.assertEqual(snapshot(rate='0.1')['total'],'0.10')
        self.assertEqual(invoice.parse_rate('123,45'),invoice.parse_rate('123.45'))

    def test_period_leap_month_archived_and_active_timer_excluded_without_mutation(self):
        sheet = dict(id='archived',name='Arquivada',archived=True,timesheet=[entry('2024-02-28'),entry('2024-02-29',start='23:59',end='24:00'),entry('2024-03-01')],timesheet_trash=[entry()],timesheet_active=dict(started='2024-02-29T12:00:00',description='timer'))
        data = dict(timesheets=[sheet]);before=copy.deepcopy(data)
        result = invoice.prepare(data,'archived',reference='TEST',issued_on='2026-10-18',start='2024-02-01',end='2024-02-29',**PROFILE)
        self.assertEqual(result['minutes'],61)
        self.assertEqual(len(result['entries']),2)
        self.assertTrue(result['warnings'])
        self.assertFalse(result['period']['all_history'])
        self.assertEqual(invoice.prepare(data,'archived',reference='TEST',issued_on='2026-10-18',**PROFILE)['minutes'],121)
        self.assertEqual(data,before)
        with self.assertRaises(ValueError):snapshot(start='2026-10-19',end='2026-10-20')
        with self.assertRaises(ValueError):snapshot(start='2026-10-18')

    def test_rate_format_required_parties_tax_length_and_currency_language_independence(self):
        for rate in ['0','-1','nan','Infinity','1,234','1.234','1,234.56','1.234,56',1.2,'1e2']:
            with self.subTest(rate=rate),self.assertRaises(ValueError):snapshot(rate=rate)
        for fields in [dict(issuer={'name':'','tax_id':'00000000000'}),dict(client={'name':'Client','tax_id':'1','address':'A'}),dict(client={'name':'Client','tax_id':'00000000000','address':''}),dict(language='es'),dict(currency='R$')]:
            with self.subTest(fields=fields),self.assertRaises(ValueError):snapshot(**fields)
        self.assertEqual(snapshot(language='en',currency='brl')['currency'],'BRL')
        self.assertEqual(snapshot(language='pt',currency='USD')['currency'],'USD')
        self.assertEqual(invoice.format_money('123.45','pt'),'123,45')
        self.assertEqual(invoice.format_money('123.45','en'),'123.45')

    def test_cnpj_alphanumeric_numeric_cpf_and_format_only_validation(self):
        self.assertEqual(invoice.tax_id('ab.cde.123/f45g-00'),'AB.CDE.123/F45G-00')
        self.assertEqual(invoice.tax_id('abcde123f45g00'),'ABCDE123F45G00')
        self.assertEqual(invoice.tax_id('00000000000'),'00000000000')
        for value in ['AB.CDE.123/F45G-A0','ABCDE123F45G0A','ABCDE123F45G0','ABC.DE1.23F/45G0-00']:
            with self.subTest(value=value),self.assertRaises(ValueError):invoice.tax_id(value)

    def test_snapshot_recheck_rejects_mutated_total_and_control_characters(self):
        result=snapshot();result['total']='0.00'
        with self.assertRaises(ValueError):invoice.validate_snapshot(result)
        with self.assertRaises(ValueError):snapshot([entry(description='invalid\x00text')])
        with self.assertRaises(ValueError):snapshot([])


class InvoiceProfileTests(unittest.TestCase):
    def test_isolated_sheet_clients_global_issuer_language_and_private_permissions(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'invoice-profiles.json'
            sentinel=Path(folder)/'notes.json';sentinel.write_text('unchanged')
            self.assertEqual(invoice_profiles.load('sheet-a',path)['currency'],'BRL')
            self.assertFalse(path.exists())
            invoice_profiles.save('sheet-a',PROFILE,path)
            other=copy.deepcopy(PROFILE);other['client']['name']='Outro cliente';other['currency']='USD';other['rate']='10.00';other['issuer']['name']='Emitente atualizado';other['language']='en'
            invoice_profiles.save('sheet-b',other,path)
            saved=invoice_profiles.load('sheet-a',path)
            self.assertEqual(saved['client'],PROFILE['client'])
            self.assertEqual(saved['issuer']['name'],'Emitente atualizado')
            self.assertEqual(saved['language'],'en')
            self.assertEqual(saved['currency'],'BRL')
            self.assertEqual(invoice_profiles.load('sheet-b',path)['currency'],'USD')
            self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o600)
            self.assertEqual(sentinel.read_text(),'unchanged')

    def test_damaged_file_and_failed_atomic_write_preserve_original(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'profiles.json';path.write_text('damaged')
            with self.assertRaises(ValueError):invoice_profiles.load('a',path)
            with self.assertRaises(ValueError):invoice_profiles.save('a',PROFILE,path)
            self.assertEqual(path.read_text(),'damaged')
            path.unlink();invoice_profiles.save('a',PROFILE,path);before=path.read_bytes()
            with patch('atomic_json.os.replace',side_effect=OSError('synthetic failure')):
                with self.assertRaises(OSError):invoice_profiles.save('b',PROFILE,path)
            self.assertEqual(path.read_bytes(),before)
            self.assertEqual(list(Path(folder).glob('.invoice-profiles-*')),[])

    def test_concurrent_profile_saves_keep_every_sheet(self):
        with tempfile.TemporaryDirectory() as folder:
            script='import sys,json;sys.path.insert(0,sys.argv[1]);import invoice_profiles;invoice_profiles.save(sys.argv[2],json.loads(sys.argv[3]))'
            jobs=[]
            try:
                for index in range(6):
                    jobs.append(subprocess.Popen([sys.executable,'-c',script,str(ROOT/'app'),str(index),json.dumps(PROFILE)],env={**os.environ,'XDG_DATA_HOME':folder},stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True))
                for job in jobs:
                    stdout,stderr=job.communicate(timeout=10)
                    self.assertEqual(job.returncode,0,stderr)
                path=Path(folder)/'orbitz-workspace/invoice-profiles.json'
                self.assertEqual(set(invoice_profiles.read(path)['sheets']),{str(i) for i in range(6)})
            finally:
                for job in jobs:
                    if job.poll() is None:job.kill()
                    job.communicate()


class InvoicePdfTests(unittest.TestCase):
    def test_pt_en_text_unicode_embedded_font_multipage_and_no_xml_injection(self):
        long_profile=copy.deepcopy(PROFILE)
        long_profile['client']['address']='Rua Sintética - endereço fiscal longo. '*45
        entries=[entry(description=('Ação <tag> & revisão\n'*35)+'END_ACTIVITY') for _ in range(4)]
        with tempfile.TemporaryDirectory() as folder:
            for language,title,total in [('pt','Fatura de serviços','BRL 493,80'),('en','Service invoice','BRL 493.80')]:
                with self.subTest(language=language):
                    document=invoice.build_snapshot(dict(id='a',name='Empresa sintética',timesheet=entries),reference='INVOICE-TEST',issued_on='2026-10-18',**{**long_profile,'language':language})
                    path=invoice_pdf.write(document,Path(folder)/(language+'.pdf'))
                    content=subprocess.run(['pdftotext','-layout',str(path),'-'],capture_output=True,text=True,check=True).stdout
                    self.assertIn(title,content);self.assertIn('João Ação <emitente> & Cia',content)
                    self.assertIn('Clínica Sintética',content);self.assertIn(total,content)
                    self.assertEqual(content.count('END_ACTIVITY'),4)
                    self.assertGreater(len(content.split('\f')),2)
                    self.assertIn('<tag> & revisão',content)
                    fonts=subprocess.run(['pdffonts',str(path)],capture_output=True,text=True,check=True).stdout
                    self.assertIn('DejaVuSans',fonts)
                    self.assertIn('yes yes yes',fonts)
                    self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o600)

    def test_pdf_overwrite_confirmation_atomic_failure_and_symlink_refusal(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'invoice.pdf';path.write_bytes(b'original')
            with self.assertRaises(FileExistsError):invoice_pdf.write(snapshot(),path)
            self.assertEqual(path.read_bytes(),b'original')
            with patch.object(invoice_pdf,'_build',side_effect=RuntimeError('synthetic render failure')):
                with self.assertRaises(RuntimeError):invoice_pdf.write(snapshot(),path,overwrite=True)
            self.assertEqual(path.read_bytes(),b'original')
            self.assertEqual(list(Path(folder).glob('.invoice-*')),[])
            invoice_pdf.write(snapshot(),path,overwrite=True)
            self.assertTrue(path.read_bytes().startswith(b'%PDF'))
            link=Path(folder)/'link.pdf';link.symlink_to(path)
            with self.assertRaises(ValueError):invoice_pdf.write(snapshot(),link,overwrite=True)

    def test_pdf_no_clobber_when_target_appears_while_rendering(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'invoice.pdf'
            def rendering(document,stream):
                stream.write(b'generated')
                path.write_bytes(b'concurrent user file')
            with patch.object(invoice_pdf,'_build',side_effect=rendering):
                with self.assertRaises(FileExistsError):invoice_pdf.write(snapshot(),path)
            self.assertEqual(path.read_bytes(),b'concurrent user file')


if __name__=='__main__':unittest.main()
