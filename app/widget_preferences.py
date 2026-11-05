"""One-place widget configuration with a live renderer and asynchronous city search."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime,timedelta
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,Gdk,GLib
from ui_language import ui
import widget_model as model
import widget_render
import weather_backend


def text(key):return ui.msg('workspace.widget.'+key)


class WidgetPreferences(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL,spacing=12)
        self.alive=True;self.executor=ThreadPoolExecutor(max_workers=1);self.fields={};self.locations=[];self.search_busy=False
        self.config=model.read();self.loading=True
        self.enabled=ui.widget(Gtk.CheckButton,label=text('enable'));self.enabled.set_active(self.config['enabled']);self.pack_start(self.enabled,False,False,0)
        self.revealer=Gtk.Revealer();self.revealer.set_transition_type(Gtk.RevealerTransitionType.NONE);self.pack_start(self.revealer,True,True,0)
        body=Gtk.Box(spacing=18);self.revealer.add(body)
        book=Gtk.Notebook();book.set_hexpand(True);body.pack_start(book,True,True,0)
        self.grids={}
        for key in ('content','appearance','position'):
            scroll=Gtk.ScrolledWindow();scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC);scroll.set_min_content_height(320)
            grid=Gtk.Grid(column_spacing=12,row_spacing=10,margin=12);scroll.add(grid)
            book.append_page(scroll,ui.widget(Gtk.Label,label=text(key)));self.grids[key]=grid
        self.row_counts={key:0 for key in self.grids}
        previewbox=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8);previewbox.set_size_request(300,-1);body.pack_start(previewbox,True,True,0)
        previewbox.pack_start(ui.widget(Gtk.Label,label=text('preview'),xalign=0),False,False,0)
        self.preview=widget_render.WidgetPreview(self.config);previewbox.pack_start(self.preview,True,True,0)
        previewbox.pack_start(ui.widget(Gtk.Label,label=text('example_data'),wrap=True,xalign=0,max_width_chars=35),False,False,0)
        self.preview_error=Gtk.Label(xalign=0,wrap=True,max_width_chars=35);previewbox.pack_start(self.preview_error,False,False,0)
        self.combo('language', [('pt-BR','Português (Brasil)'),('en-US','English (US)')],'content')
        self.entry('timezone','content');self.fields['timezone'].set_placeholder_text('local / America/Sao_Paulo')
        self.entry('time_format','content');self.entry('date_format','content')
        self.time_preset=self.preset('time_format',[
            ('%H:%M:%S','24_seconds'),('%H:%M','24_minutes'),('%I:%M:%S','12_seconds'),('%I:%M','12_minutes')])
        self.date_preset=self.preset('date_format',[
            ('%A %b %d','date_words'),('%d/%m/%Y','date_day_first'),('%m/%d/%Y','date_month_first'),('%Y-%m-%d','date_iso')])
        hint=ui.widget(Gtk.Label,label=text('format_help'),xalign=0,wrap=True,max_width_chars=48);self.row('content',None,hint)
        self.combo('unit',[('celsius','°C'),('fahrenheit','°F')],'content')
        self.search=Gtk.Entry();self.search.set_placeholder_text(ui.tr('workspace.widget.city_placeholder'))
        self.search.set_text(self.config['location']['name']);self.row('content',text('city'),self.search)
        self.search_button=ui.widget(Gtk.Button,label=text('search'));self.search_button.connect('clicked',self.search_city)
        self.search.connect('activate',self.search_city);self.row('content',None,self.search_button)
        self.results=Gtk.ComboBoxText();self.results.set_hexpand(True)
        for cell in self.results.get_cells():cell.set_property('max-width-chars',32)
        self.row('content',text('results'),self.results);self.results.connect('changed',self.choose_city)
        self.search_status=Gtk.Label(xalign=0,wrap=True,max_width_chars=44);self.row('content',None,self.search_status)
        self.location_name=Gtk.Entry(text=self.config['location']['name']);self.row('content',text('location_name'),self.location_name)
        self.location_name.connect('changed',self.changed)
        self.latitude=self.coordinate(self.config['location']['latitude'],-90,90);self.row('content',text('latitude'),self.latitude)
        self.longitude=self.coordinate(self.config['location']['longitude'],-180,180);self.row('content',text('longitude'),self.longitude)
        self.location_zone=Gtk.Entry(text=self.config['location']['timezone']);self.row('content',text('location_timezone'),self.location_zone);self.location_zone.connect('changed',self.changed)
        link=Gtk.LinkButton.new_with_label('https://open-meteo.com/','Open-Meteo · CC BY 4.0 · GeoNames');self.row('content',None,link)
        self.combo('theme', [('light',ui.tr('workspace.widget.theme_light')),('dark',ui.tr('workspace.widget.theme_dark'))],'appearance')
        for key in ('show_time','show_date','show_weather','show_location','show_condition','show_feels','show_range','show_humidity','show_rain'):
            self.check(key,'appearance')
        for key in ('clock_font','date_font','weather_font'):
            field=Gtk.FontButton(font=self.config[key]);field.set_use_size(False);field.set_show_size(False)
            self.fields[key]=field;self.row('appearance',text(key),field);field.connect('font-set',self.changed)
        for key in ('clock_size','date_size','weather_size'):
            self.spin(key,'appearance')
        for key in ('clock_color','date_color','weather_color','background_color','border_color'):
            value=Gdk.RGBA()
            value.red,value.green,value.blue,value.alpha=widget_render.rgba(self.config[key])
            field=Gtk.ColorButton(rgba=value,use_alpha=True)
            self.fields[key]=field;self.row('appearance',text(key),field);field.connect('color-set',self.changed)
        for key in ('border_width','radius'):self.spin(key,'appearance')
        scale=Gtk.SpinButton.new_with_range(25,300,1);scale.set_value(self.config['scale']*100)
        self.fields['scale']=scale;self.row('position',text('scale'),scale);scale.connect('value-changed',self.changed)
        for key in ('width','height','x','y','refresh_minutes'):self.spin(key,'position')
        for key in ('locked','start_at_login'):self.check(key,'position')
        info=ui.widget(Gtk.Label,label=text('desktop_note'),xalign=0,wrap=True,max_width_chars=46);self.row('position',None,info)
        self.fields['theme'].connect('changed',self.theme_changed)
        self.enabled.connect('toggled',self.changed)
        self.loading=False;self.changed();self.timer=GLib.timeout_add_seconds(1,self.tick)
        self.connect('destroy',self.cleanup)

    def theme_changed(self,*_):
        if self.loading:return
        palette=model.THEMES[self.fields['theme'].get_active_id()]
        for key,color in palette.items():
            value=Gdk.RGBA()
            value.red,value.green,value.blue,value.alpha=widget_render.rgba(color)
            self.fields[key].set_rgba(value)
        self.changed()

    def row(self,page,label,field):
        grid=self.grids[page];row=self.row_counts[page];self.row_counts[page]+=1
        field.set_hexpand(True)
        if label is None:grid.attach(field,0,row,2,1)
        else:
            caption=ui.widget(Gtk.Label,label=label,xalign=0,wrap=True,max_width_chars=24)
            grid.attach(caption,0,row,1,1);grid.attach(field,1,row,1,1)
            ui.call(field.get_accessible(),'set_name',label)

    def entry(self,key,page):
        field=Gtk.Entry(text=self.config[key]);field.set_max_length(120);self.fields[key]=field
        self.row(page,text(key),field);field.connect('changed',self.changed)

    def combo(self,key,choices,page):
        field=Gtk.ComboBoxText()
        for value,label in choices:field.append(value,label)
        field.set_active_id(self.config[key]);self.fields[key]=field;self.row(page,text(key),field);field.connect('changed',self.changed)

    def preset(self,key,choices):
        field=Gtk.ComboBoxText()
        for value,label in choices:ui.combo_append(field,value,text(label))
        ui.combo_append(field,'custom',text('custom'))
        current=self.config[key]
        field.set_active_id(current if current in dict(choices) else 'custom')
        self.row('content',text(key+'_preset'),field)
        def selected(*_):
            value=field.get_active_id()
            if value and value!='custom':self.fields[key].set_text(value)
        field.connect('changed',selected)
        return field

    def spin(self,key,page):
        low,high=model.RANGES[key];field=Gtk.SpinButton.new_with_range(low,high,1)
        field.set_value(self.config[key]);field.set_numeric(True);self.fields[key]=field
        self.row(page,text(key),field);field.connect('value-changed',self.changed)

    def coordinate(self,value,low,high):
        field=Gtk.SpinButton.new_with_range(low,high,.0001);field.set_digits(4);field.set_value(value);field.set_numeric(True)
        field.connect('value-changed',self.changed);return field

    def check(self,key,page):
        field=ui.widget(Gtk.CheckButton,label=text(key));field.set_active(self.config[key]);self.fields[key]=field
        self.row(page,None,field);field.connect('toggled',self.changed)

    def value(self):
        config=deepcopy(self.config);config['enabled']=self.enabled.get_active()
        for key,field in self.fields.items():
            if key=='scale':config[key]=field.get_value()/100
            elif key in model.BOOLEANS:config[key]=field.get_active()
            elif key in model.RANGES:config[key]=field.get_value_as_int()
            elif key.endswith('_color'):
                color=field.get_rgba();config[key]='#'+''.join(f'{round(v*255):02x}' for v in (color.red,color.green,color.blue,color.alpha))
            elif key.endswith('_font'):config[key]=field.get_font_name()
            elif key in ('language','unit','theme'):config[key]=field.get_active_id()
            else:config[key]=field.get_text().strip()
        config['location']=dict(name=self.location_name.get_text().strip(),latitude=self.latitude.get_value(),
            longitude=self.longitude.get_value(),timezone=self.location_zone.get_text().strip())
        return model.validate(config)

    def sample(self,config):
        day=model.local_now({**config,'timezone':config['location']['timezone']}).date()
        transform=(lambda c:c*9/5+32) if config['unit']=='fahrenheit' else (lambda c:c)
        return dict(location=config['location'],unit=config['unit'],stale=False,
            current=dict(temperature=transform(28),apparent_temperature=transform(32),humidity=57,weather_code=0,is_day=1),
            days=[dict(date=day.isoformat(),temp_min=transform(19),temp_max=transform(28),precipitation_probability=92)])

    def changed(self,*_):
        if self.loading or not self.alive:return
        self.revealer.set_reveal_child(self.enabled.get_active())
        try:
            config=self.value();self.preview.config=config;self.preview.payload=self.sample(config);self.preview.queue_draw()
            self.preview_error.set_text('')
        except ValueError as error:
            self.preview_error.set_text(ui.tr('workspace.widget.invalid',reason=str(error)))

    def tick(self):
        if not self.alive:return False
        if self.enabled.get_active():self.preview.queue_draw()
        return True

    def search_city(self,*_):
        if self.search_busy:return
        query=self.search.get_text().strip()
        if len(query)<2:
            ui.call(self.search_status,'set_text',text('search_min'));return
        self.search_busy=True;self.search_button.set_sensitive(False)
        ui.call(self.search_status,'set_text',text('searching'));language=self.fields['language'].get_active_id()
        future=self.executor.submit(weather_backend.geocode,query,language=language)
        def done(future):
            try:result,error=future.result(),None
            except Exception:result,error=None,True
            GLib.idle_add(self.search_done,result,error)
        future.add_done_callback(done)

    def search_done(self,result,error):
        if not self.alive:return False
        self.search_busy=False;self.search_button.set_sensitive(True)
        self.results.remove_all();self.locations=[]
        if error:ui.call(self.search_status,'set_text',text('search_failed'));return False
        self.locations=result['results']
        for index,location in enumerate(self.locations):
            self.results.append(str(index),', '.join(v for v in (location['name'],location.get('admin1',''),location.get('country','')) if v))
        ui.call(self.search_status,'set_text',text('choose_result') if self.locations else text('no_results'))
        return False

    def choose_city(self,*_):
        identity=self.results.get_active_id()
        if identity is None:return
        location=self.locations[int(identity)]
        self.loading=True
        self.location_name.set_text(location['name']);self.latitude.set_value(location['latitude']);self.longitude.set_value(location['longitude'])
        self.location_zone.set_text(location['timezone']);self.loading=False;self.changed()

    def cleanup(self,*_):
        self.alive=False
        if self.timer:GLib.source_remove(self.timer);self.timer=0
        self.executor.shutdown(wait=False,cancel_futures=True)
