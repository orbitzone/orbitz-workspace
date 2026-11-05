"""Standalone boundaries tested without user data or a graphical session."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class StandaloneTests(unittest.TestCase):
    def test_domain_paths_and_language_are_owned_by_this_app(self):
        with tempfile.TemporaryDirectory() as folder:
            env = dict(os.environ, XDG_DATA_HOME=folder, XDG_CONFIG_HOME=folder,
                       PYTHONPATH=str(ROOT/'app'), ORBITZ_LOCALE='pt-BR',
                       GSETTINGS_BACKEND='memory')
            code = '''import json,store,external_store,ui_state,invoice_history,invoice_profiles,workspace_backup,calendar_accounts,google_oauth
from ui_language import ui
print(json.dumps([str(p) for p in (store.DATA,external_store.PATH,ui_state.PATH,invoice_history.ROOT,invoice_profiles.PATH,workspace_backup.DATA,calendar_accounts.LOCK_ROOT,google_oauth.private_config_path())]+[ui.get_locale()]))
'''
            result = subprocess.run([sys.executable,'-c',code],env=env,capture_output=True,text=True,check=True)
            paths = json.loads(result.stdout)
            self.assertEqual(paths[-1], 'pt-BR')
            for path in paths[:-1]:
                self.assertTrue(Path(path).is_relative_to(Path(folder)/'orbitz-workspace'), path)
            self.assertFalse((Path(folder)/'orbitz-widgets').exists())

    def test_launcher_does_not_reference_original_checkout(self):
        source = (ROOT/'data/orbitz-workspace').read_text()
        self.assertNotIn('/home/', source)
        self.assertNotIn('orbitz-widgets', source)
        self.assertIn('io.orbitz.Workspace', (ROOT/'app/calendar-app.py').read_text())

    def test_product_identity_is_not_shared_with_widgets(self):
        source = (ROOT/'app/credential_vault.py').read_text()
        self.assertIn('io.orbitz.Workspace.iCloud', source)
        self.assertIn('io.orbitz.Workspace.Provider', source)
        self.assertNotIn('io.orbitz.Calendar.', source)
        self.assertIn("author='Orbitz Workspace'", (ROOT/'app/invoice_pdf.py').read_text())
