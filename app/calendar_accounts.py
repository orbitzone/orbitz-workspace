"""Provider lifecycle: private vault credentials, public metadata, cache-independent I/O."""
from ui_language import ui as _i18n
from contextlib import contextmanager
import fcntl
import hashlib
import os
from pathlib import Path
import re
import stat
import time
import calendar_http as http
from calendar_events import CalendarError
from credential_vault import ProviderVault
from google_client import GoogleClient
from calendly_client import CalendlyClient
import google_oauth
import external_store as remote

LOCK_ROOT=Path(os.environ.get('XDG_DATA_HOME') or Path.home()/'.local/share')/'orbitz-workspace/.calendar-provider-locks'
_ACCESS={}


def _identity(provider,resource):return provider+'-'+hashlib.sha256(resource.encode()).hexdigest()


def _validate(provider,identity):
    if provider not in ('google','calendly') or not isinstance(identity,str) or not re.fullmatch(provider+r'-[0-9a-f]{64}',identity):raise _i18n.exception(CalendarError, 'domain.calendar_accounts.invalid_calendar_connection')


@contextmanager
def _lock(provider,identity,cancel_event=None):
    _validate(provider,identity)
    if LOCK_ROOT.absolute().resolve()!=LOCK_ROOT.absolute():raise _i18n.exception(CalendarError, 'domain.calendar_accounts.symlinked_authorization_directory_refused')
    LOCK_ROOT.mkdir(parents=True,exist_ok=True,mode=0o700);LOCK_ROOT.chmod(0o700)
    fd=os.open(LOCK_ROOT/(identity+'.lock'),os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW|os.O_NONBLOCK,0o600)
    with os.fdopen(fd,'r+') as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):raise _i18n.exception(CalendarError, 'domain.calendar_accounts.invalid_authorization_lock')
        os.fchmod(stream.fileno(),0o600)
        deadline=time.monotonic()+20
        while True:
            http.cancelled(cancel_event)
            try:fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB);break
            except BlockingIOError:
                if time.monotonic()>=deadline:raise _i18n.exception(CalendarError, 'domain.calendar_accounts.another_authorization_is_in_progress_try_again') from None
                time.sleep(.05)
        yield


def _label(value):
    if not isinstance(value,str) or not 0<len(value.strip())<=100 or any(ord(c)<32 for c in value):raise _i18n.exception(CalendarError, 'domain.calendar_accounts.enter_a_connection_name_of_up_to_100_characters')
    return value.strip()


def _connected(provider,identity):
    _validate(provider,identity)
    account=next((account for account in remote.read()['accounts'] if account.get('id')==identity and account.get('provider')==provider),None)
    if account is None:raise _i18n.exception(CalendarError, 'domain.calendar_accounts.connection_removed_refresh_the_calendar_list')
    return account


def _commit(account,payload,cancel_event,access=None):
    provider,identity=account['provider'],account['id']
    with _lock(provider,identity,cancel_event):
        http.cancelled(cancel_event)
        if any(value.get('id')==identity for value in remote.read()['accounts']):raise _i18n.exception(CalendarError, 'domain.calendar_accounts.this_account_is_already_connected_disconnect_before_reconnecting')
        vault=ProviderVault();written=False;added=False
        try:
            vault.put(provider,identity,payload);written=True
            http.cancelled(cancel_event)
            remote.add_account(account);added=True
            http.cancelled(cancel_event)
            if access:_ACCESS[identity]=access
            return account
        except Exception:
            _ACCESS.pop(identity,None)
            pending=False
            if added:
                try:remote.remove_account(identity)
                except Exception:pending=True
            if written:
                try:vault.delete(provider,identity)
                except Exception:pending=True
            if pending:raise _i18n.exception(CalendarError, 'domain.calendar_accounts.connection_not_confirmed_check_removal_of_the_connection_and_vaul') from None
            raise


def connect_google(config_path,label,*,cancel_event=None,open_browser=None,on_progress=None):
    label=_label(label)
    credentials=google_oauth.authorize(config_path,cancel_event=cancel_event,open_browser=open_browser,on_progress=on_progress)
    google_oauth.notify_progress(on_progress,'loading_calendars')
    calendars=GoogleClient(credentials['access_token'],cancel_event=cancel_event).discover()
    primary=next((calendar['remote_id'] for calendar in calendars if calendar['primary']),calendars[0]['remote_id'])
    identity=_identity('google',credentials['config']['client_id']+'|'+primary)
    account=dict(id=identity,provider='google',label=label,calendars=calendars)
    payload={key:credentials[key] for key in ('config','refresh_token','scope')}
    # Access tokens are held only in RAM, under the same lifecycle lock.
    google_oauth.notify_progress(on_progress,'saving_credentials')
    return _commit(account,payload,cancel_event,access=(credentials['access_token'],credentials['expires_at']))


def connect_calendly(token,label,*,cancel_event=None):
    label=_label(label);token=http.secret(token)
    calendars=CalendlyClient(token,cancel_event=cancel_event).discover()
    identity=_identity('calendly',calendars[0]['user_uri'])
    account=dict(id=identity,provider='calendly',label=label,calendars=calendars)
    return _commit(account,dict(token=token),cancel_event)


def _access(provider,identity,cancel_event):
    # File lock serializes refresh + vault rotation across threads/processes.
    # Release it before fetching pages, allowing calendars in one account to sync.
    with _lock(provider,identity,cancel_event):
        http.cancelled(cancel_event);_connected(provider,identity)
        vault=ProviderVault()
        if provider=='calendly':return http.secret(vault.get(provider,identity)['token'])
        cached=_ACCESS.get(identity)
        if cached and cached[1]>time.time()+60:return cached[0]
        previous=vault.get(provider,identity)
        refreshed=google_oauth.refresh(previous,cancel_event=cancel_event)
        # Google commonly omits refresh_token in refresh responses. refresh()
        # carries the previous token forward; rotated grants are saved first.
        payload={key:refreshed[key] for key in ('config','refresh_token','scope')}
        vault.put(provider,identity,payload)
        http.cancelled(cancel_event)
        _ACCESS[identity]=(refreshed['access_token'],refreshed['expires_at'])
        return refreshed['access_token']


def events(account,calendar,month,*,cancel_event=None):
    try:provider,identity=account['provider'],account['id']
    except (KeyError,TypeError):raise _i18n.exception(CalendarError, 'domain.calendar_accounts.invalid_calendar_connection') from None
    connected=_connected(provider,identity)
    current=next((value for value in connected['calendars'] if value.get('id')==calendar.get('id')),None)
    if current!=calendar:raise _i18n.exception(CalendarError, 'domain.calendar_accounts.calendar_changed_refresh_the_list_before_querying')
    token=_access(provider,identity,cancel_event)
    client=(GoogleClient if provider=='google' else CalendlyClient)(token,cancel_event=cancel_event)
    try:return client.events(calendar,identity,month)
    except Exception:
        _ACCESS.pop(identity,None)
        raise


def disconnect(account):
    try:provider,identity=account['provider'],account['id']
    except (KeyError,TypeError):raise _i18n.exception(CalendarError, 'domain.calendar_accounts.invalid_calendar_connection') from None
    with _lock(provider,identity):
        _ACCESS.pop(identity,None)
        ProviderVault().delete(provider,identity)
        remote.remove_account(identity)
