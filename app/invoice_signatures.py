"""PDF versions presented by the user as signed; no signature verification."""
from ui_language import ui as _i18n
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
import uuid
import invoice_history as history

STATUS = 'imported_pending_validation'
STATUS_LABEL = 'Importada, validação pendente'


def _directory(root,invoice_id,create=False):
    directory = root/history._id(invoice_id)/'versions'
    if directory.is_symlink():
        raise _i18n.exception(ValueError, 'domain.invoice_signatures.symlinked_versions_folder_refused')
    if create:
        directory.mkdir(exist_ok=True,mode=0o700)
        directory.chmod(0o700)
    if directory.exists() and not directory.is_dir():
        raise _i18n.exception(ValueError, 'domain.invoice_signatures.invalid_versions_folder')
    return directory


def _metadata(invoice_id,identity,original_hash,pdf,created_at):
    return dict(version=1,id=identity,invoice_id=invoice_id,original_pdf_sha256=original_hash,
                pdf_sha256=hashlib.sha256(pdf).hexdigest(),pdf_size=len(pdf),created_at=created_at,
                status=STATUS,status_label=STATUS_LABEL)


def _get(directory,invoice_id,version_id,original_hash,verify_pdf=True):
    version_id = history._id(version_id)
    child = directory/version_id
    if child.is_symlink() or not child.is_dir():
        raise _i18n.exception(ValueError, 'domain.invoice_signatures.invalid_version_directory')
    if {path.name for path in child.iterdir()} != {'metadata.json','invoice.pdf'}:
        raise _i18n.exception(ValueError, 'domain.invoice_signatures.unexpected_version_contents_files_preserved')
    data = json.loads(history._read(child/'metadata.json',history.MAX_METADATA))
    if not isinstance(data,dict) or data.get('id')!=version_id or data.get('invoice_id')!=invoice_id or type(data.get('version')) is not int or data['version']!=1:
        raise _i18n.exception(ValueError, 'domain.invoice_signatures.invalid_version_metadata')
    if datetime.fromisoformat(data['created_at']).tzinfo is None:
        raise _i18n.exception(ValueError, 'domain.invoice_signatures.invalid_import_date')
    if type(data.get('pdf_size')) is not int or not 0<data['pdf_size']<=history.MAX_PDF or not isinstance(data.get('pdf_sha256'),str) or not re.fullmatch('[0-9a-f]{64}',data['pdf_sha256']):
        raise _i18n.exception(ValueError, 'domain.invoice_signatures.invalid_version_pdf_metadata')
    if verify_pdf:
        pdf = history._read(child/'invoice.pdf',history.MAX_PDF)
        if not pdf.startswith(b'%PDF-'):
            raise _i18n.exception(ValueError, 'domain.invoice_signatures.invalid_version_file')
        expected = _metadata(invoice_id,version_id,original_hash,pdf,data['created_at'])
    else:
        info = (child/'invoice.pdf').lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_size!=data['pdf_size']:
            raise _i18n.exception(ValueError, 'domain.invoice_signatures.invalid_version_file')
        pdf = None
        expected = _metadata(invoice_id,version_id,original_hash,b'',data['created_at'])
        expected.update(pdf_size=data['pdf_size'],pdf_sha256=data['pdf_sha256'])
    if data!=expected:
        raise _i18n.exception(ValueError, 'domain.invoice_signatures.invalid_version_integrity_no_signature_has_been_validated')
    return data,pdf


