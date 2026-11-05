"""Google Calendar REST: calendar list and expanded events, strictly read-only."""
from ui_language import ui as _i18n
import hashlib
import re
import time
from urllib.parse import urlencode,quote
from zoneinfo import ZoneInfo
import calendar_http as http
import calendar_api_events as normalized
from calendar_events import CalendarError

BASE='https://www.googleapis.com/calendar/v3'


class GoogleClient:
    def __init__(self,access_token,*,cancel_event=None):
        self.token=http.secret(access_token);self.cancel_event=cancel_event

    def _pages(self,path,params):
        deadline=time.monotonic()+60;seen=set();items=[]
        for index in range(http.MAX_PAGES):
            http.check_page(index,deadline,len(items),self.cancel_event)
            page=http.request_json(BASE+path+'?'+urlencode(params),host='www.googleapis.com',path_prefix='/calendar/v3/',bearer=self.token,cancel_event=self.cancel_event)
            batch=page.get('items',[])
            if not isinstance(batch,list):raise _i18n.exception(CalendarError, 'domain.google_client.invalid_google_response')
            items.extend(batch);http.check_page(index,deadline,len(items),self.cancel_event)
            token=page.get('nextPageToken')
            if not token:return items
            token=http.page_token(token)
            if token in seen:raise _i18n.exception(CalendarError, 'domain.google_client.repeated_google_pagination_previous_cache_preserved')
            seen.add(token);params=dict(params,pageToken=token)
        raise _i18n.exception(CalendarError, 'domain.google_client.page_limit_previous_cache_preserved')

    def discover(self):
        calendars=[]
        for item in self._pages('/users/me/calendarList',dict(maxResults=250,showDeleted='false')):
            try:
                if not isinstance(item,dict):raise ValueError()
                if item.get('deleted'):continue
                remote_id=item['id']
                if not isinstance(remote_id,str) or not 0<len(remote_id)<=1024 or any(ord(c)<32 for c in remote_id):raise ValueError()
                name=item.get('summary','Calendário')
                if not isinstance(name,str):raise ValueError()
                zone=item.get('timeZone','America/Sao_Paulo');ZoneInfo(zone)
                color=item.get('backgroundColor','#82cfff')
                if not isinstance(color,str) or not re.fullmatch('#[0-9a-fA-F]{6}',color):color='#82cfff'
                reminders=item.get('defaultReminders',[])
                if not isinstance(reminders,list):raise ValueError()
                reminders=[dict(method=r['method'],minutes=r['minutes']) for r in reminders if isinstance(r,dict) and r.get('method') in ('popup','email') and type(r.get('minutes')) is int and 0<=r['minutes']<=10080]
                calendars.append(dict(id=hashlib.sha256(remote_id.encode()).hexdigest(),remote_id=remote_id,name=name[:200],color=color,timezone=zone,primary=item.get('primary') is True,default_reminders=reminders))
            except (ValueError,KeyError,TypeError):raise _i18n.exception(CalendarError, 'domain.google_client.invalid_google_calendar_list') from None
        if not calendars:raise _i18n.exception(CalendarError, 'domain.google_client.no_calendars_were_found_in_this_google_account')
        return calendars

    def events(self,calendar,account_id,month):
        start,end=normalized.window(month)
        remote_id=calendar.get('remote_id')
        if not isinstance(remote_id,str) or not 0<len(remote_id)<=1024:raise _i18n.exception(CalendarError, 'domain.google_client.invalid_google_calendar')
        params=dict(timeMin=start.isoformat(),timeMax=end.isoformat(),singleEvents='true',showDeleted='true',maxResults=1000,orderBy='startTime')
        result={}
        for item in self._pages('/calendars/'+quote(remote_id,safe='')+'/events',params):
            value=normalized.google(item,account_id,calendar)
            if value:result[value['key']]=value
        return sorted(result.values(),key=lambda value:value['start'])
