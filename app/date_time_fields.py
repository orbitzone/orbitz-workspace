"""Shared calendar dialogs and separate hour/minute selectors for editable fields."""
from datetime import date
import re
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,Gdk,GLib,GObject
from ui_language import ui


def tr(key):return ui.tr('workspace.picker.'+key)


def attach_date_picker(entry):
    entry.set_icon_from_icon_name(Gtk.EntryIconPosition.SECONDARY,'x-office-calendar-symbolic')
    entry.set_icon_tooltip_text(Gtk.EntryIconPosition.SECONDARY,tr('date'))
    pending=[False]
    def show():
        try:
            parent=entry.get_toplevel()
            if not isinstance(parent,Gtk.Window):return False
            dialog=Gtk.Dialog(title=tr('date'),transient_for=parent,modal=True,destroy_with_parent=True)
            dialog.add_buttons(tr('cancel'),Gtk.ResponseType.CANCEL,tr('select'),Gtk.ResponseType.OK)
            calendar=Gtk.Calendar();calendar.set_margin_top(16);calendar.set_margin_bottom(16)
            calendar.set_margin_start(16);calendar.set_margin_end(16)
            try:chosen=date.fromisoformat(entry.get_text().strip())
            except ValueError:chosen=date.today()
            calendar.select_month(chosen.month-1,chosen.year);calendar.select_day(chosen.day)
            dialog.get_content_area().add(calendar)
            calendar.connect('day-selected-double-click',lambda *_:dialog.response(Gtk.ResponseType.OK))
            dialog.show_all()
            try:
                if dialog.run()==Gtk.ResponseType.OK:
                    year,month,day=calendar.get_date()
                    entry.set_text(date(year,month+1,day).isoformat())
            finally:dialog.destroy()
        finally:pending[0]=False
        return False
    def request():
        if not pending[0] and entry.get_sensitive() and entry.get_editable():
            pending[0]=True;GLib.idle_add(show)
    def pressed(_,event):
        if event.button==1:request();return True
        return False
    def key(_,event):
        if event.keyval==Gdk.KEY_Down and event.state&Gdk.ModifierType.MOD1_MASK:
            request();return True
        return False
    entry.connect('button-press-event',pressed)
    entry.connect('icon-press',lambda *_:request())
    entry.connect('key-press-event',key)
    return entry


class CompactTimeChoice(Gtk.MenuButton):
    """A bounded popover, avoiding GTK's screen-height ComboBox menu."""
    __gsignals__={'changed':(GObject.SignalFlags.RUN_LAST,None,())}

    def __init__(self):
        super().__init__()
        self.values=[];self.active=None
        content=Gtk.Box(spacing=6)
        self.caption=Gtk.Label(label='—');content.add(self.caption)
        content.add(Gtk.Image.new_from_icon_name('pan-down-symbolic',Gtk.IconSize.MENU))
        self.add(content);content.show_all()
        self.popup=Gtk.Popover.new(self)
        scroll=Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC)
        scroll.set_min_content_height(220);scroll.set_max_content_height(220)
        scroll.set_propagate_natural_height(True)
        scroll.set_min_content_width(64)
        self.list=Gtk.ListBox();self.list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.list.set_activate_on_single_click(True)
        self.list.connect('row-activated',self.choose)
        scroll.add(self.list);self.popup.add(scroll)
        self.set_popover(self.popup)
        self.popup.connect('show',self.opened)
        self.connect('destroy',self.cleanup)
        self.focus_source=0

    def append(self,key,label):
        self.values.append((key,label))
        row=Gtk.ListBoxRow();text=Gtk.Label(label=label,margin=6)
        row.add(text);self.list.add(row);row.show_all()

    def get_model(self):return self.values
    def get_active_id(self):return self.active

    def set_active_id(self,key):
        for index,(value,label) in enumerate(self.values):
            if value==key:
                changed=self.active!=key;self.active=key;self.caption.set_text(label)
                self.list.select_row(self.list.get_row_at_index(index))
                if changed:self.emit('changed')
                return True
        return False

    def choose(self,_,row):
        self.set_active_id(self.values[row.get_index()][0]);self.popup.popdown();self.grab_focus()

    def opened(self,*_):
        self.popup.get_child().show_all()
        if self.focus_source:GLib.source_remove(self.focus_source)
        self.focus_source=GLib.idle_add(self.focus_selected)

    def focus_selected(self):
        self.focus_source=0
        row=self.list.get_selected_row()
        if row:row.grab_focus()
        return False

    def cleanup(self,*_):
        if self.focus_source:GLib.source_remove(self.focus_source);self.focus_source=0


class TimeField(Gtk.Box):
    __gsignals__={'changed':(GObject.SignalFlags.RUN_LAST,None,()),'activate':(GObject.SignalFlags.RUN_LAST,None,())}

    def __init__(self,text='',allow_end_of_day=False):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL,spacing=5)
        self.loading=False;self.raw='';self.default_activate=False;self.allow_end_of_day=allow_end_of_day
        self.hour=CompactTimeChoice();self.minute=CompactTimeChoice()
        for combo,count,name in ((self.hour,25 if allow_end_of_day else 24,'hour'),(self.minute,60,'minute')):
            combo.append('','—')
            for value in range(count):combo.append(f'{value:02}',f'{value:02}')
            combo.get_accessible().set_name(tr(name))
            combo.set_tooltip_text(tr(name));combo.connect('changed',self.selected)
            combo.connect('key-press-event',self.key)
        self.pack_start(self.hour,False,False,0)
        self.pack_start(Gtk.Label(label=':'),False,False,0)
        self.pack_start(self.minute,False,False,0)
        self.set_text(text)

    def selected(self,*_):
        if self.loading:return
        self.loading=True
        hour=self.hour.get_active_id() or '';minute=self.minute.get_active_id() or ''
        if hour=='24':minute='00';self.minute.set_active_id('00')
        self.minute.set_sensitive(hour!='24')
        self.raw='' if not hour and not minute else f'{hour}:{minute}'
        self.loading=False;self.emit('changed')

    def set_text(self,text):
        text=str(text);self.loading=True
        valid=re.fullmatch(r'(\d{2}):(\d{2})',text)
        hour,minute=valid.groups() if valid else ('','')
        self.hour.set_active_id(hour if hour and int(hour)<(25 if self.allow_end_of_day else 24) else '')
        self.minute.set_active_id(minute if minute and int(minute)<60 else '')
        self.minute.set_sensitive(hour!='24')
        self.raw=text;self.loading=False;self.emit('changed')

    def get_text(self):return self.raw
    def set_max_length(self,*_):pass
    def set_width_chars(self,*_):pass
    def set_activates_default(self,value):self.default_activate=value
    def grab_focus(self):return self.hour.grab_focus()

    def key(self,widget,event):
        if event.keyval in (Gdk.KEY_Return,Gdk.KEY_KP_Enter) and not widget.popup.get_visible():
            self.emit('activate')
            if self.default_activate:self.get_toplevel().activate_default()
            return True
        return False
