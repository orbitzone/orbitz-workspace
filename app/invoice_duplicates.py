"""Non-blocking evidence of overlapping billed time; never marks live hours."""
import invoice
import invoice_history as history
import timesheet


def _intervals(entries):
    days={}
    for entry in entries:
        days.setdefault(entry['date'],[]).append((timesheet.clock_minutes(entry['start']),timesheet.clock_minutes(entry['end'])))
    result={}
    for day,values in days.items():
        merged=[]
        for start,end in sorted(values):
            if merged and start<=merged[-1][1]:merged[-1]=(merged[-1][0],max(end,merged[-1][1]))
            else:merged.append((start,end))
        result[day]=merged
    return result


def _overlap(left,right):
    left,right=_intervals(left),_intervals(right)
    minutes=0
    for day in left.keys() & right.keys():
        a,b=left[day],right[day];i=j=0
        while i<len(a) and j<len(b):
            minutes+=max(0,min(a[i][1],b[j][1])-max(a[i][0],b[j][0]))
            if a[i][1]<=b[j][1]:i+=1
            else:j+=1
    return minutes


def check(snapshot,*,root=None):
    snapshot=invoice.validate_snapshot(snapshot)
    scanned=history.list_records(root=root)
    matches=[];legacy=False
    for record in scanned['records']:
        old=record['snapshot']
        if old['sheet_id']!=snapshot['sheet_id']:continue
        if not old.get('source_entries') or not snapshot.get('source_entries'):legacy=True
        minutes=_overlap(snapshot['entries'],old['entries'])
        if not minutes:continue
        sources={}
        for source in old.get('source_entries',[]):sources.setdefault((source['id'],source['date']),[]).append(source)
        exact=any(_overlap([source],sources.get((source['id'],source['date']),[]))>0 for source in snapshot.get('source_entries',[]))
        matches.append(dict(id=record['id'],reference=record['reference'],minutes=minutes,basis='entry_id_and_time' if exact else 'time_overlap_legacy' if not old.get('source_entries') else 'time_overlap'))
    warnings=[]
    if legacy:warnings.append('Há faturas sem vínculo de origem completo; a comparação usa os horários registrados e não garante ausência de duplicidade.')
    if scanned['errors']:warnings.append('Registros indisponíveis não puderam ser comparados; revise o histórico antes de emitir.')
    return dict(matches=matches,warnings=warnings,incomplete=legacy or bool(scanned['errors']))
