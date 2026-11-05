"""Reviewable service invoices from completed local timesheet entries; no I/O."""
from ui_language import ui as _i18n
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
import re
import timesheet
import sheet_context


def text(value, label, maximum):
    if not isinstance(value, str) or not 0 < len(value.strip()) <= maximum:
        raise _i18n.exception(ValueError, 'domain.invoice.required_field', label=label)
    if any(ord(c) < 32 and c not in '\n\t' for c in value):
        raise _i18n.exception(ValueError, 'domain.invoice.invalid_field_controls', label=label)
    return value.strip()


def tax_id(value):
    value = text(value, 'CPF/CNPJ', 18).upper()
    if not any(re.fullmatch(pattern, value, re.ASCII) for pattern in (
        r'[0-9]{11}', r'[A-Z0-9]{12}[0-9]{2}', r'[0-9]{3}\.[0-9]{3}\.[0-9]{3}-[0-9]{2}',
        r'[A-Z0-9]{2}\.[A-Z0-9]{3}\.[A-Z0-9]{3}/[A-Z0-9]{4}-[0-9]{2}',
    )):
        raise _i18n.exception(ValueError, 'domain.invoice.enter_a_cpf_with_11_digits_or_a_cnpj_with_12_alphanumeric_positio')
    return value


def party(value, client=False):
    if not isinstance(value, dict):
        raise _i18n.exception(ValueError, 'domain.invoice.invalid_issuer_client_data')
    result = {'name':text(value.get('name'), _i18n.msg('domain.invoice.field_name'), 200), 'tax_id':tax_id(value.get('tax_id'))}
    if client:
        result['address'] = text(value.get('address'), _i18n.msg('domain.invoice.field_tax_address'), 2000)
    return result


def parse_rate(value):
    # One decimal separator and up to cents: grouped thousands are never inferred.
    if isinstance(value, Decimal):
        value = str(value)
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]{1,12}(?:[.,][0-9]{1,2})?', value.strip()):
        raise _i18n.exception(ValueError, 'domain.invoice.use_a_positive_rate_without_thousands_separators_with_up_to_two_d')
    try:
        amount = Decimal(value.strip().replace(',', '.'))
    except InvalidOperation:
        raise _i18n.exception(ValueError, 'domain.invoice.invalid_hourly_rate') from None
    if not amount.is_finite() or amount <= 0:
        raise _i18n.exception(ValueError, 'domain.invoice.the_hourly_rate_must_be_positive_and_finite')
    return amount


def validate_profile(profile):
    if not isinstance(profile, dict):
        raise _i18n.exception(ValueError, 'domain.invoice.invalid_invoice_profile')
    currency = profile.get('currency', 'BRL')
    if not isinstance(currency, str) or not re.fullmatch(r'[A-Za-z]{3}', currency):
        raise _i18n.exception(ValueError, 'domain.invoice.enter_a_three_letter_currency_for_example_brl_or_usd')
    language = profile.get('language', 'pt')
    if language not in ('pt', 'en'):
        raise _i18n.exception(ValueError, 'domain.invoice.invalid_invoice_language')
    return dict(issuer=party(profile.get('issuer')), client=party(profile.get('client'), True),
                rate=format(parse_rate(profile.get('rate')), '.2f'), currency=currency.upper(), language=language)


def iso_date(value):
    try:
        if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
            raise ValueError()
    except ValueError:
        raise _i18n.exception(ValueError, 'domain.invoice.use_a_valid_date_in_yyyy_mm_dd_format') from None
    return value


