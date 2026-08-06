"""A5 audit hook: record project-local file opens without absolute paths."""
from __future__ import annotations

import json
import os
import sys
import threading
from datetime import UTC, datetime
from pathlib import Path


_root_value = os.environ.get("P4_A5_PROJECT_ROOT")
_log_value = os.environ.get("P4_A5_ACCESS_LOG")
_root = Path(_root_value).resolve() if _root_value else None
_log = Path(_log_value).resolve() if _log_value else None
_guard = threading.local()


def _audit(event: str, args: tuple[object, ...]) -> None:
    if event != "open" or _root is None or _log is None or getattr(_guard, "active", False):
        return
    value = args[0] if args else None
    if not isinstance(value, (str, bytes, os.PathLike)):
        return
    try:
        path = Path(os.fsdecode(value))
        resolved = (Path.cwd() / path).resolve() if not path.is_absolute() else path.resolve()
        relative = resolved.relative_to(_root).as_posix()
    except (OSError, ValueError):
        return
    if resolved == _log:
        return
    record = {
        "event": "open",
        "path": relative,
        "mode": str(args[1]) if len(args) > 1 else "",
        "atUtc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
    data = (json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    _guard.active = True
    try:
        descriptor = os.open(_log, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
        try:
            os.write(descriptor, data)
        finally:
            os.close(descriptor)
    finally:
        _guard.active = False


sys.addaudithook(_audit)
