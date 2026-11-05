"""Durable JSON replacement; callers retain their locking and backup policies."""
import contextlib
import json
import os
import tempfile


def write(path, data, *, prefix, suffix='', indent=None, encoding=None):
    """Replace a file only after serialization and fsync of its private temporary."""
    fd, temporary = tempfile.mkstemp(prefix=prefix, suffix=suffix, dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding=encoding) as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump(data, stream, ensure_ascii=False, indent=indent)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary)
