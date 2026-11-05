"""Private PAT consultation of Calendly v2; no scheduling/cancellation/webhooks."""
from ui_language import ui as _i18n
import hashlib
import re
import time
from urllib.parse import urlencode,urlsplit,parse_qs
import calendar_http as http
import calendar_api_events as normalized
from calendar_events import CalendarError

BASE='https://api.calendly.com'
SCOPES=('users:read','scheduled_events:read')


def user_uri(value):
    part=http.checked_url(value,'api.calendly.com','/users/')
    if part.query or not re.fullmatch(r'/users/[A-Za-z0-9_-]{1,128}',part.path):raise _i18n.exception(CalendarError, 'domain.calendly_client.invalid_calendly_identity')
    return 'https://api.calendly.com'+part.path


class CalendlyClient:
    def __init__(self,token,*,cancel_event=None):self.token=http.secret(token);self.cancel_event=cancel_event

    def discover(self):
        data=http.request_json(BASE+'/users/me',host='api.calendly.com',path_prefix='/users/me',bearer=self.token,cancel_event=self.cancel_event)
        try:
            resource=data['resource'];uri=user_uri(resource['uri']);name=resource.get('name','Calendly')
            if not isinstance(name,str):raise ValueError()
            return [dict(id=hashlib.sha256(uri.encode()).hexdigest(),user_uri=uri,name=('Calendly · '+name)[:200],color='#006bff')]
        except (ValueError,KeyError,TypeError):raise _i18n.exception(CalendarError, 'domain.calendly_client.invalid_calendly_account_check_the_token_and_its_read_scopes') from None

    def events(self,calendar,account_id,month):
        start,end=normalized.window(month)
        user=user_uri(calendar.get('user_uri'))
        params=dict(user=user,min_start_time=start.isoformat(),max_start_time=end.isoformat(),count=100,sort='start_time:asc')
        deadline=time.monotonic()+60;seen=set();result={};count=0
        for index in range(http.MAX_PAGES):
            http.check_page(index,deadline,count,self.cancel_event)
            page=http.request_json(BASE+'/scheduled_events?'+urlencode(params),host='api.calendly.com',path_prefix='/scheduled_events',bearer=self.token,cancel_event=self.cancel_event)
            batch=page.get('collection')
            if not isinstance(batch,list):raise _i18n.exception(CalendarError, 'domain.calendly_client.invalid_calendly_response')
            count+=len(batch);http.check_page(index,deadline,count,self.cancel_event)
            for item in batch:
                value=normalized.calendly(item,account_id,calendar)
                if value:result[value['key']]=value
            pagination=page.get('pagination') or {}
            if not isinstance(pagination,dict):raise _i18n.exception(CalendarError, 'domain.calendly_client.invalid_calendly_pagination')
            next_url=pagination.get('next_page')
            token=pagination.get('next_page_token')
            if next_url:
                part=http.checked_url(next_url,'api.calendly.com','/scheduled_events')
                if part.path!='/scheduled_events':raise _i18n.exception(CalendarError, 'domain.calendly_client.invalid_calendly_pagination')
                try:query=parse_qs(part.query,max_num_fields=12,keep_blank_values=True)
                except ValueError:raise _i18n.exception(CalendarError, 'domain.calendly_client.invalid_calendly_pagination') from None
                for key,values in query.items():
                    if len(values)!=1 or key not in set(params)|{'page_token'}:raise _i18n.exception(CalendarError, 'domain.calendly_client.invalid_calendly_pagination')
                    if key!='page_token' and values[0]!=str(params[key]):raise _i18n.exception(CalendarError, 'domain.calendly_client.calendly_pagination_scope_changed_query_refused')
                if len(query.get('page_token',[]))!=1:raise _i18n.exception(CalendarError, 'domain.calendly_client.incomplete_calendly_pagination')
                extracted=query['page_token'][0]
                if token and token!=extracted:raise _i18n.exception(CalendarError, 'domain.calendly_client.inconsistent_calendly_pagination')
                token=extracted
            if not token:return sorted(result.values(),key=lambda value:value['start'])
            token=http.page_token(token)
            if token in seen:raise _i18n.exception(CalendarError, 'domain.calendly_client.repeated_calendly_pagination_previous_cache_preserved')
            seen.add(token);params=dict(params,page_token=token)
        raise _i18n.exception(CalendarError, 'domain.calendly_client.calendly_exceeded_the_page_limit_previous_cache_preserved')
