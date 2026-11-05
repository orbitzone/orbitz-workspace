#!/usr/bin/python3
"""Short native X11/XWayland smoke test using temporary settings and no network."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='orbitz-widget-x11-') as folder:
    os.environ.update(GDK_BACKEND='x11',GDK_CORE_DEVICE_EVENTS='1',XDG_DATA_HOME=folder+'/data',XDG_CONFIG_HOME=folder+'/config',XDG_CACHE_HOME=folder+'/cache',GSETTINGS_BACKEND='memory',GIO_USE_VFS='local')
    os.environ.pop('GTK_USE_PORTAL',None)
    sys.path.insert(0,str(ROOT/'app'))
    import json
    import gi
    gi.require_version('Gtk','3.0');gi.require_version('GdkX11','3.0')
    from gi.repository import Gtk,Gdk,GdkX11,Gio,GLib
    import ui_state,widget_model as model
    from desktop_widget import DesktopWidget
    application=Gtk.Application(application_id='io.orbitz.Workspace.WidgetX11QA',flags=Gio.ApplicationFlags.NON_UNIQUE)
    assert application.register(None)
    config=model.validate(dict(enabled=True,show_weather=False,x=100,y=100))
    ui_state.set(model.KEY,config)
    window=DesktopWidget(application,config)
    result={}
    def verify():
        try:
            native=window.get_window();xid=GdkX11.X11Window.get_xid(native)
            props=subprocess.check_output(['xprop','-id',str(xid),'_NET_WM_WINDOW_TYPE','_NET_WM_STATE'],text=True)
            assert window.x11 and '_NET_WM_WINDOW_TYPE_NORMAL' in props
            assert '_NET_WM_STATE_BELOW' not in props
            assert all(button.get_mapped() and button.get_event_window().has_native() for button in window.hit_buttons.values() if button.get_visible())
            position=list(window.get_position())
            assert position==[config['x'],config['y']],position
            window.persist_position()
            saved=model.read();assert [saved['x'],saved['y']]==position
            assert window.shortcuts and window.shortcuts.alive,'X11 shortcut monitor did not start'
            result.update(backend=type(window.get_display()).__name__,position=position,properties=props,hover_shortcuts=True,
                          standalone=True,no_network=True)
        except Exception as error:result['error']=repr(error)
        finally:window.destroy();loop.quit()
        return False
    loop=GLib.MainLoop();GLib.timeout_add(1000,verify);loop.run()
    target=ROOT/'docs/qa/desktop-widget-2026-11-03/x11-report.json'
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False))
    assert 'error' not in result,result
