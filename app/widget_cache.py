"""Disposable bounded weather cache owned exclusively by Orbitz Workspace."""
import json
import math
import os
from pathlib import Path
import stat
import time
import atomic_json


def cache_path(name):
    if not isinstance(name,str) or Path(name).name!=name or name in ('','.','..'):
        raise ValueError('Invalid weather cache name')
    return Path(os.environ.get('XDG_CACHE_HOME') or Path.home()/'.cache')/'orbitz-workspace'/'weather'/name


def load(name,age=86400):
    try:
        fd=os.open(cache_path(name),os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        with os.fdopen(fd,'rb') as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):return None
            raw=stream.read(262145)
        if len(raw)>262144:return None
        item=json.loads(raw)
        saved=item['saved']
        if type(saved) not in (int,float) or not math.isfinite(saved) or not 0<=time.time()-saved<=age:return None
        return item['data']
    except (OSError,ValueError,TypeError,KeyError,RecursionError):return None


def save(name,data):
    try:
        if len(json.dumps(data,allow_nan=False).encode())>250000:return
        path=cache_path(name);path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        atomic_json.write(path,dict(saved=time.time(),data=data),prefix='.weather-')
    except (OSError,ValueError,TypeError):pass
