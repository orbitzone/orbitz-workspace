"""Read-only subscription feeds, including Apple holiday calendars."""
from ui_language import ui as _i18n
from datetime import date,datetime,timedelta
import gzip,hashlib,io,ipaddress,socket
from urllib.parse import urlsplit,urlunsplit,urljoin
from urllib.request import Request,build_opener
from urllib.error import HTTPError,URLError
import apple_client as apple
from calendar_events import ZONE, normalize_events
MAX=16*1024*1024

def subscription_url(value):
    value=value.strip()
    if value.lower().startswith('webcal://'):value='https://'+value[9:]
    parsed=urlsplit(value)
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None,443):raise _i18n.exception(apple.CalendarError, 'domain.ics_client.enter_an_https_or_webcal_calendar_subscription_link')
    return urlunsplit((parsed.scheme,parsed.netloc,parsed.path,parsed.query,''))

def public_host(url):
    try:
        host=urlsplit(url).hostname
        for result in socket.getaddrinfo(host,443,type=socket.SOCK_STREAM):
            if not ipaddress.ip_address(result[4][0]).is_global:raise _i18n.exception(apple.CalendarError, 'domain.ics_client.the_link_must_point_to_a_public_calendar_service')
    except socket.gaierror:raise _i18n.exception(apple.CalendarError, 'domain.ics_client.could_not_find_the_subscription_server') from None

def fetch(url):
    url=subscription_url(url);opener=build_opener(apple.NoRedirect())
    for _ in range(5):
        public_host(url)
        try:
            request=Request(url,headers={'User-Agent':'OrbitzCalendar/1.0','Accept':'text/calendar','Accept-Encoding':'gzip'})
            with opener.open(request,timeout=20) as response:
                raw=response.read(MAX+1)
                if len(raw)>MAX:raise _i18n.exception(apple.CalendarError, 'domain.ics_client.the_calendar_file_is_too_large')
                if raw[:2]==b'\x1f\x8b':
                    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:raw=stream.read(MAX+1)
                if len(raw)>MAX:raise _i18n.exception(apple.CalendarError, 'domain.ics_client.the_calendar_file_is_too_large')
                if b'BEGIN:VCALENDAR' not in raw:raise _i18n.exception(apple.CalendarError, 'domain.ics_client.the_address_returned_a_page_rather_than_an_icalendar_ics_subscrip')
                return raw
        except HTTPError as error:
            if error.code in (301,302,303,307,308) and error.headers.get('Location'):
                url=subscription_url(urljoin(url,error.headers['Location']));continue
            raise _i18n.exception(apple.CalendarError, 'domain.ics_client.http_failure', status=str(error.code)) from None
        except (URLError,OSError,EOFError):raise _i18n.exception(apple.CalendarError, 'domain.ics_client.could_not_download_the_subscription_check_your_connection_and_the') from None
    raise _i18n.exception(apple.CalendarError, 'domain.ics_client.the_subscription_redirected_the_connection_too_many_times')

def parse(raw,account_id,calendar_id,month):
    first=date.fromisoformat(month+'-01');last=(first.replace(day=28)+timedelta(days=4)).replace(day=1)
    a=datetime.combine(first,datetime.min.time(),ZONE)-timedelta(days=2)
    b=datetime.combine(last,datetime.min.time(),ZONE)+timedelta(days=2)
    return normalize_events(raw,account_id,calendar_id,a,b)

def events(url,account_id,calendar_id,month):return parse(fetch(url),account_id,calendar_id,month)

def account(name,url):
    name=name.strip()
    if not 0<len(name)<=100:raise _i18n.exception(apple.CalendarError, 'domain.ics_client.enter_a_name_of_up_to_100_characters')
    url=subscription_url(url);digest=hashlib.sha256(url.encode()).hexdigest()
    return dict(id='ics-'+digest,provider='ics',label=name,calendars=[dict(id=digest,url=url,name=name,color='#82cfff')])