def build_snapshot(sheet, *, issuer, client, rate, reference, issued_on,
                   currency='BRL', language='pt', start=None, end=None):
    profile = validate_profile(dict(issuer=issuer, client=client, rate=rate, currency=currency, language=language))
    reference = text(reference, _i18n.msg('domain.invoice.field_reference'), 100)
    issued_on = iso_date(issued_on)
    if not isinstance(sheet, dict) or not isinstance(sheet.get('timesheet'), list):
        raise _i18n.exception(ValueError, 'domain.invoice.invalid_timesheet')
    identity = text(sheet.get('id'), _i18n.msg('domain.invoice.field_sheet_identity'), 200)
    name = text(sheet.get('name'), _i18n.msg('domain.invoice.field_sheet_name'), 200)
    all_history = start is None and end is None
    if not all_history:
        start, end = iso_date(start), iso_date(end)
        if start > end:
            raise _i18n.exception(ValueError, 'domain.invoice.the_period_end_must_be_on_or_after_its_start')
    entries = []
    source_ids = {}
    for entry in sheet['timesheet']:
        value = timesheet.validate_activity(entry)
        value['description'] = text(value['description'], _i18n.msg('domain.invoice.field_description'), 1000)
        if all_history or start <= value['date'] <= end:
            item=dict(value, minutes=timesheet.activity_minutes(value))
            source_ids[id(item)]=entry.get('id')
            entries.append(item)
    entries.sort(key=lambda entry:(entry['date'],entry['start']))
    if not entries:
        raise _i18n.exception(ValueError, 'domain.invoice.no_completed_entries_in_the_selected_period')
    minutes = sum(entry['minutes'] for entry in entries)
    with localcontext() as context:
        context.prec = 50
        total = (Decimal(minutes) * Decimal(profile['rate']) / Decimal(60)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
    if all_history:
        start, end = entries[0]['date'], entries[-1]['date']
    warnings = ['Cronômetro ativo ignorado; somente registros concluídos entram na fatura.'] if sheet.get('timesheet_active') else []
    extra = {}
    context=sheet_context.validate(sheet.get('context'))
    if any(context.values()):extra['context']=context
    if all(isinstance(source_ids[id(e)],str) and 0<len(source_ids[id(e)])<=200 for e in entries):
        extra['source_entries']=[dict(id=source_ids[id(e)],**{k:e[k] for k in ('date','start','end')}) for e in entries]
    return dict(version=1, **extra, sheet_id=identity, sheet_name=name, reference=reference, issued_on=issued_on,
                **profile, minutes=minutes, hours=f'{minutes//60:02d}:{minutes%60:02d}', total=format(total,'.2f'),
                period=dict(start=start,end=end,all_history=all_history), entries=entries, warnings=warnings)


def prepare(data, sheet_id, **kwargs):
    if not isinstance(data, dict) or not isinstance(data.get('timesheets'), list):
        raise _i18n.exception(ValueError, 'domain.invoice.invalid_timesheet_data')
    if any(not isinstance(sheet,dict) for sheet in data['timesheets']):
        raise _i18n.exception(ValueError, 'domain.invoice.invalid_timesheet_data')
    sheet = next((sheet for sheet in data['timesheets'] if sheet.get('id') == sheet_id), None)
    if sheet is None:
        raise _i18n.exception(ValueError, 'domain.invoice.timesheet_not_found_refresh_the_workspace')
    return build_snapshot(sheet, **kwargs)


def validate_snapshot(snapshot):
    if not isinstance(snapshot, dict) or snapshot.get('version') != 1 or not isinstance(snapshot.get('period'), dict):
        raise _i18n.exception(ValueError, 'domain.invoice.invalid_invoice_preview')
    if type(snapshot.get('minutes')) is not int:
        raise _i18n.exception(ValueError, 'domain.invoice.invalid_preview_minutes')
    period = snapshot['period']
    if type(period.get('all_history')) is not bool:
        raise _i18n.exception(ValueError, 'domain.invoice.invalid_preview_period')
    rebuilt = build_snapshot(dict(id=snapshot.get('sheet_id'), name=snapshot.get('sheet_name'), timesheet=snapshot.get('entries')),
                             issuer=snapshot.get('issuer'), client=snapshot.get('client'), rate=snapshot.get('rate'),
                             currency=snapshot.get('currency'), language=snapshot.get('language'),
                             reference=snapshot.get('reference'), issued_on=snapshot.get('issued_on'),
                             start=None if period['all_history'] else period.get('start'), end=None if period['all_history'] else period.get('end'))
    for key in ('minutes','hours','total','entries','period'):
        if snapshot.get(key) != rebuilt[key]:
            raise _i18n.exception(ValueError, 'domain.invoice.the_invoice_preview_changed_review_it_again_before_exporting')
    if 'context' in snapshot:
        rebuilt['context']=sheet_context.validate(snapshot['context'])
    if 'source_entries' in snapshot:
        sources=snapshot['source_entries']
        if not isinstance(sources,list) or len(sources)!=len(rebuilt['entries']):raise _i18n.exception(ValueError, 'domain.invoice.invalid_activity_source')
        for source,entry in zip(sources,rebuilt['entries']):
            if not isinstance(source,dict) or set(source)!={'id','date','start','end'} or not isinstance(source.get('id'),str) or not 0<len(source['id'])<=200 or any(source[k]!=entry[k] for k in ('date','start','end')):
                raise _i18n.exception(ValueError, 'domain.invoice.invalid_activity_source')
        rebuilt['source_entries']=[dict(source) for source in sources]
    return rebuilt


def format_money(value, language='pt'):
    result = format(Decimal(value), '.2f')
    return result.replace('.', ',') if language == 'pt' else result
