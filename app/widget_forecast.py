"""Compact weather dashboard with a hero card and a seven-day outlook."""
from datetime import date,datetime,time
import math
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk
from ui_language import ui
import widget_model as model


class WeatherIcon(Gtk.DrawingArea):
    def __init__(self,code,size=48):
        super().__init__();self.code=code;self.set_size_request(size,size);self.connect('draw',self.paint)

    def paint(self,widget,c):
        width,height=self.get_allocated_width(),self.get_allocated_height()
        factor=min(width,height)/64
        c.translate((width-64*factor)/2,(height-64*factor)/2);c.scale(factor,factor)
        code=self.code
        if code in (0,1,2):
            c.set_source_rgb(1,.64,.08);c.arc(39,23,14,0,math.tau);c.fill()
        if code!=0:
            c.set_source_rgb(*((.55,.58,.62) if code>=3 else (.92,.94,.96)))
            for x,y,r in ((19,33,11),(29,26,14),(43,34,12)):
                c.arc(x,y,r,0,math.tau);c.fill()
            c.rectangle(18,32,26,13);c.fill()
        if 50<=code<=99:
            if code>=95:
                c.set_source_rgb(1,.73,.15);c.move_to(34,39);c.line_to(26,51);c.line_to(33,50);c.line_to(29,60);c.line_to(42,44);c.line_to(34,45);c.close_path();c.fill()
            else:
                c.set_source_rgb(.35,.76,.92);c.set_line_width(2.5);c.set_line_cap(1)
                for x in (20,30,40):c.move_to(x,49);c.line_to(x-3,56);c.stroke()
        return False


class SolarIcon(Gtk.DrawingArea):
    """Outlined half sun, horizon and directional arrow, matching the reference."""
    def __init__(self,rising):
        super().__init__();self.rising=rising;self.set_size_request(36,36)
        self.connect('draw',self.paint)

    def paint(self,widget,c):
        size=min(self.get_allocated_width(),self.get_allocated_height())
        c.translate((self.get_allocated_width()-size)/2,(self.get_allocated_height()-size)/2)
        c.scale(size/40,size/40)
        color=self.get_style_context().get_color(Gtk.StateFlags.NORMAL)
        c.set_source_rgba(color.red,color.green,color.blue,color.alpha)
        c.set_line_width(1.3);c.set_line_cap(1);c.set_line_join(1)
        c.arc(20,22,8,math.pi,2*math.pi);c.stroke()
        c.move_to(4,23);c.line_to(36,23);c.stroke()
        for degrees in (0,30,60,90,120,150,180):
            angle=math.radians(degrees)
            c.move_to(20+12*math.cos(angle),22-12*math.sin(angle))
            c.line_to(20+16*math.cos(angle),22-16*math.sin(angle));c.stroke()
        c.move_to(20,28);c.line_to(20,38);c.stroke()
        tip=28 if self.rising else 38
        base=tip+4 if self.rising else tip-4
        c.move_to(16,base);c.line_to(20,tip);c.line_to(24,base);c.stroke()
        return False


def label(text='',style=None,align=0):
    item=Gtk.Label(label=text,xalign=align)
    if style:item.get_style_context().add_class(style)
    return item


