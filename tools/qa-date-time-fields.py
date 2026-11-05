import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from date_time_fields import TimeField,attach_date_picker
from gi.repository import Gtk,Gdk,GLib
from unittest.mock import patch
window=Gtk.Window();box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL);window.add(box)
entry=attach_date_picker(Gtk.Entry(text='2026-11-03'));box.add(entry)
field=TimeField();box.add(field);window.show_all()
assert len(field.hour.get_model())==25 and len(field.minute.get_model())==61
assert field.get_text()==''
field.hour.set_active_id('09');field.minute.set_active_id('07');assert field.get_text()=='09:07'
field.set_text('23:59');assert field.hour.get_active_id()=='23' and field.minute.get_active_id()=='59'
end=TimeField(allow_end_of_day=True);end.hour.set_active_id('24');assert end.get_text()=='24:00' and not end.minute.get_sensitive()
end.hour.set_active_id('23');assert end.minute.get_sensitive()
changes=[];field.connect('changed',lambda *_:changes.append(field.get_text()));field.set_text('');assert changes==['']
field.set_text('bad draft');assert field.get_text()=='bad draft'
def pump():
 while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
def choose(dialog):
 cal=dialog.get_content_area().get_children()[0]
 assert isinstance(cal,Gtk.Calendar)
 cal.select_month(1,2028);cal.select_day(29)
 return Gtk.ResponseType.OK
with patch.object(Gtk.Dialog,'run',choose):
 entry.emit('icon-press',Gtk.EntryIconPosition.SECONDARY,None)
 pump()
assert entry.get_text()=='2028-02-29'
with patch.object(Gtk.Dialog,'run',return_value=Gtk.ResponseType.CANCEL):
 entry.emit('icon-press',Gtk.EntryIconPosition.SECONDARY,None);pump()
assert entry.get_text()=='2028-02-29'
field.set_text('12:59')
field.minute.set_active(True)
import time
for _ in range(12):pump();time.sleep(.02)
assert field.minute.popup.get_mapped()
assert field.minute.list.get_mapped()
assert field.minute.list.get_row_at_index(1).get_child().get_mapped()
assert 180<=field.minute.popup.get_allocated_height()<=260,field.minute.popup.get_allocated_height()
assert field.minute.list.get_selected_row().get_index()==60
field.minute.list.emit('row-activated',field.minute.list.get_row_at_index(1))
assert field.get_text()=='12:00'
window.destroy();end.destroy()
print('PASS: calendário, ano bissexto, cancelar, horas/minutos, 24:00 e rascunhos.')
