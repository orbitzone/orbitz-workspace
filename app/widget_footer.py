"""In-widget Orbitz footer with an upward, hover-accessible support panel."""
import ctypes
import ctypes.util
from pathlib import Path
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,Gdk,GLib,GdkPixbuf

GITHUB='https://github.com/orbitzone'
SITE='https://www.orbit.zone/'
_font_loaded=False


def load_brand_font():
    global _font_loaded
    if _font_loaded:return
    font=Path(__file__).with_name('fonts')/'Orbitron.ttf'
    library=ctypes.CDLL(ctypes.util.find_library('fontconfig') or 'libfontconfig.so.1')
    library.FcConfigGetCurrent.restype=ctypes.c_void_p
    library.FcConfigAppFontAddFile.argtypes=[ctypes.c_void_p,ctypes.c_char_p]
    library.FcConfigAppFontAddFile.restype=ctypes.c_int
    if not library.FcConfigAppFontAddFile(library.FcConfigGetCurrent(),bytes(font)):
        raise RuntimeError('Unable to load bundled Orbitron font')
    gi.require_version('PangoCairo','1.0')
    from gi.repository import PangoCairo
    PangoCairo.FontMap.get_default().changed()
    _font_loaded=True



class WidgetFooter(Gtk.EventBox):
    def __init__(self,owner,config=None):
        load_brand_font()
        super().__init__()
        self.owner=owner;self.close_timer=0;self.active=False
        self.set_visible_window(False)
        self.set_halign(Gtk.Align.END);self.set_valign(Gtk.Align.END)
        self.set_margin_end(20);self.set_margin_bottom(8)
        self.box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=5);self.add(self.box)
        self.panel=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=3)
        self.panel.get_style_context().add_class('orbitz-support-panel')
        self.panel.set_no_show_all(True);self.box.pack_start(self.panel,False,False,0)
        self.links=Gtk.Box(spacing=4);self.panel.pack_start(self.links,False,False,0)
        self.paypal=Gtk.Button(label='PayPal');self.paypal.set_sensitive(False)
        self.github=Gtk.Button(label='GitHub');self.links.add(self.paypal);self.links.add(self.github)
        for button,name in ((self.paypal,'paypal'),(self.github,'github')):
            pixbuf=GdkPixbuf.Pixbuf.new_from_file_at_scale(str(Path(__file__).with_name('icons')/(name+'.svg')),18,18,True)
            label=button.get_child()
            button.remove(label)
            content=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=5)
            content.set_halign(Gtk.Align.CENTER);content.set_valign(Gtk.Align.CENTER)
            image=Gtk.Image.new_from_pixbuf(pixbuf)
            image.set_halign(Gtk.Align.CENTER);image.set_valign(Gtk.Align.CENTER)
            label.set_valign(Gtk.Align.CENTER);label.set_yalign(.5)
            content.pack_start(image,False,False,0)
            content.pack_start(label,False,False,0)
            button.add(content)
        self.site=Gtk.Button();self.panel.pack_start(self.site,False,False,0)
        self.github.connect('clicked',lambda *_:self.open_uri(GITHUB))
        self.site.connect('clicked',lambda *_:self.open_uri(SITE))
        self.trigger=Gtk.Button(label='ORBITZ');self.trigger.set_halign(Gtk.Align.END)
        self.trigger.get_style_context().add_class('orbitz-brand')
        self.box.pack_end(self.trigger,False,False,0)
        for widget in (self.trigger,self.panel,self.links,self.github,self.paypal,self.site):
            widget.add_events(Gdk.EventMask.ENTER_NOTIFY_MASK|Gdk.EventMask.LEAVE_NOTIFY_MASK)
            widget.connect('enter-notify-event',self.entered)
            widget.connect('leave-notify-event',self.left)
        for button in (self.trigger,self.github,self.site):button.connect('map',self.native_button)
        self.owner.connect('key-press-event',self.key)
        self.css=Gtk.CssProvider()
        for widget in (self,self.box,self.panel,self.links,self.paypal,self.github,self.site,self.trigger):
            widget.get_style_context().add_provider(self.css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.connect('destroy',self.cleanup)
        self.update(config if config is not None else owner.config)

    def native_button(self,button):
        if getattr(self.owner,'x11','X11' in type(self.owner.get_display()).__name__):
            window=button.get_event_window()
            if window:window.ensure_native();window.raise_()

    def update(self,config):
        signature=tuple(config[key] for key in ('theme','scale','width','language'))+(getattr(self.owner,'resize_active',False),)
        if getattr(self,'style_signature',None)==signature:return
        self.style_signature=signature
        light=config['theme']=='light'
        fg,bg,edge,hover=('#161616','#e6e6e6','#aaaaaa','#d4d4d4') if light else ('#eaf5ff','#222222','#484848','#363636')
        size=max(8,min(14,round(9*config['scale'])))
        self.css.load_from_data(('''
        .orbitz-brand, .orbitz-brand:hover, .orbitz-brand:active {background:transparent; border:0; box-shadow:none; padding:0; min-height:0; min-width:0; color:%s; font-family:Orbitron,Sans; font-weight:bold; font-size:%dpx;}
        .orbitz-support-panel {background:%s; color:%s; border:1px solid %s; border-radius:10px; padding:6px;}
        .orbitz-support-panel button {background:transparent; color:%s; border:0; box-shadow:none; padding:7px; min-width:0; min-height:0; font-size:%dpx;}
        .orbitz-support-panel button:hover {background:%s;}
        .orbitz-support-panel button:disabled {color:#8795a2; opacity:1;}
        .orbitz-support-panel image, .orbitz-support-panel image:disabled {opacity:1; -gtk-icon-effect:none;}
        '''%(fg,size,bg,fg,edge,fg,size,hover)).encode())
        self.links.set_orientation(Gtk.Orientation.HORIZONTAL if config['width']*config['scale']>=260 else Gtk.Orientation.VERTICAL)
        en=config['language']=='en-US'
        self.paypal.set_tooltip_text('PayPal link coming soon' if en else 'Link do PayPal em breve')
        self.github.set_tooltip_text('Follow us on GitHub' if en else 'Siga-nos no GitHub')
        self.site.set_label('Visit orbit.zone' if en else 'Visite orbit.zone')
        self.trigger.get_accessible().set_name('ORBITZ · links')
        if getattr(self.owner,'resize_active',False):
            self.cancel_close();self.active=False;self.panel.hide();self.hide()
        else:self.show()

    def cancel_close(self):
        if self.close_timer:GLib.source_remove(self.close_timer);self.close_timer=0

    def pointer_inside(self):
        # Query physical coordinates: child/native icon windows emit crossing events
        # even when the pointer is still inside the visible panel.
        if not self.get_mapped():return False
        pointer=self.get_display().get_default_seat().get_pointer()
        _,px,py=pointer.get_position()
        origin=self.owner.get_window().get_origin()
        position=self.translate_coordinates(self.owner,0,0)
        if position is None:return False
        x,y=position;allocation=self.get_allocation()
        x+=origin[-2];y+=origin[-1]
        return x<=px<x+allocation.width and y<=py<y+allocation.height

    def watch_pointer(self):
        if not self.active:self.close_timer=0;return False
        if self.pointer_inside():self.outside_since=None;return True
        now=GLib.get_monotonic_time()
        if self.outside_since is None:self.outside_since=now;return True
        if now-self.outside_since<250000:return True
        self.close_timer=0;self.conceal();return False

    def ensure_pointer_watch(self):
        if self.active and not self.close_timer:
            self.close_timer=GLib.timeout_add(100,self.watch_pointer)

    def entered(self,*_):
        self.outside_since=None
        if _ and _[0] is self.trigger:self.reveal()
        self.ensure_pointer_watch();return False

    def left(self,*_):
        self.ensure_pointer_watch();return False

    def reveal(self):
        if getattr(self.owner,'resize_active',False):return
        self.active=True;self.outside_since=None
        self.panel.set_no_show_all(False);self.panel.show_all();self.panel.set_no_show_all(True)
        getattr(self.owner,'update_input_regions',lambda:None)()
        self.ensure_pointer_watch()

    def conceal(self):
        self.cancel_close();self.active=False;self.panel.hide()
        if getattr(self.owner,'alive',True):getattr(self.owner,'update_input_regions',lambda:None)()
        return False

    def key(self,widget,event):
        if event.keyval==Gdk.KEY_Escape and self.active:
            self.conceal();return True
        return False

    def open_uri(self,uri):
        Gtk.show_uri_on_window(self.owner,uri,Gtk.get_current_event_time());self.conceal()

    def cleanup(self,*_):self.cancel_close()


class WorkspaceFooter(WidgetFooter):
    """The same footer in the main window, independent of desktop-widget settings."""
    def __init__(self,owner):
        super().__init__(owner,self.workspace_config())
        self.set_margin_end(20);self.set_margin_bottom(20)
        self.settings=Gtk.Settings.get_default()
        for key in ('gtk-theme-name','gtk-application-prefer-dark-theme'):
            self.settings.connect('notify::'+key,self.theme_updated)
        self.connect('destroy',self.disconnect_settings)

    def workspace_config(self):
        from ui_language import ui
        settings=Gtk.Settings.get_default()
        name=(settings.get_property('gtk-theme-name') or '').lower()
        dark=settings.get_property('gtk-application-prefer-dark-theme') or 'dark' in name
        return dict(theme='dark' if dark else 'light',scale=1,language=ui.get_locale(),width=700)

    def theme_updated(self,*_):self.update(self.workspace_config())

    def reveal(self):
        self.update(self.workspace_config())
        super().reveal()

    def disconnect_settings(self,*_):
        self.settings.disconnect_by_func(self.theme_updated)
