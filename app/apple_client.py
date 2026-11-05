"""Read-only Apple CalDAV transport; shared event helpers remain re-exported."""
from ui_language import ui as _i18n
import base64,hashlib,re
from datetime import date,datetime,timedelta,timezone
from urllib.request import Request,build_opener,HTTPRedirectHandler
from urllib.error import HTTPError,URLError
from urllib.parse import urljoin,urlsplit
from defusedxml import ElementTree as XML
# Compatibility exports used by the planner and existing integrations.
from calendar_events import (
    CalendarError, ZONE, normalize_events, json_identity, canonical,
    local_value, on_day, alarm_minutes,
)

NS={'d':'DAV:','c':'urn:ietf:params:xml:ns:caldav','a':'http://apple.com/ns/ical/'}

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

def apple_url(url,base='https://caldav.icloud.com/'):
    result=urljoin(base,url);parsed=urlsplit(result)
    if parsed.scheme!='https' or not parsed.hostname or not (parsed.hostname=='icloud.com' or parsed.hostname.endswith('.icloud.com')) or parsed.username or parsed.password or parsed.port not in (None,443):
        raise _i18n.exception(CalendarError, 'domain.apple_client.icloud_returned_an_invalid_calendar_address')
    return result

class AppleClient:
    def __init__(self,email,password):self.email=email;self.password=password
    def request(self,method,url,body,depth='0'):
        if method not in ('PROPFIND','REPORT'):raise _i18n.exception(CalendarError, 'domain.apple_client.operation_not_allowed')
        url=apple_url(url);opener=build_opener(NoRedirect())
        token=base64.b64encode((self.email+':'+self.password).encode()).decode()
        for _ in range(5):
            request=Request(url,data=body.encode(),method=method,headers={'Authorization':'Basic '+token,'Content-Type':'application/xml; charset=utf-8','Depth':depth,'User-Agent':'OrbitzCalendar/1.0'})
            try:
                with opener.open(request,timeout=20) as response:
                    raw=response.read(16*1024*1024+1)
                    if len(raw)>16*1024*1024:raise _i18n.exception(CalendarError, 'domain.apple_client.the_calendar_exceeded_the_read_limit_for_this_period')
                    try:return XML.fromstring(raw),url
                    except Exception:raise _i18n.exception(CalendarError, 'domain.apple_client.icloud_returned_invalid_calendar_data') from None
            except HTTPError as error:
                if error.code in (301,302,303,307,308):
                    location=error.headers.get('Location')
                    if not location:raise _i18n.exception(CalendarError, 'domain.apple_client.icloud_redirect_without_a_destination') from None
                    url=apple_url(location,url);continue
                if error.code in (401,403):raise _i18n.exception(CalendarError, 'domain.apple_client.access_denied_by_icloud_check_the_email_and_app_specific_password') from None
                if error.code==429:raise _i18n.exception(CalendarError, 'domain.apple_client.icloud_rate_limited_queries_wait_and_try_again') from None
                raise _i18n.exception(CalendarError, 'domain.apple_client.http_failure', status=str(error.code)) from None
            except (URLError,TimeoutError,OSError):raise _i18n.exception(CalendarError, 'domain.apple_client.could_not_access_icloud_check_your_connection_and_try_again') from None
        raise _i18n.exception(CalendarError, 'domain.apple_client.icloud_redirected_the_connection_too_many_times')

    def propfind(self,url,properties,depth='0'):
        body=f'<d:propfind xmlns:d="DAV:" xmlns:c="{NS["c"]}" xmlns:a="{NS["a"]}"><d:prop>{properties}</d:prop></d:propfind>'
        return self.request('PROPFIND',url,body,depth)

    def discover(self):
        root,url=self.propfind('https://caldav.icloud.com/','<d:current-user-principal/>')
        principal=first_property(root,'d:current-user-principal/d:href')
        if not principal:raise _i18n.exception(CalendarError, 'domain.apple_client.icloud_did_not_report_a_calendar_account_check_whether_icloud_cal')
        root,url=self.propfind(apple_url(principal,url),'<c:calendar-home-set/>')
        home=first_property(root,'c:calendar-home-set/d:href')
        if not home:raise _i18n.exception(CalendarError, 'domain.apple_client.could_not_locate_calendars_for_this_account')
        root,url=self.propfind(apple_url(home,url),'<d:displayname/><d:resourcetype/><a:calendar-color/><c:supported-calendar-component-set/>','1')
        result=[]
        for response in root.findall('d:response',NS):
            prop=successful_property(response)
            if prop is None or prop.find('d:resourcetype/c:calendar',NS) is None:continue
            components=prop.findall('c:supported-calendar-component-set/c:comp',NS)
            if components and not any(c.get('name')=='VEVENT' for c in components):continue
            href=response.findtext('d:href','',NS)
            if not href:continue
            location=apple_url(href,url)
            name=prop.findtext('d:displayname','Calendário',NS) or 'Calendário'
            color=prop.findtext('a:calendar-color','#82cfff',NS)[:7]
            if not re.fullmatch(r'#[0-9A-Fa-f]{6}',color):color='#82cfff'
            result.append(dict(id=hashlib.sha256(location.encode()).hexdigest(),url=location,name=name[:200],color=color))
        if not result:raise _i18n.exception(CalendarError, 'domain.apple_client.no_event_calendars_were_found_in_this_icloud_account')
        return result

    def events(self,calendar,account_id,month):
        first=date.fromisoformat(month+'-01');last=(first.replace(day=28)+timedelta(days=4)).replace(day=1)
        start=datetime.combine(first,datetime.min.time(),ZONE)-timedelta(days=2)
        end=datetime.combine(last,datetime.min.time(),ZONE)+timedelta(days=2)
        a,b=[d.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ') for d in (start,end)]
        body=f'''<c:calendar-query xmlns:d="DAV:" xmlns:c="{NS['c']}"><d:prop><d:getetag/><c:calendar-data><c:expand start="{a}" end="{b}"/></c:calendar-data></d:prop><c:filter><c:comp-filter name="VCALENDAR"><c:comp-filter name="VEVENT"><c:time-range start="{a}" end="{b}"/></c:comp-filter></c:comp-filter></c:filter></c:calendar-query>'''
        root,_=self.request('REPORT',calendar['url'],body,'1');events={}
        for response in root.findall('d:response',NS):
            prop=successful_property(response)
            if prop is None:continue
            raw=prop.findtext('c:calendar-data','',NS)
            if not raw:continue
            for event in normalize_events(raw,account_id,calendar['id'],start,end):events[event['key']]=event
        return sorted(events.values(),key=lambda e:e['start'])

def successful_property(response):
    for stat in response.findall('d:propstat',NS):
        status=stat.findtext('d:status','',NS).split()
        if len(status)>1 and status[1].startswith('2'):return stat.find('d:prop',NS)
    return None

def first_property(root,path):
    for response in root.findall('d:response',NS):
        prop=successful_property(response)
        if prop is not None:
            value=prop.findtext(path,'',NS)
            if value:return value
    return None
