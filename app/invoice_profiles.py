"""Private invoice preferences, independent of task/timesheet/calendar data."""
from ui_language import ui as _i18n
import fcntl
import json
import os
from pathlib import Path
import stat
import atomic_json
from invoice import validate_profile, text

PATH = Path(os.environ.get('XDG_DATA_HOME') or Path.home()/'.local/share')/'orbitz-workspace/invoice-profiles.json'
MAX_BYTES = 2 * 1024 * 1024


def read(path=None):
    path = Path(path) if path is not None else PATH
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return dict(version=1, issuer=None, language='pt', sheets={})
    try:
        with os.fdopen(fd, 'rb') as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError()
            raw = stream.read(MAX_BYTES+1)
        if len(raw) > MAX_BYTES:
            raise ValueError()
        data = json.loads(raw)
        if not isinstance(data, dict) or data.get('version') != 1 or data.get('language') not in ('pt','en') or not isinstance(data.get('sheets'),dict):
            raise ValueError()
        if data['issuer'] is not None:
            from invoice import party
            if party(data['issuer']) != data['issuer']:
                raise ValueError()
        for identity, sheet in data['sheets'].items():
            text(identity, 'Identidade da timesheet', 200)
            if not isinstance(sheet, dict) or set(sheet) != {'client','rate','currency'} or data['issuer'] is None:
                raise ValueError()
            validate_profile(dict(sheet,issuer=data['issuer'],language=data['language']))
        return data
    except (ValueError, KeyError, TypeError):
        raise _i18n.exception(ValueError, 'domain.invoice_profiles.invalid_invoice_profile_file_original_preserved') from None


def load(sheet_id, path=None, *, context=None):
    sheet_id = text(sheet_id, 'Identidade da timesheet', 200)
    data = read(path)
    sheet = data['sheets'].get(sheet_id, dict(client=dict(name='',tax_id='',address=''),rate='',currency='BRL'))
    if sheet_id not in data['sheets'] and context is not None:
        import sheet_context
        sheet['client']['name'] = sheet_context.validate(context)['client_name']
    return dict(sheet,issuer=data['issuer'] or dict(name='',tax_id=''),language=data['language'])


def save(sheet_id, profile, path=None):
    sheet_id = text(sheet_id, 'Identidade da timesheet', 200)
    profile = validate_profile(profile)
    path = Path(path) if path is not None else PATH
    path.parent.mkdir(parents=True,exist_ok=True)
    fd = os.open(str(path)+'.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    with os.fdopen(fd,'r+') as lock:
        if not stat.S_ISREG(os.fstat(lock.fileno()).st_mode):
            raise _i18n.exception(ValueError, 'domain.invoice_profiles.invalid_profile_lock')
        os.fchmod(lock.fileno(),0o600)
        fcntl.flock(lock,fcntl.LOCK_EX)
        data = read(path)
        data['issuer'],data['language'] = profile['issuer'],profile['language']
        data['sheets'][sheet_id] = {key:profile[key] for key in ('client','rate','currency')}
        if len(json.dumps(data,ensure_ascii=False).encode('utf-8')) > MAX_BYTES:
            raise _i18n.exception(ValueError, 'domain.invoice_profiles.profile_file_size_limit_reached_original_preserved')
        atomic_json.write(path,data,prefix='.invoice-profiles-',encoding='utf-8')
    return load(sheet_id,path)
