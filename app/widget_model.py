"""Validated portable desktop clock settings and locale-independent presentation."""
from copy import deepcopy
from datetime import datetime
import math
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

KEY='desktop-widget'
THEMES={
    'light':dict(clock_color='#161616ff',date_color='#161616ff',weather_color='#161616ff',background_color='#ffffff33',border_color='#161616ff'),
    'dark':dict(clock_color='#ffffffff',date_color='#ffffffff',weather_color='#ffffffff',background_color='#00000033',border_color='#ffffffff')}

DEFAULTS=dict(theme='light',enabled=False,start_at_login=False,language='pt-BR',timezone='local',
    location=dict(name='Brasília, DF',latitude=-15.7939,longitude=-47.8828,timezone='America/Sao_Paulo'),
    unit='celsius',time_format='%H:%M:%S',date_format='%A %b %d',
    show_time=True,show_date=True,show_weather=True,show_location=True,show_condition=True,
    show_feels=True,show_range=True,show_humidity=True,show_rain=True,
    width=440,height=410,scale=1.0,x=60,y=80,locked=False,
    clock_font='Sans',date_font='Sans',weather_font='Sans',clock_size=84,date_size=36,weather_size=22,
    clock_color='#161616ff',date_color='#161616ff',weather_color='#161616ff',
    background_color='#ffffff33',border_color='#161616ff',border_width=3,radius=20,refresh_minutes=10)
BOOLEANS={key for key,value in DEFAULTS.items() if type(value) is bool}
RANGES=dict(width=(280,1600),height=(180,1600),x=(-32768,32768),y=(-32768,32768),
    clock_size=(12,200),date_size=(10,100),weather_size=(9,70),border_width=(0,12),radius=(0,100),refresh_minutes=(5,60))
WEEKDAYS={'pt-BR':('segunda','terça','quarta','quinta','sexta','sábado','domingo'),
          'en-US':('Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday')}
MONTHS={'pt-BR':('janeiro','fevereiro','março','abril','maio','junho','julho','agosto','setembro','outubro','novembro','dezembro'),
        'en-US':('January','February','March','April','May','June','July','August','September','October','November','December')}
SHORT_WEEKDAYS={'pt-BR':('seg','ter','qua','qui','sex','sáb','dom'),'en-US':('Mon','Tue','Wed','Thu','Fri','Sat','Sun')}
SHORT_MONTHS={'pt-BR':('jan','fev','mar','abr','mai','jun','jul','ago','set','out','nov','dez'),
              'en-US':('Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec')}
WORDS={
'pt-BR':dict(feels='Sensação',humidity='Umidade',rain='Chuva hoje',unavailable='Clima indisponível',loading='Carregando clima…',stale='Sem conexão · última previsão salva',
    clear='Céu limpo',partly='Parcialmente nublado',cloudy='Nublado',fog='Neblina',drizzle='Garoa',rainy='Chuva',snow='Neve',storm='Trovoadas',weather='Clima'),
'en-US':dict(feels='Feels like',humidity='Humidity',rain='Rain today',unavailable='Weather unavailable',loading='Loading weather…',stale='Offline · last saved forecast',
    clear='Clear sky',partly='Partly cloudy',cloudy='Cloudy',fog='Fog',drizzle='Drizzle',rainy='Rain',snow='Snow',storm='Thunderstorms',weather='Weather')}


def validate_format(value):
    if not isinstance(value,str) or not 1<=len(value)<=120 or any(ord(c)<32 for c in value):raise ValueError('Invalid date/time format')
    # Only documented strftime tokens, no arbitrary execution or platform extensions.
    if re.sub(r'%(?:[%aAbBHIMSpdemyYzZjuwV])','',value).find('%')>=0:raise ValueError('Unsupported date/time token')
    return value


