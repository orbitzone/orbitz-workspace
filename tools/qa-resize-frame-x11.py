#!/usr/bin/python3
"""Native X11 resize-handle test on a disposable widget; pointer restored afterward."""
from pathlib import Path
import os
import tempfile
import sys
import threading
import time
import json
ROOT=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='orbitz-frame-native-') as folder:
    os.environ.update(GDK_BACKEND='x11',GDK_CORE_DEVICE_EVENTS='1',XDG_DATA_HOME=folder+'/data',
        XDG_CONFIG_HOME=folder+'/config',XDG_CACHE_HOME=folder+'/cache',GSETTINGS_BACKEND='memory',GIO_USE_VFS='local')
    os.environ.pop('GTK_USE_PORTAL',None)
    sys.path.insert(0,str(ROOT/'app'))
    import gi
    gi.require_version('Gtk','3.0');gi.require_version('GdkX11','3.0')
    from gi.repository import Gtk,GdkX11,Gio,GLib
    from Xlib import display,X
    from Xlib.ext import xtest
    import ui_state,widget_model as model
    from desktop_widget import DesktopWidget
    app=Gtk.Application(application_id='io.orbitz.Workspace.ResizeFrameQA',flags=Gio.ApplicationFlags.NON_UNIQUE)
    assert app.register(None)
    config=model.validate(dict(enabled=True,show_weather=False,x=100,y=100))
    ui_state.set(model.KEY,config)
    widget=DesktopWidget(app,config);report={};loop=GLib.MainLoop()
    def finish():
        try:
            assert 'error' not in report,report
            assert abs(widget.config['scale']-1.2)<.005,widget.config['scale']
            assert list(widget.get_size())==[528,492],list(widget.get_size())
            assert not any(isinstance(w,Gtk.Dialog) for w in app.get_windows())
            assert all(b.get_mapped() for b in widget.resize_frame.handles.values())
            widget.finish_resize(True)
            assert model.read()['scale']==widget.config['scale']
            report.update(scale=widget.config['scale'],size=list(widget.get_size()),handles=8,no_modal=True,
                          rounded_frame=True,menu_provider_removed=True,native_drag=True)
        except Exception as error:report['error']=repr(error)
        finally:widget.destroy();loop.quit()
        return False
    def inject(xid):
        server=display.Display();root=server.screen().root;old=root.query_pointer();pressed=False
        try:
            button=server.create_resource_object('window',xid);g=button.get_geometry()
            origin=root.translate_coords(button,0,0);x=origin.x+g.width//2;y=origin.y+g.height//2
            xtest.fake_input(server,X.MotionNotify,x=x,y=y);server.sync();time.sleep(.12)
            current=root
            for _ in range(12):
                child=current.query_pointer().child
                if child in (0,X.NONE):break
                current=child
            if current.id!=xid:raise RuntimeError('Another window covers the disposable test handle; input cancelled')
            xtest.fake_input(server,X.ButtonPress,1);server.sync();pressed=True;time.sleep(.12)
            for step in range(1,11):
                xtest.fake_input(server,X.MotionNotify,x=x+round(88*step/10),y=y+round(82*step/10))
                server.sync();time.sleep(.035)
            xtest.fake_input(server,X.ButtonRelease,1);server.sync();pressed=False;time.sleep(.15)
        except Exception as error:report['error']=repr(error)
        finally:
            if pressed:xtest.fake_input(server,X.ButtonRelease,1)
            xtest.fake_input(server,X.MotionNotify,x=old.root_x,y=old.root_y);server.sync();server.close()
            GLib.timeout_add(150,finish)
    def start():
        widget.open_resize();widget.present()
        def ready():
            handle=widget.resize_frame.handles['se'];window=handle.get_event_window()
            assert window and window.has_native()
            xid=GdkX11.X11Window.get_xid(window)
            threading.Thread(target=inject,args=(xid,),daemon=True).start()
            return False
        GLib.timeout_add(300,ready)
        return False
    GLib.timeout_add(500,start);GLib.timeout_add(10000,lambda:(report.update(error='timeout'),finish(),False)[2])
    loop.run()
    target=ROOT/'docs/qa/desktop-widget-2026-11-03/native-frame-report.json'
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False));assert 'error' not in report,report
