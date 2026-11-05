"""Timesheet calculations, validation and exports; no UI dependencies."""
from ui_language import ui as _i18n
import csv
from datetime import date,datetime,timedelta
import io
import uuid
import sheet_context

class OverlapError(ValueError):pass

def clock_minutes(value):
    if value=='24:00':return 1440
    if not isinstance(value,str) or len(value)!=5:raise _i18n.exception(ValueError, 'domain.timesheet.use_the_hh_mm_time_format')
    try:
        parsed=datetime.strptime(value,'%H:%M')
        if parsed.strftime('%H:%M')!=value:raise ValueError()
    except ValueError:raise _i18n.exception(ValueError, 'domain.timesheet.use_a_valid_time_in_hh_mm_format') from None
    return parsed.hour*60+parsed.minute

def activity_minutes(entry):return clock_minutes(entry['end'])-clock_minutes(entry['start'])

def validate_activity(raw):
    if not isinstance(raw,dict):raise _i18n.exception(ValueError, 'domain.timesheet.invalid_time_entry')
    text=raw.get('description');day=raw.get('date')
    if not isinstance(text,str) or not 0<len(text.strip())<=1000:raise _i18n.exception(ValueError, 'domain.timesheet.enter_a_description_of_up_to_1000_characters')
    try:
        if not isinstance(day,str) or date.fromisoformat(day).isoformat()!=day:raise ValueError()
    except ValueError:raise _i18n.exception(ValueError, 'domain.timesheet.invalid_date') from None
    start=raw.get('start');end=raw.get('end')
    if clock_minutes(start)>=1440 or clock_minutes(end)<=clock_minutes(start):
        raise _i18n.exception(ValueError, 'domain.timesheet.the_end_must_be_after_the_start_to_cross_midnight_use_one_row_per')
    return dict(description=text.strip(),date=day,start=start,end=end)

def overlaps(entries,value,identity=None):
    return [e for e in entries if e['id']!=identity and e['date']==value['date'] and
            clock_minutes(e['start'])<clock_minutes(value['end']) and clock_minutes(value['start'])<clock_minutes(e['end'])]

def has_overlaps(entries):
    day=None;last_end=-1
    for entry in sorted(entries,key=lambda e:(e['date'],e['start'])):
        if entry['date']!=day:day=entry['date'];last_end=-1
        start,end=clock_minutes(entry['start']),clock_minutes(entry['end'])
        if start<last_end:return True
        last_end=max(last_end,end)
    return False

def check_overlap(entries,value,identity=None,allow=False):
    found=overlaps(entries,value,identity)
    if found and not allow:
        e=found[0]
        raise _i18n.exception(OverlapError, 'domain.timesheet.overlap_confirmation', description=e['description'], start=e['start'], end=e['end'], day=e['date'])

def bounds(day,period):
    chosen=date.fromisoformat(day)
    if period=='week':
        start=chosen-timedelta(days=chosen.weekday());end=start+timedelta(days=6)
    elif period=='month':
        start=chosen.replace(day=1);end=(start.replace(day=28)+timedelta(days=4)).replace(day=1)-timedelta(days=1)
    elif period=='day':start=end=chosen
    else:raise _i18n.exception(ValueError, 'domain.timesheet.invalid_period')
    return start.isoformat(),end.isoformat()

def entries_for(entries,start,end):return sorted((e for e in entries if start<=e['date']<=end),key=lambda e:(e['date'],e['start']))

def total(entries):return sum(activity_minutes(e) for e in entries)
def duration(minutes):return f'{minutes//60:02d}h {minutes%60:02d}min'

def csv_text(entries,start,end):
    stream=io.StringIO(newline='');writer=csv.writer(stream,delimiter=';')
    writer.writerow(['Data','Descrição','Início','Fim','Horas','Minutos'])
    selected=entries_for(entries,start,end)
    for e in selected:
        # Prevent spreadsheet formula evaluation of user descriptions.
        description=e['description']
        if description.lstrip().startswith(('=','+','-','@')):description="'"+description
        minutes=activity_minutes(e)
        writer.writerow([e['date'],description,e['start'],e['end'],f'{minutes//60:02d}:{minutes%60:02d}',minutes])
    minutes=total(selected);writer.writerow(['','TOTAL','','',f'{minutes//60:02d}:{minutes%60:02d}',minutes])
    return stream.getvalue()

