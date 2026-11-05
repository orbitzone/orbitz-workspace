"""Launch a separate desktop widget and maintain its explicitly requested autostart."""
import os
from pathlib import Path
import subprocess
import sys
import widget_model as model


def autostart_path():
    return Path(os.environ.get('XDG_CONFIG_HOME') or Path.home()/'.config')/'autostart/io.orbitz.Workspace.DesktopWidget.desktop'


def desktop_quote(value):
    return '"'+str(value).replace('\\','\\\\').replace('"','\\"').replace('`','\\`').replace('$','\\$')+'"'


def update_autostart(config):
    path=autostart_path()
    if not(config['enabled'] and config['start_at_login']):
        path.unlink(missing_ok=True);return
    path.parent.mkdir(parents=True,exist_ok=True)
    entry=Path(__file__).with_name('desktop_widget.py').resolve()
    contents='\n'.join(['[Desktop Entry]','Type=Application','Name=Orbitz Workspace Desktop Widget',
        'Exec='+desktop_quote(sys.executable)+' '+desktop_quote(entry)+' --autostart',
        'Icon=io.orbitz.Workspace','Terminal=false',''])
    # This file belongs to the current user; never create a global startup entry.
    import tempfile
    fd,temp=tempfile.mkstemp(prefix='.orbitz-widget-',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as stream:stream.write(contents)
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)


def start(config=None):
    config=config or model.read()
    if not config['enabled']:return None
    env=dict(os.environ)
    # Prefer XWayland where available: desktop positioning hints are X11 features.
    if not env.get('GDK_BACKEND') and env.get('DISPLAY'):env['GDK_BACKEND']='x11,wayland'
    logdir=Path(os.environ.get('XDG_CACHE_HOME') or Path.home()/'.cache')/'orbitz-workspace'
    logdir.mkdir(parents=True,exist_ok=True,mode=0o700)
    with (logdir/'desktop-widget.log').open('w') as log:
        os.chmod(log.name,0o600)
        return subprocess.Popen([sys.executable,str(Path(__file__).with_name('desktop_widget.py'))],
            env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)


def apply(config):
    config=model.validate(config)
    import ui_state
    ui_state.set(model.KEY,config)
    update_autostart(config)
    # An existing widget observes changes (including disabling) within one second.
    if config['enabled']:start(config)


def open_workspace(preferences=False):
    # Use the desktop launcher so the compositor receives the user activation context.
    try:
        import gi
        gi.require_version('Gtk','3.0');gi.require_version('Gdk','3.0')
        from gi.repository import Gio,Gdk,Gtk
        info=Gio.DesktopAppInfo.new('io.orbitz.Workspace.desktop')
        display=Gdk.Display.get_default()
        if info and display:
            context=display.get_app_launch_context()
            context.set_timestamp(Gtk.get_current_event_time())
            if preferences and 'Preferences' in info.list_actions():
                info.launch_action('Preferences',context);return
            if not preferences:
                info.launch([],context);return
    except Exception:pass
    arguments=[sys.executable,str(Path(__file__).with_name('calendar-app.py'))]
    if preferences:arguments.append('--preferences')
    subprocess.Popen(arguments,start_new_session=True)
