"""Normalize API events to the existing cached read-only planner contract."""
from ui_language import ui as _i18n
from datetime import date,datetime,timedelta,timezone
from zoneinfo import ZoneInfo
import hashlib
from calendar_events import CalendarError,ZONE,json_identity,local_value,canonical


def window(month):
    try:
        first=date.fromisoformat(month+'-01')
        if first.strftime('%Y-%m')!=month:raise ValueError()
        last=(first.replace(day=28)+timedelta(days=4)).replace(day=1)
        return datetime.combine(first,datetime.min.time(),ZONE)-timedelta(days=2),datetime.combine(last,datetime.min.time(),ZONE)+timedelta(days=2)
    except (TypeError,ValueError):raise _i18n.exception(CalendarError, 'domain.calendar_api_events.invalid_query_month') from None


def instant(value,zone=None):
    if not isinstance(value,str):raise ValueError()
    result=datetime.fromisoformat(value.replace('Z','+00:00'))
    if result.tzinfo is None:
        if not zone:raise ValueError()
        result=result.replace(tzinfo=ZoneInfo(zone))
    return result


def event(account_id,calendar_id,uid,occurrence,title,start,end,*,all_day=False,alarms=None,location=''):
    if not isinstance(uid,str) or not uid or len(uid)>2048 or end<=start:raise ValueError()
    if not isinstance(title,str) or not isinstance(location,str):raise ValueError()
    # Never persist API URLs, invitee links or arbitrary rich HTML descriptions.
    if '://' in location:location=''
    return dict(key=hashlib.sha256(json_identity(account_id,calendar_id,uid,occurrence).encode()).hexdigest(),
                uid=uid,occurrence=occurrence,title=(title or 'Sem título')[:1000],start=local_value(start),end=local_value(end),
                all_day=all_day,alarm_minutes=[] if all_day else sorted(set(alarms or []),reverse=True),categories='',description='',location=location[:1000])


def google(item,account_id,calendar):
    try:
        if not isinstance(item,dict):raise ValueError()
        if item.get('status')=='cancelled':return None
        begin,finish=item['start'],item['end']
        all_day='date' in begin
        if all_day:
            start,end=date.fromisoformat(begin['date']),date.fromisoformat(finish['date'])
        else:
            zone=calendar.get('timezone','America/Sao_Paulo')
            start=instant(begin['dateTime'],begin.get('timeZone',zone));end=instant(finish['dateTime'],finish.get('timeZone',zone))
        occurrence='single'
        original=item.get('originalStartTime')
        if original:
            occurrence=original['date'] if 'date' in original else canonical(instant(original['dateTime'],original.get('timeZone',calendar.get('timezone','America/Sao_Paulo'))))
        reminders=item.get('reminders',{})
        values=calendar.get('default_reminders',[]) if reminders.get('useDefault') else reminders.get('overrides',[])
        alarms=[]
        for value in values:
            minutes=value.get('minutes') if isinstance(value,dict) else None
            if value.get('method') in ('popup','email') and type(minutes) is int and 0<=minutes<=10080:alarms.append(minutes)
        return event(account_id,calendar['id'],item['id'],occurrence,item.get('summary','Sem título'),start,end,all_day=all_day,alarms=alarms,location=item.get('location',''))
    except (KeyError,TypeError,ValueError,AttributeError):raise _i18n.exception(CalendarError, 'domain.calendar_api_events.invalid_google_event_previous_cache_preserved') from None


def calendly(item,account_id,calendar):
    try:
        if not isinstance(item,dict):raise ValueError()
        if item.get('status')=='canceled':return None
        if item.get('status')!='active':raise ValueError()
        uri=item['uri']
        from urllib.parse import urlsplit
        part=urlsplit(uri)
        import re
        if part.scheme!='https' or part.netloc!='api.calendly.com' or part.query or part.fragment or not re.fullmatch(r'/scheduled_events/[A-Za-z0-9_-]{1,128}',part.path):raise ValueError()
        location=item.get('location') or {}
        return event(account_id,calendar['id'],part.path.rsplit('/',1)[-1],'single',item.get('name','Sem título'),
                     instant(item['start_time']),instant(item['end_time']),location=location.get('location',''))
    except (KeyError,TypeError,ValueError,AttributeError):raise _i18n.exception(CalendarError, 'domain.calendar_api_events.invalid_calendly_event_previous_cache_preserved') from None