def validate(raw):
    if not isinstance(raw,dict):raise ValueError('Invalid desktop widget settings')
    result=deepcopy(DEFAULTS);result.update({k:v for k,v in raw.items() if k in DEFAULTS})
    if 'theme' not in raw and raw.get('clock_color','').lower() in ('#ffffff','#ffffffff'):
        result['theme']='dark'
    if result['theme'] not in THEMES:raise ValueError('Invalid theme')
    if type(result['scale']) not in (int,float) or not math.isfinite(result['scale']) or not .25<=result['scale']<=3:
        raise ValueError('Invalid scale')
    result['scale']=float(result['scale'])
    for key in BOOLEANS:
        if type(result[key]) is not bool:raise ValueError('Invalid '+key)
    for key,(low,high) in RANGES.items():
        if type(result[key]) is not int or not low<=result[key]<=high:raise ValueError('Invalid '+key)
    if result['language'] not in WORDS or result['unit'] not in ('celsius','fahrenheit'):raise ValueError('Invalid language/unit')
    for key in ('time_format','date_format'):validate_format(result[key])
    if not isinstance(result['timezone'],str):raise ValueError('Invalid timezone')
    if result['timezone']!='local':
        try:ZoneInfo(result['timezone'])
        except (ValueError,ZoneInfoNotFoundError):raise ValueError('Invalid timezone') from None
    for key in ('clock_color','date_color','weather_color','background_color','border_color'):
        if not isinstance(result[key],str) or not re.fullmatch(r'#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?',result[key]):raise ValueError('Invalid '+key)
    for key in ('clock_font','date_font','weather_font'):
        if not isinstance(result[key],str) or not 1<=len(result[key])<=100 or any(ord(c)<32 for c in result[key]):raise ValueError('Invalid font')
    location=result['location']
    if not isinstance(location,dict):raise ValueError('Invalid location')
    for key,low,high in [('latitude',-90,90),('longitude',-180,180)]:
        value=location.get(key)
        if type(value) not in (int,float) or not math.isfinite(value) or not low<=value<=high:raise ValueError('Invalid location')
    name=location.get('name')
    if not isinstance(name,str) or not 1<=len(name.strip())<=160 or any(ord(c)<32 for c in name):raise ValueError('Invalid location name')
    zone=location.get('timezone','UTC')
    try:ZoneInfo(zone)
    except (ValueError,TypeError,ZoneInfoNotFoundError):raise ValueError('Invalid location timezone') from None
    result['location']=dict(name=name.strip(),latitude=float(location['latitude']),longitude=float(location['longitude']),timezone=zone)
    if not any(result[key] for key in ('show_time','show_date','show_weather')):raise ValueError('Show at least one section')
    return result


def read(preferences=None):
    if preferences is None:import ui_state as preferences
    return validate(preferences.get(KEY,{}))


def localized_format(now,pattern,language):
    values={'A':WEEKDAYS[language][now.weekday()],'a':SHORT_WEEKDAYS[language][now.weekday()],
            'B':MONTHS[language][now.month-1],'b':SHORT_MONTHS[language][now.month-1]}
    # Translate tokens before strftime, keeping escaped percent sequences literal.
    parts=re.split(r'(%.)',pattern)
    return ''.join(values[part[1]] if part.startswith('%') and len(part)==2 and part[1] in values else now.strftime(part) for part in parts)


def local_now(config,now=None):
    now=now or datetime.now().astimezone()
    return now.astimezone() if config['timezone']=='local' else now.astimezone(ZoneInfo(config['timezone']))


def condition(code,is_day,language):
    if code==0:key,icon='clear','☀️' if is_day else '🌙'
    elif code in (1,2):key,icon='partly','🌤'
    elif code==3:key,icon='cloudy','☁'
    elif code in (45,48):key,icon='fog','🌫'
    elif code in (51,53,55,56,57):key,icon='drizzle','🌦'
    elif code in (71,73,75,77,85,86):key,icon='snow','❄'
    elif code in (95,96,99):key,icon='storm','⛈'
    elif code in (61,63,65,66,67,80,81,82):key,icon='rainy','🌧'
    else:key,icon='weather','🌡'
    return icon,WORDS[language][key]


