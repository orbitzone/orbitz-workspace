"""Calendar invoice periods, without GTK, stored profiles or personal data."""
from datetime import date
import calendar
from types import SimpleNamespace
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from invoice_period_ui import PeriodSelection, InvoicePeriodPicker


class PeriodTests(unittest.TestCase):
    def test_default_all_and_initial_agenda_month(self):
        model = PeriodSelection('2026-12-31')
        self.assertEqual((model.year, model.month), (2026, 12))
        self.assertTrue(model.ready)
        self.assertEqual(model.bounds(), (None, None))
        self.assertFalse(model.includes(date(2026, 12, 31)))

    def test_civil_month_lengths_and_leap_centuries(self):
        for year, month, length in [(2026, 2, 28), (2028, 2, 29), (2026, 4, 30),
                (2026, 1, 31), (1900, 2, 28), (2000, 2, 29), (2100, 2, 28)]:
            with self.subTest(year=year, month=month):
                model = PeriodSelection(date(year, month, 15))
                model.set_mode('month')
                self.assertEqual(model.bounds(), (date(year, month, 1).isoformat(), date(year, month, length).isoformat()))
                self.assertTrue(model.includes(date(year, month, length)))
                self.assertIn('Mês civil', model.summary())

    def test_range_requires_two_clicks_and_same_day_is_valid(self):
        model = PeriodSelection('2026-10-19')
        model.set_mode('range')
        self.assertFalse(model.ready)
        with self.assertRaises(ValueError): model.bounds()
        model.choose(date(2026, 10, 19))
        self.assertFalse(model.ready)
        self.assertIn('Falta', model.summary())
        self.assertTrue(model.includes(date(2026, 10, 19)))
        with self.assertRaises(ValueError): model.bounds()
        model.choose(date(2026, 10, 19))
        self.assertTrue(model.ready)
        self.assertEqual(model.bounds(), ('2026-10-19', '2026-10-19'))

    def test_inverse_clicks_cross_year_inclusive_and_restart(self):
        model = PeriodSelection('2027-01-04')
        model.set_mode('range')
        model.choose(date(2027, 1, 4))
        model.navigate(-1)
        self.assertFalse(model.ready)
        self.assertEqual(model.start, date(2027, 1, 4))
        model.choose(date(2026, 12, 29))
        self.assertEqual(model.bounds(), ('2026-12-29', '2027-01-04'))
        for day in [date(2026, 12, 29), date(2027, 1, 1), date(2027, 1, 4)]:
            self.assertTrue(model.includes(day))
        self.assertFalse(model.includes(date(2027, 1, 5)))
        model.choose(date(2026, 12, 10))
        self.assertFalse(model.ready)
        self.assertIsNone(model.end)

    def test_navigation_browses_without_changing_range(self):
        model = PeriodSelection('2026-01-20')
        model.set_mode('range')
        model.choose(date(2026, 1, 20))
        model.choose(date(2026, 3, 1))
        expected = model.bounds()
        for amount in (1, -12, 12, -1):
            model.navigate(amount)
            self.assertEqual(model.bounds(), expected)
        model.set_mode('month')
        model.navigate(-1)
        self.assertEqual(model.bounds(), ('2025-12-01', '2025-12-31'))

    def test_clear_modes_and_supported_year_boundaries(self):
        model = PeriodSelection(date(1, 1, 1))
        model.navigate(-1)
        self.assertEqual((model.year, model.month), (1, 1))
        model.set_mode('range')
        model.choose(date(1, 1, 1))
        model.clear()
        self.assertFalse(model.ready)
        model.set_mode('all')
        self.assertEqual(model.bounds(), (None, None))
        self.assertIsNone(model.start)
        model = PeriodSelection(date(9999, 12, 1))
        model.navigate(1)
        self.assertEqual((model.year, model.month), (9999, 12))
        with self.assertRaises(ValueError): model.set_mode('invalid')

    def test_selected_bounds_feed_invoice_snapshot_inclusively(self):
        from invoice_ui import InvoiceSession
        model = PeriodSelection('2026-12-31')
        model.set_mode('range')
        model.choose(date(2026, 12, 31))
        model.navigate(1)
        model.choose(date(2027, 1, 1))
        sheet = dict(id='test-sheet', name='Teste', archived=False, timesheet=[
            dict(description='Sintético', date=day, start='10:00', end='11:00')
            for day in ('2026-12-30', '2026-12-31', '2027-01-01', '2027-01-02')])
        session = InvoiceSession(lambda: {'timesheets': [sheet]})
        start, end = model.bounds()
        snapshot = session.prepare('test-sheet', dict(issuer=dict(name='Teste', tax_id='00000000000'),
            client=dict(name='Teste', tax_id='00000000000000', address='Endereço sintético'),
            rate='60', currency='BRL', language='pt', reference='TESTE', issued_on='2027-01-02',
            start=start, end=end))
        self.assertEqual(snapshot['minutes'], 120)
        self.assertEqual([entry['date'] for entry in snapshot['entries']], ['2026-12-31', '2027-01-01'])

    def test_semantic_signature_preserves_review_for_browsing_and_focus(self):
        picker = object.__new__(InvoicePeriodPicker)
        picker.model = PeriodSelection('2026-12-10')
        picker.model.set_mode('range')
        picker.model.choose(date(2026, 12, 10))
        picker.model.choose(date(2027, 1, 5))
        picker._refresh = Mock()
        picker.changed = Mock()
        signature = picker.model.selection_key()
        for amount in (-12, 1, 12, -1):
            picker._navigate(amount)
            self.assertEqual(picker.model.selection_key(), signature)
        picker.changed.assert_not_called()
        picker.model.set_mode('month')
        picker.days = [date(picker.model.year, picker.model.month, 15)]
        picker._choose(0)  # Choosing a day of the already-selected month changes no bounds.
        picker.changed.assert_not_called()
        picker._navigate(1)
        picker.changed.assert_called_once()
        picker.changed.reset_mock()
        picker._navigate(0)
        picker.changed.assert_not_called()

    def test_keyboard_focus_notifies_only_when_selected_month_changes(self):
        picker = object.__new__(InvoicePeriodPicker)
        picker.model = PeriodSelection('2026-12-30')
        picker.model.set_mode('month')
        picker.changed = Mock()
        picker.Gdk = SimpleNamespace(KEY_Left=1, KEY_Right=2, KEY_Up=3, KEY_Down=4,
            KEY_Page_Up=5, KEY_Page_Down=6)
        def refresh():
            picker.days = [date(picker.model.year, picker.model.month, day) for day in
                range(1, calendar.monthrange(picker.model.year, picker.model.month)[1] + 1)]
            picker.buttons = [Mock() for _ in picker.days]
        picker._refresh = refresh
        refresh()
        self.assertTrue(picker._key(SimpleNamespace(keyval=2), 29))
        picker.changed.assert_not_called()  # Dec30 -> Dec31 is focus only.
        picker._key(SimpleNamespace(keyval=2), 30)  # Dec31 -> Jan1 changes civil month.
        self.assertEqual((picker.model.year, picker.model.month), (2027, 1))
        picker.changed.assert_called_once()
        picker.model.set_mode('range')
        picker.model.choose(date(2027, 1, 1))
        picker.model.choose(date(2027, 1, 2))
        picker.changed.reset_mock()
        expected = picker.model.bounds()
        picker._key(SimpleNamespace(keyval=6), 0)  # Browse a month, keep the reviewed range.
        picker._key(SimpleNamespace(keyval=1), 0)  # Focus across a month boundary, no selection.
        self.assertEqual(picker.model.bounds(), expected)
        picker.changed.assert_not_called()

    def test_picker_navigation_and_selection_notify_without_implicit_click(self):
        picker = object.__new__(InvoicePeriodPicker)
        picker.model = PeriodSelection('2026-10-19')
        picker.model.set_mode('range')
        picker._refresh = Mock()
        picker.changed = Mock()
        picker.days = [date(2026, 10, 19)]
        picker._choose(0)
        self.assertEqual(picker.model.start, date(2026, 10, 19))
        picker._navigate(12)
        self.assertIsNone(picker.model.end)
        self.assertFalse(picker.model.ready)
        self.assertEqual(picker.changed.call_count, 1)
        picker._clear()
        self.assertIsNone(picker.model.start)
        self.assertEqual(picker.changed.call_count, 2)


if __name__ == '__main__':
    unittest.main()
