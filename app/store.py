#!/usr/bin/python3
"""Local planner store; serialize edits and preserve existing notes/tasks."""
from ui_language import ui as _i18n
import contextlib
from datetime import date,datetime,timedelta
import fcntl
import json
import os
from pathlib import Path
import sys
import uuid
import shutil
import hashlib
import re
from timesheet import clock_minutes,activity_minutes,validate_activity
import timesheet
import atomic_json

DATA=Path(os.environ.get('XDG_DATA_HOME') or Path.home()/'.local/share')/'orbitz-workspace'/'notes.json'

def read(path=DATA):
    try:data=json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:data={'notes':'','tasks':[]}
    if not isinstance(data,dict) or not isinstance(data.get('notes'),str) or not isinstance(data.get('tasks'),list):
        raise _i18n.exception(ValueError, 'domain.store.invalid_notes_and_tasks_file_the_original_was_preserved')
    for task in data['tasks']:
        if not isinstance(task,dict) or not isinstance(task.get('id'),str) or not isinstance(task.get('text'),str) or type(task.get('done')) is not bool:
            raise _i18n.exception(ValueError, 'domain.store.invalid_task_file_original_preserved')
        task.setdefault('date',date.today().isoformat());task.setdefault('time','');task.setdefault('reminder',10)
    timesheet.migrate(data)
    return data

def write(data,path=DATA):
    path.parent.mkdir(parents=True,exist_ok=True)
    # Snapshot the previous complete file before every committed edit.
    if path.exists():
        backups=path.parent/'planner-backups';backups.mkdir(mode=0o700,exist_ok=True)
        snapshot=backups/(datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'-'+uuid.uuid4().hex[:8]+'.json')
        shutil.copyfile(path,snapshot);snapshot.chmod(0o600)
        with snapshot.open('rb') as stream:os.fsync(stream.fileno())
    atomic_json.write(path, data, prefix='.notes-', suffix='.tmp', indent=2, encoding='utf-8')
    # Retention cannot invalidate a save; backups remain specific to this store.
    with contextlib.suppress(OSError):
        for old in sorted((path.parent/'planner-backups').glob('*.json'))[:-60]:old.unlink()

def fingerprint(data):
    return hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def backup_file(name,path=DATA):
    if not isinstance(name,str) or Path(name).name!=name or not name.endswith('.json'):raise _i18n.exception(ValueError, 'domain.store.invalid_copy')
    directory=path.parent/'planner-backups';candidate=directory/name
    if candidate.is_symlink() or not candidate.is_file():raise _i18n.exception(ValueError, 'domain.store.copy_not_found')
    return candidate

def list_backups(path=DATA):
    return [p.name for p in sorted((path.parent/'planner-backups').glob('*.json'),reverse=True) if not p.is_symlink()]

def summary(data):
    return dict(tasks=len(data['tasks']),sheets=len(data['timesheets']),
        entries=sum(len(s['timesheet']) for s in data['timesheets']),
        minutes=sum(timesheet.total(s['timesheet']) for s in data['timesheets']),
        active=sum(bool(s.get('timesheet_active')) for s in data['timesheets']),notes=len(data['notes']))

def validate_task(raw):
    text=raw.get('text');day=raw.get('date');clock=raw.get('time','');reminder=raw.get('reminder',10)
    if not isinstance(text,str) or not 0<len(text.strip())<=1000:raise _i18n.exception(ValueError, 'domain.store.enter_a_task_of_up_to_1000_characters')
    if not isinstance(day,str) or len(day)!=10:raise _i18n.exception(ValueError, 'domain.store.use_the_yyyy_mm_dd_date_format')
    try:date.fromisoformat(day)
    except ValueError:raise _i18n.exception(ValueError, 'domain.store.invalid_date') from None
    if not isinstance(clock,str):raise _i18n.exception(ValueError, 'domain.store.invalid_time')
    if clock:
        try:
            if len(clock)!=5 or datetime.strptime(clock,'%H:%M').strftime('%H:%M')!=clock:raise ValueError()
        except ValueError:raise _i18n.exception(ValueError, 'domain.store.use_the_hh_mm_time_format_for_example_14_30') from None
    if type(reminder) is not int or not 0<=reminder<=10080:raise _i18n.exception(ValueError, 'domain.store.the_reminder_must_be_between_0_and_10080_minutes_before')
    return dict(text=text.strip(),date=day,time=clock,reminder=reminder)

