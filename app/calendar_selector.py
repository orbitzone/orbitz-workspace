"""Below-field popovers; scrolling is used only when screen space runs out."""
from ui_language import ui
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,GObject,Pango

def below(button):
    popover=Gtk.Popover.new(button);popover.set_position(Gtk.PositionType.BOTTOM)
    popover.set_constrain_to(Gtk.PopoverConstraint.NONE)
    scroll=ui.widget(Gtk.ScrolledWindow,);scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC)
    scroll.set_propagate_natural_width(True);scroll.set_propagate_natural_height(True)
    scroll.set_max_content_height(480)
    rows=ui.widget(Gtk.Box,orientation=Gtk.Orientation.VERTICAL,spacing=2,margin=6);scroll.add(rows);popover.add(scroll)
    def size(*_):
        height=480
        if button.get_window():
            monitor=button.get_display().get_monitor_at_window(button.get_window())
            if monitor:
                area=monitor.get_workarea();top=button.get_toplevel();coords=button.translate_coordinates(top,0,0)
                if coords:
                    bottom=top.get_window().get_origin()[-1]+coords[-1]+button.get_allocated_height()
                    height=max(80,min(600,area.y+area.height-bottom-24))
        scroll.set_max_content_height(height)
        rows.set_size_request(max(1,button.get_allocated_width()-20),-1)
    scroll.show_all()
    popover.connect('show',size);button.set_popover(popover)
    return popover,rows

class CalendarSelector(Gtk.MenuButton):
    __gsignals__={'changed':(GObject.SignalFlags.RUN_FIRST,None,())}
    def __init__(self):
        super().__init__();self.identity=None;self.options={}
        box=ui.widget(Gtk.Box,spacing=8);self.add(box)
        self.text=ui.widget(Gtk.Label,xalign=0);self.text.set_ellipsize(Pango.EllipsizeMode.END);self.text.set_max_width_chars(28)
        box.pack_start(self.text,True,True,0)
        box.pack_end(Gtk.Image.new_from_icon_name('pan-down-symbolic',Gtk.IconSize.MENU),False,False,0)
        self.menu,self.rows=below(self)
    def append(self,identity,title):
        item=ui.widget(Gtk.Button,);item.set_relief(Gtk.ReliefStyle.NONE);row=ui.widget(Gtk.Box,spacing=8)
        check=Gtk.Image.new_from_icon_name('object-select-symbolic',Gtk.IconSize.MENU);check.set_opacity(0)
        row.pack_start(check,False,False,0)
        text=ui.widget(Gtk.Label,label=title,xalign=0);text.set_max_width_chars(48);text.set_ellipsize(Pango.EllipsizeMode.END)
        row.pack_start(text,True,True,0);item.add(row);ui.call(item, 'set_tooltip_text', title)
        def choose(*_):self.set_active_id(identity);self.menu.popdown()
        item.connect('clicked',choose);self.rows.pack_start(item,False,False,0)
        self.options[identity]=(title,check);item.show_all()
    def remove_all(self):
        for child in self.rows.get_children():child.destroy()
        self.options={};self.identity=None
    def get_active_id(self):return self.identity
    def get_active_text(self):return str(self.options.get(self.identity,('',None))[0])
    def set_active_id(self,identity):
        if identity not in self.options:return False
        changed=identity!=self.identity;self.identity=identity
        ui.call(self.text, 'set_text', self.options[identity][0]);ui.call(self, 'set_tooltip_text', self.options[identity][0])
        for key,(_,check) in self.options.items():check.set_opacity(1 if key==identity else 0)
        if changed:self.emit('changed')
        return True
