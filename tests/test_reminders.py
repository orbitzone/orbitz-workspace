"""Reminder boundaries, external deduplication and durable delivery state."""
from datetime import datetime, timedelta
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import reminders

class ReminderTests(unittest.TestCase):
    def setUp(self):
        self.start=datetime(2026,11,3,12,0).astimezone()
        self.task=dict(id='task',text='Revisão',date='2026-11-03',time='12:00',reminder=10,done=False)
        self.data={'tasks':[self.task]}
        self.event=dict(key='event',title='Evento',start=self.start.isoformat(),all_day=False,alarm_minutes=[5,10])
        self.external=dict(accounts=[dict(id='account',calendars=[dict(id='calendar')])],cache={'account|calendar|2026-11':dict(events=[self.event])})

    def test_lead_boundary_start_and_expiry(self):
        for minutes,expected in [(-11,0),(-10,1),(0,1),(1,0)]:
            self.assertEqual(len(reminders.collect(self.data,now=self.start+timedelta(minutes=minutes))),expected)

    def test_done_dismissed_and_rescheduled(self):
        self.task['done']=True
        self.assertEqual(reminders.collect(self.data,now=self.start),[])
        self.task['done']=False;self.task['dismissed']='2026-11-03|12:00|10'
        self.assertEqual(reminders.collect(self.data,now=self.start),[])
        self.task['reminder']=5
        self.assertEqual(len(reminders.collect(self.data,now=self.start)),1)

    def test_zero_minute_and_invalid_leads(self):
        self.task['reminder']=0
        self.assertEqual(reminders.collect(self.data,now=self.start-timedelta(seconds=1)),[])
        self.assertEqual(len(reminders.collect(self.data,now=self.start)),1)
        for lead in (-1,10081,True,'10'):
            self.task['reminder']=lead
            self.assertEqual(reminders.collect(self.data,now=self.start),[])

    def test_cached_events_disabled_all_day_and_duplicate_month_caches(self):
        self.external['cache']['account|calendar|2026-12']=dict(events=[self.event])
        self.assertEqual(len(reminders.collect({},self.external,self.start)),1)
        self.external['accounts'][0]['enabled']=False
        self.assertEqual(reminders.collect({},self.external,self.start),[])
        self.external['accounts'][0]['enabled']=True;self.event['all_day']=True
        self.assertEqual(reminders.collect({},self.external,self.start),[])

    def test_converted_completed_task_suppresses_event(self):
        self.task['external_source']={'key':'event'};self.task['done']=True
        self.assertEqual(reminders.collect(self.data,self.external,self.start),[])
        self.task['done']=False
        self.assertEqual(len(reminders.collect(self.data,self.external,self.start)),1)

    def test_notification_sent_once_across_restarts(self):
        prefs=Mock();prefs.get.return_value=[];notify=Mock()
        service=reminders.ReminderService(notify,prefs)
        service.poll(self.data,now=self.start);service.poll(self.data,now=self.start)
        notify.assert_called_once()
        prefs.get.return_value=service.sent
        reminders.ReminderService(notify,prefs).poll(self.data,now=self.start)
        notify.assert_called_once()

    def test_failed_delivery_is_retryable(self):
        prefs=Mock();prefs.get.return_value=[];notify=Mock(side_effect=RuntimeError('delivery failed'))
        service=reminders.ReminderService(notify,prefs)
        with self.assertRaises(RuntimeError):service.poll(self.data,now=self.start)
        self.assertEqual(service.sent,[]);prefs.set.assert_not_called()
