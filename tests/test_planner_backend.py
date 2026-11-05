"""Planner boundary regressions using synthetic calendars and temporary data only."""
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from datetime import date, datetime
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
import atomic_json
import apple_client
import calendar_events
import credential_vault
import external_store
import ics_client
import store
import timesheet
import ui_state


class PersistenceTests(unittest.TestCase):
    def test_atomic_failure_preserves_original_and_cleans_temporary(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'data.json'
            path.write_text('{"original": true}')
            for data, fail_replace in [({'invalid': object()}, False), ({'new': 1}, True)]:
                with self.subTest(fail_replace=fail_replace):
                    if fail_replace:
                        with patch.object(atomic_json.os, 'replace', side_effect=OSError('replace failed')):
                            with self.assertRaises(OSError):
                                atomic_json.write(path, data, prefix='.test-')
                    else:
                        with self.assertRaises(TypeError):
                            atomic_json.write(path, data, prefix='.test-')
                    self.assertEqual(path.read_text(), '{"original": true}')
                    self.assertEqual(list(Path(folder).iterdir()), [path])

    def test_atomic_permissions_and_durability_order(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'data.json'
            operations = []
            real_fsync, real_replace = os.fsync, os.replace
            def fsync(fd):
                operations.append('directory' if stat.S_ISDIR(os.fstat(fd).st_mode) else 'file')
                real_fsync(fd)
            def replace(source, destination):
                self.assertEqual(stat.S_IMODE(os.stat(source).st_mode), 0o600)
                operations.append('replace')
                real_replace(source, destination)
            with patch.object(atomic_json.os, 'fsync', side_effect=fsync), patch.object(atomic_json.os, 'replace', side_effect=replace):
                atomic_json.write(path, {'text': 'ação'}, prefix='.test-', encoding='utf-8')
            self.assertEqual(operations, ['file', 'replace', 'directory'])
            self.assertEqual(json.loads(path.read_text()), {'text': 'ação'})
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_store_backups_restore_and_retention(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'notes.json'
            store.modify({'action': 'task', 'text': 'Original', 'date': '2026-10-18'}, path)
            original = store.read(path)
            store.modify({'action': 'notes', 'notes': 'alterado'}, path)
            name = store.list_backups(path)[0]
            backup = store.backup_file(name, path)
            request = dict(action='backup_restore', name=name, expected=store.fingerprint(store.read(path)), backup_hash=hashlib.sha256(backup.read_bytes()).hexdigest())
            restored = store.modify(request, path)
            self.assertEqual(restored, original)
            # Restore first snapshots the complete state being replaced.
            self.assertTrue(any(json.loads((path.parent/'planner-backups'/n).read_text())['notes'] == 'alterado' for n in store.list_backups(path)))
            with self.assertRaises(ValueError):
                store.modify({**request, 'expected': 'stale'}, path)
            for i in range(61):
                store.modify({'action': 'notes', 'notes': str(i)}, path)
            self.assertEqual(len(store.list_backups(path)), 60)
            self.assertEqual(store.read(path)['notes'], '60')
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_drafts_and_external_accounts_remain_independent(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(ui_state, 'PATH', Path(folder)/'ui.json'), patch.object(external_store, 'PATH', Path(folder)/'external.json'):
            ui_state.set('draft', {'description': 'rascunho'})
            account = {'id': 'synthetic', 'email': 'test@example.invalid', 'calendars': [{'id': 'calendar'}]}
            external_store.add_account(account)
            external_store.put_cache('synthetic', {'id': 'calendar'}, '2026-10', [{'title': 'Evento'}], 1)
            with self.assertRaises(ValueError):
                external_store.add_account(account)
            external_store.remove_account('synthetic')
            self.assertEqual(external_store.read(), {'accounts': [], 'cache': {}})
            self.assertEqual(ui_state.get('draft'), {'description': 'rascunho'})
            ui_state.set('draft', None)
            self.assertEqual(ui_state.read(), {})
            ui_state.PATH.write_text('damaged')
            self.assertEqual(ui_state.get('draft', 'fallback'), 'fallback')
            with self.assertRaises(ValueError):
                ui_state.set('draft', 'new')
            self.assertEqual(ui_state.PATH.read_text(), 'damaged')
            self.assertIs(external_store.Vault, credential_vault.Vault)

    def test_cli_concurrent_edits_are_serialized(self):
        with tempfile.TemporaryDirectory() as folder:
            environment = {**os.environ, 'XDG_DATA_HOME': folder}
            processes = []
            try:
                for i in range(8):
                    process = subprocess.Popen(
                        [sys.executable, str(ROOT/'app/store.py')],
                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        text=True, env=environment,
                    )
                    processes.append(process)
                    process.stdin.write(json.dumps(dict(action='task', text=f'Task {i}', date='2026-10-18')))
                    process.stdin.close()
                    process.stdin = None
                for process in processes:
                    stdout, stderr = process.communicate(timeout=10)
                    self.assertEqual(process.returncode, 0, stderr)
                    self.assertTrue(json.loads(stdout)['ok'])
                saved = store.read(Path(folder)/'orbitz-workspace/notes.json')
                self.assertEqual({task['text'] for task in saved['tasks']}, {f'Task {i}' for i in range(8)})
            finally:
                for process in processes:
                    if process.poll() is None:
                        process.kill()
                    process.communicate()

    def test_task_timesheet_contract_and_midnight_timer(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'notes.json'
            data = store.modify(dict(action='task', text='Tarefa', date='2026-10-18'), path)
            identity = data['tasks'][0]['id']
            store.modify(dict(action='toggle', id=identity), path)
            request = dict(action='task_timesheet', task_id=identity, sheet_id='default', start='09:00', end='10:00')
            data = store.modify(request, path)
            self.assertEqual(data['timesheets'][0]['timesheet'][0]['source_task_id'], identity)
            with self.assertRaises(ValueError):store.modify(request, path)
            timesheet.modify(data, dict(action='timesheet_start', description='Virada'), now=datetime(2026,10,18,23,50))
            timesheet.modify(data, dict(action='timesheet_stop'), now=datetime(2026,10,19,0,10))
            entries = data['timesheets'][0]['timesheet']
            self.assertEqual([(e['start'],e['end']) for e in entries[-2:]], [('23:50','24:00'),('00:00','00:10')])
            self.assertEqual(timesheet.total(entries), 80)
            csv = timesheet.csv_text([{**entries[0], 'description': '=1+1'}], '2026-10-18','2026-10-19')
            self.assertIn("'=1+1", csv)


class CalendarTests(unittest.TestCase):
    FEED = '''BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Orbitz Test//EN
BEGIN:VEVENT
UID:recurring-synthetic
DTSTART:20261018T120000Z
DTEND:20261018T130000Z
RRULE:FREQ=DAILY;COUNT=3
EXDATE:20261019T120000Z
SUMMARY:Reunião
BEGIN:VALARM
ACTION:DISPLAY
DESCRIPTION:Aviso
TRIGGER:-PT10M
END:VALARM
END:VEVENT
BEGIN:VEVENT
UID:all-day-synthetic
DTSTART;VALUE=DATE:20261020
DTEND;VALUE=DATE:20261022
SUMMARY:Dia inteiro
END:VEVENT
END:VCALENDAR
'''

    def test_shared_normalization_identity_recurrence_and_alarms(self):
        data = ics_client.parse(self.FEED, 'account', 'calendar', '2026-10')
        self.assertIs(apple_client.normalize_events, calendar_events.normalize_events)
        self.assertIs(apple_client.CalendarError, calendar_events.CalendarError)
        recurring = [e for e in data if e['uid']=='recurring-synthetic']
        self.assertEqual([e['start'] for e in recurring], ['2026-10-18T09:00:00-03:00','2026-10-20T09:00:00-03:00'])
        self.assertEqual([e['alarm_minutes'] for e in recurring], [[10.0],[10.0]])
        for event in recurring:
            expected = hashlib.sha256(calendar_events.json_identity('account','calendar',event['uid'],event['occurrence']).encode()).hexdigest()
            self.assertEqual(event['key'], expected)
        self.assertEqual(len({e['key'] for e in data}), 3)
        all_day = next(e for e in data if e['all_day'])
        self.assertEqual(all_day['alarm_minutes'], [])
        self.assertTrue(apple_client.on_day(all_day, date(2026,10,21)))
        self.assertFalse(apple_client.on_day(all_day, date(2026,10,22)))

    def test_invalid_calendar_and_unsafe_urls_preserve_error_contract(self):
        with self.assertRaises(apple_client.CalendarError):
            ics_client.parse('invalid calendar', 'account','calendar','2026-10')
        for url in ['http://caldav.icloud.com/', 'https://icloud.com.evil.invalid/', 'https://user:pass@caldav.icloud.com/']:
            with self.assertRaises(apple_client.CalendarError):apple_client.apple_url(url)
        self.assertEqual(ics_client.subscription_url('webcal://example.invalid/calendar#fragment'), 'https://example.invalid/calendar')


if __name__ == '__main__':
    unittest.main()