def modify_entries(data,request,now=None):
    entries=data['timesheet'];action=request['action'];now=now or datetime.now()
    if action=='timesheet':
        value=validate_activity(request);identity=request.get('id')
        entry=next((e for e in entries if e['id']==identity),None)
        if identity and entry is None:raise _i18n.exception(ValueError, 'domain.timesheet.this_entry_has_already_been_removed_refresh_the_workspace')
        if entry and 'expected' in request and entry!=request['expected']:raise _i18n.exception(ValueError, 'domain.timesheet.this_entry_changed_in_another_window_reopen_it_before_editing')
        check_overlap(entries,value,identity,request.get('allow_overlap') is True)
        if entry is None:entry={'id':str(uuid.uuid4())};entries.append(entry)
        entry.update(value)
    elif action=='timesheet_delete':
        entry=next((e for e in entries if e['id']==request.get('id')),None)
        if entry is None:raise _i18n.exception(ValueError, 'domain.timesheet.entry_not_found')
        data.setdefault('timesheet_trash',[]).append(dict(entry));entries.remove(entry)
    elif action=='timesheet_undo':
        trash=data.setdefault('timesheet_trash',[])
        if not trash:raise _i18n.exception(ValueError, 'domain.timesheet.no_deletion_to_undo')
        entry=trash[-1]
        if any(e['id']==entry['id'] for e in entries):raise _i18n.exception(ValueError, 'domain.timesheet.this_entry_has_already_been_restored')
        if entry.get('source_task_id') and any(e.get('source_task_id')==entry['source_task_id'] for e in entries):
            raise _i18n.exception(ValueError, 'domain.timesheet.this_task_already_has_another_entry_in_this_timesheet')
        check_overlap(entries,entry,allow=request.get('allow_overlap') is True)
        entries.append(trash.pop())
    elif action=='timesheet_start':
        if data.get('timesheet_active'):raise _i18n.exception(ValueError, 'domain.timesheet.an_activity_is_already_running')
        description=request.get('description','')
        if not isinstance(description,str) or not 0<len(description.strip())<=1000:raise _i18n.exception(ValueError, 'domain.timesheet.enter_a_description_of_up_to_1000_characters')
        data['timesheet_active']={'description':description.strip(),'started':now.replace(second=0,microsecond=0).isoformat()}
    elif action=='timesheet_stop':
        active=data.get('timesheet_active')
        if not active:raise _i18n.exception(ValueError, 'domain.timesheet.no_running_activity')
        start=datetime.fromisoformat(active['started']);end=now.replace(second=0,microsecond=0)
        if end<=start:raise _i18n.exception(ValueError, 'domain.timesheet.the_activity_must_last_at_least_one_minute_wait_or_adjust_the_sys')
        pending=[]
        while start<end:
            midnight=datetime.combine(start.date()+timedelta(days=1),datetime.min.time())
            stop=min(end,midnight)
            value=validate_activity(dict(description=active['description'],date=start.date().isoformat(),start=start.strftime('%H:%M'),end='24:00' if stop==midnight else stop.strftime('%H:%M')))
            check_overlap(entries,value,allow=request.get('allow_overlap') is True)
            pending.append(dict(id=str(uuid.uuid4()),**value));start=stop
        entries.extend(pending);data['timesheet_active']=None
    else:raise _i18n.exception(ValueError, 'domain.timesheet.invalid_timesheet_action')


