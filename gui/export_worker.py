"""Background worker for link dataset export."""

from __future__ import annotations

from threading import Event
from typing import Any, Dict

from PySide6.QtCore import QObject, Signal, Slot

from core.link_dataset_exporter import LinkDatasetExportCancelled, LinkDatasetExporter


class LinkDatasetExportWorker(QObject):
    progress = Signal(int, int)
    finished = Signal(bool, object, str)

    def __init__(self, export_config: Dict[str, Any]):
        super().__init__()
        self.export_config = export_config
        self._cancelled = Event()

    def cancel(self) -> None:
        """Request cancellation; safe to call directly from the GUI thread."""
        self._cancelled.set()

    def _report_progress(self, done: int, total: int) -> bool:
        self.progress.emit(done, total)
        return not self._cancelled.is_set()

    @Slot()
    def run(self) -> None:
        try:
            result = LinkDatasetExporter().export(
                **self.export_config,
                progress_callback=self._report_progress,
            )
        except LinkDatasetExportCancelled:
            self.finished.emit(False, None, "")
        except Exception as exc:
            self.finished.emit(False, None, str(exc))
        else:
            self.finished.emit(True, result, "")
