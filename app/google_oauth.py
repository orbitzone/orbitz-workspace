"""Google Desktop authorization using browser, loopback, state and S256 PKCE."""
from ui_language import ui as _i18n
import base64
from contextlib import contextmanager
import hashlib
from http.server import BaseHTTPRequestHandler,HTTPServer
import json
import os
from pathlib import Path
import secrets
import stat
import time
from urllib.parse import urlencode,urlsplit,parse_qs
import webbrowser
import calendar_http as http
from calendar_events import CalendarError

SCOPES=('https://www.googleapis.com/auth/calendar.calendarlist.readonly','https://www.googleapis.com/auth/calendar.events.readonly')
AUTH_URL='https://accounts.google.com/o/oauth2/v2/auth'
TOKEN_URL='https://oauth2.googleapis.com/token'
DEFAULT_CLIENT_ID='227612761270-gua91gpqp9agb5flm164ind5fk7l38hq.apps.googleusercontent.com'


def private_config_path(config_home=None):
    home=Path(config_home) if config_home is not None else Path(os.environ.get('XDG_CONFIG_HOME') or Path.home()/'.config')
    path=home/'orbitz-workspace/google-client.json'
    if not path.is_absolute() or path.resolve()!=path:
        raise _i18n.exception(CalendarError, 'domain.google_oauth.invalid_or_symlinked_private_oauth_configuration_directory')
    return path


def _client_config(data,required_client_id=None,require_secret=False):
    import re
    if not isinstance(data,dict) or not isinstance(data.get('client_id'),str) or not re.fullmatch(r'[A-Za-z0-9._-]{1,200}\.apps\.googleusercontent\.com',data['client_id']):raise ValueError()
    if required_client_id is not None and data['client_id']!=required_client_id:raise ValueError()
    if data.get('token_uri',TOKEN_URL)!=TOKEN_URL or data.get('auth_uri',AUTH_URL) not in (AUTH_URL,'https://accounts.google.com/o/oauth2/auth'):raise ValueError()
    result=dict(client_id=data['client_id'])
    if data.get('client_secret'):result['client_secret']=http.secret(data['client_secret'])
    if require_secret and 'client_secret' not in result:raise ValueError()
    return result


def read_client_config(path,*,private=False,required_client_id=None):
    try:
        path=Path(path).absolute()
        if private:
            if path.resolve()!=path:raise ValueError()
            parent=path.parent.stat()
            if parent.st_uid!=os.getuid() or stat.S_IMODE(parent.st_mode)&0o077:raise ValueError()
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        with os.fdopen(fd,'rb') as stream:
            info=os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode):raise ValueError()
            if private and (info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)&0o077):raise ValueError()
            raw=stream.read(32769)
        if len(raw)>32768:raise ValueError()
        return _client_config(json.loads(raw)['installed'],required_client_id,require_secret=private)
    except (OSError,ValueError,KeyError,TypeError):raise _i18n.exception(CalendarError, 'domain.google_oauth.invalid_google_oauth_configuration_check_the_desktop_client_and_c') from None


def load_config(path=None):
    if path is not None:return read_client_config(path)
    configured=private_config_path()
    if os.path.lexists(configured):
        # Never fall back silently when an installed maintainer configuration is
        # damaged, linked, world-readable, incomplete or belongs to another ID.
        return read_client_config(configured,private=True,required_client_id=DEFAULT_CLIENT_ID)
    return _client_config({'client_id':DEFAULT_CLIENT_ID},required_client_id=DEFAULT_CLIENT_ID)


