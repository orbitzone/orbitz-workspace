"""Maintainer setup with synthetic secrets and isolated XDG config directories."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'app'))
import google_oauth as oauth
import calendar_http as http
from calendar_events import CalendarError

SPEC=importlib.util.spec_from_file_location('configure_google_client',REPO/'tools/configure-google-client.py')
setup=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(setup)
SECRET='synthetic-maintainer-secret-SENTINEL'


class GoogleClientConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.home=self.base/'config'
        environment=patch.dict(os.environ,{'XDG_CONFIG_HOME':str(self.home)});environment.start();self.addCleanup(environment.stop)
        self.source=self.base/'desktop-fixture.json'
        self.config={'client_id':oauth.DEFAULT_CLIENT_ID,'client_secret':SECRET}
        self.source.write_text(json.dumps({'installed':dict(self.config,auth_uri=oauth.AUTH_URL,token_uri=oauth.TOKEN_URL,project_id='not-copied')}))
        self.target=oauth.private_config_path()

    def test_none_falls_back_only_when_absent_then_private_matching_config_loads(self):
        self.assertEqual(oauth.load_config(),{'client_id':oauth.DEFAULT_CLIENT_ID})
        setup.configure(self.source)
        self.assertEqual(oauth.load_config(),self.config)
        self.assertEqual(self.target.stat().st_mode & 0o777,0o600)
        self.assertEqual(self.target.parent.stat().st_mode & 0o777,0o700)
        self.assertEqual(json.loads(self.target.read_text()),{'installed':self.config})
        self.assertNotIn('project_id',self.target.read_text())
        setup.configure(self.source)  # Identical configuration is idempotent.
        self.assertTrue(setup.check())

    def test_check_and_cli_do_not_expose_values_and_never_authenticate(self):
        output=io.StringIO()
        with patch.object(oauth,'authorize',side_effect=AssertionError('no auth')),patch.object(http,'request_json',side_effect=AssertionError('no network')),contextlib.redirect_stdout(output),patch.object(sys,'argv',['configure-google-client.py','--from-json',str(self.source)]):setup.main()
        with contextlib.redirect_stdout(output),patch.object(sys,'argv',['configure-google-client.py','--check']):setup.main()
        self.assertIn('GOOGLE_CLIENT_CONFIG_OK',output.getvalue())
        self.assertNotIn(SECRET,output.getvalue());self.assertNotIn(oauth.DEFAULT_CLIENT_ID,output.getvalue())

    def test_mismatch_missing_secret_web_config_and_injected_endpoint_are_refused(self):
        invalid=[{'installed':dict(self.config,client_id='different.apps.googleusercontent.com')},{'installed':{'client_id':oauth.DEFAULT_CLIENT_ID}},{'web':self.config},{'installed':dict(self.config,token_uri='https://evil.invalid/token')}]
        for value in invalid:
            with self.subTest(value_type=list(value)):
                self.source.write_text(json.dumps(value))
                with self.assertRaises(ValueError) as failed:setup.configure(self.source)
                self.assertNotIn(SECRET,str(failed.exception));self.assertFalse(self.target.exists())

    def test_present_but_invalid_never_falls_back_or_reads_private_values_into_errors(self):
        setup.configure(self.source)
        for value in [{'installed':dict(self.config,client_id='different.apps.googleusercontent.com')}, {'installed':{'client_id':oauth.DEFAULT_CLIENT_ID}}, {'private':SECRET}]:
            self.target.write_text(json.dumps(value));self.target.chmod(0o600)
            with self.assertRaises(CalendarError) as failed:oauth.load_config()
            self.assertNotIn(SECRET,str(failed.exception))
        self.target.write_text('x'*32769)
        with self.assertRaises(CalendarError):oauth.load_config()

    def test_insecure_permissions_symlinks_and_repository_destination_refused(self):
        setup.configure(self.source);self.target.chmod(0o644)
        with self.assertRaises(CalendarError):oauth.load_config()
        self.target.chmod(0o600);self.target.parent.chmod(0o755)
        with self.assertRaises(CalendarError):oauth.load_config()
        self.target.parent.chmod(0o700);self.target.unlink();self.target.symlink_to(self.source)
        with self.assertRaises(CalendarError):oauth.load_config()
        with self.assertRaises(CalendarError):setup.configure(self.source)
        self.target.unlink()
        linked=self.base/'linked-config';linked.symlink_to(self.home)
        with self.assertRaises(CalendarError):setup.configure(self.source,config_home=linked)
        with self.assertRaises(ValueError):setup.configure(self.source,config_home=REPO/'unsafe-test-config')
        self.assertFalse((REPO/'unsafe-test-config').exists())

    def test_atomic_failure_and_explicit_replace_preserve_previous_config(self):
        setup.configure(self.source);original=self.target.read_bytes()
        changed=dict(self.config,client_secret='synthetic-rotated-secret-SENTINEL')
        self.source.write_text(json.dumps({'installed':changed}))
        with self.assertRaises(FileExistsError):setup.configure(self.source)
        self.assertEqual(self.target.read_bytes(),original)
        with patch.object(setup.os,'replace',side_effect=OSError('synthetic replace failure')):
            with self.assertRaises(OSError):setup.configure(self.source,replace=True)
        self.assertEqual(self.target.read_bytes(),original)
        self.assertEqual(list(self.target.parent.glob('.google-client-*')),[])
        setup.configure(self.source,replace=True)
        self.assertEqual(oauth.load_config(),changed)

    def test_default_token_post_uses_provided_secret_and_existing_refresh_config_unchanged(self):
        setup.configure(self.source)
        class Flow:
            verifier='synthetic-verifier';redirect_uri='http://127.0.0.1:1234/'
            def authorization_url(self,config):
                self.assertion='client_secret' not in oauth.AUTH_URL
                return oauth.AUTH_URL+'?client_id='+config['client_id']
            def wait(self,cancel_event):return 'synthetic-code'
            def close(self):pass
        tokens=dict(access_token='synthetic-access',refresh_token='synthetic-refresh',token_type='Bearer',scope=' '.join(oauth.SCOPES),expires_in=3600)
        with patch.object(oauth,'Loopback',return_value=Flow()),patch.object(http,'request_json',return_value=tokens) as request:
            result=oauth.authorize(open_browser=lambda url:SECRET not in url)
            self.assertEqual(request.call_args.kwargs['form']['client_secret'],SECRET)
            self.assertEqual(result['config'],self.config)
        previous=dict(config={'client_id':'legacy.apps.googleusercontent.com','client_secret':'synthetic-existing-secret'},refresh_token='old-refresh',scope=' '.join(oauth.SCOPES))
        response={key:value for key,value in tokens.items() if key!='refresh_token'}
        with patch.object(oauth,'load_config',side_effect=AssertionError('refresh must use existing vault grant')),patch.object(http,'request_json',return_value=response) as request:
            refreshed=oauth.refresh(previous)
            self.assertEqual(request.call_args.kwargs['form']['client_secret'],'synthetic-existing-secret')
            self.assertEqual(refreshed['refresh_token'],'old-refresh')
            self.assertEqual(previous['config']['client_id'],'legacy.apps.googleusercontent.com')

    def test_gitignore_patterns_cover_config_and_download_names(self):
        for name in ('client_secret_fixture.json','credentials.json','google-client.json'):
            result=subprocess.run(['git','check-ignore','--quiet','--no-index',name],cwd=REPO)
            self.assertEqual(result.returncode,0)


if __name__=='__main__':unittest.main()
