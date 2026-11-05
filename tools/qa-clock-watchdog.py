import sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from unittest.mock import patch
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,Gio
import widget_model as m
from desktop_widget import DesktopWidget
app=Gtk.Application(application_id='io.orbitz.ClockWatchdogQA',flags=Gio.ApplicationFlags.NON_UNIQUE);app.register(None)
def pump(seconds):
 until=time.monotonic()+seconds
 while time.monotonic()<until:
  while Gtk.events_pending():Gtk.main_iteration_do(False)
  time.sleep(.01)
with patch.object(DesktopWidget,'refresh_weather',return_value=False):
 c=m.validate({**m.read(),'x':80,'y':80})
 w=DesktopWidget(app,c);pump(2.2)
 assert w.clock_ticks>=2 and w.draw_count>=2
 with patch.object(w.area,'queue_draw'):
  w.last_draw_monotonic=time.monotonic()-4
  w.tick_clock();assert w.redraw_recoveries>=1
  pump(.5)
 with patch.object(w.get_window(),'process_updates'),patch.object(w.area,'queue_draw'),patch.object(w,'hide',wraps=w.hide) as hide,patch.object(w,'show',wraps=w.show) as show:
  w.last_draw_monotonic=time.monotonic()-7;w.tick_clock()
  assert hide.called and show.called
  pump(1.5)
 before=w.draw_count;pump(2.1);assert w.draw_count>before
 w.destroy()
print('PASS: clock ticks, redraw recovery, remap fallback, subsequent frames advance.')
