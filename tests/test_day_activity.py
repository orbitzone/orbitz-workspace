"""Marker/agenda projections use synthetic cached events and local activities only."""
import ast
from datetime import date,timedelta
from types import SimpleNamespace
from unittest.mock import Mock
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from day_activity import external_activity,local_activity,local_details,day_description
from ui_language import ui


class DayActivityTests(unittest.TestCase):
    def setUp(self):
        self.accounts=[dict(id='personal',calendars=[dict(id='main')]),dict(id='holidays',calendars=[dict(id='br')])]
        self.key=lambda a,c,m:a+'|'+c+'|'+m
        self.holiday=dict(title='Feriado de teste',start='2026-11-02',end='2026-11-03',all_day=True)
        self.cache={self.key('holidays','br','2026-11'):dict(events=[self.holiday])}
        self.data=dict(tasks=[dict(date='2026-11-20',text='Tarefa de teste',done=False),dict(date='2026-11-15',text='Concluída',done=True)],
            timesheets=[dict(id='work',name='Trabalho',archived=False,timesheet=[dict(date='2026-11-20')]),
                dict(id='old',name='Arquivo',archived=True,timesheet=[dict(date='2026-11-15')])])

    def external(self,day,selected='personal|main'):
        return external_activity(self.accounts,self.cache,self.key,selected,day,
            lambda e:e['title'].startswith('Feriado'),lambda a,c:a['id']+' · '+c['id'])

    def test_other_source_holiday_explains_marker_with_origin(self):
        events,others,holidays=self.external(date(2026,11,2))
        self.assertEqual(events,[])
        self.assertEqual(others,[(self.holiday,'holidays · br')])
        self.assertEqual(holidays,['Feriado de teste · holidays · br'])
        self.assertTrue(events or others)  # Same marker predicate as the month UI.

    def test_selected_source_holiday_is_not_duplicated_in_context(self):
        self.cache[self.key('personal','main','2026-11')]=dict(events=[dict(self.holiday)])
        events,others,_=self.external(date(2026,11,2))
        self.assertEqual(events,[self.holiday]);self.assertEqual(others,[])

    def test_disabled_source_has_no_cached_events_or_holiday_markers(self):
        self.accounts[1]['enabled']=False
        self.assertEqual(self.external(date(2026,11,2),'holidays|br'),([],[],[]))
        self.accounts[1]['enabled']=True
        self.assertEqual(len(self.external(date(2026,11,2),'holidays|br')[0]),1)

    def test_other_source_personal_event_is_not_exposed_or_marked(self):
        self.cache[self.key('holidays','br','2026-11')]['events']=[dict(self.holiday,title='Evento pessoal')]
        self.assertEqual(self.external(date(2026,11,2)),([],[],[]))

    def test_tasks_and_hours_explain_local_markers_with_context(self):
        day=date(2026,11,20);tasks,sheets=local_activity(self.data,day)
        self.assertEqual([t['text'] for t in tasks],['Tarefa de teste'])
        self.assertEqual([s['id'] for s,_ in sheets],['work'])
        details=local_details(self.data,day)
        self.assertEqual(details,['Atividades locais: 1 tarefa(s) pendente(s)','Horas locais: Trabalho · 1 registro(s)'])

    def test_selected_day_alone_has_no_activity_marker(self):
        day=date(2026,11,15)
        self.assertEqual(self.external(day),([],[],[]))
        self.assertEqual(local_activity(self.data,day),([],[]))
        self.assertEqual(local_details(self.data,day),[])
        self.assertEqual(day_description(day,True),['15/11/2026','Data selecionada'])
        self.assertEqual(day_description(day),['15/11/2026'])

    def test_all_day_end_is_exclusive_and_activity_tooltip_is_explicit(self):
        self.assertEqual(self.external(date(2026,11,3)),([],[],[]))
        text=day_description(date(2026,11,20),True,True,[],local_details(self.data,date(2026,11,20)))
        self.assertIn('Atividades neste dia',text);self.assertIn('Data selecionada',text)

class AgendaIntegrationTests(unittest.TestCase):
    setUp=DayActivityTests.setUp
    def test_agenda_and_markers_share_context_and_local_routes(self):
        module=Path(__file__).resolve().parents[1]/'app/external_ui.py'
        node=next(n for n in ast.parse(module.read_text()).body if isinstance(n,ast.ClassDef))
        labels=[];buttons=[]
        def label(**kwargs):labels.append(kwargs.get('label',''));return Mock()
        def button(**kwargs):
            widget=Mock();buttons.append((kwargs['label'],widget));return widget
        remote=SimpleNamespace(read=lambda:dict(cache=self.cache),cache_key=self.key)
        namespace=dict(ui=ui,date=date,timedelta=timedelta,remote=remote,external_activity=external_activity,
            local_activity=local_activity,Gtk=SimpleNamespace(Label=label,Button=button),re=__import__('re'))
        exec(compile(ast.Module(body=[node],type_ignores=[]),'external_ui.py','exec'),namespace)
        obj=object.__new__(namespace['ExternalCalendars']);obj.alive=True;obj.accounts=self.accounts
        obj.selector=SimpleNamespace(get_active_id=lambda:'personal|main')
        obj.source_label=lambda a,c:a['id']+' · '+c['id']
        obj.is_holiday=lambda e:e['title'].startswith('Feriado')
        obj.rows=Mock();obj.rows.get_children.return_value=[];obj.title=Mock();obj.status=Mock();obj.busy=set()
        obj.window=SimpleNamespace(day='2026-11-02',data=self.data,calendar=Mock(),show_area=Mock(),focus_sheet=Mock())
        obj.window.calendar.get_date.return_value=(2026,10,2)
        obj.selected_cache=lambda:((self.accounts[0],self.accounts[0]['calendars'][0],'2026-11'),{})
        obj.render()
        self.assertTrue(any('Feriado de teste' in text and 'Fonte: holidays · br' in text for text in labels))
        obj.window.day='2026-11-20';labels.clear();obj.render()
        self.assertTrue(any('Tarefa de teste' in text for text in labels))
        self.assertTrue(any('Horas locais · Trabalho' in text for text in labels))
        for title,widget in buttons:
            callback=widget.connect.call_args.args[1];callback(None)
        obj.window.show_area.assert_called_with('tasks');obj.window.focus_sheet.assert_called_with('work')
        details={20:local_details(self.data,date(2026,11,20))}
        obj.mark_days(details)
        obj.window.calendar.mark_day.assert_called_with(2)
        holidays,actual=obj.window.calendar.finish_marks.call_args.args
        self.assertIn(2,holidays);self.assertEqual(actual[20],details[20])

if __name__=='__main__':unittest.main()
