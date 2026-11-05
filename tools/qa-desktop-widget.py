#!/usr/bin/python3
"""Real GTK desktop-widget walkthrough, with temporary XDG data and synthetic weather."""
from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime,timedelta
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import time
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/'docs/qa/desktop-widget-2026-11-03'


def main():
    OUTPUT.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='orbitz-widget-qa-') as temporary:
        os.environ.update(XDG_DATA_HOME=temporary+'/data',XDG_CONFIG_HOME=temporary+'/config',XDG_CACHE_HOME=temporary+'/cache',GSETTINGS_BACKEND='memory',ORBITZ_LOCALE='pt-BR')
        sys.path.insert(0,str(ROOT/'app'))
        import gi
        gi.require_version('Gtk','3.0')
        from gi.repository import Gtk,Gio,GLib,Gdk
        import cairo
        import widget_model as model,widget_control as control,weather_backend,ui_state,workspace_ui,external_ui
        from widget_preferences import WidgetPreferences
        from desktop_widget import DesktopWidget
        from ui_language import ui
        captured=[];errors=[];queue=[]
        def exception(typ,value,tb):errors.append(str(value));sys.__excepthook__(typ,value,tb)
        sys.excepthook=exception
        def wait(milliseconds=150):
            loop=GLib.MainLoop();GLib.timeout_add(milliseconds,lambda:(loop.quit(),False)[1]);loop.run()
        def widgets(widget,cls):
            result=[widget] if isinstance(widget,cls) else []
            if isinstance(widget,Gtk.Container):
                for child in widget.get_children():result+=widgets(child,cls)
            return result
        def shot(window,name):
            wait(100);window.check_resize()
            width,height=window.get_allocated_width(),window.get_allocated_height()
            surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,width,height);window.draw(cairo.Context(surface))
            surface.write_to_png(str(OUTPUT/(name+'.png')));captured.append(name)
        original_run=Gtk.Dialog.run
        def run(dialog):
            assert queue,'Unexpected dialog '+str(dialog.get_title())
            callback,response=queue.pop(0)
            def respond():
                try:callback(dialog);dialog.response(response)
                except Exception as error:errors.append(repr(error));dialog.response(Gtk.ResponseType.CANCEL)
                return False
            GLib.timeout_add(120,respond);return original_run(dialog)
        with ExitStack() as stack:
            stack.enter_context(patch.object(external_ui.ExternalCalendars,'sync',return_value=None))
            stack.enter_context(patch.object(external_ui.ExternalCalendars,'run',return_value=None))
            spec=importlib.util.spec_from_file_location('workspace_app',ROOT/'app/calendar-app.py')
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            app=module.CalendarApp();app.set_flags(app.get_flags()|Gio.ApplicationFlags.NON_UNIQUE);assert app.register(None)
            stack.enter_context(patch.object(app,'send_notification',return_value=None))
            window=module.CalendarWindow(app);wait()
            stack.enter_context(patch.object(Gtk.Dialog,'run',run))
            def initial(dialog):
                panel=widgets(dialog,WidgetPreferences)[0]
                assert not panel.revealer.get_reveal_child();shot(dialog,'preferences-disabled')
            queue.append((initial,Gtk.ResponseType.CANCEL));workspace_ui.open_preferences(window)
            assert ui_state.get(model.KEY) is None
            results={'results':[dict(id=1,name='São Paulo',latitude=-23.5505,longitude=-46.6333,timezone='America/Sao_Paulo',admin1='São Paulo',country='Brasil')]}
            def configure(dialog):
                panel=widgets(dialog,WidgetPreferences)[0]
                assert panel.value()['background_color']=='#00000033'
                panel.enabled.set_active(True);wait()
                assert panel.revealer.get_reveal_child();shot(dialog,'preferences-content')
                with patch.object(weather_backend,'geocode',return_value=results):
                    panel.search.set_text('São Paulo');panel.search_button.clicked();wait(250)
                assert panel.locations;panel.results.set_active(0)
                assert panel.location_name.get_text()=='São Paulo'
                panel.fields['language'].set_active_id('en-US');panel.time_preset.set_active_id('%I:%M %p')
                panel.date_preset.set_active_id('%m/%d/%Y');panel.fields['start_at_login'].set_active(True)
                book=widgets(panel,Gtk.Notebook)[0];book.set_current_page(1);shot(dialog,'preferences-appearance')
                book.set_current_page(2);shot(dialog,'preferences-position')
                panel.fields['show_humidity'].set_active(False);panel.fields['clock_size'].set_value(76)
                assert panel.value()['time_format']=='%I:%M %p'
            with patch.object(control,'start') as start:
                queue.append((configure,Gtk.ResponseType.OK));workspace_ui.open_preferences(window)
                start.assert_called_once()
            config=model.read();assert config['enabled'] and config['location']['name']=='São Paulo'
            assert config['language']=='en-US' and config['show_humidity'] is False
            assert control.autostart_path().exists()
            def canceled(dialog):
                panel=widgets(dialog,WidgetPreferences)[0];panel.enabled.set_active(False)
            queue.append((canceled,Gtk.ResponseType.CANCEL));workspace_ui.open_preferences(window)
            assert model.read()==config
            service=app
            def forecast(selected,unit='celsius',**kwargs):
                day=datetime.now().date()
                return dict(location={**selected,'timezone':'America/Sao_Paulo'},unit=unit,stale=False,
                    current=dict(temperature=28,apparent_temperature=32,humidity=57,weather_code=0,is_day=1),
                    days=[dict(date=(day+timedelta(days=i)).isoformat(),temp_min=19,temp_max=28,precipitation_probability=92,weather_code=1,wind_speed_max=12) for i in range(7)])
            with patch.object(weather_backend,'forecast',side_effect=forecast):
                widget=DesktopWidget(service,config);wait(250)
                assert widget.payload and not widget.error
                shot(widget,'widget-english-12h')
                def event(kind,button=1,state=0):
                    x,y,w,h=widget.hit_regions[kind]
                    return SimpleNamespace(button=button,state=state,x=x+w/2,y=y+h/2,
                        x_root=100,y_root=100,time=0,type=Gdk.EventType.BUTTON_PRESS)
                def dispatch_click(kind):
                    x,y,w,h=widget.hit_regions[kind]
                    for typ in (Gdk.EventType.BUTTON_PRESS,Gdk.EventType.BUTTON_RELEASE):
                        packet=Gdk.Event.new(typ);packet.window=widget.hit_buttons[kind].get_event_window()
                        packet.button=1;packet.x=w/2;packet.y=h/2
                        packet.x_root=packet.x;packet.y_root=packet.y
                        packet.time=Gdk.CURRENT_TIME;packet.state=0
                        packet.set_device(widget.get_display().get_default_seat().get_pointer())
                        Gtk.main_do_event(packet)
                    wait(80)
                with patch.object(control,'open_workspace') as open_main,patch.object(widget,'begin_move_drag') as drag:
                    dispatch_click('clock')
                    open_main.assert_called_once();drag.assert_not_called()
                    dispatch_click('weather');wait()
                    assert widget.forecast_window and len(widget.forecast_window.rows.get_children())==7
                    shot(widget.forecast_window,'forecast-seven-days')
                    widget.forecast_window.destroy();wait()
                    moved=event('weather',state=Gdk.ModifierType.MOD4_MASK)
                    widget.pressed(widget,moved);widget.released(widget,moved)
                    drag.assert_called_once();assert widget.forecast_window is None
                    widget.config['locked']=True;widget.pressed(widget,moved)
                    self_calls=drag.call_count;assert self_calls==1
                    widget.config['locked']=False
                with patch.object(Gtk.Menu,'popup_at_pointer'):
                    menu=widget.menu(None)
                    assert len(menu.get_children())==7
                    assert all('Open-Meteo' not in (item.get_label() or '') for item in menu.get_children())
                    menu.destroy()
                def drag_handle(edge,dx,dy):
                    wait(100)
                    handle=widget.resize_frame.handles[edge]
                    for typ,root_x,root_y in ((Gdk.EventType.BUTTON_PRESS,100,100),
                            (Gdk.EventType.MOTION_NOTIFY,100+dx,100+dy),
                            (Gdk.EventType.BUTTON_RELEASE,100+dx,100+dy)):
                        packet=Gdk.Event.new(typ);packet.window=handle.get_event_window()
                        packet.x=9;packet.y=9;packet.x_root=root_x;packet.y_root=root_y
                        packet.time=Gdk.CURRENT_TIME
                        packet.state=0 if typ==Gdk.EventType.BUTTON_PRESS else Gdk.ModifierType.BUTTON1_MASK
                        if typ!=Gdk.EventType.MOTION_NOTIFY:packet.button=1
                        packet.set_device(widget.get_display().get_default_seat().get_pointer())
                        Gtk.main_do_event(packet)
                        if typ==Gdk.EventType.BUTTON_PRESS:assert widget.resize_frame.drag is not None,'Handle did not receive button press'
                    wait(100)
                original=deepcopy(widget.config)
                key=SimpleNamespace(keyval=Gdk.KEY_t,state=Gdk.ModifierType.CONTROL_MASK)
                widget.key_pressed(widget,key);widget.key_released(widget,key)
                assert widget.resize_frame is not None
                assert len(widget.resize_frame.handles)==8
                assert all(not isinstance(w,Gtk.Dialog) for w in app.get_windows())
                drag_handle('se',220,205)
                assert model.pixel_size(widget.config)==(660,615),(widget.config['scale'],widget.resize_frame.drag)
                assert list(widget.get_size())==[660,615]
                for field in ('width','height','clock_size','date_size','weather_size','border_width','radius'):
                    assert widget.config[field]==original[field]
                shot(widget,'widget-scaled-150-percent')
                shot(widget,'resize-frame-controls')
                widget.finish_resize(False);wait()
                assert widget.config['scale']==original['scale'] and model.read()['scale']==original['scale']
                widget.key_pressed(widget,key);widget.key_released(widget,key)
                drag_handle('se',220,205)
                widget.key_pressed(widget,key);widget.key_released(widget,key)
                assert widget.resize_frame is None and model.read()['scale']==1.5
                widget.open_resize();wait()
                escape=SimpleNamespace(keyval=Gdk.KEY_Escape,state=0)
                widget.key_pressed(widget,escape)
                assert widget.resize_frame is None
                widget.open_resize();wait();widget.resize_frame.done.clicked()
                assert widget.resize_frame is None
                config=model.read()
                config.update(language='pt-BR',time_format='%H:%M:%S',date_format='%A %b %d',show_humidity=True)
                ui_state.set(model.KEY,config);widget.poll();shot(widget,'widget-portuguese-reference')
                config.update(background_color='#173a66dd',border_color='#6fd5ffff',radius=44)
                ui_state.set(model.KEY,config);widget.poll();shot(widget,'widget-custom-colors')
                # Position settings never depend on the main Workspace window staying alive.
                window.destroy();wait();assert widget.get_visible()
                widget.toggle_lock();widget.poll();assert widget.config['locked']
                widget.toggle_lock();widget.poll();assert not widget.config['locked']
                with patch.object(weather_backend,'forecast',side_effect=OSError('offline')):
                    widget.refresh_weather(True);wait(250)
                assert widget.error and widget.payload is None;shot(widget,'widget-weather-offline')
                widget.destroy();wait()
            # Production process stays up after the main UI closes, and exits when disabled.
            config.update(show_weather=False,enabled=True,start_at_login=False)
            ui_state.set(model.KEY,config);control.update_autostart(config)
            process=control.start(config)
            try:
                wait(900);assert process.poll() is None,'Independent widget exited unexpectedly'
                config['enabled']=False;control.apply(config)
                process.wait(timeout=5);assert process.returncode==0
            finally:
                if process.poll() is None:process.terminate();process.wait(timeout=5)
            assert not control.autostart_path().exists()
            assert not errors,errors
        result=dict(screens=captured,errors=errors,checks=['enable/reveal','cancel-preserves-settings','city-search','formats-12h-24h',
            'PT/EN','live-preview','appearance','autostart-opt-in','weather-offline','lock-position','clock-single-click','weather-single-click-seven-days','super-drag','plain-click-does-not-drag','Ctrl+T',
            'proportional-scale','eight-handles','rounded-frame','native-handle-events','Esc-finishes','Done-finishes','menu-without-provider','resize-cancel','resize-save','independent-process','disable-stops-process'])
        (OUTPUT/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
