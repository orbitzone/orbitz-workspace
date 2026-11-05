"""Private, atomic PT/EN service invoice PDFs, with embedded Unicode fonts."""
from ui_language import ui as _i18n
import os
from pathlib import Path
import stat
import tempfile
import threading
from xml.sax.saxutils import escape
import invoice

_FONT_LOCK = threading.Lock()
LABELS = {
    'pt':dict(title='Fatura de serviços',reference='Referência',issued='Data de emissão',period='Período',all_history='Todo o histórico',issuer='Emitente',client='Cliente',address='Endereço fiscal',sheet='Timesheet',hours='Horas',rate='Valor por hora',total='Total',activities='Atividades concluídas',date='Data / horário',description='Descrição',duration='Duração',footer='Fatura de serviços - não é documento fiscal eletrônico.',page='Página'),
    'en':dict(title='Service invoice',reference='Reference',issued='Issue date',period='Period',all_history='All history',issuer='Issuer',client='Client',address='Billing address',sheet='Timesheet',hours='Hours',rate='Hourly rate',total='Total',activities='Completed activities',date='Date / time',description='Description',duration='Duration',footer='Service invoice - not an electronic tax document.',page='Page'),
}


def fonts():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    with _FONT_LOCK:
        if 'OrbitzInvoice' not in pdfmetrics.getRegisteredFontNames():
            folder = Path('/usr/share/fonts/truetype/dejavu')
            if not (folder/'DejaVuSans.ttf').is_file() or not (folder/'DejaVuSans-Bold.ttf').is_file():
                raise _i18n.exception(ValueError, 'domain.invoice_pdf.dejavu_sans_font_unavailable_install_fonts_dejavu_core')
            pdfmetrics.registerFont(TTFont('OrbitzInvoice',str(folder/'DejaVuSans.ttf')))
            pdfmetrics.registerFont(TTFont('OrbitzInvoiceBold',str(folder/'DejaVuSans-Bold.ttf')))
            pdfmetrics.registerFontFamily('OrbitzInvoice',normal='OrbitzInvoice',bold='OrbitzInvoiceBold',italic='OrbitzInvoice',boldItalic='OrbitzInvoiceBold')
    return pdfmetrics.getFont('OrbitzInvoice').face.charWidths


