"""Portable clock settings, locale/format boundaries, and isolated widget startup."""
from copy import deepcopy
from datetime import datetime, timezone
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import widget_model as model
import widget_control as control
import ui_state


class WidgetModelTests(unittest.TestCase):
    def setUp(self):self.config=model.validate({})

    def test_defaults_match_clock_and_weather_reference(self):
        self.assertFalse(self.config['enabled']);self.assertEqual(self.config['time_format'],'%H:%M:%S')
        self.assertEqual(self.config['location']['name'],'Brasília, DF')
        self.assertTrue(self.config['show_feels'] and self.config['show_humidity'] and self.config['show_rain'])

    def test_validation_rejects_bad_formats_colors_coordinates_and_types(self):
        for changed in [dict(scale=0),dict(scale=float('nan')),dict(scale=True),dict(scale=4),dict(width=True),dict(width=0),dict(height=99999),dict(language='es'),dict(timezone='../../etc/passwd'),
                        dict(time_format='%Q'),dict(date_format='x\n'),dict(background_color='red; bad{}'),dict(clock_font='x\n'),
                        dict(location=dict(name='x',latitude=float('nan'),longitude=0)),dict(show_time=False,show_date=False,show_weather=False)]:
            with self.subTest(changed=changed),self.assertRaises(ValueError):model.validate(changed)

    def test_locale_is_independent_of_system_locale_and_percent_escape(self):
        now=datetime(2026,11,3,13,53,43,tzinfo=timezone.utc)
        pattern='%A %b %d · %H:%M:%S · %%A'
        self.assertEqual(model.localized_format(now,pattern,'pt-BR'),'terça nov 03 · 13:53:43 · %A')
        self.assertEqual(model.localized_format(now,pattern,'en-US'),'Tuesday Nov 03 · 13:53:43 · %A')
        self.assertEqual(model.localized_format(now,'%I:%M %p','en-US'),'01:53 PM')

    def test_clock_timezone_is_independent_from_weather_location(self):
        now=datetime(2026,11,3,16,0,tzinfo=timezone.utc)
        self.config['timezone']='America/Sao_Paulo'
        self.assertEqual(model.local_now(self.config,now).hour,13)
        self.config['timezone']='Asia/Tokyo'
        self.assertEqual(model.local_now(self.config,now).day,4)

    def payload(self,stale=False):
        today=model.local_now({**self.config,'timezone':'America/Sao_Paulo'}).date().isoformat()
        return dict(location=self.config['location'],unit='celsius',stale=stale,
            current=dict(temperature=28,apparent_temperature=32,humidity=57,weather_code=0,is_day=1),
            days=[dict(date=today,temp_min=19,temp_max=28,precipitation_probability=92)])

    def test_weather_is_fully_translated_in_both_languages(self):
        pt='\n'.join(model.weather_lines(self.config,self.payload()))
        self.assertIn('Céu limpo · Sensação 32°C',pt);self.assertIn('Umidade 57%',pt);self.assertIn('Chuva hoje: 92%',pt)
        self.config['language']='en-US';en='\n'.join(model.weather_lines(self.config,self.payload()))
        self.assertIn('Clear sky · Feels like 32°C',en);self.assertIn('Humidity 57%',en);self.assertNotIn('Sensação',en)

    def test_widget_uses_todays_forecast_condition_with_current_temperature(self):
        value=self.payload();value['current']['weather_code']=3
        value['days'][0]['weather_code']=95
        result='\n'.join(model.weather_lines(self.config,value))
        self.assertIn('Trovoadas',result)
        self.assertNotIn('Hoje:',result)
        self.assertNotIn('Nublado',result)
        self.assertIn('28°C',result)
        self.assertIn('Sensação 32°C',result)
        self.config['language']='en-US'
        self.assertIn('Thunderstorm','\n'.join(model.weather_lines(self.config,value)))
        value['days'][0]['date']='2000-01-01'
        self.assertNotIn('Thunderstorm','\n'.join(model.weather_lines(self.config,value)))

    def test_visibility_and_yesterdays_forecast_never_look_current(self):
        value=self.payload(True);value['days'][0]['date']='2000-01-01'
        result='\n'.join(model.weather_lines(self.config,value))
        self.assertNotIn('Chuva hoje:',result);self.assertNotIn('↓',result);self.assertIn('última previsão salva',result)
        self.config.update(show_location=False,show_condition=False,show_feels=False,show_range=False,show_humidity=False,show_rain=False)
        rows=model.weather_lines(self.config,self.payload());self.assertEqual(len(rows),1);self.assertNotIn('Brasília',rows[0])
        self.config['show_weather']=False
        self.assertEqual([kind for kind,_ in model.lines(self.config)],['clock','date'])

    def test_error_text_never_claims_a_successful_forecast(self):
        self.assertEqual(model.weather_lines(self.config,error=True),['Clima indisponível'])
        self.config['language']='en-US'
        self.assertEqual(model.weather_lines(self.config,error=True),['Weather unavailable'])

    def test_settings_roundtrip_without_modifying_other_data(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(ui_state,'PATH',Path(folder)/'planner-ui.json'):
            ui_state.set('unrelated-draft',{'text':'preserve'})
            config=model.validate(dict(enabled=True,unit='fahrenheit',language='en-US'))
            ui_state.set(model.KEY,config)
            self.assertEqual(model.read(),config);self.assertEqual(ui_state.get('unrelated-draft'),{'text':'preserve'})

    def test_scale_changes_only_physical_canvas_size(self):
        original=model.validate({})
        for scale in (.25,.5,1,1.5,2,3):
            scaled=model.validate({**original,'scale':scale})
            self.assertEqual(model.pixel_size(scaled),(round(440*scale),round(410*scale)))
            for key in original:
                if key!='scale':self.assertEqual(original[key],scaled[key])

    def test_hits_respect_scaled_region_boundaries_and_hidden_sections(self):
        regions={'clock':(0,20,220,50),'weather':(0,100,220,80)}
        self.assertEqual(model.hit_region(regions,100,40),'clock')
        self.assertEqual(model.hit_region(regions,100,120),'weather')
        self.assertIsNone(model.hit_region(regions,100,85))
        self.assertIsNone(model.hit_region(regions,230,120))

    def test_every_handle_scales_uniformly_and_keeps_opposite_anchor(self):
        original=model.validate({});old_w,old_h=model.pixel_size(original)
        for edge in ('nw','n','ne','e','se','s','sw','w'):
            dx=-220 if 'w' in edge else 220 if 'e' in edge else 0
            dy=-205 if 'n' in edge else 205 if 's' in edge else 0
            changed=model.resize_from_handle(original,edge,dx,dy)
            with self.subTest(edge=edge):
                self.assertEqual(changed['scale'],1.5)
                self.assertEqual(model.pixel_size(changed),(660,615))
                if 'w' in edge:self.assertEqual(changed['x']+660,original['x']+old_w)
                elif 'e' in edge:self.assertEqual(changed['x'],original['x'])
                else:self.assertEqual(changed['x']+330,original['x']+old_w/2)
                if 'n' in edge:self.assertEqual(changed['y']+615,original['y']+old_h)
                elif 's' in edge:self.assertEqual(changed['y'],original['y'])
                else:self.assertLessEqual(abs(changed['y']+307.5-(original['y']+old_h/2)),.5)
                for key in ('width','height','clock_size','date_size','weather_size','border_width','radius'):
                    self.assertEqual(changed[key],original[key])

    def test_resize_limits_and_bad_pointer_input(self):
        config=model.validate({})
        self.assertEqual(model.resize_from_handle(config,'e',-10000,0)['scale'],.25)
        self.assertEqual(model.resize_from_handle(config,'s',0,10000)['scale'],3)
        for edge,dx,dy in [('x',0,0),('se',float('nan'),0),('se',0,float('inf'))]:
            with self.assertRaises(ValueError):model.resize_from_handle(config,edge,dx,dy)


class WidgetControlTests(unittest.TestCase):
    def test_autostart_is_explicit_and_removable_in_own_namespace(self):
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{'XDG_CONFIG_HOME':folder}):
            config=model.validate({});control.update_autostart(config)
            self.assertFalse(control.autostart_path().exists())
            config.update(enabled=True,start_at_login=True);control.update_autostart(config)
            contents=control.autostart_path().read_text()
            self.assertIn('desktop_widget.py',contents);self.assertIn('--autostart',contents)
            self.assertNotIn('gnome-shell',contents)
            config['enabled']=False;control.update_autostart(config);self.assertFalse(control.autostart_path().exists())

    def test_disabled_widget_never_starts(self):
        with patch.object(control.subprocess,'Popen') as spawn:
            self.assertIsNone(control.start(model.validate({})));spawn.assert_not_called()

    def test_separate_process_prefers_xwayland_without_altering_main_environment(self):
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{'XDG_CACHE_HOME':folder,'DISPLAY':':99','WAYLAND_DISPLAY':'wayland-0'}),patch.object(control.subprocess,'Popen') as spawn:
            with patch.dict(os.environ,{},clear=False):
                original=os.environ.pop('GDK_BACKEND',None)
                try:
                    control.start(model.validate(dict(enabled=True)))
                    self.assertEqual(spawn.call_args.kwargs['env']['GDK_BACKEND'],'x11,wayland')
                    self.assertNotIn('GDK_BACKEND',os.environ)
                    self.assertTrue(spawn.call_args.kwargs['start_new_session'])
                    self.assertTrue(spawn.call_args.args[0][1].endswith('desktop_widget.py'))
                finally:
                    if original is not None:os.environ['GDK_BACKEND']=original

    def test_desktop_exec_quoting_preserves_special_characters(self):
        self.assertEqual(control.desktop_quote('/path with spaces/app.py'),'"/path with spaces/app.py"')
        self.assertIn('\\$',control.desktop_quote('$HOME'))

    def test_open_workspace_passes_user_activation_to_desktop_launcher(self):
        import gi
        gi.require_version('Gtk','3.0');gi.require_version('Gdk','3.0')
        from gi.repository import Gio,Gdk,Gtk
        info=Mock();display=Mock();context=display.get_app_launch_context.return_value
        with patch.object(Gio.DesktopAppInfo,'new',return_value=info),patch.object(Gdk.Display,'get_default',return_value=display),patch.object(Gtk,'get_current_event_time',return_value=1234),patch.object(control.subprocess,'Popen') as spawn:
            control.open_workspace()
        context.set_timestamp.assert_called_with(1234);info.launch.assert_called_once_with([],context);spawn.assert_not_called()

    def test_preferences_uses_desktop_action_with_activation_context(self):
        from gi.repository import Gio,Gdk,Gtk
        info=Mock();info.list_actions.return_value=['Preferences'];display=Mock()
        with patch.object(Gio.DesktopAppInfo,'new',return_value=info),patch.object(Gdk.Display,'get_default',return_value=display),patch.object(Gtk,'get_current_event_time',return_value=1234),patch.object(control.subprocess,'Popen') as spawn:
            control.open_workspace(True)
        info.launch_action.assert_called_once_with('Preferences',display.get_app_launch_context.return_value);spawn.assert_not_called()
