"""Hover-scoped keyboard capture and modifier-only movement without real input injection."""
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from widget_shortcuts import HoverShortcuts
try:
    from Xlib import X
except ImportError:
    X=None

@unittest.skipIf(X is None,'python3-xlib is needed for X11 hover shortcuts')
class HoverShortcutTests(unittest.TestCase):
    def setUp(self):
        h=self.helper=HoverShortcuts.__new__(HoverShortcuts)
        h.X=X;h.window=Mock();h.window.config={'locked':False};h.window.resize_active=False;h.window.get_position.return_value=(100,200)
        h.root=Mock();h.display=Mock();h.display.pending_events.return_value=0
        h.keycode=28;h.grabbed=False;h.key_held=False;h.drag=None;h.alive=True;h.failed=False;h.timer=0;h.watch=0
        h.modifiers=[X.ControlMask|mask for mask in (0,X.LockMask,X.Mod2Mask,X.LockMask|X.Mod2Mask)]
        h.over_widget=Mock(return_value=True);h.activate=Mock();h.released=Mock()
        self.pointer=SimpleNamespace(mask=0,root_x=10,root_y=20)
        h.root.query_pointer.return_value=self.pointer

    def test_ctrl_t_is_grabbed_only_while_pointer_is_over_widget(self):
        h=self.helper;h.poll();self.assertTrue(h.grabbed)
        self.assertEqual(h.root.grab_key.call_count,4)
        h.over_widget.return_value=False;h.poll()
        self.assertFalse(h.grabbed);self.assertEqual(h.root.ungrab_key.call_count,4)

    def test_plain_mouse_button_never_starts_a_move(self):
        self.pointer.mask=X.Button1Mask;self.helper.poll()
        self.assertIsNone(self.helper.drag);self.helper.window.move.assert_not_called()

    def test_super_drag_tracks_pointer_even_after_leaving_widget_and_persists_drop(self):
        h=self.helper;self.pointer.mask=X.Mod4Mask|X.Button1Mask;h.poll()
        self.assertEqual(h.drag,(10,20,100,200))
        self.pointer.root_x=30;self.pointer.root_y=50;h.over_widget.return_value=False;h.poll()
        h.window.move.assert_called_with(120,230)
        self.pointer.mask=0;h.poll()
        self.assertIsNone(h.drag);h.window.persist_position.assert_called_once()

    def test_locked_position_blocks_super_drag(self):
        self.pointer.mask=X.Mod4Mask|X.Button1Mask;self.helper.window.config['locked']=True
        self.helper.poll();self.assertIsNone(self.helper.drag)

    def test_key_autorepeat_does_not_toggle_resize_repeatedly(self):
        h=self.helper;h.display.pending_events.side_effect=[1,1,0]
        h.display.next_event.return_value=SimpleNamespace(type=X.KeyPress,detail=h.keycode)
        h.events(None,1);h.activate.assert_called_once()
        h.display.pending_events.side_effect=None;h.display.pending_events.return_value=0
        h.display.query_keymap.return_value=[0]*32
        h.poll();h.released.assert_called_once();self.assertFalse(h.key_held)

    def test_cleanup_ungrabs_shortcut_and_closes_its_own_connection(self):
        h=self.helper;h.grab(True);h.close()
        self.assertFalse(h.alive);self.assertFalse(h.grabbed);h.display.close.assert_called_once()
