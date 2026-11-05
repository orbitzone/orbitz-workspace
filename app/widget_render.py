"""Shared Cairo/Pango renderer for the desktop widget and its live preview."""
import math
import cairo
import gi
gi.require_version('Gtk','3.0')
gi.require_version('PangoCairo','1.0')
from gi.repository import Gtk,Pango,PangoCairo
import widget_model as model


def rgba(value):
    value=value[1:]
    if len(value)==6:value+='ff'
    return tuple(int(value[i:i+2],16)/255 for i in (0,2,4,6))


def rounded(context,x,y,width,height,radius):
    radius=min(radius,width/2,height/2)
    context.new_sub_path()
    for cx,cy,a,b in [(x+width-radius,y+radius,-90,0),(x+width-radius,y+height-radius,0,90),
                       (x+radius,y+height-radius,90,180),(x+radius,y+radius,180,270)]:
        context.arc(cx,cy,radius,math.radians(a),math.radians(b))
    context.close_path()


def draw(context,config,width,height,payload=None,error=False,now=None):
    # The preview uses exactly the same logical canvas as the real widget.
    context.save()
    scale=min(width/config['width'],height/config['height'])
    dx=(width-config['width']*scale)/2;dy=(height-config['height']*scale)/2
    context.translate(dx,dy);context.scale(scale,scale)
    w,h=config['width'],config['height'];border=config['border_width']
    rounded(context,border/2,border/2,w-border,h-border,config['radius'])
    context.set_source_rgba(*rgba(config['background_color']));context.fill_preserve()
    if border:
        context.set_source_rgba(*rgba(config['border_color']));context.set_line_width(border);context.stroke()
    else:context.new_path()
    rows=model.lines(config,payload,error,now);layouts=[];available=w-36-border*2
    previous=None
    for kind,text in rows:
        layout=PangoCairo.create_layout(context)
        description=Pango.FontDescription(config[kind+'_font'])
        size=config[kind+'_size']
        description.set_absolute_size(size*Pango.SCALE);layout.set_font_description(description);layout.set_text(text,-1)
        tw,th=layout.get_pixel_size()
        if tw>available:
            description.set_absolute_size(max(6,size*available/tw)*Pango.SCALE)
            layout.set_font_description(description);tw,th=layout.get_pixel_size()
        gap=14 if previous and kind!=previous else (1 if kind=='weather' else 10)
        layouts.append((kind,layout,tw,th,gap if previous else 0));previous=kind
    total=sum(th+gap for _,_,_,th,gap in layouts)
    content_height=h-26  # Reserve the bottom strip for the in-widget brand link.
    vertical=min(1,(content_height-36-border*2)/max(1,total))
    y=(content_height-total*vertical)/2
    regions={}
    for kind,layout,tw,th,gap in layouts:
        y+=gap*vertical
        left,top=dx,dy+y*scale
        bottom=top+th*vertical*scale
        if kind in regions:
            old=regions[kind];regions[kind]=(left,old[1],w*scale,bottom-old[1])
        else:regions[kind]=(left,top,w*scale,bottom-top)
        context.save()
        context.translate((w-tw*vertical)/2,y);context.scale(vertical,vertical)
        context.set_source_rgba(*rgba(config[kind+'_color']));PangoCairo.show_layout(context,layout)
        context.restore();y+=th*vertical
    context.restore()
    return regions


class WidgetPreview(Gtk.DrawingArea):
    def __init__(self,config=None):
        super().__init__();self.config=config or model.validate({});self.payload=None;self.error=False
        self.set_size_request(320,250);self.connect('draw',self.paint)
    def paint(self,widget,context):
        # Checkerboard makes background opacity visible in both GTK themes.
        width,height=self.get_allocated_width(),self.get_allocated_height()
        for x in range(0,width,16):
            for y in range(0,height,16):
                shade=.20 if (x//16+y//16)%2 else .26
                context.set_source_rgb(shade,shade,shade);context.rectangle(x,y,16,16);context.fill()
        context.translate(8,8)
        draw(context,self.config,width-16,height-16,self.payload,self.error)
        return True
