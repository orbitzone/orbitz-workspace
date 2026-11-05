"""Bounded fixed-host calendar HTTP; credentials only in headers/form, never errors."""
from ui_language import ui as _i18n
import json
import time
from urllib.error import HTTPError,URLError
from urllib.parse import urlsplit,urlencode
from urllib.request import Request,build_opener,HTTPRedirectHandler
from calendar_events import CalendarError

MAX_PAGES=20
MAX_ITEMS=10000


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


def cancelled(event):
    if event is not None and event.is_set():raise _i18n.exception(CalendarError, 'domain.calendar_http.connection_cancelled')


def secret(value):
    if not isinstance(value,str) or not 0<len(value)<=16384 or any(ord(c)<33 or ord(c)>126 for c in value):
        raise _i18n.exception(CalendarError, 'domain.calendar_http.invalid_credential_enter_the_complete_value_without_spaces')
    return value


def checked_url(url,host,path_prefix):
    try:
        part=urlsplit(url)
        if part.scheme!='https' or part.hostname!=host or part.port not in (None,443) or part.username or part.password or part.fragment or not part.path.startswith(path_prefix):raise ValueError()
        if any(ord(c)<33 for c in url):raise ValueError()
    except (TypeError,ValueError):raise _i18n.exception(CalendarError, 'domain.calendar_http.invalid_calendar_address_query_refused') from None
    return part


def _token_error_message(error):
    # Only allowlisted identifiers and two exact templates produce fixed text.
    # No arbitrary description, header, URL or credential is ever returned.
    messages={
        'invalid_client':_i18n.msg('domain.calendar_http.client_not_accepted_invalid_client_check_the_project_desktop_conf'),
        'invalid_grant':_i18n.msg('domain.calendar_http.code_or_authorization_denied_expired_invalid_grant'),
        'access_denied':_i18n.msg('domain.calendar_http.authorization_not_granted_access_denied'),
        'invalid_scope':_i18n.msg('domain.calendar_http.read_scopes_not_accepted_invalid_scope'),
        'unauthorized_client':_i18n.msg('domain.calendar_http.client_not_authorized_for_this_flow_unauthorized_client'),
        'invalid_request':_i18n.msg('domain.calendar_http.authorization_request_rejected_invalid_request'),
    }
    try:
        raw=error.read(4097)
        if len(raw)>4096:return None
        payload=json.loads(raw)
        code=payload.get('error') if isinstance(payload,dict) else None
        if not isinstance(code,str) or code not in messages:return None
        if code=='invalid_request' and payload.get('error_description') in (
            'client_secret is missing.', 'Missing required parameter: client_secret'):
            return _i18n.msg('domain.calendar_http.the_endpoint_reported_that_the_desktop_client_client_secret_param')
        return messages[code]
    except (OSError,ValueError,TypeError):return None


def _token_error(error):
    """Compatibility: callers still receive only a sanitized builtin string."""
    message = _token_error_message(error)
    return str(message) if message is not None else None


def request_json(url,*,host,path_prefix,bearer=None,form=None,cancel_event=None,timeout=15,limit=2*1024*1024):
    cancelled(cancel_event);checked_url(url,host,path_prefix)
    headers={'Accept':'application/json','User-Agent':'OrbitzCalendar/1.0'}
    if bearer is not None:headers['Authorization']='Bearer '+secret(bearer)
    body=None
    if form is not None:
        if host!='oauth2.googleapis.com' or url!='https://oauth2.googleapis.com/token':raise _i18n.exception(CalendarError, 'domain.calendar_http.remote_writes_are_not_allowed')
        body=urlencode(form).encode('ascii');headers['Content-Type']='application/x-www-form-urlencoded'
    request=Request(url,data=body,headers=headers,method='POST' if form is not None else 'GET')
    try:
        with build_opener(NoRedirect()).open(request,timeout=timeout) as response:
            raw=response.read(limit+1)
        cancelled(cancel_event)
        if len(raw)>limit:raise _i18n.exception(CalendarError, 'domain.calendar_http.calendar_response_exceeded_the_read_limit')
        value=json.loads(raw)
        if not isinstance(value,dict):raise ValueError()
        return value
    except HTTPError as error:
        detail=None
        token_endpoint=url=='https://oauth2.googleapis.com/token' and form is not None
        try:
            if token_endpoint:detail=_token_error_message(error)
        finally:error.close()
        status=str(error.code) if type(error.code) is int and 100<=error.code<=599 else _i18n.msg('domain.calendar_http.unavailable')
        if token_endpoint:
            failure=_i18n.exception(CalendarError, 'domain.calendar_http.token_exchange_failure', status=status,
                                   detail=detail or _i18n.msg('domain.calendar_http.unrecognized_error_response_could_not_complete_this_stage'))
        else:
            if error.code in (400,401):key='domain.calendar_http.authorization_unavailable_or_expired_reconnect_the_account'
            elif error.code==403:key='domain.calendar_http.permission_denied_check_the_granted_read_scopes'
            elif error.code==429:key='domain.calendar_http.query_limit_reached_wait_before_refreshing'
            else:key='domain.calendar_http.could_not_query_the_calendar_local_data_was_preserved'
            if host=='www.googleapis.com':
                path=urlsplit(url).path
                stage=_i18n.msg('domain.calendar_http.calendar_list') if path=='/calendar/v3/users/me/calendarList' else _i18n.msg('domain.calendar_http.event_query') if path.startswith('/calendar/v3/calendars/') and path.endswith('/events') else _i18n.msg('domain.calendar_http.api_query')
                if error.code==400:key='domain.calendar_http.the_api_refused_the_submitted_query'
                elif error.code==401:key='domain.calendar_http.the_api_did_not_accept_the_submitted_authorization'
                failure=_i18n.exception(CalendarError, 'domain.calendar_http.api_stage_failure', stage=stage, status=status, detail=_i18n.msg(key))
            else:
                failure=_i18n.exception(CalendarError, key)
        raise failure from None
    except (URLError,OSError,TimeoutError,ValueError,UnicodeError):
        raise _i18n.exception(CalendarError, 'domain.calendar_http.connection_failed_or_invalid_calendar_response_local_data_preserv') from None


def page_token(value):
    if not isinstance(value,str) or not 0<len(value)<=4096 or any(ord(c)<33 or ord(c)>126 for c in value):raise _i18n.exception(CalendarError, 'domain.calendar_http.invalid_calendar_pagination')
    return value


def check_page(index,deadline,count,cancel_event):
    cancelled(cancel_event)
    if index>=MAX_PAGES or time.monotonic()>deadline or count>MAX_ITEMS:
        raise _i18n.exception(CalendarError, 'domain.calendar_http.query_exceeded_the_limit_previous_cache_preserved')