def weather_lines(config,payload=None,error=False):
    words=WORDS[config['language']]
    if not payload:return [words['unavailable'] if error else words['loading']]
    current=payload['current'];today=local_now({**config,'timezone':payload['location']['timezone']}).date().isoformat()
    daily=next((day for day in payload['days'] if day['date']==today),None)
    # Never present yesterday's precipitation/temperature range as today's forecast.
    symbol='°C' if config['unit']=='celsius' else '°F'
    # Match the forecast card for today, rather than mixing two condition periods.
    daily_condition=daily is not None and 'weather_code' in daily
    code=daily['weather_code'] if daily_condition else current['weather_code']
    icon,label=condition(code,True if daily_condition else current['is_day'],config['language'])
    rows=[f"{icon} "+(config['location']['name']+' · ' if config['show_location'] else '')+f"{current['temperature']:.0f}{symbol}"]
    pieces=[]
    if config['show_condition']:pieces.append(label)
    if config['show_feels']:pieces.append(f"{words['feels']} {current['apparent_temperature']:.0f}{symbol}")
    if pieces:rows.append(' · '.join(pieces))
    pieces=[]
    if config['show_range'] and daily:pieces.append(f"↓ {daily['temp_min']:.0f}°  ↑ {daily['temp_max']:.0f}°")
    if config['show_humidity']:pieces.append(f"{words['humidity']} {current['humidity']:.0f}%")
    if pieces:rows.append(' · '.join(pieces))
    if config['show_rain'] and daily:rows.append(f"{words['rain']}: {daily['precipitation_probability']:.0f}%")
    if payload.get('stale'):rows.append(words['stale'])
    return rows


def lines(config,payload=None,error=False,now=None):
    now=local_now(config,now);result=[]
    if config['show_time']:result.append(('clock',localized_format(now,config['time_format'],config['language'])))
    if config['show_date']:result.append(('date',localized_format(now,config['date_format'],config['language'])))
    if config['show_weather']:result.extend(('weather',text) for text in weather_lines(config,payload,error))
    return result


def pixel_size(config):
    """Keep the logical canvas unchanged; scale every visual element uniformly."""
    return round(config['width']*config['scale']),round(config['height']*config['scale'])


def hit_region(regions,x,y):
    for kind,(left,top,width,height) in regions.items():
        if left<=x<=left+width and top<=y<=top+height:return kind
    return None


def resize_from_handle(config,handle,dx,dy,origin=None):
    """Uniform scale, keeping the opposite edge/corner (or edge center) anchored."""
    if handle not in ('nw','n','ne','e','se','s','sw','w'):raise ValueError('Invalid resize handle')
    if any(type(v) not in (int,float) or not math.isfinite(v) for v in (dx,dy)):raise ValueError('Invalid pointer delta')
    width,height=config['width'],config['height'];start=config['scale']
    horizontal=-1 if 'w' in handle else 1 if 'e' in handle else 0
    vertical=-1 if 'n' in handle else 1 if 's' in handle else 0
    if horizontal and vertical:scale=start+(horizontal*width*dx+vertical*height*dy)/(width*width+height*height)
    elif horizontal:scale=start+horizontal*dx/width
    else:scale=start+vertical*dy/height
    scale=max(.25,min(3,scale))
    result=deepcopy(config);result['scale']=scale
    old_w,old_h=pixel_size(config);new_w,new_h=pixel_size(result)
    x,y=origin or (config['x'],config['y'])
    result['x']=round(x+(old_w-new_w if horizontal<0 else 0 if horizontal>0 else (old_w-new_w)/2))
    result['y']=round(y+(old_h-new_h if vertical<0 else 0 if vertical>0 else (old_h-new_h)/2))
    for key in ('x','y'):result[key]=max(RANGES[key][0],min(RANGES[key][1],result[key]))
    return validate(result)
