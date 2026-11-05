"""Rounded in-place transform frame with eight native GTK resize handles."""
from copy import deepcopy
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,Gdk,GLib
from ui_language import ui
import widget_model as model
from widget_render import rounded


class ResizeFrame(Gtk.Fixed):
    HANDLE=18
    def __init__(self,owner):
        super().__init__();self.owner=owner;self.drag=None;self.device=None;self.native_idle=0;self.alive=True
        self.set_halign(Gtk.Align.FILL);self.set_valign(Gtk.Align.FILL)
        self.width,self.height=model.pixel_size(owner.config)
        self.canvas=Gtk.DrawingArea();self.canvas.connect('draw',self.paint);self.put(self.canvas,0,0)
        css=Gtk.CssProvider();css.load_from_data(b'''
.orbitz-resize-shield, .orbitz-resize-shield:hover, .orbitz-resize-shield:active, .orbitz-resize-shield:focus {background:transparent; border:0; box-shadow:none; padding:0; outline:0; min-width:0; min-height:0;}
.orbitz-resize-handle, .orbitz-resize-handle:hover, .orbitz-resize-handle:active {background:#477b9d; border:2px solid #dceeff; border-radius:5px; padding:0; min-width:0; min-height:0; box-shadow:none;}
.orbitz-resize-tip {background:rgba(16,23,32,.92); color:#eaf3ff; padding:7px 10px; border-radius:10px; font-size:11px;}
.orbitz-resize-done {background:#152638; color:#eaf3ff; border:1px solid #83cfff; border-radius:7px; padding:4px 12px;}
''')
        def style(widget,name):
            widget.get_style_context().add_class(name)
            widget.get_style_context().add_provider(css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.shield=Gtk.Button();style(self.shield,'orbitz-resize-shield')
        self.shield.connect('button-press-event',self.background);self.put(self.shield,0,0)
        self.hint=Gtk.Label(justify=Gtk.Justification.CENTER,wrap=True)
        self.hint.set_width_chars(1);self.hint.set_max_width_chars(40);style(self.hint,'orbitz-resize-tip');self.put(self.hint,24,24)
        self.done=Gtk.Button();ui.set(self.done,'label',ui.msg('workspace.widget.resize_done'));style(self.done,'orbitz-resize-done')
        self.done.connect('clicked',lambda *_:owner.finish_resize(True));self.put(self.done,0,0)
        self.handles={}
        self.cursors={'nw':'nwse-resize','se':'nwse-resize','ne':'nesw-resize','sw':'nesw-resize',
                      'n':'ns-resize','s':'ns-resize','e':'ew-resize','w':'ew-resize'}
        for edge in ('nw','n','ne','e','se','s','sw','w'):
            handle=Gtk.Button();handle.set_size_request(self.HANDLE,self.HANDLE);style(handle,'orbitz-resize-handle')
            handle.add_events(Gdk.EventMask.POINTER_MOTION_MASK|Gdk.EventMask.BUTTON_PRESS_MASK|Gdk.EventMask.BUTTON_RELEASE_MASK)
            handle.connect('button-press-event',self.start_drag,edge)
            handle.connect('motion-notify-event',self.motion)
            handle.connect('button-release-event',self.release)
            handle.get_accessible().set_name(ui.tr('workspace.widget.resize_handle',edge=edge))
            self.handles[edge]=handle;self.put(handle,0,0)
        self.connect('map',self.mapped);self.connect('destroy',self.cleanup)
        self.set_geometry(self.width,self.height)

    def set_geometry(self,width,height):
        self.width,self.height=width,height
        self.set_size_request(width,height);self.canvas.set_size_request(width,height);self.shield.set_size_request(width,height)
        size=self.HANDLE
        positions={'nw':(0,0),'n':((width-size)/2,0),'ne':(width-size,0),'e':(width-size,(height-size)/2),
                   'se':(width-size,height-size),'s':((width-size)/2,height-size),'sw':(0,height-size),'w':(0,(height-size)/2)}
        for edge,(x,y) in positions.items():self.move(self.handles[edge],round(x),round(y))
        hint_width=max(60,min(320,width-54));self.hint.set_size_request(hint_width,-1)
        self.hint.set_text(ui.tr('workspace.widget.resize_frame_hint'))
        self.move(self.hint,round((width-hint_width)/2),24 if height>180 else 16)
        self.done.set_size_request(80,30);self.move(self.done,max(0,round((width-80)/2)),max(48,height-58))
        self.canvas.queue_draw()

    def paint(self,widget,context):
        context.save()
        radius=max(12,min(44,self.owner.config['radius']*self.owner.config['scale']))
        rounded(context,8,8,max(1,self.width-16),max(1,self.height-16),radius)
        context.set_source_rgba(.51,.81,1,1);context.set_line_width(2);context.set_dash([6,4]);context.stroke();context.restore()
        return True

    def background(self,button,event):
        if event.button==3:self.owner.menu(event)
        self.shield.grab_focus();return True

    def mapped(self,*_):
        if not self.native_idle:self.native_idle=GLib.idle_add(self.prepare_input)

    def prepare_input(self):
        self.native_idle=0
        if not self.alive:return False
        for button in (self.shield,*self.handles.values(),self.done):
            window=button.get_event_window()
            if window is not None and self.owner.x11:
                if not window.has_native():window.ensure_native()
                window.raise_()
        for edge,button in self.handles.items():
            window=button.get_event_window()
            if window:window.set_cursor(Gdk.Cursor.new_from_name(self.get_display(),self.cursors[edge]))
        self.done.grab_focus()
        return False

    def start_drag(self,button,event,edge):
        if event.button!=1:return True
        origin=self.owner.get_position() if self.owner.x11 else (self.owner.config['x'],self.owner.config['y'])
        self.drag=dict(config=deepcopy(self.owner.config),edge=edge,x=event.x_root,y=event.y_root,origin=origin)
        self.device=event.get_device() if hasattr(event,'get_device') else None
        if self.device:
            window=button.get_event_window()
            self.device.grab(window,Gdk.GrabOwnership.APPLICATION,False,
                Gdk.EventMask.POINTER_MOTION_MASK|Gdk.EventMask.BUTTON_RELEASE_MASK,
                Gdk.Cursor.new_from_name(self.get_display(),self.cursors[edge]),event.time)
        button.grab_add()
        return True

    def drag_to(self,x,y):
        if self.drag is None:return
        state=self.drag
        config=model.resize_from_handle(state['config'],state['edge'],x-state['x'],y-state['y'],state['origin'])
        self.owner.resize_draft=config;self.owner.apply(config)

    def motion(self,button,event):
        if self.drag:self.drag_to(event.x_root,event.y_root)
        return True

    def release(self,button,event):
        if event.button==1 and self.drag:
            self.drag_to(event.x_root,event.y_root);self.end_drag(event.time)
        return True

    def end_drag(self,time=Gdk.CURRENT_TIME):
        if self.device:
            self.device.ungrab(time);self.device=None
        grab=Gtk.grab_get_current()
        if grab in self.handles.values():grab.grab_remove()
        self.drag=None

    def cleanup(self,*_):
        self.alive=False;self.end_drag()
        if self.native_idle:GLib.source_remove(self.native_idle);self.native_idle=0
