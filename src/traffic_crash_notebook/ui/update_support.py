from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from ..updates import (
    PortableRelease,
    UpdateCancelled,
    UpdateError,
    download_portable_update,
    fetch_update_manifest,
)


class UpdateCheckThread(QThread):
    manifest_ready = Signal(object)
    check_failed = Signal(str)

    def run(self) -> None:
        try:
            self.manifest_ready.emit(fetch_update_manifest())
        except UpdateError as error:
            self.check_failed.emit(str(error))
        except Exception as error:
            self.check_failed.emit(f"Unexpected update-check error: {error}")


class UpdateDownloadThread(QThread):
    download_progress = Signal(int, int)
    download_ready = Signal(str)
    download_failed = Signal(str)
    download_cancelled = Signal()

    def __init__(
        self,
        release: PortableRelease,
        destination_directory: str | Path,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.release = release
        self.destination_directory = Path(destination_directory)

    def run(self) -> None:
        try:
            path = download_portable_update(
                self.release,
                self.destination_directory,
                progress=self.download_progress.emit,
                cancelled=self.isInterruptionRequested,
            )
            self.download_ready.emit(str(path))
        except UpdateCancelled:
            self.download_cancelled.emit()
        except UpdateError as error:
            self.download_failed.emit(str(error))
        except Exception as error:
            self.download_failed.emit(f"Unexpected update-download error: {error}")
