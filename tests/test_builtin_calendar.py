"""CAL-07 persistent optional built-in ICS source; temporary data only, no HTTP."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
import external_store as remote


class BuiltinCalendarTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.base=Path(self.temporary.name)
        override=patch.object(remote,'PATH',self.base/'data/external-calendars.json');override.start();self.addCleanup(override.stop)

    def test_general_read_never_creates_default_explicit_ensure_idempotent(self):
        self.assertEqual(remote.read(),{'accounts':[],'cache':{}})
        self.assertFalse(remote.PATH.exists())
        account=remote.ensure_default_calendar()
        self.assertTrue(remote.is_builtin(account));self.assertTrue(remote.is_enabled(account))
        self.assertEqual(account['label'],'Brasil · Datas comemorativas')
        self.assertEqual(account['calendars'][0]['url'],remote.BRAZIL_CALENDAR_URL)
        before=remote.PATH.read_bytes();stamp=remote.PATH.stat()
        self.assertEqual(remote.ensure_default_calendar(),account)
        self.assertEqual(remote.PATH.read_bytes(),before)
        self.assertEqual((remote.PATH.stat().st_ino,remote.PATH.stat().st_mtime_ns),(stamp.st_ino,stamp.st_mtime_ns))
        self.assertEqual(len(remote.read()['accounts']),1)

    def test_adopts_legacy_url_without_changing_identity_custom_fields_or_cache(self):
        legacy=dict(id='legacy-account',provider='ics',label='Meu rótulo',custom='preservado',calendars=[dict(id='legacy-calendar',url=remote.BRAZIL_CALENDAR_URL,name='Nome pessoal',color='#123456',custom='campo')])
        remote.add_account(legacy)
        remote.put_cache(legacy['id'],legacy['calendars'][0],'2026-10',[{'title':'Cache sintético'}],'previous')
        before=copy.deepcopy(remote.read());adopted=remote.ensure_default_calendar()
        for key,value in legacy.items():self.assertEqual(adopted[key],value)
        self.assertEqual(remote.read()['cache'],before['cache'])
        self.assertEqual(adopted['id'],'legacy-account');self.assertTrue(adopted['enabled'])
        duplicate={**legacy,'id':'different-account-id'}
        with self.assertRaises(ValueError):remote.add_account(duplicate)
        self.assertEqual(len(remote.read()['accounts']),1)

    def test_toggle_persisted_remove_disables_and_late_cache_write_is_ignored(self):
        account=remote.ensure_default_calendar();calendar=account['calendars'][0]
        remote.put_cache(account['id'],calendar,'2026-10',[{'title':'Original cache'}],'before')
        expected=copy.deepcopy(remote.read()['cache'])
        disabled=remote.set_builtin_enabled(account['id'],False)
        self.assertFalse(remote.is_enabled(disabled))
        raw=remote.PATH.read_bytes()
        remote.put_cache(account['id'],calendar,'2026-10',[{'title':'Late result'}],'late')
        self.assertEqual(remote.PATH.read_bytes(),raw)
        self.assertFalse(remote.ensure_default_calendar()['enabled'])
        self.assertEqual(remote.read()['cache'],expected)
        self.assertTrue(remote.set_builtin_enabled(account['id'],True)['enabled'])
        remote.remove_account(account['id'])
        self.assertEqual(len(remote.read()['accounts']),1)
        self.assertFalse(remote.ensure_default_calendar()['enabled'])
        self.assertEqual(remote.read()['cache'],expected)

    def test_previously_deleted_default_recreated_enabled_without_touching_other_accounts(self):
        other=dict(id='other',provider='ics',label='Outra',calendars=[dict(id='other-cal',url='https://example.invalid/feed.ics',name='Outra')])
        remote.add_account(other);remote.put_cache('other',other['calendars'][0],'2026-10',[],'old')
        original=copy.deepcopy(remote.read());account=remote.ensure_default_calendar()
        def old_deletion(data):data['accounts']=[value for value in data['accounts'] if value['id']!=account['id']]
        remote.update(old_deletion)
        restored=remote.ensure_default_calendar()
        self.assertTrue(restored['enabled']);self.assertEqual(restored['id'],account['id'])
        self.assertEqual(next(value for value in remote.read()['accounts'] if value['id']=='other'),other)
        self.assertEqual(remote.read()['cache'],original['cache'])
        remote.remove_account('other')
        self.assertEqual([value['id'] for value in remote.read()['accounts']],[account['id']])
        self.assertEqual(remote.read()['cache'],{})

    def test_toggle_strict_bool_and_builtin_flag_cannot_authorize_another_url(self):
        account=remote.ensure_default_calendar()
        spoof=dict(id='spoof',provider='ics',builtin=remote.BUILTIN_MARKER,calendars=[dict(id='spoofcal',url='https://example.invalid/other.ics')])
        remote.add_account(spoof);before=remote.PATH.read_bytes()
        self.assertFalse(remote.is_builtin(spoof))
        for invalid in (0,1,'true',None):
            with self.subTest(invalid=invalid),self.assertRaises(ValueError):remote.set_builtin_enabled(account['id'],invalid)
        for identity in ('spoof','missing'):
            with self.assertRaises(ValueError):remote.set_builtin_enabled(identity,False)
        self.assertEqual(remote.PATH.read_bytes(),before)
        remote.remove_account('spoof')
        self.assertFalse(any(value['id']=='spoof' for value in remote.read()['accounts']))

    def test_invalid_or_ambiguous_legacy_is_preserved_not_duplicated(self):
        account=remote.ensure_default_calendar()
        for enabled in (0,'false'):
            def damage(data):data['accounts'][0]['enabled']=enabled
            remote.update(damage);before=remote.PATH.read_bytes()
            with self.assertRaises(ValueError):remote.ensure_default_calendar()
            self.assertEqual(remote.PATH.read_bytes(),before)
        def ambiguous(data):
            data['accounts'][0]['enabled']=True
            data['accounts'][0]['calendars'].append(dict(id='other',url='https://example.invalid/other.ics'))
        remote.update(ambiguous);before=remote.PATH.read_bytes()
        with self.assertRaises(ValueError):remote.ensure_default_calendar()
        self.assertEqual(remote.PATH.read_bytes(),before)

    def test_concurrent_ensure_keeps_one_record(self):
        script='import sys;sys.path.insert(0,sys.argv[1]);import external_store;external_store.ensure_default_calendar()'
        jobs=[];environment={**os.environ,'XDG_DATA_HOME':str(self.base/'xdg')}
        try:
            for _ in range(4):jobs.append(subprocess.Popen([sys.executable,'-c',script,str(ROOT/'app')],env=environment,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True))
            for job in jobs:
                output,error=job.communicate(timeout=10);self.assertEqual(job.returncode,0,error)
            data=json.loads((self.base/'xdg/orbitz-workspace/external-calendars.json').read_text())
            self.assertEqual(len(data['accounts']),1);self.assertTrue(data['accounts'][0]['enabled'])
        finally:
            for job in jobs:
                if job.poll() is None:job.kill()
                job.communicate()


if __name__=='__main__':unittest.main()
