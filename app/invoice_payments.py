"""Manual payment reports, separate from immutable invoices and signatures."""
from ui_language import ui as _i18n
from datetime import datetime,timezone
import json
import os
import atomic_json
import invoice_history as history


def _read(folder,identity):
    path=folder/identity/'payment.json'
    if not os.path.lexists(path):return dict(status='not_reported',updated_at=None)
    value=json.loads(history._read(path,32768))
    if not isinstance(value,dict) or set(value)!={'version','invoice_id','status','updated_at'} or type(value['version']) is not int or value['version']!=1 or value['invoice_id']!=identity or value['status'] not in ('not_reported','reported_paid') or not isinstance(value['updated_at'],str) or datetime.fromisoformat(value['updated_at']).tzinfo is None:
        raise _i18n.exception(ValueError, 'domain.invoice_payments.invalid_manual_payment_status_file_preserved')
    return {key:value[key] for key in ('status','updated_at')}


def get(identity,*,root=None):
    history._id(identity)
    with history._locked(root) as folder:
        history._get(folder,identity,verify_pdf=False)
        return _read(folder,identity)


def set_paid(identity,paid,*,root=None):
    history._id(identity)
    if type(paid) is not bool:raise _i18n.exception(ValueError, 'domain.invoice_payments.invalid_manual_payment_confirmation')
    with history._locked(root) as folder:
        history._get(folder,identity,verify_pdf=False)
        _read(folder,identity)
        value=dict(version=1,invoice_id=identity,status='reported_paid' if paid else 'not_reported',updated_at=datetime.now(timezone.utc).isoformat())
        atomic_json.write(folder/identity/'payment.json',value,prefix='.payment-',encoding='utf-8')
        return {key:value[key] for key in ('status','updated_at')}
