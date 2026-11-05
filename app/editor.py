#!/usr/bin/python3
"""Multiline editor isolated from GNOME Shell; shared locked planner storage."""
from ui_language import ui
import sys
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gio, GLib, Gdk
import store

COLORS = [(ui.msg('workspace.dialogs.editor.yellow'),'#ffe293'), (ui.msg('workspace.dialogs.editor.pink'),'#ffd6df'), (ui.msg('workspace.dialogs.editor.green'),'#d9edb5'),
          (ui.msg('workspace.dialogs.editor.blue'),'#cce7ff'), (ui.msg('workspace.dialogs.editor.purple'),'#e5d7fa'), (ui.msg('workspace.dialogs.editor.peach'),'#ffdbb5')]

class NoteWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title=ui.tr('workspace.editor.notas_rapidas_orbitz'))
        ui.set(self,'title',ui.msg('workspace.editor.notas_rapidas_orbitz'))
        self.set_default_size(530, 480)
        self.set_size_request(350, 300)
        self.timer=0; self.dirty=False; self.loading=False; self.read_error=False
        self.history=[]; self.position=0; self.history_timer=0
        box=ui.widget(Gtk.Box,orientation=Gtk.Orientation.VERTICAL, spacing=12, margin=18)
        self.add(box)
        header=ui.widget(Gtk.Box,spacing=8); box.pack_start(header,False,False,0)
        heading=ui.widget(Gtk.Label,label=ui.msg('workspace.editor.notas_rapidas'), xalign=0)
        header.pack_start(heading,True,True,0)
        save=ui.widget(Gtk.Button,label=ui.msg('workspace.editor.salvar')); save.connect('clicked',lambda *_:self.flush())
        header.pack_end(save,False,False,0)
        palette=ui.widget(Gtk.Box,spacing=5); box.pack_start(palette,False,False,0)
        for name,color in COLORS:
            button=ui.widget(Gtk.Button,label='●'); ui.call(button,'set_tooltip_text',name)
            css=ui.widget(Gtk.CssProvider,); css.load_from_data(f'button {{color:{color};background:#30343b;background-image:none;}}'.encode())
            button.get_style_context().add_provider(css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            button.connect('clicked',self.color_changed,color); palette.pack_start(button,False,False,0)
        self.text=ui.widget(Gtk.TextView,wrap_mode=Gtk.WrapMode.WORD_CHAR, left_margin=14,right_margin=14,top_margin=14,bottom_margin=14)
        self.buffer=self.text.get_buffer()
        scroll=ui.widget(Gtk.ScrolledWindow,); scroll.set_policy(Gtk.PolicyType.AUTOMATIC,Gtk.PolicyType.AUTOMATIC)
        scroll.add(self.text); box.pack_start(scroll,True,True,0)
        self.status=ui.widget(Gtk.Label,xalign=0,wrap=True); box.pack_start(self.status,False,False,0)
        hint=ui.widget(Gtk.Label,label=ui.msg('workspace.editor.salvamento_automatico_ctrl_z_desfaz_ctrl_shift_z_refaz'), xalign=0,wrap=True)
        box.pack_start(hint,False,False,0)
        self.css=ui.widget(Gtk.CssProvider,)
        self.text.get_style_context().add_provider(self.css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.saved=''; self.color='#ffe293'
        try:
            data=store.modify({'action':'get'}); self.saved=data['notes'];self.color=data.get('note_color',self.color)
        except (OSError,ValueError) as error:
            self.read_error=True;ui.call(self.status,'set_text',ui.error_message(error));self.text.set_editable(False);save.set_sensitive(False);palette.set_sensitive(False)
        self.apply_color(); ui.call(self.buffer,'set_text',self.saved);self.history=[self.saved]
        if not self.read_error:ui.call(self.status,'set_text',ui.msg('workspace.editor.tudo_salvo_neste_computador'))
        self.buffer.connect('changed',self.changed)
        self.connect('delete-event',self.on_close)
        self.connect('key-press-event',self.key_press)
        self.show_all(); self.text.grab_focus()

    def value(self):
        return self.buffer.get_text(self.buffer.get_start_iter(),self.buffer.get_end_iter(),True)

    def apply_color(self):
        if self.color not in dict(COLORS).values():self.color=COLORS[0][1]
        self.css.load_from_data(f'textview, textview text {{background-color:{self.color};color:#161616;caret-color:#161616;font:15px Sans;}}'.encode())

    def color_changed(self,_button,color):
        try:store.modify({'action':'note_color','color':color})
        except (OSError,ValueError) as error:ui.call(self.status,'set_text',ui.error_message(error));return
        self.color=color;self.apply_color()

    def record(self):
        if self.history_timer:GLib.source_remove(self.history_timer);self.history_timer=0
        value=self.value()
        if value!=self.history[self.position]:
            self.history=self.history[:self.position+1]+[value]
            self.history=self.history[-60:];self.position=len(self.history)-1
        return False

    def changed(self,*_):
        if self.loading or self.read_error:return
        self.dirty=self.value()!=self.saved
        ui.call(self.status,'set_text','Salvando…' if self.dirty else ui.msg('workspace.dialogs.editor.saved'))
        if self.timer:GLib.source_remove(self.timer)
        self.timer=GLib.timeout_add(500,self.flush)
        if self.history_timer:GLib.source_remove(self.history_timer)
        self.history_timer=GLib.timeout_add(300,self.record)

    def flush(self):
        if self.timer:GLib.source_remove(self.timer);self.timer=0
        if self.read_error or not self.dirty:return False
        try:
            value=self.value()
            store.modify({'action':'notes','notes':value,'expected_notes':self.saved})
        except (OSError,ValueError) as error:
            ui.call(self.status,'set_text',ui.msg('workspace.dialogs.editor.error', error=ui.error_message(error)));return False
        self.saved=value;self.dirty=False
        ui.call(self.status,'set_text',ui.msg('workspace.editor.tudo_salvo_neste_computador'));return False

    def undo(self,redo=False):
        self.record();next_position=self.position+(1 if redo else -1)
        if not 0<=next_position<len(self.history):return
        self.position=next_position;self.loading=True
        ui.call(self.buffer,'set_text',self.history[self.position]);self.loading=False
        # Schedule save without creating another history branch.
        self.dirty=self.value()!=self.saved
        if self.timer:GLib.source_remove(self.timer)
        self.timer=GLib.timeout_add(500,self.flush)
        ui.call(self.status,'set_text','Salvando…' if self.dirty else ui.msg('workspace.dialogs.editor.saved'))

    def key_press(self,_window,event):
        if event.state&Gdk.ModifierType.CONTROL_MASK:
            key=Gdk.keyval_name(event.keyval).lower()
            if key=='s':self.flush();return True
            if key in ('z','y'):
                self.undo(key=='y' or bool(event.state&Gdk.ModifierType.SHIFT_MASK));return True
        return False

    def on_close(self,*_):
        self.flush()
        if self.dirty:
            ui.call(self.status,'set_text',ui.msg('workspace.editor.a_janela_continua_aberta_porque_ha_texto_nao_salvo_copie_o_texto_ou_tente_ctrl_s'));return True
        if self.history_timer:GLib.source_remove(self.history_timer);self.history_timer=0
        return False


def main():
    app=ui.widget(Gtk.Application,application_id='io.orbitz.Workspace.NoteEditor',flags=Gio.ApplicationFlags.FLAGS_NONE)
    def activate(application):
        window=application.get_active_window() or NoteWindow(application)
        window.present()
    app.connect('activate',activate)
    return app.run(sys.argv)

if __name__=='__main__':sys.exit(main())