def _build(snapshot, stream):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, LongTable, Table, TableStyle
    glyphs = fonts()
    for value in (snapshot['reference'],snapshot['sheet_name'],snapshot['issuer']['name'],snapshot['client']['name'],snapshot['client']['address'],*(entry['description'] for entry in snapshot['entries']),*snapshot.get('context',{}).values()):
        if any(ord(character) not in glyphs and character not in '\n\t' for character in value):
            raise _i18n.exception(ValueError, 'domain.invoice_pdf.the_text_contains_characters_unsupported_by_the_pdf_font_review_b')
    labels = LABELS[snapshot['language']]
    base = ParagraphStyle('Body',fontName='OrbitzInvoice',fontSize=9,leading=14,spaceAfter=6,splitLongWords=True)
    title = ParagraphStyle('Title',parent=base,fontName='OrbitzInvoiceBold',fontSize=24,leading=30,spaceAfter=14)
    heading = ParagraphStyle('Heading',parent=base,fontName='OrbitzInvoiceBold',fontSize=11,leading=16,spaceBefore=12,spaceAfter=6)
    numeric = ParagraphStyle('Numeric',parent=base,alignment=TA_RIGHT)
    def paragraph(value,style=base):
        return Paragraph(escape(str(value)).replace('\n','<br/>'),style)
    def money(value):
        return snapshot['currency'] + ' ' + invoice.format_money(value,snapshot['language'])
    story = [paragraph(labels['title'],title),paragraph(labels['reference']+': '+snapshot['reference']),
             paragraph(labels['issued']+': '+snapshot['issued_on']),paragraph(labels['sheet']+': '+snapshot['sheet_name'])]
    context_labels = {'pt':dict(client_name='Cliente/destinatário (contexto)',project_contract='Contrato / projeto',department_costcenter='Departamento / centro de custo'), 'en':dict(client_name='Client/recipient (context)',project_contract='Contract / project',department_costcenter='Department / cost center')}
    for key,value in snapshot.get('context',{}).items():
        if value:story.append(paragraph(context_labels[snapshot['language']][key]+': '+value))
    period = snapshot['period']
    period_text = period['start']+' - '+period['end']
    if period['all_history']:
        period_text = labels['all_history']+' ('+period_text+')'
    story.append(paragraph(labels['period']+': '+period_text))
    for key in ('issuer','client'):
        party = snapshot[key]
        story.extend([paragraph(labels[key],heading),paragraph(party['name']),paragraph('CPF/CNPJ: '+party['tax_id'])])
        if key == 'client':
            story.extend([paragraph(labels['address'],heading),paragraph(party['address'])])
    story.append(Spacer(1,12))
    summary = Table([[paragraph(labels['hours']),paragraph(snapshot['hours'],numeric)],
                     [paragraph(labels['rate']),paragraph(money(snapshot['rate']),numeric)],
                     [paragraph(labels['total'],heading),paragraph(money(snapshot['total']),heading)]], colWidths=[260,251])
    summary.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),colors.HexColor('#eef3f7')),('LEFTPADDING',(0,0),(-1,-1),12),('RIGHTPADDING',(0,0),(-1,-1),12),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),5),('VALIGN',(0,0),(-1,-1),'TOP')]))
    story.extend([summary,paragraph(labels['activities'],heading)])
    rows = [[paragraph(labels['date']),paragraph(labels['description']),paragraph(labels['duration'])]]
    for entry in snapshot['entries']:
        remaining = paragraph(entry['description'])
        chunks = []
        # ReportLab 3.6.8 cannot split a table row. Split its Paragraph first,
        # preserving every fragment while keeping each row comfortably page-sized.
        while True:
            parts = remaining.split(323, 280)
            if not parts:
                raise _i18n.exception(ValueError, 'domain.invoice_pdf.could_not_paginate_the_activity_description')
            chunks.append(parts[0])
            if len(parts) == 1:
                break
            remaining = parts[1]
        for index, description in enumerate(chunks):
            when = entry['date']+'\n'+entry['start']+' - '+entry['end'] if index == 0 else ('Continuação' if snapshot['language']=='pt' else 'Continued')
            duration = f"{entry['minutes']//60:02d}:{entry['minutes']%60:02d}" if index == 0 else ''
            rows.append([paragraph(when),description,paragraph(duration,numeric)])
    activities = LongTable(rows,colWidths=[100,335,76],repeatRows=1,splitByRow=1,hAlign='LEFT')
    activities.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#eef3f7')),('LINEBELOW',(0,0),(-1,0),0.6,colors.HexColor('#a9b6c3')),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),6),('RIGHTPADDING',(0,0),(-1,-1),6),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6),('LINEBELOW',(0,1),(-1,-1),0.2,colors.HexColor('#dce3e8'))]))
    story.append(activities)
    def page(canvas,document):
        canvas.saveState()
        canvas.setFont('OrbitzInvoice',7)
        canvas.setFillColor(colors.HexColor('#52606d'))
        canvas.drawString(42,25,labels['footer'])
        canvas.drawRightString(A4[0]-42,25,labels['page']+' '+str(document.page))
        canvas.restoreState()
    document = SimpleDocTemplate(stream,pagesize=A4,leftMargin=42,rightMargin=42,topMargin=38,bottomMargin=45,title=labels['title'],author='Orbitz Workspace',allowSplitting=True)
    document.build(story,onFirstPage=page,onLaterPages=page)


def _stamp(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise _i18n.exception(ValueError, 'domain.invoice_pdf.the_pdf_destination_must_be_a_regular_file_without_a_symlink')
    return info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns


def write(snapshot, path, *, overwrite=False):
    snapshot = invoice.validate_snapshot(snapshot)
    path = Path(path).expanduser().absolute()
    if path.suffix.lower() != '.pdf':
        raise _i18n.exception(ValueError, 'domain.invoice_pdf.choose_a_file_with_a_pdf_extension')
    if type(overwrite) is not bool:
        raise _i18n.exception(ValueError, 'domain.invoice_pdf.invalid_overwrite_confirmation')
    previous = None
    if path.exists() or path.is_symlink():
        if not overwrite:
            raise _i18n.exception(FileExistsError, 'domain.invoice_pdf.the_pdf_already_exists_confirm_replacement_in_the_interface')
        previous = _stamp(path)
    fd, temporary = tempfile.mkstemp(prefix='.invoice-',suffix='.pdf',dir=path.parent)
    try:
        with os.fdopen(fd,'w+b') as stream:
            os.fchmod(stream.fileno(),0o600)
            _build(snapshot,stream)
            stream.flush()
            os.fsync(stream.fileno())
        if previous is not None:
            if _stamp(path) != previous:
                raise _i18n.exception(FileExistsError, 'domain.invoice_pdf.the_file_changed_during_generation_replacement_cancelled')
            os.replace(temporary,path)
        else:
            # Atomic no-clobber publication, including a target created during rendering.
            os.link(temporary,path)
        directory = os.open(path.parent,os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return path


render_pdf = write
