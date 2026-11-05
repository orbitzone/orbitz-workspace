"""Standalone reminder scheduling for local tasks and cached external events."""
from datetime import datetime, timedelta
import hashlib


def collect(data, external=None, now=None):
    now = (now or datetime.now()).astimezone()
    items = {}
    tasks = data.get('tasks', [])

    def add(key, title, start, lead, area):
        if type(lead) is not int or not 0 <= lead <= 10080:
            return
        try:
            start = datetime.fromisoformat(start).astimezone()
        except (ValueError, TypeError):
            return
        if start-timedelta(minutes=lead) <= now < start+timedelta(minutes=1):
            identity = hashlib.sha256(key.encode()).hexdigest()
            items[identity] = dict(id=identity, title=title, day=start.date().isoformat(),
                                   time=start.strftime('%H:%M'), area=area, start=start)

    for task in tasks:
        stamp = '|'.join(str(task.get(key, '')) for key in ('date', 'time', 'reminder'))
        if task.get('done') or not task.get('time') or task.get('dismissed') == stamp:
            continue
        add('task|'+task['id']+'|'+stamp, task['text'],
            task['date']+'T'+task['time'], task.get('reminder', 10), 'tasks')

    external = external or {}
    for account in external.get('accounts', []):
        if not account.get('enabled', True):
            continue
        for calendar in account.get('calendars', []):
            prefix = account['id']+'|'+calendar['id']+'|'
            for cache_key, cache in external.get('cache', {}).items():
                if not cache_key.startswith(prefix):
                    continue
                for event in cache.get('events', []):
                    if event.get('all_day'):
                        continue
                    if any(t.get('external_source', {}).get('key') == event['key'] and
                           t.get('date') == event['start'][:10] and t.get('time') == event['start'][11:16]
                           for t in tasks):
                        continue
                    leads = [n for n in event.get('alarm_minutes', []) if type(n) is int and 0 <= n <= 10080]
                    lead = max(leads) if leads else 10
                    add('event|'+event['key']+'|'+event['start']+'|'+str(lead),
                        event['title'], event['start'], lead, 'events')
    return sorted(items.values(), key=lambda item: (item['start'], item['id']))


class ReminderService:
    def __init__(self, notify, preferences):
        self.notify, self.preferences = notify, preferences
        saved = preferences.get('reminder-sent', [])
        self.sent = [value for value in saved if isinstance(value, str)][-256:] if isinstance(saved, list) else []

    def poll(self, data, external=None, now=None):
        for item in collect(data, external, now):
            if item['id'] in self.sent:
                continue
            self.notify(item)
            self.sent = (self.sent + [item['id']])[-256:]
            self.preferences.set('reminder-sent', self.sent)