def migrate(data):
    """Move the original history, deleted entries and timer together, once."""
    if 'timesheets' not in data:
        data['timesheets']=[dict(id='default',name='Geral',archived=False,
            timesheet=data.pop('timesheet',[]),timesheet_trash=data.pop('timesheet_trash',[]),
            timesheet_active=data.pop('timesheet_active',None))]
    sheets=data['timesheets']
    if not isinstance(sheets,list):raise _i18n.exception(ValueError, 'domain.timesheet.invalid_timesheet_list_original_preserved')
    identities=set()
    for sheet in sheets:
        if not isinstance(sheet,dict) or not isinstance(sheet.get('id'),str) or sheet['id'] in identities:
            raise _i18n.exception(ValueError, 'domain.timesheet.invalid_timesheet_identity')
        identities.add(sheet['id'])
        if not isinstance(sheet.get('name'),str) or not sheet['name'].strip() or type(sheet.get('archived')) is not bool:
            raise _i18n.exception(ValueError, 'domain.timesheet.invalid_timesheet')
        if not isinstance(sheet.get('timesheet'),list) or not isinstance(sheet.get('timesheet_trash',[]),list):
            raise _i18n.exception(ValueError, 'domain.timesheet.invalid_timesheet_history')
        for entry in sheet['timesheet']+sheet.get('timesheet_trash',[]):
            if not isinstance(entry,dict) or not isinstance(entry.get('id'),str):raise _i18n.exception(ValueError, 'domain.timesheet.invalid_time_entry')
            validate_activity(entry)
        if 'context' in sheet:sheet_context.validate(sheet['context'])
        active=sheet.get('timesheet_active')
        if active is not None:
            if not isinstance(active,dict) or not isinstance(active.get('description'),str):raise _i18n.exception(ValueError, 'domain.timesheet.invalid_running_activity')
            datetime.fromisoformat(active['started'])
    return data

def get_sheet(data,identity):
    sheet=next((s for s in data['timesheets'] if s['id']==identity),None)
    if sheet is None:raise _i18n.exception(ValueError, 'domain.timesheet.timesheet_not_found_refresh_the_workspace')
    return sheet

def modify(data,request,now=None):
    migrate(data);action=request['action']
    if action=='sheet_create':
        name=sheet_context.name(request.get('name',''))
        context=sheet_context.validate(request.get('context'))
        if any(s['name'].casefold()==name.casefold() for s in data['timesheets']):
            raise _i18n.exception(ValueError, 'domain.timesheet.a_timesheet_with_this_name_already_exists_also_check_archived_tim')
        data['timesheets'].append(dict(id=str(uuid.uuid4()),name=name,context=context,archived=False,timesheet=[],timesheet_trash=[],timesheet_active=None))
        return
    sheet=None if action=='sheet_reorder' else get_sheet(data,request.get('sheet_id','default'))
    if action in ('sheet_rename','sheet_update'):
        name=sheet_context.name(request.get('name',sheet['name']))
        context=sheet_context.validate(request['context']) if 'context' in request else None
        if any(s['id']!=sheet['id'] and s['name'].casefold()==name.casefold() for s in data['timesheets']):raise _i18n.exception(ValueError, 'domain.timesheet.a_timesheet_with_this_name_already_exists')
        sheet['name']=name
        if context is not None:sheet['context']=context
    elif action=='sheet_reorder':
        order=request.get('order')
        active=[s for s in data['timesheets'] if not s['archived']]
        if not isinstance(order,list) or len(order)!=len(active) or len(set(order))!=len(order) or set(order)!={s['id'] for s in active}:
            raise _i18n.exception(ValueError, 'domain.timesheet.the_tabs_changed_refresh_and_try_again')
        by_id={s['id']:s for s in active};data['timesheets']=[by_id[i] for i in order]+[s for s in data['timesheets'] if s['archived']]
    elif action=='sheet_archive':
        if sheet.get('timesheet_active'):raise _i18n.exception(ValueError, 'domain.timesheet.stop_the_running_activity_before_archiving_this_timesheet')
        sheet['archived']=True
    elif action=='sheet_restore':sheet['archived']=False
    elif action=='sheet_delete':
        if not sheet['archived']:raise _i18n.exception(ValueError, 'domain.timesheet.archive_the_timesheet_before_permanently_deleting_it')
        data['timesheets'].remove(sheet)
    else:
        if sheet['archived']:raise _i18n.exception(ValueError, 'domain.timesheet.this_timesheet_is_archived_restore_it_before_changing_its_history')
        modify_entries(sheet,request,now)