def modify(request,path=DATA):
    path.parent.mkdir(parents=True,exist_ok=True)
    lock=os.open(str(path)+'.lock',os.O_CREAT|os.O_RDWR,0o600)
    try:
        fcntl.flock(lock,fcntl.LOCK_EX)
        data=read(path);action=request.get('action')
        if action=='get':return data
        if action in ('timesheet','timesheet_delete','timesheet_undo','timesheet_start','timesheet_stop','sheet_create','sheet_archive','sheet_restore','sheet_delete','sheet_rename','sheet_update','sheet_reorder'):
            timesheet.modify(data,request)
        elif action=='backup_restore':
            if request.get('expected')!=fingerprint(data):raise _i18n.exception(ValueError, 'domain.store.data_changed_since_the_preview_select_the_copy_again_before_resto')
            backup=backup_file(request.get('name'),path)
            if request.get('backup_hash')!=hashlib.sha256(backup.read_bytes()).hexdigest():raise _i18n.exception(ValueError, 'domain.store.the_selected_copy_changed_reopen_the_preview')
            restored=read(backup)
            # A restoration saves the current state as a normal backup first.
            write(restored,path);return restored
        elif action=='external_task':
            source=request.get('source')
            if not isinstance(source,dict) or source.get('provider') not in ('icloud','ics','google','calendly') or not isinstance(source.get('key'),str) or not re.fullmatch('[0-9a-f]{64}',source['key']):
                raise _i18n.exception(ValueError, 'domain.store.invalid_event_source')
            for key in ('account_id','calendar_id','calendar_name','uid','occurrence','start','end'):
                if not isinstance(source.get(key),str) or len(source[key])>2048:raise _i18n.exception(ValueError, 'domain.store.invalid_event_metadata')
            if type(source.get('all_day')) is not bool:raise _i18n.exception(ValueError, 'domain.store.invalid_event_type')
            try:
                for key in ('start','end'):
                    if source['all_day']:date.fromisoformat(source[key])
                    else:datetime.fromisoformat(source[key])
            except ValueError:raise _i18n.exception(ValueError, 'domain.store.invalid_source_time') from None
            if any(t.get('external_source',{}).get('key')==source['key'] for t in data['tasks']):
                raise _i18n.exception(ValueError, 'domain.store.this_event_has_already_been_added_as_a_task')
            value=validate_task(request)
            if len(data['tasks'])>=2000:raise _i18n.exception(ValueError, 'domain.store.the_limit_of_2000_tasks_has_been_reached')
            task=dict(id=str(uuid.uuid4()),done=False,external_source={k:source[k] for k in ('key','provider','account_id','calendar_id','calendar_name','uid','occurrence','start','end','all_day')},**value)
            data['tasks'].append(task)
        elif action=='task_timesheet':
            task=next((t for t in data['tasks'] if t['id']==request.get('task_id')),None)
            if task is None:raise _i18n.exception(ValueError, 'domain.store.the_task_was_removed_refresh_the_workspace')
            if not task['done']:raise _i18n.exception(ValueError, 'domain.store.complete_the_task_before_adding_it_to_the_timesheet')
            if request.get('expected_task') is not None and request['expected_task']!={k:task[k] for k in ('text','date')}:
                raise _i18n.exception(ValueError, 'domain.store.the_task_changed_reopen_the_entry_to_use_the_updated_data')
            sheet=timesheet.get_sheet(data,request.get('sheet_id'))
            if any(e.get('source_task_id')==task['id'] for e in sheet['timesheet']):
                raise _i18n.exception(ValueError, 'domain.store.this_task_has_already_been_added_to_this_timesheet')
            timesheet.modify(data,dict(action='timesheet',sheet_id=sheet['id'],
                description=task['text'],date=task['date'],start=request.get('start'),end=request.get('end'),
                allow_overlap=request.get('allow_overlap') is True))
            sheet['timesheet'][-1]['source_task_id']=task['id']
        elif action=='notes':
            value=request.get('notes')
            if not isinstance(value,str) or len(value)>100000:raise _i18n.exception(ValueError, 'domain.store.the_note_must_have_up_to_100_000_characters')
            if 'expected_notes' in request and request['expected_notes'] != data['notes']:
                raise _i18n.exception(ValueError, 'domain.store.the_note_changed_in_another_editor_your_text_was_kept_in_this_win')
            data['notes']=value
        elif action=='note_color':
            color=request.get('color')
            if color not in ['#ffe293','#ffd6df','#d9edb5','#cce7ff','#e5d7fa','#ffdbb5']:raise _i18n.exception(ValueError, 'domain.store.choose_a_color_from_note_palette')
            data['note_color']=color
        elif action=='task':
            value=validate_task(request);identity=request.get('id')
            task=next((t for t in data['tasks'] if t['id']==identity),None)
            if identity and task is None:raise _i18n.exception(ValueError, 'domain.store.this_task_has_already_been_removed_refresh_the_workspace')
            if task is None:
                if len(data['tasks'])>=2000:raise _i18n.exception(ValueError, 'domain.store.the_limit_of_2000_tasks_has_been_reached')
                task={'id':str(uuid.uuid4()),'done':False};data['tasks'].append(task)
            if any(task.get(k)!=value[k] for k in ('date','time','reminder')):task.pop('dismissed',None)
            task.update(value)
        elif action in ('toggle','delete','dismiss'):
            task=next((t for t in data['tasks'] if t['id']==request.get('id')),None)
            if task is None:raise _i18n.exception(ValueError, 'domain.store.task_not_found')
            if action=='toggle':task['done']=not task['done'];task.pop('dismissed',None)
            elif action=='delete':data['tasks'].remove(task)
            else:
                if request.get('stamp')!=stamp(task):return data
                task['dismissed']=stamp(task)
        else:raise _i18n.exception(ValueError, 'domain.store.invalid_action')
        write(data,path);return data
    finally:os.close(lock)

def stamp(task):return '|'.join(str(task.get(k,'')) for k in ('date','time','reminder'))

def due(data,now=None):
    now=now or datetime.now();items=[]
    for task in data['tasks']:
        if task.get('done') or not task.get('time') or task.get('dismissed')==stamp(task):continue
        try:
            start=datetime.fromisoformat(task['date']+'T'+task['time'])
            lead=int(task.get('reminder',10))
            # At zero minutes, keep the start alert visible for one minute.
            if start-timedelta(minutes=lead)<=now<start+timedelta(minutes=1 if lead==0 else 0):
                items.append(task)
        except (ValueError,TypeError,KeyError):continue
    return items

def main():
    try:
        request=json.loads(sys.stdin.read(1048577))
        if not isinstance(request,dict):raise _i18n.exception(ValueError, 'domain.store.invalid_request')
        print(json.dumps({'ok':True,'data':modify(request)},ensure_ascii=False))
    except (OSError,ValueError,TypeError) as error:
        print(json.dumps({'ok':False,'error':str(error)},ensure_ascii=False));return 1
    return 0
if __name__=='__main__':sys.exit(main())
