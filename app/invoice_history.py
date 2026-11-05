"""Private immutable invoice copies; no index and no access to prior user PDFs."""
from ui_language import ui as _i18n
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
import uuid
import invoice

ROOT = Path(os.environ.get('XDG_DATA_HOME') or Path.home()/'.local/share')/'orbitz-workspace/invoices'
MAX_PDF = 128 * 1024 * 1024
MAX_METADATA = 4 * 1024 * 1024


def _id(value):
    if not isinstance(value,str) or not re.fullmatch('[0-9a-f]{32}',value):
        raise _i18n.exception(ValueError, 'domain.invoice_history.invalid_invoice_record_identity')
    return value


def _root(root):
    path = Path(root) if root is not None else ROOT
    path = path.absolute()
    if path.resolve() != path:
        raise _i18n.exception(ValueError, 'domain.invoice_history.invoice_history_does_not_accept_a_symlinked_path')
    return path


def _sync(directory):
    fd = os.open(directory,os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:os.fsync(fd)
    finally:os.close(fd)


@contextmanager
def _locked(root,create=False):
    root = _root(root)
    if create:
        root.mkdir(parents=True,exist_ok=True,mode=0o700)
        root.chmod(0o700)
    if not root.exists():
        yield None
        return
    if not root.is_dir():
        raise _i18n.exception(ValueError, 'domain.invoice_history.invalid_invoice_storage')
    try:
        fd = os.open(root/'.lock',os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK | (os.O_CREAT if create else 0),0o600)
    except FileNotFoundError:
        if any(root.iterdir()):
            raise _i18n.exception(ValueError, 'domain.invoice_history.history_lock_unavailable_records_preserved') from None
        yield root
        return
    with os.fdopen(fd,'r+') as lock:
        if not stat.S_ISREG(os.fstat(lock.fileno()).st_mode):
            raise _i18n.exception(ValueError, 'domain.invoice_history.invalid_history_lock')
        if create:os.fchmod(lock.fileno(),0o600)
        fcntl.flock(lock,fcntl.LOCK_EX)
        yield root


def _read(path,limit):
    fd = os.open(path,os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
            raise _i18n.exception(ValueError, 'domain.invoice_history.invoice_file_invalid_or_above_the_size_limit')
        value = stream.read(limit+1)
        after = os.fstat(stream.fileno())
    if len(value)>limit or (before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns) or len(value)!=after.st_size:
        raise _i18n.exception(ValueError, 'domain.invoice_history.invoice_file_changed_while_being_read')
    return value


def _write(path,value):
    fd = os.open(path,os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as stream:
        os.fchmod(stream.fileno(),0o600)
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())


def _validated_snapshot(value):
    # Metadata is an untrusted JSON boundary. The timesheet validator expects
    # mappings; reject malformed activities here rather than masking arbitrary
    # programming errors from the domain with a broad exception handler.
    if not isinstance(value,dict) or not isinstance(value.get('entries'),list) or any(not isinstance(entry,dict) for entry in value['entries']):
        raise _i18n.exception(ValueError, 'domain.invoice_history.invalid_invoice_activity_structure')
    return invoice.validate_snapshot(value)


def _metadata(identity,snapshot,pdf,created_at):
    canonical_id = re.sub('[^A-Z0-9]','',snapshot['client']['tax_id'].upper())
    client_key = hashlib.sha256(canonical_id.encode('ascii')).hexdigest()
    issued_on = snapshot['issued_on']
    return dict(version=1,id=identity,created_at=created_at,snapshot=snapshot,
                client_key=client_key,client_id=client_key,client_name=snapshot['client']['name'],
                **{key:snapshot[key] for key in ('sheet_id','sheet_name','issued_on','reference','period','hours','minutes','rate','total','currency','language')},
                issued_year=int(issued_on[:4]),issued_month=int(issued_on[5:7]),
                pdf_sha256=hashlib.sha256(pdf).hexdigest(),pdf_size=len(pdf))


def _get(root,identity,verify_pdf=True):
    identity = _id(identity)
    if root is None:
        raise _i18n.exception(FileNotFoundError, 'domain.invoice_history.invoice_record_not_found')
    directory = root/identity
    if directory.is_symlink() or not directory.is_dir():
        raise _i18n.exception(ValueError, 'domain.invoice_history.invalid_invoice_record_directory')
    names = {path.name for path in directory.iterdir()}
    if not {'metadata.json','invoice.pdf'} <= names or names - {'metadata.json','invoice.pdf','versions','payment.json'}:
        raise _i18n.exception(ValueError, 'domain.invoice_history.unexpected_record_contents_files_preserved')
    data = json.loads(_read(directory/'metadata.json',MAX_METADATA))
    if not isinstance(data,dict) or data.get('id')!=identity or type(data.get('version')) is not int or data['version']!=1:
        raise _i18n.exception(ValueError, 'domain.invoice_history.invalid_invoice_metadata')
    timestamp = datetime.fromisoformat(data['created_at'])
    if timestamp.tzinfo is None:
        raise _i18n.exception(ValueError, 'domain.invoice_history.invalid_record_date')
    snapshot = _validated_snapshot(data['snapshot'])
    if type(data.get('pdf_size')) is not int or not 0 < data['pdf_size'] <= MAX_PDF or not isinstance(data.get('pdf_sha256'),str) or not re.fullmatch('[0-9a-f]{64}',data['pdf_sha256']):
        raise _i18n.exception(ValueError, 'domain.invoice_history.invalid_pdf_metadata')
    if verify_pdf:
        pdf = _read(directory/'invoice.pdf',MAX_PDF)
        expected = _metadata(identity,snapshot,pdf,data['created_at'])
        if not pdf.startswith(b'%PDF-'):
            raise _i18n.exception(ValueError, 'domain.invoice_history.invalid_invoice_record_integrity')
    else:
        # Browsing does not load/hash the entire archive. Full verification is
        # reserved for get/open/export/delete; obvious size/type damage is flagged.
        info = (directory/'invoice.pdf').lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_size != data['pdf_size']:
            raise _i18n.exception(ValueError, 'domain.invoice_history.invalid_pdf_file')
        pdf = None
        expected = _metadata(identity,snapshot,b'',data['created_at'])
        expected.update(pdf_sha256=data['pdf_sha256'],pdf_size=data['pdf_size'])
    if data != expected:
        raise _i18n.exception(ValueError, 'domain.invoice_history.invalid_invoice_record_integrity')
    return data,pdf


def record(snapshot,pdf_path,*,root=None):
    snapshot = _validated_snapshot(snapshot)
    pdf = _read(Path(pdf_path),MAX_PDF)
    if not pdf.startswith(b'%PDF-'):
        raise _i18n.exception(ValueError, 'domain.invoice_history.the_exported_file_does_not_contain_a_valid_pdf')
    with _locked(root,create=True) as folder:
        for _ in range(8):
            identity = uuid.uuid4().hex
            if not os.path.lexists(folder/identity):break
        else:
            raise _i18n.exception(RuntimeError, 'domain.invoice_history.could_not_create_a_unique_invoice_identity')
        data = _metadata(identity,snapshot,pdf,datetime.now(timezone.utc).isoformat())
        raw = json.dumps(data,ensure_ascii=False,indent=2).encode('utf-8')
        if len(raw)>MAX_METADATA:
            raise _i18n.exception(ValueError, 'domain.invoice_history.invoice_metadata_exceeds_the_history_limit')
        with tempfile.TemporaryDirectory(prefix='.record-',dir=folder) as temporary:
            stage = Path(temporary)/identity
            stage.mkdir(mode=0o700)
            _write(stage/'invoice.pdf',pdf)
            _write(stage/'metadata.json',raw)
            _sync(stage)
            if os.path.lexists(folder/identity):
                raise _i18n.exception(FileExistsError, 'domain.invoice_history.invoice_identity_already_exists_previous_record_preserved')
            os.rename(stage,folder/identity)
            _sync(folder)
        return data


def get(identity,*,root=None):
    _id(identity)
    with _locked(root) as folder:
        return _get(folder,identity)[0]


def resolve_pdf(identity,*,root=None):
    _id(identity)
    with _locked(root) as folder:
        _get(folder,identity)
        return folder/identity/'invoice.pdf'


get_path = resolve_pdf


def list_records(*,root=None):
    records,errors = [],[]
    with _locked(root) as folder:
        if folder is None:return dict(records=[],errors=[])
        for directory in sorted(folder.iterdir()):
            if directory.name=='.lock':continue
            if directory.name.startswith(('.record-','.deleted-')):
                errors.append(dict(id='',message='Operação interrompida no histórico; arquivos preservados.'))
                continue
            try:
                _id(directory.name)
                records.append(_get(folder,directory.name,verify_pdf=False)[0])
            except (ValueError,KeyError,TypeError,OSError,UnicodeError):
                errors.append(dict(id=directory.name if re.fullmatch('[0-9a-f]{32}',directory.name) else '',message='Registro inválido ou indisponível; arquivos preservados.'))
    records.sort(key=lambda record:(record['issued_on'],record['created_at'],record['id']),reverse=True)
    return dict(records=records,errors=errors)


def _stamp(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise _i18n.exception(ValueError, 'domain.invoice_history.the_copy_destination_must_be_a_regular_file_without_a_symlink')
    return info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns


def _export_bytes(pdf,target,*,overwrite=False,root=None):
    if type(overwrite) is not bool:
        raise _i18n.exception(ValueError, 'domain.invoice_history.invalid_replacement_confirmation')
    target = Path(target).expanduser().absolute()
    if target.suffix.lower()!='.pdf':
        raise _i18n.exception(ValueError, 'domain.invoice_history.choose_a_file_with_a_pdf_extension')
    if target.resolve().is_relative_to(_root(root)):
        raise _i18n.exception(ValueError, 'domain.invoice_history.the_copy_must_be_outside_managed_storage')
    previous = None
    if target.exists() or target.is_symlink():
        if not overwrite:raise _i18n.exception(FileExistsError, 'domain.invoice_history.the_copy_already_exists_confirm_replacement_in_the_interface')
        previous = _stamp(target)
    fd,name = tempfile.mkstemp(prefix='.invoice-copy-',suffix='.pdf',dir=target.parent)
    try:
        with os.fdopen(fd,'wb') as stream:
            os.fchmod(stream.fileno(),0o600)
            stream.write(pdf);stream.flush();os.fsync(stream.fileno())
        if previous is None:
            os.link(name,target)
        else:
            if _stamp(target)!=previous:
                raise _i18n.exception(FileExistsError, 'domain.invoice_history.the_destination_changed_during_copying_existing_file_preserved')
            os.replace(name,target)
        _sync(target.parent)
    finally:Path(name).unlink(missing_ok=True)
    return target


def export_copy(identity,target,*,overwrite=False,root=None):
    _id(identity)
    with _locked(root) as folder:
        data,pdf = _get(folder,identity)
        return _export_bytes(pdf,target,overwrite=overwrite,root=root)


def _check_versions_delete(directory):
    versions = directory/'versions'
    if not os.path.lexists(versions):return
    if versions.is_symlink() or not versions.is_dir():
        raise _i18n.exception(ValueError, 'domain.invoice_history.invalid_versions_folder_original_preserved')
    for child in versions.iterdir():
        identity = child.name.removeprefix('.deleted-')
        _id(identity)
        if child.is_symlink() or not child.is_dir():
            raise _i18n.exception(ValueError, 'domain.invoice_history.invalid_version_folder_original_preserved')
        for item in child.iterdir():
            if item.name not in ('metadata.json','invoice.pdf') or not stat.S_ISREG(item.lstat().st_mode):
                raise _i18n.exception(ValueError, 'domain.invoice_history.unexpected_version_contents_original_preserved')


def delete(identity,*,root=None):
    _id(identity)
    with _locked(root) as folder:
        if folder is None:raise _i18n.exception(FileNotFoundError, 'domain.invoice_history.invoice_record_not_found')
        deleted = folder/('.deleted-'+identity)
        if deleted.exists() or deleted.is_symlink():
            raise _i18n.exception(ValueError, 'domain.invoice_history.previous_deletion_pending_files_preserved_for_recovery')
        _get(folder,identity)
        _check_versions_delete(folder/identity)
        payment=folder/identity/'payment.json'
        if os.path.lexists(payment) and not stat.S_ISREG(payment.lstat().st_mode):raise _i18n.exception(ValueError, 'domain.invoice_history.invalid_payment_status_record_preserved')
        os.rename(folder/identity,deleted)
        _sync(folder)
        try:
            shutil.rmtree(deleted)
            _sync(folder)
        except OSError:
            raise _i18n.exception(OSError, 'domain.invoice_history.record_removed_from_the_list_private_cleanup_pending_the_external') from None


def get_payment(identity,*,root=None):
    import invoice_payments
    return invoice_payments.get(identity,root=root)


def set_payment(identity,state,*,root=None):
    if state not in ('not_reported','reported_paid'):raise _i18n.exception(ValueError, 'domain.invoice_history.invalid_manual_payment_status')
    import invoice_payments
    return invoice_payments.set_paid(identity,state=='reported_paid',root=root)


def possible_duplicates(snapshot,*,root=None):
    import invoice_duplicates
    return invoice_duplicates.check(snapshot,root=root)
