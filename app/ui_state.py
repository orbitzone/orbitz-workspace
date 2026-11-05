"""Small durable UI preferences/drafts, separate from historical records."""
from ui_language import ui as _i18n
import fcntl,json,os
import atomic_json
from pathlib import Path
PATH=Path(os.environ.get('XDG_DATA_HOME') or Path.home()/'.local/share')/'orbitz-workspace'/'planner-ui.json'

def read():
    try:
        data=json.loads(PATH.read_text())
        if not isinstance(data,dict):raise _i18n.exception(ValueError, 'domain.ui_state.invalid_drafts_file_original_preserved')
        return data
    except FileNotFoundError:return {}

def get(key,default=None):
    # A damaged draft file must never prevent access to the historical records.
    # Writes still fail explicitly, preserving the damaged file for recovery.
    try:return read().get(key,default)
    except (OSError,ValueError):return default

def set(key,value):
    PATH.parent.mkdir(parents=True,exist_ok=True)
    with open(str(PATH)+'.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX);data=read()
        if value is None:data.pop(key,None)
        else:data[key]=value
        atomic_json.write(PATH, data, prefix='.planner-ui-')
