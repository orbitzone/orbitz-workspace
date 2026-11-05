"""External calendar accounts and caches; no credentials or task data."""
from ui_language import ui as _i18n
import copy,fcntl,hashlib,json,os
import atomic_json
from credential_vault import Vault  # Existing callers use external_store.Vault.
from pathlib import Path
PATH=Path(os.environ.get('XDG_DATA_HOME') or Path.home()/'.local/share')/'orbitz-workspace'/'external-calendars.json'

BRAZIL_CALENDAR_URL='https://calendar.google.com/calendar/ical/pt.brazilian%23holiday%40group.v.calendar.google.com/public/basic.ics'
BRAZIL_CALENDAR_LABEL='Brasil · Datas comemorativas'
BUILTIN_MARKER='brazil-observances'


def _has_builtin_url(account):
    if not isinstance(account,dict) or account.get('provider')!='ics':return False
    calendars=account.get('calendars')
    return isinstance(calendars,list) and any(isinstance(calendar,dict) and calendar.get('url')==BRAZIL_CALENDAR_URL for calendar in calendars)


def is_builtin(account):
    return _has_builtin_url(account) and len(account['calendars'])==1


def is_enabled(account):
    return isinstance(account,dict) and account.get('enabled',True) is True


def ensure_default_calendar():
    """Explicit interface initialization; general read() has no side effects."""
    selected=[]
    def ensure(data):
        matches=[account for account in data['accounts'] if _has_builtin_url(account)]
        if matches:
            # Do not split or delete ambiguous legacy multi-calendar accounts.
            if len(matches)!=1 or not is_builtin(matches[0]):raise _i18n.exception(ValueError, 'domain.external_store.duplicate_or_grouped_brazilian_source_records_preserved_for_revie')
            account=matches[0]
            if not isinstance(account.get('id'),str) or not account['id'] or not isinstance(account['calendars'][0].get('id'),str) or not account['calendars'][0]['id']:raise _i18n.exception(ValueError, 'domain.external_store.invalid_brazilian_source_identity_original_preserved')
            if 'enabled' in account and type(account['enabled']) is not bool:raise _i18n.exception(ValueError, 'domain.external_store.invalid_brazilian_source_state_original_preserved')
            account['builtin']=BUILTIN_MARKER
            account.setdefault('enabled',True)
        else:
            digest=hashlib.sha256(BRAZIL_CALENDAR_URL.encode()).hexdigest()
            identity='ics-'+digest
            if any(account.get('id')==identity for account in data['accounts']):raise _i18n.exception(ValueError, 'domain.external_store.the_default_source_identity_is_already_in_use_records_preserved')
            account=dict(id=identity,provider='ics',label=BRAZIL_CALENDAR_LABEL,builtin=BUILTIN_MARKER,enabled=True,
                         calendars=[dict(id=digest,url=BRAZIL_CALENDAR_URL,name=BRAZIL_CALENDAR_LABEL,color='#82cfff')])
            data['accounts'].append(account)
        selected.append(account)
    update(ensure)
    return selected[0]


def set_builtin_enabled(identity,enabled):
    if type(enabled) is not bool:raise _i18n.exception(ValueError, 'domain.external_store.the_default_source_state_must_be_boolean')
    selected=[]
    def change(data):
        account=next((account for account in data['accounts'] if account.get('id')==identity),None)
        if not is_builtin(account):raise _i18n.exception(ValueError, 'domain.external_store.state_changes_are_only_available_for_the_default_brazilian_source')
        account['enabled']=enabled;account['builtin']=BUILTIN_MARKER
        selected.append(account)
    update(change)
    return selected[0]

def read():
    try:data=json.loads(PATH.read_text())
    except FileNotFoundError:return {'accounts':[],'cache':{}}
    if not isinstance(data,dict) or not isinstance(data.get('accounts'),list) or not isinstance(data.get('cache'),dict):raise _i18n.exception(ValueError, 'domain.external_store.invalid_external_calendar_file_original_preserved')
    return data

def update(callback):
    PATH.parent.mkdir(parents=True,exist_ok=True)
    with open(str(PATH)+'.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX);data=read();before=copy.deepcopy(data);callback(data)
        if data==before:return data
        atomic_json.write(PATH, data, prefix='.external-')
    return data

def add_account(account):
    def add(data):
        if _has_builtin_url(account) and any(_has_builtin_url(existing) for existing in data['accounts']):raise _i18n.exception(ValueError, 'domain.external_store.the_brazilian_source_is_already_available_use_enable_in_connectio')
        if any(a['id']==account['id'] or (account.get('email') and a.get('email','').casefold()==account['email'].casefold()) for a in data['accounts']):raise _i18n.exception(ValueError, 'domain.external_store.this_account_is_already_connected_disconnect_it_in_manage_connect')
        data['accounts'].append(account)
    return update(add)

def remove_account(identity):
    def remove(data):
        account=next((a for a in data['accounts'] if a['id']==identity),None)
        if is_builtin(account):
            account['enabled']=False;account['builtin']=BUILTIN_MARKER
        elif account:
            ids={c['id'] for c in account['calendars']};data['accounts'].remove(account)
            data['cache']={k:v for k,v in data['cache'].items() if not any(k.startswith(identity+'|'+i+'|') for i in ids)}
    return update(remove)

def cache_key(account_id,calendar_id,month):return '|'.join((account_id,calendar_id,month))
def put_cache(account_id,calendar,month,events,updated):
    def save(data):
        account=next((a for a in data['accounts'] if a['id']==account_id),None)
        if is_enabled(account) and any(c['id']==calendar['id'] for c in account['calendars']):
            data['cache'][cache_key(account_id,calendar['id'],month)]={'events':events,'updated':updated}
    return update(save)
