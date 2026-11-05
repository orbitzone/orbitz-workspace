"""X11/XWayland hover-scoped Ctrl+T and Super-drag; never grab other app shortcuts globally."""
from gi.repository import GLib


class HoverShortcuts:
    def __init__(self,window,activate,released):
        from Xlib import X,XK,display
        self.X=X;self.window=window;self.activate=activate;self.released=released
        self.display=display.Display();self.root=self.display.screen().root
        self.keycode=self.display.keysym_to_keycode(XK.string_to_keysym('t'))
        self.grabbed=False;self.key_held=False;self.drag=None;self.alive=True;self.failed=False
        self.modifiers=[X.ControlMask|extra for extra in (0,X.LockMask,X.Mod2Mask,X.LockMask|X.Mod2Mask)]
        self.timer=GLib.timeout_add(35,self.poll)
        self.watch=GLib.io_add_watch(self.display.fileno(),GLib.IO_IN|GLib.IO_HUP|GLib.IO_ERR,self.events)

    def over_widget(self):
        device=self.window.get_display().get_default_seat().get_pointer()
        target,_,_=device.get_window_at_position()
        return bool(target and target.get_toplevel()==self.window.get_window())

    def grab(self,active):
        if active==self.grabbed or (active and self.failed):return
        if active:
            def denied(*_):self.failed=True
            for modifiers in self.modifiers:
                self.root.grab_key(self.keycode,modifiers,False,self.X.GrabModeAsync,self.X.GrabModeAsync,onerror=denied)
            self.display.sync();self.grabbed=True
            if self.failed:self.grab(False)
        else:
            for modifiers in self.modifiers:self.root.ungrab_key(self.keycode,modifiers)
            self.display.flush();self.grabbed=False

    def poll(self):
        if not self.alive:return False
        try:
            pointer=self.root.query_pointer();down=bool(pointer.mask&self.X.Button1Mask)
            over=self.over_widget()
            if self.drag:
                px,py,wx,wy=self.drag
                self.window.move(wx+pointer.root_x-px,wy+pointer.root_y-py)
                if not down:
                    self.drag=None;self.window.persist_position()
            elif over and down and pointer.mask&self.X.Mod4Mask and not self.window.config['locked'] and not getattr(self.window,'resize_active',False):
                wx,wy=self.window.get_position();self.drag=(pointer.root_x,pointer.root_y,wx,wy)
            self.grab(over and not self.drag)
            self.events(None,GLib.IO_IN)
            if self.key_held:
                keys=self.display.query_keymap()
                if not keys[self.keycode//8]&(1<<(self.keycode%8)):
                    self.key_held=False;self.released()
        except Exception:self.close();return False
        return True

    def events(self,source,condition):
        if condition&(GLib.IO_HUP|GLib.IO_ERR):self.close();return False
        try:
            while self.display.pending_events():
                event=self.display.next_event()
                if event.type==self.X.KeyPress and event.detail==self.keycode and not self.key_held:
                    self.key_held=True;self.activate(getattr(event,'time',None))
        except Exception:self.close();return False
        return self.alive

    def close(self):
        if not self.alive:return
        self.alive=False
        try:self.grab(False);self.display.close()
        except Exception:pass
        if self.timer:GLib.source_remove(self.timer);self.timer=0
        if self.watch:GLib.source_remove(self.watch);self.watch=0
