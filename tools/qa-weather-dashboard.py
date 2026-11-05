import sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,Gdk
from datetime import timedelta
from unittest.mock import Mock
import widget_model as m
from widget_forecast import ForecastWindow
app=Gtk.Application(application_id='io.orbitz.WeatherDashboardQA');app.register(None)
parent=Gtk.ApplicationWindow(application=app);refresh=Mock()
c=m.read();today=m.local_now(c).date()
p={'location':c['location'],'current':dict(time=str(today)+'T21:30',temperature=22,apparent_temperature=25,humidity=89,weather_code=3,is_day=0),'days':[dict(date=str(today+timedelta(days=i)),weather_code=[95,61,3,0,2,51,95][i],temp_min=19,temp_max=29,precipitation_probability=90,wind_speed_max=12) for i in range(7)]}
for day in p['days']:
 day.update(sunrise=day['date']+'T05:34',sunset=day['date']+'T18:16',daylight_duration=45742)
w=ForecastWindow(parent,refresh)
def pump():
 for _ in range(25):
  while Gtk.events_pending():Gtk.main_iteration_do(False)
  time.sleep(.02)
for lang,theme in [('en-US','dark'),('pt-BR','light')]:
 c.update(language=lang,theme=theme);w.update(c,p);w.show_all();pump()
 assert len(w.rows.get_children())==7
 assert w.solar.get_visible() and not w.summary.get_visible()
 assert '5:34' in w.sunrise.get_text() or '05:34' in w.sunrise.get_text()
 for card in w.rows.get_children():
  x,y=card.translate_coordinates(w,0,0);a=card.get_allocation()
  assert x>=0 and x+a.width<=w.get_allocated_width(),(x,a.width,w.get_allocated_width())
 pix=Gdk.pixbuf_get_from_window(w.get_window(),0,0,w.get_allocated_width(),w.get_allocated_height())
 pix.savev('/tmp/orbitz-weather-'+theme+'.png','png',[],[])
w.update(c,{**p,'stale':True});assert w.status.get_visible()
w.update(c,None,error=True);assert 'indisponível' in w.heading.get_text()
refresh.reset_mock();w.refresh.clicked();refresh.assert_called_once()
w.destroy();parent.destroy()
print('PASS: sete dias, layout sem cortes, Light/Dark, PT/EN, erro, cache antigo e atualizar.')
