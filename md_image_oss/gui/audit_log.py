"""Append-only JSONL audit log.

Records every meaningful action — config changes, batch starts, per-file
processing results, errors. Sensitive material (AccessKeys, file contents)
is never written. Files are rotated monthly so a single file stays
human-scrollable.

Storage location follows OS conventions via ``platformdirs``:
- macOS:   ~/Library/Logs/md-image-oss/
- Windows: %LOCALAPPDATA%/md-image-oss/Logs/
- Linux:   ~/.local/state/md-image-oss/log/  (XDG)
"""

from __future__ import annotations

import getpass
import json
import os
import socket
import threading
import uuid
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional

from .. import __version__


def _log_dir() -> Path:
    try:
        from platformdirs import user_log_dir
        return Path(user_log_dir("md-image-oss", "md-image-oss"))
    except ImportError:
        return Path.home() / ".md-image-oss" / "logs"


def _current_log_file() -> Path:
    d = _log_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d / f"audit-{datetime.now().strftime('%Y-%m')}.log"


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _safe_user() -> str:
    try:
        return getpass.getuser()
    except Exception:
        return "unknown"


def _safe_host() -> str:
    try:
        return socket.gethostname()
    except Exception:
        return "unknown"


class AuditLogger:
    """Thread-safe append-only JSONL logger.

    Use ``with AuditLogger.session() as audit:`` to open a session that
    auto-emits ``app_start`` / ``app_end`` events. Or just instantiate one
    directly for ad-hoc records.
    """

    _LOCK = threading.Lock()

    def __init__(self, session_id: Optional[str] = None) -> None:
        self.session_id = session_id or uuid.uuid4().hex
        self.user = _safe_user()
        self.host = _safe_host()

    # ----------------------------------------------------------------- write
    def write(self, event: str, **fields: Any) -> None:
        record = {
            "ts": _now_iso(),
            "session_id": self.session_id,
            "app_version": __version__,
            "user": self.user,
            "host": self.host,
            "event": event,
        }
        for k, v in fields.items():
            record[k] = _coerce(v)
        line = json.dumps(record, ensure_ascii=False)
        path = _current_log_file()
        with self._LOCK:
            with open(path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
                f.flush()

    # ------------------------------------------------------------ shortcuts
    def app_start(self) -> None:
        self.write("app_start")

    def app_end(self) -> None:
        self.write("app_end")

    def config_changed(self, fields_updated: list[str]) -> None:
        self.write("config_changed", fields_updated=fields_updated)

    def connection_test(self, success: bool, error: str = "") -> None:
        self.write("connection_test", status="success" if success else "error", error=error)

    def batch_start(self, files_count: int, options: Any) -> None:
        self.write("batch_start", files_count=files_count, options=_coerce(options))

    def batch_end(self, success: int, failed: int, cancelled: int, total_duration_ms: int) -> None:
        self.write(
            "batch_end",
            success=success,
            failed=failed,
            cancelled=cancelled,
            total_duration_ms=total_duration_ms,
        )

    def file_processed(
        self,
        input_path: Path,
        output_path: Optional[Path],
        mode: str,
        backup_path: Optional[Path],
        stats: dict,
        duration_ms: int,
        status: str,
        error: str = "",
    ) -> None:
        self.write(
            "file_processed",
            input=str(input_path),
            output=str(output_path) if output_path else None,
            mode=mode,
            backup=str(backup_path) if backup_path else None,
            stats=stats,
            duration_ms=duration_ms,
            status=status,
            error=error,
        )


def _coerce(value: Any) -> Any:
    """Make sure a value is JSON-serialisable."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return {k: _coerce(v) for k, v in asdict(value).items()}
    if isinstance(value, dict):
        return {str(k): _coerce(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_coerce(v) for v in value]
    return str(value)


def log_files() -> list[Path]:
    """Return all audit log files, newest first."""
    d = _log_dir()
    if not d.exists():
        return []
    return sorted(d.glob("audit-*.log"), reverse=True)


def iter_records(limit: Optional[int] = None) -> Iterator[dict]:
    """Yield audit records newest-to-oldest, across all monthly files."""
    count = 0
    for path in log_files():
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for raw in reversed(lines):
            raw = raw.strip()
            if not raw:
                continue
            try:
                yield json.loads(raw)
            except ValueError:
                continue
            count += 1
            if limit is not None and count >= limit:
                return


def open_log_directory() -> Path:
    d = _log_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d
