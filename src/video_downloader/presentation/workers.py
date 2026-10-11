from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from video_downloader.domain.models import DownloadProgress, ProgressState


class WorkerSignals(QObject):
    succeeded = Signal(object)
    failed = Signal(object)
    progress = Signal(object)
    finished = Signal()


class TaskWorker(QRunnable):
    def __init__(self, task: Callable[..., Any], *args: Any) -> None:
        super().__init__()
        self.signals = WorkerSignals()
        self._task = task
        self._args = args

    @Slot()
    def run(self) -> None:
        try:
            result = self._task(*self._args)
        except Exception as exc:
            self.signals.failed.emit(exc)
        else:
            self.signals.succeeded.emit(result)
        finally:
            self.signals.finished.emit()


class DownloadWorker(QRunnable):
    def __init__(self, task: Callable[..., Any], *args: Any) -> None:
        super().__init__()
        self.signals = WorkerSignals()
        self._task = task
        self._args = args
        self._cancelled = threading.Event()
        self._progress_lock = threading.Lock()
        self._last_progress_time = 0.0
        self._last_progress_state: ProgressState | None = None

    def cancel(self) -> None:
        self._cancelled.set()

    def is_cancelled(self) -> bool:
        return self._cancelled.is_set()

    def report_progress(self, progress: DownloadProgress) -> None:
        # Parallel fragments can produce hundreds of callbacks per second.
        # Keep the GUI responsive while delivering every phase transition.
        now = time.monotonic()
        with self._progress_lock:
            if (progress.state == ProgressState.DOWNLOADING
                    and self._last_progress_state == progress.state
                    and now - self._last_progress_time < 0.1):
                return
            self._last_progress_time = now
            self._last_progress_state = progress.state
        self.signals.progress.emit(progress)

    @Slot()
    def run(self) -> None:
        try:
            result = self._task(*self._args, self.report_progress, self.is_cancelled)
        except Exception as exc:
            self.signals.failed.emit(exc)
        else:
            self.signals.succeeded.emit(result)
        finally:
            self.signals.finished.emit()
