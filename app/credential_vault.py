"""iCloud credentials stored exclusively in the desktop Secret Service."""
from ui_language import ui as _i18n

class Vault:
    """Passwords live exclusively in the desktop Secret Service."""
    def _service(self):
        import gi
        gi.require_version('Secret','1');from gi.repository import Secret
        schema=Secret.Schema.new('io.orbitz.Workspace.iCloud',Secret.SchemaFlags.NONE,{'account':Secret.SchemaAttributeType.STRING})
        return Secret,schema
    def put(self,identity,password):
        Secret,schema=self._service()
        if not Secret.password_store_sync(schema,{'account':identity},Secret.COLLECTION_DEFAULT,'Orbitz Workspace · Calendário iCloud',password,None):
            raise _i18n.exception(ValueError, 'domain.credential_vault.could_not_store_the_password_in_the_system_vault')
    def get(self,identity):
        Secret,schema=self._service();password=Secret.password_lookup_sync(schema,{'account':identity},None)
        if not password:raise _i18n.exception(ValueError, 'domain.credential_vault.the_calendar_password_is_unavailable_in_the_vault_unlock_the_vaul')
        return password
    def delete(self,identity):
        Secret,schema=self._service();Secret.password_clear_sync(schema,{'account':identity},None)


class ProviderVault:
    """OAuth/PAT material stays in a separate Secret Service schema, never JSON caches."""
    def _service(self):
        import gi
        gi.require_version('Secret','1')
        from gi.repository import Secret
        schema=Secret.Schema.new('io.orbitz.Workspace.Provider',Secret.SchemaFlags.NONE,
                                 {'account':Secret.SchemaAttributeType.STRING,'provider':Secret.SchemaAttributeType.STRING})
        return Secret,schema

    def _attributes(self,provider,identity):
        import re
        from calendar_events import CalendarError
        if provider not in ('google','calendly') or not isinstance(identity,str) or not re.fullmatch(provider+r'-[0-9a-f]{64}',identity):
            raise _i18n.exception(CalendarError, 'domain.credential_vault.invalid_credential_identity')
        return dict(provider=provider,account=identity)

    def put(self,provider,identity,payload):
        import json
        from calendar_events import CalendarError
        attributes=self._attributes(provider,identity)
        if not isinstance(payload,dict):raise _i18n.exception(CalendarError, 'domain.credential_vault.invalid_provider_credential')
        value=json.dumps(payload,ensure_ascii=False)
        if len(value)>65536:raise _i18n.exception(CalendarError, 'domain.credential_vault.provider_credential_exceeds_the_limit')
        Secret,schema=self._service()
        try:
            if not Secret.password_store_sync(schema,attributes,Secret.COLLECTION_DEFAULT,'Orbitz Workspace · Calendário '+provider,value,None):raise ValueError()
        except Exception:raise _i18n.exception(CalendarError, 'domain.credential_vault.could_not_store_authorization_in_the_system_vault') from None

    def get(self,provider,identity):
        import json
        from calendar_events import CalendarError
        attributes=self._attributes(provider,identity);Secret,schema=self._service()
        try:
            value=Secret.password_lookup_sync(schema,attributes,None)
            if not value or len(value)>65536:raise ValueError()
            result=json.loads(value)
            if not isinstance(result,dict):raise ValueError()
            return result
        except Exception:raise _i18n.exception(CalendarError, 'domain.credential_vault.authorization_unavailable_in_the_vault_unlock_it_or_reconnect_the') from None

    def delete(self,provider,identity):
        from calendar_events import CalendarError
        attributes=self._attributes(provider,identity);Secret,schema=self._service()
        try:Secret.password_clear_sync(schema,attributes,None)
        except Exception:raise _i18n.exception(CalendarError, 'domain.credential_vault.could_not_remove_authorization_from_the_vault') from None
