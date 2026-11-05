"""Read-only day projections shared by calendar markers and agenda context."""
from calendar_events import on_day


def local_activity(data, day):
    stamp=day.isoformat()
    tasks=[t for t in data.get('tasks',[]) if t.get('date')==stamp and not t.get('done')]
    sheets=[(s,[e for e in s.get('timesheet',[]) if e.get('date')==stamp])
        for s in data.get('timesheets',[]) if not s.get('archived')]
    return tasks,[(s,entries) for s,entries in sheets if entries]


def local_details(data, day):
    tasks,sheets=local_activity(data,day)
    result=[]
    if tasks:result.append(f'Atividades locais: {len(tasks)} tarefa(s) pendente(s)')
    result += [f'Horas locais: {s["name"]} · {len(entries)} registro(s)' for s,entries in sheets]
    return result


def external_activity(accounts, cache, cache_key, selected, day, is_holiday, source_label):
    month=day.strftime('%Y-%m');visible=[];holidays=[]
    for account in accounts:
        if not account.get('enabled',True):continue
        for calendar in account['calendars']:
            active=selected==account['id']+'|'+calendar['id']
            events=cache.get(cache_key(account['id'],calendar['id'],month),{}).get('events',[])
            for event in events:
                if not on_day(event,day):continue
                if active:visible.append(event)
                if is_holiday(event):holidays.append((event,source_label(account,calendar),active))
    def signature(event):return tuple(event.get(k) for k in ('title','start','end'))
    active_holidays={signature(e) for e,_,active in holidays if active}
    others=[];seen=set(active_holidays)
    for event,source,active in holidays:
        identity=signature(event)
        if not active and identity not in seen:
            others.append((event,source));seen.add(identity)
    holiday_details=list(dict.fromkeys(e['title']+' · '+source for e,source,_ in holidays))
    return visible,others,holiday_details


def day_description(day, selected=False, activities=False, holidays=(), details=()):
    text=[day.strftime('%d/%m/%Y')]
    if selected:text.append('Data selecionada')
    if activities and (details or not holidays):text.append('Atividades neste dia')
    text += ['Feriado: '+t for t in holidays]+list(details)
    return text


# UI descriptors share the same read-only projections; raw string APIs remain available.
def local_detail_messages(data,day):
    from ui_language import ui
    tasks,sheets=local_activity(data,day)
    result=[]
    if tasks:result.append(ui.msg('workspace.live.local_tasks', count=len(tasks)))
    result += [ui.msg('workspace.live.local_hours', name=sheet['name'], count=len(entries)) for sheet,entries in sheets]
    return result


def day_messages(day,selected=False,activities=False,holidays=(),details=()):
    from ui_language import ui
    text=[ui.date_text(day)]
    if selected:text.append(ui.msg('workspace.live.selected_date'))
    if activities and (details or not holidays):text.append(ui.msg('workspace.live.day_activities'))
    return text+[ui.msg('workspace.live.holiday', title=title) for title in holidays]+list(details)
