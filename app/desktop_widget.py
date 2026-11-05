#!/usr/bin/python3
"""An independent GTK desktop clock/weather process; no GNOME Shell extension."""
import os
if not os.environ.get('GDK_BACKEND') and os.environ.get('DISPLAY'):
    os.environ['GDK_BACKEND']='x11,wayland'
# Use core pointer events for the widget's native X11 input windows.
os.environ.setdefault('GDK_CORE_DEVICE_EVENTS','1')
import sys
import time
from concurrent.futures import ThreadPoolExecutor
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,Gdk,Gio,GLib
import cairo
from ui_language import ui
import ui_state
import widget_model as model
import widget_render
import widget_control
import weather_backend


class DesktopWidget(Gtk.ApplicationWindow):
    def __init__(self,app,config):
        super().__init__(application=app,title='Orbitz Workspace · Desktop Widget')
        self.config=config;self.payload=None;self.error=False;self.alive=True;self.busy=False
        self.clock_ticks=0;self.last_clock_tick=None
        self.draw_count=0;self.last_draw_monotonic=time.monotonic();self.redraw_recoveries=0;self.last_remap_monotonic=0
        self.last_fetch=0;self.weather_identity=None;self.position_timer=0;self.applying=True
        self.input_counts={'press':0,'release':0,'hotkey':0};self.last_hit=None
        self.hit_regions={};self.pending_click=None;self.forecast_window=None;self.resize_frame=None
        self.shortcuts=None;self.hotkey_down=False;self.resize_active=False;self.resize_original=None;self.resize_draft=None
        self.executor=ThreadPoolExecutor(max_workers=1)
        self.set_decorated(False);self.set_resizable(False);self.set_app_paintable(True)
        self.set_accept_focus(True);self.set_focus_on_map(False)
        self.set_skip_taskbar_hint(True);self.set_skip_pager_hint(True)
        self.x11='X11' in type(self.get_display()).__name__
        if self.x11:
            # Forcing DESKTOP/BELOW made the visible widget click-through on the user's compositor.
            # Use a normal, unpinned window; other applications can cover it normally.
            self.set_type_hint(Gdk.WindowTypeHint.NORMAL);self.set_keep_below(False);self.stick()
        visual=self.get_screen().get_rgba_visual()
        if visual:self.set_visual(visual)
        provider=Gtk.CssProvider();provider.load_from_data(b'window {background-color:transparent;box-shadow:none;}')
        self.get_style_context().add_provider(provider,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.overlay=Gtk.Overlay();self.add(self.overlay)
        self.area=Gtk.DrawingArea();self.overlay.add(self.area)
        self.hit_buttons={};self.region_update=0;self.restore_timer=0;self.requested_position=None
        button_css=Gtk.CssProvider()
        button_css.load_from_data(b'.orbitz-widget-hit, .orbitz-widget-hit:hover, .orbitz-widget-hit:active, .orbitz-widget-hit:focus {background:transparent; color:transparent; border:0; box-shadow:none; padding:0; min-height:0; min-width:0; outline:0;}')
        for kind in ('clock','date','weather'):
            button=Gtk.Button();button.set_halign(Gtk.Align.FILL);button.set_valign(Gtk.Align.START)
            button.get_style_context().add_class('orbitz-widget-hit')
            button.get_style_context().add_provider(button_css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            ui.call(button.get_accessible(),'set_name',ui.msg('workspace.widget.forecast_title' if kind=='weather' else 'workspace.widget.open'))
            button.connect('button-press-event',self.pointer_background)
            button.connect('clicked',self.button_clicked,kind)
            button.set_no_show_all(True)
            self.overlay.add_overlay(button);self.overlay.set_overlay_pass_through(button,False)
            self.hit_buttons[kind]=button
        from widget_footer import WidgetFooter
        self.footer=WidgetFooter(self)
        self.overlay.add_overlay(self.footer)
        self.overlay.set_overlay_pass_through(self.footer,False)
        self.area.connect('draw',self.draw_content)
        self.area.set_can_focus(True)
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK|Gdk.EventMask.BUTTON_RELEASE_MASK|Gdk.EventMask.KEY_PRESS_MASK|Gdk.EventMask.KEY_RELEASE_MASK)
        self.connect('button-press-event',self.pointer_background)
        self.connect('button-release-event',self.released)
        self.connect('key-press-event',self.key_pressed)
        self.connect('key-release-event',self.key_released)
        self.connect('configure-event',self.configured)
        self.connect('map-event',self.restore_on_map)
        self.connect('destroy',self.cleanup)
        self.connect('delete-event',self.closed)
        self.apply(config);self.show_all();self.tick=GLib.timeout_add_seconds(1,self.poll)
        self.clock_timer=GLib.timeout_add(1000,self.tick_clock)
        if self.x11:
            try:
                from widget_shortcuts import HoverShortcuts
                self.shortcuts=HoverShortcuts(self,self.hotkey,self.hotkey_released)
            except Exception:pass
        GLib.idle_add(self.refresh_weather)

    def apply(self,config):
        self.applying=True;self.config=config;ui.refresh(config['language'])
        width,height=model.pixel_size(config)
        if hasattr(self,'footer'):self.footer.update(config)
        if self.resize_frame is not None:self.resize_frame.set_geometry(width,height)
        self.area.set_size_request(width,height)
        self.resize(width,height)
        if self.x11:
            x,y=config['x'],config['y']
            monitors=[self.get_display().get_monitor(i).get_workarea() for i in range(self.get_display().get_n_monitors())]
            if not self.resize_active and monitors and not any(r.x<=x<r.x+r.width-32 and r.y<=y<r.y+r.height-32 for r in monitors):
                x,y=monitors[0].x+40,monitors[0].y+40
            self.requested_position=(x,y);self.move(x,y)
        self.area.queue_draw();self.update_forecast();GLib.idle_add(self.applied)

    def applied(self):self.applying=False;return False

    def restore_on_map(self,*_):
        if not self.x11:return False
        self.applying=True
        if self.restore_timer:GLib.source_remove(self.restore_timer)
        self.restore_timer=GLib.timeout_add(150,self.restore_mapped_position)
        return False

    def restore_mapped_position(self):
        self.restore_timer=0
        if self.alive and self.requested_position is not None:self.move(*self.requested_position)
        GLib.idle_add(self.applied)
        return False

    def draw_content(self,area,context):
        self.draw_count+=1;self.last_draw_monotonic=time.monotonic()
        context.set_operator(cairo.OPERATOR_SOURCE);context.set_source_rgba(0,0,0,0);context.paint()
        context.set_operator(cairo.OPERATOR_OVER)
        self.hit_regions=widget_render.draw(context,self.config,area.get_allocated_width(),area.get_allocated_height(),self.payload,self.error)
        if not self.region_update:self.region_update=GLib.idle_add(self.update_input_regions)
        return True

    def update_input_regions(self):
        self.region_update=0
        if not self.alive:return False
        self.footer.update(self.config)
        for kind,button in self.hit_buttons.items():
            if self.resize_active or self.footer.active:button.hide();continue
            region=self.hit_regions.get(kind)
            if not region:button.hide();continue
            _,y,_,height=region
            top=max(0,round(y));height=max(1,round(height))
            if button.get_margin_top()!=top:button.set_margin_top(top)
            if button.get_size_request().height!=height:button.set_size_request(-1,height)
            button.show()
            if self.x11:
                event_window=button.get_event_window()
                if event_window is not None and not event_window.has_native():event_window.ensure_native()
        return False

    def pointer_background(self,widget,event):
        if event.button==3 or (event.button==1 and event.state&(Gdk.ModifierType.SUPER_MASK|Gdk.ModifierType.MOD4_MASK)):
            return self.pressed(widget,event)
        return False

    def button_clicked(self,button,kind):
        self.input_counts['press']+=1;self.last_hit=kind
        if kind=='weather':self.open_forecast()
        else:widget_control.open_workspace()

    def tick_clock(self):
        if not self.alive:return False
        self.clock_ticks+=1;self.last_clock_tick=time.time()
        self.area.queue_draw()
        if time.monotonic()-self.last_draw_monotonic>3 and self.get_mapped():
            # After suspend/compositor changes, queue_draw may leave a stale frame
            # although GLib timers still run. Invalidate the native window too.
            window=self.get_window()
            if window:
                self.redraw_recoveries+=1
                window.invalidate_rect(None,True)
                window.process_updates(True)
                clock=self.get_frame_clock()
                if clock:clock.request_phase(Gdk.FrameClockPhase.UPDATE|Gdk.FrameClockPhase.PAINT)
                self.get_display().flush()
            if time.monotonic()-self.last_draw_monotonic>5 and time.monotonic()-self.last_remap_monotonic>10:
                # Recreate the compositor mapping only if invalidation did not
                # recover painting; do not activate or resize the window.
                self.last_remap_monotonic=time.monotonic()
                self.hide();self.show()
        return True

    def poll(self):
        if not self.alive:return False
        try:
            config=model.read()
            if not config['enabled']:self.destroy();return False
            if self.resize_frame is None and config!=self.config:self.apply(config)
        except (ValueError,OSError):pass  # Preserve the last valid view during an interrupted write.
        try:self.refresh_weather()
        except Exception:
            import traceback
            traceback.print_exc()
        return True

    def identity(self):
        location=self.config['location']
        return location['latitude'],location['longitude'],location['name'],self.config['unit']

    def refresh_weather(self,force=False):
        if not self.alive or (not self.config['show_weather'] and self.forecast_window is None) or self.busy:return False
        identity=self.identity()
        if not force and identity==self.weather_identity and time.monotonic()-self.last_fetch<self.config['refresh_minutes']*60:return False
        # Never display weather for the previous city/unit while a new request is pending.
        if identity!=self.weather_identity:self.payload=None;self.error=False
        self.weather_identity=identity;self.last_fetch=time.monotonic();self.busy=True
        self.update_forecast()
        selected={key:self.config['location'][key] for key in ('latitude','longitude','name')};unit=self.config['unit']
        def work():
            try:return weather_backend.forecast(selected,unit,refresh=force,allow_stale=True),None
            except Exception:return None,True
        future=self.executor.submit(work)
        def done(future):
            try:payload,error=future.result()
            except Exception:payload,error=None,True
            GLib.idle_add(self.deliver,identity,payload,error)
        future.add_done_callback(done)
        return False

    def deliver(self,identity,payload,error):
        if not self.alive:return False
        self.busy=False
        if identity==self.identity():
            self.payload=payload;self.error=bool(error);self.area.queue_draw()
            self.area.set_tooltip_text(ui.tr('workspace.widget.interaction_help')+'\nOpen-Meteo · CC BY 4.0 · GeoNames')
            self.update_forecast()
        return False

    def pressed(self,window,event):
        self.input_counts['press']+=1
        if event.button==3:self.menu(event);return True
        if event.button!=1:return False
        self.pending_click=None
        if event.state&(Gdk.ModifierType.SUPER_MASK|Gdk.ModifierType.MOD4_MASK):
            if not self.config['locked']:
                self.begin_move_drag(event.button,int(event.x_root),int(event.y_root),event.time)
            return True
        if event.type==Gdk.EventType.BUTTON_PRESS:
            self.area.grab_focus()
            kind=model.hit_region(self.hit_regions,event.x,event.y);self.last_hit=kind
            # Act while the originating user event is current, preserving desktop activation.
            if kind in ('clock','date'):widget_control.open_workspace()
            elif kind=='weather':self.open_forecast()
        return True

    def released(self,window,event):
        self.input_counts['release']+=1
        self.pending_click=None
        return event.button==1

    def key_pressed(self,window,event):
        if self.resize_active and event.keyval in (Gdk.KEY_Escape,Gdk.KEY_Return,Gdk.KEY_KP_Enter):
            self.finish_resize(True);return True
        if event.state&Gdk.ModifierType.CONTROL_MASK and Gdk.keyval_to_lower(event.keyval)==Gdk.KEY_t:
            self.hotkey(getattr(event,'time',None));return True
        return False

    def key_released(self,window,event):
        if Gdk.keyval_to_lower(event.keyval)==Gdk.KEY_t:self.hotkey_released()
        return False

    def hotkey_released(self):self.hotkey_down=False

    def hotkey(self,timestamp=None):
        if self.hotkey_down:return
        self.hotkey_down=True;self.input_counts['hotkey']+=1
        if self.resize_frame is not None:self.finish_resize(True)
        else:self.open_resize(timestamp)

    def open_forecast(self):
        if self.forecast_window is None:
            from widget_forecast import ForecastWindow
            self.forecast_window=ForecastWindow(self,lambda:self.refresh_weather(True))
            self.forecast_window.connect('destroy',self.forecast_closed)
        self.refresh_weather();self.update_forecast()
        self.forecast_window.show_all();self.forecast_window.present_with_time(Gtk.get_current_event_time())

    def forecast_closed(self,*_):self.forecast_window=None

    def update_forecast(self):
        if self.forecast_window is not None:
            self.forecast_window.update(self.config,self.payload,self.busy,self.error)

    def open_resize(self,timestamp=None):
        if self.resize_frame is not None:self.finish_resize(True);return
        from copy import deepcopy
        from widget_resize import ResizeFrame
        if self.position_timer:GLib.source_remove(self.position_timer);self.position_timer=0
        self.resize_original=deepcopy(self.config)
        if self.x11:
            x,y=self.get_position();self.resize_original.update(x=x,y=y)
        self.resize_draft=deepcopy(self.resize_original);self.resize_active=True
        for button in self.hit_buttons.values():button.hide()
        self.resize_frame=ResizeFrame(self);self.overlay.add_overlay(self.resize_frame)
        self.overlay.set_overlay_pass_through(self.resize_frame,False)
        self.resize_frame.show_all()
        self.present_with_time(timestamp or Gtk.get_current_event_time())

    def finish_resize(self,accepted=True):
        from copy import deepcopy
        if self.resize_frame is None:return
        chosen=deepcopy(self.resize_draft if accepted else self.resize_original)
        if accepted:
            try:
                current=model.read()
                for key in ('scale','x','y'):current[key]=chosen[key]
                ui_state.set(model.KEY,model.validate(current));chosen=current
            except (OSError,ValueError) as error:
                self.resize_frame.hint.set_text(ui.error_message(error));return
        frame=self.resize_frame
        self.resize_frame=None;self.resize_active=False;self.resize_draft=None;self.resize_original=None
        frame.destroy();self.apply(chosen);self.update_input_regions()

    def configured(self,*_):
        if self.x11 and not self.applying and self.resize_frame is None and not (self.shortcuts and self.shortcuts.drag):
            if self.position_timer:GLib.source_remove(self.position_timer)
            self.position_timer=GLib.timeout_add(400,self.persist_position)
        return False

    def persist_position(self):
        self.position_timer=0
        if not self.alive or self.resize_frame is not None:return False
        x,y=self.get_position()
        try:
            current=model.read()
            if (current['x'],current['y'])!=(x,y):
                current.update(x=x,y=y);ui_state.set(model.KEY,model.validate(current));self.config=current
        except (ValueError,OSError):pass
        return False

    def menu(self,event):
        menu=Gtk.Menu()
        actions=[('open',lambda:widget_control.open_workspace()),('customize',lambda:widget_control.open_workspace(True)),
                 ('forecast',self.open_forecast),('resize',self.open_resize),
                 ('refresh',lambda:self.refresh_weather(True)),('lock',self.toggle_lock),('remove',self.remove)]
        for key,callback in actions:
            label=ui.tr('workspace.widget.'+key)
            if key=='resize' and self.resize_active:label=ui.tr('workspace.widget.resize_finish')
            if key=='lock' and self.config['locked']:label=ui.tr('workspace.widget.unlock')
            item=Gtk.MenuItem(label=label);item.connect('activate',lambda _,fn=callback:fn());menu.append(item)
        menu.show_all();menu.popup_at_pointer(event)
        return menu

    def toggle_lock(self):
        config=model.read();config['locked']=not config['locked'];ui_state.set(model.KEY,config)

    def remove(self):
        config=model.read();config['enabled']=False;widget_control.apply(config);self.destroy()

    def closed(self,*_):self.remove();return True

    def cleanup(self,*_):
        self.alive=False
        if self.restore_timer:GLib.source_remove(self.restore_timer);self.restore_timer=0
        if self.region_update:GLib.source_remove(self.region_update);self.region_update=0
        if self.shortcuts:self.shortcuts.close();self.shortcuts=None
        if self.forecast_window:self.forecast_window.destroy();self.forecast_window=None
        if self.resize_frame:
            self.resize_frame.destroy();self.resize_frame=None
        if getattr(self,'clock_timer',0):GLib.source_remove(self.clock_timer);self.clock_timer=0
        if getattr(self,'tick',0):GLib.source_remove(self.tick);self.tick=0
        if self.position_timer:GLib.source_remove(self.position_timer);self.position_timer=0
        self.executor.shutdown(wait=False,cancel_futures=True)


class WidgetApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='io.orbitz.Workspace.DesktopWidget',flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        Gtk.Window.set_default_icon_name('io.orbitz.Workspace')
        self.connect('command-line',self.command)
        action=Gio.SimpleAction.new_stateful('widget-status',None,GLib.Variant('s','{}'))
        action.connect('activate',self.status);self.add_action(action)
        for name,method in [('show-forecast','open_forecast'),('resize-widget','open_resize')]:
            action=Gio.SimpleAction.new(name,None)
            action.connect('activate',lambda _,parameter,method=method:self.widget_action(method))
            self.add_action(action)
    def widget_action(self,method):
        for window in self.get_windows():
            if isinstance(window,DesktopWidget):getattr(window,method)();return
    def status(self,action,parameter):
        import json
        state={}
        for window in self.get_windows():
            if not isinstance(window,DesktopWidget):continue
            shortcut=window.shortcuts
            try:over=bool(shortcut and shortcut.over_widget())
            except Exception:over=False
            state=dict(backend=type(window.get_display()).__name__,counts=window.input_counts,
                clock_ticks=window.clock_ticks,last_clock_tick=window.last_clock_tick,
                draw_count=window.draw_count,draw_age_seconds=time.monotonic()-window.last_draw_monotonic,
                redraw_recoveries=window.redraw_recoveries,
                last_hit=window.last_hit,regions=window.hit_regions,
                buttons={kind:dict(visible=button.get_visible(),mapped=button.get_mapped(),
                    size=[button.get_allocated_width(),button.get_allocated_height()],
                    event_native=bool(button.get_event_window() and button.get_event_window().has_native()))
                    for kind,button in window.hit_buttons.items()},
                shortcut_alive=bool(shortcut and shortcut.alive),shortcut_grabbed=bool(shortcut and shortcut.grabbed),
                shortcut_conflict=bool(shortcut and shortcut.failed),pointer_over=over,
                forecast_open=window.forecast_window is not None,resize_open=window.resize_frame is not None)
        action.set_state(GLib.Variant('s',json.dumps(state)))
    def command(self,app,command):
        try:config=model.read()
        except (ValueError,OSError):return 1
        if not config['enabled']:return 0
        if not self.get_windows():DesktopWidget(self,config)
        return 0

if __name__=='__main__':sys.exit(WidgetApp().run(sys.argv))
