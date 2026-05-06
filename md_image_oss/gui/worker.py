"""Background QThread that runs the batch through processor + uploader.

The worker:
- selects MarkdownProcessor or HtmlProcessor per file extension
- backs up the original to ``<path>.bak`` when ``in_place`` + ``backup``
- writes new content (skips when ``dry_run``)
- streams every processor log line via ``log_line`` signal
- emits per-file status via ``file_started`` / ``file_finished``
- writes structured audit records for every action

Cancellation: setting ``cancel_requested = True`` causes the loop to break
between files (the in-flight file completes).
"""

from __future__ import annotations

import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QThread, Signal

from ..config import Config
from ..processor import HtmlProcessor, MarkdownProcessor
from ..uploader import OSSUploader
from .audit_log import AuditLogger


@dataclass
class ProcessOptions:
    in_place: bool = False
    dry_run: bool = False
    backup_on_overwrite: bool = True
    quality: int = 85
    process_remote: bool = False
    no_compress: bool = False


def _pick_processor_class(path: Path):
    return HtmlProcessor if path.suffix.lower() in (".html", ".htm") else MarkdownProcessor


def _output_path(input_path: Path, in_place: bool) -> Path:
    if in_place:
        return input_path
    suffix = input_path.suffix
    return input_path.with_name(input_path.stem + ".oss" + suffix)


class ProcessorWorker(QThread):
    file_started = Signal(int)                   # row index
    file_finished = Signal(int, dict)            # row index, result
    log_line = Signal(str)
    batch_finished = Signal(dict)                # summary

    def __init__(
        self,
        files: list[Path],
        options: ProcessOptions,
        config: Config,
        audit: AuditLogger,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.files = files
        self.options = options
        self.config = config
        self.audit = audit
        self.cancel_requested = False

    # --------------------------------------------------------------- helpers
    def _log(self, msg: str) -> None:
        self.log_line.emit(msg)

    # ---------------------------------------------------------------- entry
    def run(self) -> None:
        t0 = time.time()
        try:
            uploader = OSSUploader(self.config)
        except Exception as e:
            self._log(f"Failed to initialise uploader: {e}")
            self.audit.write("worker_error", error=str(e))
            self.batch_finished.emit({"success": 0, "failed": len(self.files), "cancelled": 0})
            return

        self.audit.batch_start(len(self.files), self.options)

        success = 0
        failed = 0
        cancelled = 0

        for row, path in enumerate(self.files):
            if self.cancel_requested:
                cancelled = len(self.files) - row
                break
            self.file_started.emit(row)
            result = self._process_one(row, path, uploader)
            if result["status"] == "success":
                success += 1
            else:
                failed += 1
            self.file_finished.emit(row, result)

        total_ms = int((time.time() - t0) * 1000)
        self.audit.batch_end(success=success, failed=failed, cancelled=cancelled, total_duration_ms=total_ms)
        self.batch_finished.emit({
            "success": success,
            "failed": failed,
            "cancelled": cancelled,
            "duration_ms": total_ms,
        })

    # ------------------------------------------------------------- per-file
    def _process_one(self, row: int, path: Path, uploader: OSSUploader) -> dict:
        t0 = time.time()
        opts = self.options
        in_place = opts.in_place
        dry_run = opts.dry_run

        backup_path: Optional[Path] = None

        try:
            content = path.read_text(encoding="utf-8")
        except Exception as e:
            err = f"Read failed: {e}"
            self._log(f"⚠ {path}: {err}")
            self._audit_file(path, None, "error", None, {}, t0, status="error", error=err)
            return {"status": "error", "error": err, "stats": {}}

        proc_cls = _pick_processor_class(path)
        processor = proc_cls(
            uploader=uploader,
            compress=not opts.no_compress,
            quality=opts.quality,
            process_remote=opts.process_remote,
            verbose=True,
            log_callback=self.log_line.emit,
        )

        self._log(f"━━ Processing {path}")
        try:
            new_content = processor.process(content, path.parent)
        except Exception as e:
            err = f"Processor failed: {e}"
            self._log(f"⚠ {path}: {err}")
            self._audit_file(
                path, None, "error", None, processor.stats, t0,
                status="error", error=err,
            )
            return {"status": "error", "error": err, "stats": dict(processor.stats)}

        # Decide output mode and write
        out_path: Optional[Path] = None
        if dry_run:
            mode = "dry_run"
            self._log(f"  ⓘ dry-run: not writing {path.name}")
        else:
            out_path = _output_path(path, in_place)
            if in_place and opts.backup_on_overwrite:
                try:
                    backup_path = Path(str(path) + ".bak")
                    shutil.copy2(path, backup_path)
                    self._log(f"  💾 backup → {backup_path}")
                except Exception as e:
                    err = f"Backup failed: {e}"
                    self._log(f"⚠ {path}: {err}")
                    self._audit_file(
                        path, None, "in_place" if in_place else "new_file", None,
                        processor.stats, t0, status="error", error=err,
                    )
                    return {"status": "error", "error": err, "stats": dict(processor.stats)}
            try:
                out_path.write_text(new_content, encoding="utf-8")
                self._log(f"  ✓ wrote {out_path}")
            except Exception as e:
                err = f"Write failed: {e}"
                self._log(f"⚠ {path}: {err}")
                self._audit_file(
                    path, out_path, "in_place" if in_place else "new_file", backup_path,
                    processor.stats, t0, status="error", error=err,
                )
                return {"status": "error", "error": err, "stats": dict(processor.stats)}
            mode = "in_place" if in_place else "new_file"

        self._audit_file(
            path, out_path, mode, backup_path,
            processor.stats, t0, status="success",
        )
        return {
            "status": "success",
            "stats": dict(processor.stats),
            "output": str(out_path) if out_path else None,
            "backup": str(backup_path) if backup_path else None,
            "mode": mode,
        }

    def _audit_file(
        self,
        input_path: Path,
        output_path: Optional[Path],
        mode: str,
        backup_path: Optional[Path],
        stats: dict,
        t0: float,
        status: str,
        error: str = "",
    ) -> None:
        self.audit.file_processed(
            input_path=input_path,
            output_path=output_path,
            mode=mode,
            backup_path=backup_path,
            stats=dict(stats),
            duration_ms=int((time.time() - t0) * 1000),
            status=status,
            error=error,
        )
