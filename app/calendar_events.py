"""Provider-independent iCalendar recurrence, identity, dates and alarm rules."""
from ui_language import ui as _i18n
import hashlib
import sys
from pathlib import Path
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent / 'vendor'))
from icalendar import Calendar
import recurring_ical_events

ZONE = ZoneInfo('America/Sao_Paulo')


class CalendarError(ValueError):
    pass


def normalize_events(raw,account_id,calendar_id,start,end):
    try:
        calendar=Calendar.from_ical(raw)
        series={str(e.get('UID','')) for e in calendar.walk('VEVENT') if e.get('RRULE') or e.get('RECURRENCE-ID')}
        instances=recurring_ical_events.of(calendar).between(start,end)
        result=[]
        for item in instances:
            if str(item.get('STATUS','')).upper()=='CANCELLED':continue
            uid=str(item.get('UID',''))
            if not uid:continue
            begin=item.decoded('DTSTART');finish=item.decoded('DTEND',None)
            all_day=not isinstance(begin,datetime)
            if finish is None:finish=begin+item.decoded('DURATION',timedelta(days=1) if all_day else timedelta())
            rid=item.decoded('RECURRENCE-ID',begin)
            occurrence=canonical(rid) if uid in series else 'single'
            key=hashlib.sha256(json_identity(account_id,calendar_id,uid,occurrence).encode()).hexdigest()
            result.append(dict(key=key,uid=uid,occurrence=occurrence,title=(str(item.get('SUMMARY','')) or 'Sem título')[:1000],
                alarm_minutes=alarm_minutes(item,begin,finish),categories=str(item.get('CATEGORIES',''))[:1000],description=str(item.get('DESCRIPTION',''))[:10000],location=str(item.get('LOCATION',''))[:1000],
                start=local_value(begin),end=local_value(finish),all_day=all_day))
        return result
    except Exception:raise _i18n.exception(CalendarError, 'domain.calendar_events.could_not_parse_this_calendar_s_events_local_data_was_preserved') from None

def json_identity(*parts):
    import json
    return json.dumps(parts,ensure_ascii=False,separators=(',',':'))

def canonical(value):
    if isinstance(value,datetime):return (value.replace(tzinfo=ZONE) if value.tzinfo is None else value).astimezone(timezone.utc).isoformat()
    return value.isoformat()

def local_value(value):
    if isinstance(value,datetime):return (value.replace(tzinfo=ZONE) if value.tzinfo is None else value).astimezone(ZONE).isoformat()
    return value.isoformat()

def on_day(event,day):
    start=date.fromisoformat(event['start'][:10]);end=date.fromisoformat(event['end'][:10])
    if event['all_day']:return start<=day<end
    if start==end:return day==start
    return start<=day<=end and (day!=end or datetime.fromisoformat(event['end']).time()!=datetime.min.time())


def alarm_minutes(item,start,end):
    """Relative or absolute VALARM triggers, expressed as minutes before start."""
    if not isinstance(start,datetime):return []
    start=start.replace(tzinfo=ZONE) if start.tzinfo is None else start
    end=end.replace(tzinfo=ZONE) if isinstance(end,datetime) and end.tzinfo is None else end
    reminders=[]
    for alarm in item.walk('VALARM'):
        try:
            trigger=alarm.decoded('TRIGGER')
            if isinstance(trigger,timedelta):
                related=str(alarm['TRIGGER'].params.get('RELATED','START')).upper()
                instant=(end if related=='END' else start)+trigger
            elif isinstance(trigger,datetime):instant=trigger.replace(tzinfo=ZONE) if trigger.tzinfo is None else trigger
            else:continue
            minutes=(start-instant).total_seconds()/60
            if 0<=minutes<=10080:reminders.append(minutes)
        except (ValueError,KeyError,TypeError):continue
    return sorted(set(reminders),reverse=True)