class ForecastWindow(Gtk.Window):
    def __init__(self,parent,refresh):
        super().__init__(title='Weather forecast - By Orbitz')
        self.titlebar=Gtk.HeaderBar(title='Weather forecast - By Orbitz')
        self.titlebar.set_show_close_button(True)
        self.titlebar.set_decoration_layout(':minimize,maximize,close')
        self.titlebar.get_style_context().add_class('weather-titlebar')
        self.set_titlebar(self.titlebar)
        self.set_keep_above(True);self.set_application(parent.get_application())
        self.set_default_size(790,540);self.set_size_request(680,480)
        self.set_skip_taskbar_hint(True)
        self.get_style_context().add_class('orbitz-forecast')
        self.css=Gtk.CssProvider()
        self.box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=16,margin=22);self.add(self.box)
        self.hero=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=18,margin=0)
        self.hero.get_style_context().add_class('weather-hero');self.box.pack_start(self.hero,False,False,0)
        top=Gtk.Box(spacing=20);self.hero.pack_start(top,False,False,0)
        self.hero_icon=Gtk.Box();top.pack_start(self.hero_icon,False,False,0)
        copy=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=5);top.pack_start(copy,True,True,0)
        self.stamp=label(style='weather-muted');copy.add(self.stamp)
        self.heading=label(style='weather-title');copy.add(self.heading)
        self.location=label(style='weather-location');copy.add(self.location)
        self.summary=label(style='weather-summary',align=.5)
        self.summary.set_no_show_all(True)
        self.summary.get_style_context().add_class('weather-strip');self.hero.add(self.summary)
        self.solar=Gtk.Box(spacing=12,halign=Gtk.Align.FILL)
        self.solar.get_style_context().add_class('weather-strip')
        self.solar.set_no_show_all(True);self.hero.add(self.solar)
        self.sunrise=label();self.sunset=label();self.daylight=label(align=.5)
        self.solar.pack_start(SolarIcon(True),False,False,0)
        self.solar.pack_start(self.sunrise,False,False,0)
        self.solar.pack_start(label('┄┄',align=.5),True,True,0)
        self.solar.pack_start(self.daylight,False,False,0)
        self.solar.pack_start(label('┄┄',align=.5),True,True,0)
        self.solar.pack_start(self.sunset,False,False,0)
        self.solar.pack_start(SolarIcon(False),False,False,0)
        self.metrics=Gtk.Box(spacing=18,homogeneous=True);self.box.pack_start(self.metrics,False,False,0)
        self.rain=label(align=.5);self.humidity=label(align=.5);self.wind=label(align=.5)
        for item in (self.rain,self.humidity,self.wind):
            item.get_style_context().add_class('weather-metric');self.metrics.add(item)
        self.status=label(style='weather-muted');self.status.set_line_wrap(True)
        self.status.set_no_show_all(True);self.box.pack_start(self.status,False,False,0)
        self.rows=Gtk.Grid(column_spacing=8,column_homogeneous=True)
        self.box.pack_start(self.rows,True,True,0)
        footer=Gtk.Box();self.box.pack_end(footer,False,False,0)
        self.refresh=Gtk.Button();self.refresh.connect('clicked',lambda *_:refresh())
        footer.pack_end(self.refresh,False,False,0)

    def apply_style(self,config):
        dark=config['theme']=='dark'
        bg,fg,card,sub,muted,edge=('#17191c','#f2f3f5','#2b2e33','#212428','#b0b5bd','#555b64') if dark else ('#f0f1f3','#22252a','#ffffff','#e4e6ea','#626973','#c4c8cf')
        self.css.load_from_data(('''
        .weather-titlebar {background:#20272f; color:#c6d5e2; border:0; border-bottom:1px solid #37414b; border-radius:12px 12px 0 0; box-shadow:none; min-height:32px; padding:0 8px;}
        .weather-titlebar .title {font-size:12px; font-weight:bold; color:#c6d5e2;}
        .weather-titlebar button.titlebutton {background:transparent; background-image:none; color:#c6d5e2; border:0; border-radius:4px; box-shadow:none; min-width:24px; min-height:24px; padding:2px; margin:2px;}
        .weather-titlebar button.titlebutton, .weather-titlebar button.titlebutton:backdrop {background:transparent; background-image:none; border:0; border-radius:0; box-shadow:none; -gtk-icon-shadow:none;}
        .weather-titlebar button.titlebutton image {background:transparent; border:0; box-shadow:none; -gtk-icon-shadow:none;}
        .weather-titlebar button.titlebutton:hover {background:#37414b; border-radius:4px;}
        .orbitz-forecast decoration, .orbitz-forecast decoration:backdrop {border-radius:12px 12px 0 0; box-shadow:none; border:0; margin:0;}
        .orbitz-forecast {background:%s; color:%s; box-shadow:none;}
        .orbitz-forecast label {color:%s;}
        .orbitz-forecast .weather-hero {background:%s; border:1px solid %s; border-radius:32px; padding:24px;}
        .orbitz-forecast .weather-title {font-size:28px; font-weight:bold;}
        .orbitz-forecast .weather-location {font-size:19px; color:%s;}
        .orbitz-forecast .weather-muted {font-size:12px; color:%s;}
        .orbitz-forecast .weather-strip {background:%s; border-radius:22px; padding:13px; font-size:14px;}
        .orbitz-forecast .weather-metric {font-size:14px; padding:4px;}
        .orbitz-forecast .weather-day {background:%s; border-radius:26px; padding:12px 4px;}
        .orbitz-forecast .weather-day-today {background:%s;}
        .orbitz-forecast .weather-high {font-size:18px; font-weight:bold;}
        .orbitz-forecast .weather-low {font-size:14px; color:%s;}
        .orbitz-forecast button {background:%s; color:%s; border:0; border-radius:16px; padding:8px 14px; box-shadow:none;}
        '''%(bg,fg,fg,card,edge,muted,muted,sub,sub,card,muted,card,fg)).encode())
        def apply(widget):
            widget.get_style_context().add_provider(self.css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            if isinstance(widget,Gtk.Container):
                for child in widget.get_children():apply(child)
        apply(self)
        apply(self.titlebar)

    def update(self,config,payload=None,busy=False,error=False):
        self.set_title('Weather forecast - By Orbitz')
        self.titlebar.set_title('Weather forecast - By Orbitz')
        self.refresh.set_label(ui.tr('workspace.widget.refresh'));self.refresh.set_sensitive(not busy)
        for child in self.rows.get_children():child.destroy()
        for child in self.hero_icon.get_children():child.destroy()
        words=model.WORDS[config['language']];en=config['language']=='en-US'
        show_solar=False
        self.location.set_text(config['location']['name'])
        if payload is None:
            self.heading.set_text(words['unavailable'] if error else words['loading'])
            self.stamp.set_text('');self.summary.set_text('—')
            for item in (self.rain,self.humidity,self.wind):item.set_text('—')
            self.status.hide()
        else:
            now=model.local_now({**config,'timezone':payload['location']['timezone']})
            today=now.date();current=payload['current']
            daily=next((d for d in payload['days'] if d['date']==today.isoformat()),None)
            symbol='°F' if config['unit']=='fahrenheit' else '°C'
            code=daily['weather_code'] if daily else current['weather_code']
            _,condition=model.condition(code,True,config['language'])
            self.hero_icon.add(WeatherIcon(code,96))
            self.heading.set_text(f"{condition} {current['temperature']:.0f}{symbol}")
            self.stamp.set_text(model.localized_format(now,'%A',config['language'])+' · '+current['time'][11:16])
            summary=f"{words['feels']} {current['apparent_temperature']:.0f}{symbol}"
            if daily:summary+=f"     ·     ↓ {daily['temp_min']:.0f}{symbol}     ↑ {daily['temp_max']:.0f}{symbol}"
            if daily and 'daylight_duration' in daily:
                def solar_time(key):
                    value=daily.get(key)
                    if not value:return '—'
                    stamp=datetime.fromisoformat(value)
                    return model.localized_format(stamp,'%I:%M %p' if en else '%H:%M',config['language']).lower()
                minutes=int(daily['daylight_duration']//60)
                self.sunrise.set_text(solar_time('sunrise'));self.sunset.set_text(solar_time('sunset'))
                self.daylight.set_text(f'{minutes//60} h {minutes%60:02} m')
                show_solar=True
                self.solar.set_tooltip_text('Sunrise · Daylight duration · Sunset' if en else 'Nascer do sol · Duração do dia · Pôr do sol')
            else:self.summary.set_tooltip_text(None)
            self.summary.set_text(summary)
            rain=words['rain'].removesuffix(' hoje').removesuffix(' today')
            self.rain.set_text(f"{rain}: {daily['precipitation_probability']:.0f}%" if daily else f'{rain}: —')
            self.humidity.set_text(f"{words['humidity']}: {current['humidity']:.0f}%")
            wind='Max wind' if en else 'Vento máx.'
            self.wind.set_text(f"{wind}: {daily['wind_speed_max']:.0f} km/h" if daily and 'wind_speed_max' in daily else f'{wind}: —')
            self.status.set_text(words['stale'] if payload.get('stale') else '')
            self.status.set_visible(bool(payload.get('stale')))
            days=[d for d in payload['days'] if date.fromisoformat(d['date'])>=today][:7]
            for index,day in enumerate(days):
                chosen=date.fromisoformat(day['date'])
                card=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=9)
                card.get_style_context().add_class('weather-day')
                if chosen==today:card.get_style_context().add_class('weather-day-today')
                stamp=('Today' if en else 'Hoje') if chosen==today else model.localized_format(datetime.combine(chosen,time()),'%a',config['language'])
                card.add(label(stamp,align=.5));card.add(WeatherIcon(day['weather_code'],48))
                card.add(label(f"{day['temp_max']:.0f}°",'weather-high',.5))
                card.add(label(f"{day['temp_min']:.0f}°",'weather-low',.5))
                _,description=model.condition(day['weather_code'],True,config['language'])
                card.set_tooltip_text(f"{chosen.isoformat()} · {description}\n{rain}: {day['precipitation_probability']:.0f}%")
                self.rows.attach(card,index,0,1,1)
        self.apply_style(config);self.hero.show_all();self.rows.show_all()
        self.summary.set_visible(not show_solar)
        if show_solar:
            self.solar.set_no_show_all(False);self.solar.show_all();self.solar.set_no_show_all(True)
        else:self.solar.hide()
        self.rows.queue_resize();self.queue_resize()
        self.check_resize()