def import_version(invoice_id,pdf_path,*,root=None):
    history._id(invoice_id)
    source = Path(pdf_path).expanduser().absolute()
    if source.resolve().is_relative_to(history._root(root)):
        raise _i18n.exception(ValueError, 'domain.invoice_signatures.select_a_copy_outside_managed_storage')
    pdf = history._read(source,history.MAX_PDF)
    if not pdf.startswith(b'%PDF-'):
        raise _i18n.exception(ValueError, 'domain.invoice_signatures.the_selected_file_does_not_contain_a_valid_pdf')
    with history._locked(root) as folder:
        original,_ = history._get(folder,invoice_id)
        directory = _directory(folder,invoice_id,create=True)
        for _ in range(8):
            identity = uuid.uuid4().hex
            if not os.path.lexists(directory/identity):break
        else:
            raise _i18n.exception(RuntimeError, 'domain.invoice_signatures.could_not_create_a_unique_version_identity')
        data = _metadata(invoice_id,identity,original['pdf_sha256'],pdf,datetime.now(timezone.utc).isoformat())
        with tempfile.TemporaryDirectory(prefix='.version-',dir=directory) as temporary:
            stage = Path(temporary)/identity
            stage.mkdir(mode=0o700)
            history._write(stage/'invoice.pdf',pdf)
            history._write(stage/'metadata.json',json.dumps(data,ensure_ascii=False,indent=2).encode('utf-8'))
            history._sync(stage)
            if os.path.lexists(directory/identity):
                raise _i18n.exception(FileExistsError, 'domain.invoice_signatures.version_identity_already_exists_previous_files_preserved')
            os.rename(stage,directory/identity)
            history._sync(directory)
        return data


def list_versions(invoice_id,*,root=None):
    history._id(invoice_id)
    versions,errors = [],[]
    with history._locked(root) as folder:
        original,_ = history._get(folder,invoice_id,verify_pdf=False)
        try:directory = _directory(folder,invoice_id)
        except (ValueError,OSError):
            return dict(versions=[],errors=[dict(id='',message='Pasta de versões indisponível; original preservado.')])
        if not directory.exists():return dict(versions=[],errors=[])
        for child in sorted(directory.iterdir()):
            try:
                versions.append(_get(directory,invoice_id,child.name,original['pdf_sha256'],verify_pdf=False)[0])
            except (ValueError,KeyError,TypeError,OSError,UnicodeError):
                errors.append(dict(id=child.name if re.fullmatch('[0-9a-f]{32}',child.name) else '',message='Versão indisponível; original e arquivos preservados.'))
    versions.sort(key=lambda version:(version['created_at'],version['id']),reverse=True)
    return dict(versions=versions,errors=errors)


def get(invoice_id,version_id,*,root=None):
    history._id(invoice_id);history._id(version_id)
    with history._locked(root) as folder:
        original,_ = history._get(folder,invoice_id,verify_pdf=False)
        return _get(_directory(folder,invoice_id),invoice_id,version_id,original['pdf_sha256'])[0]


def resolve_pdf(invoice_id,version_id,*,root=None):
    history._id(invoice_id);history._id(version_id)
    with history._locked(root) as folder:
        original,_ = history._get(folder,invoice_id,verify_pdf=False)
        directory = _directory(folder,invoice_id)
        _get(directory,invoice_id,version_id,original['pdf_sha256'])
        return directory/version_id/'invoice.pdf'


get_path = resolve_pdf


def export_copy(invoice_id,version_id,target,*,overwrite=False,root=None):
    history._id(invoice_id);history._id(version_id)
    with history._locked(root) as folder:
        original,_ = history._get(folder,invoice_id,verify_pdf=False)
        data,pdf = _get(_directory(folder,invoice_id),invoice_id,version_id,original['pdf_sha256'])
        return history._export_bytes(pdf,target,overwrite=overwrite,root=root)


def delete(invoice_id,version_id,*,root=None):
    history._id(invoice_id);history._id(version_id)
    with history._locked(root) as folder:
        original,_ = history._get(folder,invoice_id,verify_pdf=False)
        directory = _directory(folder,invoice_id)
        _get(directory,invoice_id,version_id,original['pdf_sha256'])
        deleted = directory/('.deleted-'+version_id)
        if os.path.lexists(deleted):
            raise _i18n.exception(ValueError, 'domain.invoice_signatures.previous_deletion_pending_version_preserved')
        os.rename(directory/version_id,deleted)
        history._sync(directory)
        try:
            shutil.rmtree(deleted)
            history._sync(directory)
        except OSError:
            raise _i18n.exception(OSError, 'domain.invoice_signatures.version_removed_from_the_list_private_cleanup_pending_original_an') from None

# UI vocabulary aliases; all keep the same conservative storage semantics.
add_version = import_version
resolve_version = resolve_pdf
export_version = export_copy