class Loopback:
    def __init__(self):
        self.state=secrets.token_urlsafe(32)
        self.verifier=secrets.token_urlsafe(64)
        self.code=None;self.denied=False
        owner=self
        class Server(HTTPServer):
            def get_request(self):
                sock,address=super().get_request();sock.settimeout(2);return sock,address
            def handle_error(self,*args):pass
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                valid=False;code=None;denied=False
                try:
                    part=urlsplit(self.path)
                    query=parse_qs(part.query,max_num_fields=10,keep_blank_values=True)
                    host='127.0.0.1:'+str(owner.server.server_port)
                    if self.client_address[0]!='127.0.0.1' or self.headers.get('Host')!=host or part.path!='/' or part.scheme or part.netloc or part.fragment or len(self.path)>8192:raise ValueError()
                    state=query.get('state',[])
                    if len(state)!=1 or not secrets.compare_digest(state[0],owner.state):raise ValueError()
                    if 'error' in query:
                        denied=True;valid=True
                    elif len(query.get('code',[]))==1 and 0<len(query['code'][0])<=4096:
                        code=http.secret(query['code'][0]);valid=True
                except (ValueError,TypeError):pass
                # Commit only validated results before any response I/O. A closed
                # browser may break headers/body writes after completing OAuth.
                if valid:owner.code=code;owner.denied=denied
                message=(_i18n.tr('domain.google_oauth.authorization_received_you_can_close_this_page') if valid else _i18n.tr('domain.google_oauth.invalid_authorization_response')).encode('utf-8')
                try:
                    self.send_response(200 if valid else 400)
                    self.send_header('Content-Type','text/plain; charset=utf-8');self.send_header('Content-Length',str(len(message)))
                    self.send_header('Cache-Control','no-store');self.send_header('Referrer-Policy','no-referrer');self.end_headers()
                    self.wfile.write(message)
                except (BrokenPipeError,ConnectionResetError):pass
        self.server=Server(('127.0.0.1',0),Handler)
        self.server.timeout=.2
        self.redirect_uri='http://127.0.0.1:'+str(self.server.server_port)+'/'

    def authorization_url(self,config):
        challenge=base64.urlsafe_b64encode(hashlib.sha256(self.verifier.encode('ascii')).digest()).rstrip(b'=').decode('ascii')
        return AUTH_URL+'?'+urlencode(dict(client_id=config['client_id'],redirect_uri=self.redirect_uri,response_type='code',scope=' '.join(SCOPES),state=self.state,code_challenge=challenge,code_challenge_method='S256',access_type='offline',prompt='consent'))

    def wait(self,cancel_event=None,timeout=180):
        if not isinstance(timeout,(int,float)) or not 0<timeout<=300:raise _i18n.exception(CalendarError, 'domain.google_oauth.invalid_authorization_timeout')
        deadline=time.monotonic()+timeout
        while self.code is None and not self.denied:
            http.cancelled(cancel_event)
            if time.monotonic()>=deadline:raise _i18n.exception(CalendarError, 'domain.google_oauth.google_authorization_expired_try_again')
            self.server.handle_request()
        http.cancelled(cancel_event)
        if self.denied:raise _i18n.exception(CalendarError, 'domain.google_oauth.google_authorization_was_not_granted')
        result=self.code;self.code=None
        return result

    def close(self):self.server.server_close();self.code=None;self.state='';self.verifier=''


def _tokens(response,previous=None):
    previous=previous or {}
    try:
        access=http.secret(response['access_token'])
        refresh=http.secret(response.get('refresh_token') or previous['refresh_token'])
        scopes=response.get('scope',previous.get('scope',''))
        if response.get('token_type','').lower()!='bearer' or not isinstance(scopes,str) or not set(SCOPES)<=set(scopes.split()):raise ValueError()
        expires=response.get('expires_in')
        if type(expires) is not int or not 30<=expires<=86400:raise ValueError()
        return dict(access_token=access,refresh_token=refresh,scope=scopes,expires_at=time.time()+expires)
    except (ValueError,KeyError,TypeError,AttributeError):raise _i18n.exception(CalendarError, 'domain.google_oauth.incomplete_google_authorization_grant_both_read_scopes_and_try_ag') from None


PROGRESS_STAGES=frozenset(('waiting_authorization','exchanging_token','loading_calendars','saving_credentials'))


def notify_progress(callback,stage):
    if stage not in PROGRESS_STAGES:raise _i18n.exception(ValueError, 'domain.google_oauth.invalid_authorization_stage')
    if callback is not None:
        try:callback(stage)
        except Exception:pass  # UI disposal/progress failure must not change grants.


def authorize(config_path=None,*,cancel_event=None,open_browser=None,on_progress=None):
    config=load_config(config_path);http.cancelled(cancel_event)
    try:flow=Loopback()
    except OSError:raise _i18n.exception(CalendarError, 'domain.google_oauth.could_not_open_the_local_oauth_callback_check_local_network_permi') from None
    try:
        notify_progress(on_progress,'waiting_authorization')
        try:opened=(open_browser or webbrowser.open)(flow.authorization_url(config))
        except Exception:raise _i18n.exception(CalendarError, 'domain.google_oauth.could_not_open_the_browser_to_authorize_google') from None
        if opened is False:raise _i18n.exception(CalendarError, 'domain.google_oauth.could_not_open_the_browser_to_authorize_google')
        code=flow.wait(cancel_event)
        notify_progress(on_progress,'exchanging_token')
        form=dict(config,code=code,code_verifier=flow.verifier,redirect_uri=flow.redirect_uri,grant_type='authorization_code')
        result=_tokens(http.request_json(TOKEN_URL,host='oauth2.googleapis.com',path_prefix='/token',form=form,cancel_event=cancel_event))
        http.cancelled(cancel_event)
        return dict(result,config=config)
    finally:flow.close()


def refresh(payload,*,cancel_event=None):
    try:
        config=payload['config']
        if not isinstance(config,dict):raise ValueError()
        form=dict(client_id=http.secret(config['client_id']),refresh_token=http.secret(payload['refresh_token']),grant_type='refresh_token')
        if config.get('client_secret'):form['client_secret']=http.secret(config['client_secret'])
    except (KeyError,TypeError,ValueError):raise _i18n.exception(CalendarError, 'domain.google_oauth.invalid_google_authorization_in_the_vault_reconnect_the_account') from None
    result=_tokens(http.request_json(TOKEN_URL,host='oauth2.googleapis.com',path_prefix='/token',form=form,cancel_event=cancel_event),payload)
    return dict(result,config=dict(config))
