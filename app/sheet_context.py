"""Optional non-fiscal timesheet context, independent from invoice profiles."""
from ui_language import ui as _i18n
FIELDS = ('client_name','project_contract','department_costcenter')


def validate(value):
    if value is None:return {key:'' for key in FIELDS}
    if not isinstance(value,dict) or set(value)-set(FIELDS):
        raise _i18n.exception(ValueError, 'domain.sheet_context.invalid_timesheet_context')
    result = {}
    for key in FIELDS:
        item = value.get(key,'')
        if not isinstance(item,str) or len(item.strip())>200 or any(ord(c)<32 for c in item):
            raise _i18n.exception(ValueError, 'domain.sheet_context.context_fields_must_have_up_to_200_characters_without_control_cha')
        result[key] = item.strip()
    return result


def name(value):
    if not isinstance(value,str) or not 0<len(value.strip())<=80 or any(ord(c)<32 for c in value):
        raise _i18n.exception(ValueError, 'domain.sheet_context.enter_a_timesheet_name_of_up_to_80_characters')
    return value.strip()
