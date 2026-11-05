"""Calendar with explicit event contrast and a separate holiday indicator."""
from day_activity import day_messages
from ui_language import ui
import calendar
from datetime import date,timedelta
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,GObject,Gdk
MONTHS=[ui.msg('workspace.live.month_1'), ui.msg('workspace.live.month_2'), ui.msg('workspace.live.month_3'), ui.msg('workspace.live.month_4'), ui.msg('workspace.live.month_5'), ui.msg('workspace.live.month_6'), ui.msg('workspace.live.month_7'), ui.msg('workspace.live.month_8'), ui.msg('workspace.live.month_9'), ui.msg('workspace.live.month_10'), ui.msg('workspace.live.month_11'), ui.msg('workspace.live.month_12')]
class MonthCalendar(Gtk.Box):
    _provider=None
    __gsignals__={'day-selected':(GObject.SignalFlags.RUN_FIRST,None,()),'month-changed':(GObject.SignalFlags.RUN_FIRST,None,())}
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL,spacing=4)
        self.chosen=date.today();self.year=self.chosen.year;self.month=self.chosen.month;self.marks=set();self.holidays={};self.details={}
        self.set_name('orbitz-month-calendar')
        if MonthCalendar._provider is None:
            css=Gtk.CssProvider();css.load_from_data(b'''
#orbitz-month-calendar {background-color:alpha(@theme_fg_color,0.04); color:@theme_fg_color; padding:6px; border-radius:6px;}
#orbitz-month-calendar button {padding:3px; min-width:20px; min-height:22px; border:0; box-shadow:none; background-image:none; background-color:transparent; border-radius:4px;}
#orbitz-month-calendar button.nav label {color:@theme_fg_color;}
#orbitz-month-calendar button.day {border-bottom:2px solid transparent;}
#orbitz-month-calendar button.day:hover {background-color:alpha(@theme_fg_color,0.12);}
#orbitz-month-calendar button.day label {color:@theme_fg_color;}
#orbitz-month-calendar button.outside label {color:alpha(@theme_fg_color,0.45);}
#orbitz-month-calendar button.marked label {font-weight:bold;}
#orbitz-month-calendar button.selected {background-color:@theme_selected_bg_color;}
#orbitz-month-calendar button.selected label {color:@theme_selected_fg_color;}
#orbitz-month-calendar button.holiday {border-bottom-color:#f6c453;}
''');Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(),css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            MonthCalendar._provider=css
        header=Gtk.Box(spacing=2);self.pack_start(header,False,False,0)
        def nav(text,months,tooltip):
            b=Gtk.Button(label=text);b.get_style_context().add_class('nav');ui.call(b,'set_tooltip_text',tooltip);b.connect('clicked',lambda *_:self.shift(months));header.pack_start(b,False,False,0)
        nav('«',-12,ui.msg('workspace.live.previous_year'));nav('‹',-1,ui.msg('workspace.live.previous_month'))
        self.title=Gtk.Label();header.pack_start(self.title,True,True,0)
        nav('›',1,ui.msg('workspace.live.next_month'));nav('»',12,ui.msg('workspace.live.next_year'))
        self.grid=Gtk.Grid(column_homogeneous=True,row_spacing=1,column_spacing=1);self.pack_start(self.grid,False,False,0)
        legend=Gtk.Label(xalign=0);ui.call(legend,'set_markup',ui.msg('workspace.live.calendar_legend'))
        legend.set_line_wrap(True);legend.set_max_width_chars(28)
        self.pack_start(legend,False,False,0);self.redraw()
    def get_date(self):return self.year,self.month-1,self.chosen.day
    def shift(self,months):
        n=self.year*12+self.month-1+months;year,month=divmod(n,12)
        if not 1<=year<=9998:return
        self.select_month(month,year);self.select_day(min(self.chosen.day,calendar.monthrange(year,month+1)[1]))
    def select_month(self,month,year):
        if not 1<=year<=9998:return
        changed=(year,month+1)!=(self.year,self.month)
        self.year=year;self.month=month+1;self.marks.clear();self.holidays={};self.details={};self.redraw()
        if changed:self.emit('month-changed')
    def select_day(self,day):
        if day<1 or day>calendar.monthrange(self.year,self.month)[1]:return
        self.chosen=date(self.year,self.month,day);self.redraw();self.emit('day-selected')
    def clear_marks(self):self.marks.clear();self.holidays={};self.details={}
    def mark_day(self,day):self.marks.add(day)
    def finish_marks(self,holidays=None,details=None):
        self.holidays=holidays or {};self.details=details or {};self.redraw()
    def redraw(self):
        for child in self.grid.get_children():child.destroy()
        ui.call(self.title,'set_text',MONTHS[self.month-1]+' '+str(self.year));self.buttons={}
        for column,name in enumerate([ui.msg('workspace.live.weekday_0'), ui.msg('workspace.live.weekday_1'), ui.msg('workspace.live.weekday_2'), ui.msg('workspace.live.weekday_3'), ui.msg('workspace.live.weekday_4'), ui.msg('workspace.live.weekday_5'), ui.msg('workspace.live.weekday_6')]):self.grid.attach(ui.widget(Gtk.Label,label=name),column,0,1,1)
        first=date(self.year,self.month,1);offset=(first.weekday()+1)%7
        start=first-timedelta(days=offset)
        for i in range(42):
            day=start+timedelta(days=i);inside=(day.month==self.month and day.year==self.year)
            marked=inside and day.day in self.marks;selected=day==self.chosen;holiday=inside and day.day in self.holidays
            label=Gtk.Label(label=str(day.day))
            button=Gtk.Button();button.add(label);style=button.get_style_context();style.add_class('day')
            if not inside:style.add_class('outside')
            if marked:style.add_class('marked')
            if selected:style.add_class('selected')
            if holiday:style.add_class('holiday')
            text=day_messages(day,selected,marked,self.holidays.get(day.day,[]) if inside else (),self.details.get(day.day,[]) if inside else ())
            ui.call(button,'set_tooltip_text',ui.join('\n',text));ui.call(button.get_accessible(),'set_name',ui.join(' · ',text))
            button.connect('clicked',lambda _,d=day:self.click(d));self.grid.attach(button,i%7,i//7+1,1,1)
            if inside:self.buttons[day.day]=button
        self.grid.show_all()
    def click(self,day):
        self.select_month(day.month-1,day.year);self.select_day(day.day)
