from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt, QThreadPool, QUrl
from PySide6.QtGui import QDesktopServices, QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from video_downloader.application.ports import SettingsStore
from video_downloader.application.use_cases import DownloadVideo, InspectVideo
from video_downloader.domain.errors import AppError, ErrorCode
from video_downloader.domain.models import (
    DownloadProgress,
    DownloadResult,
    ProgressState,
    VideoInfo,
    format_duration,
    validate_public_url,
)
from video_downloader.infrastructure.thumbnail import load_thumbnail
from video_downloader.presentation.icons import set_action_icon
from video_downloader.presentation.progress_view import ProgressPresenter
from video_downloader.presentation.settings_dialog import SettingsDialog
from video_downloader.presentation.text_safety import sanitize_display_text
from video_downloader.presentation.workers import DownloadWorker, TaskWorker

ERROR_TITLES = {
    ErrorCode.INVALID_LINK: "Invalid link",
    ErrorCode.NOT_FOUND: "Video not found",
    ErrorCode.VERIFICATION_REQUIRED: "Source verification required",
    ErrorCode.ACCESS_REQUIRED: "Access required",
    ErrorCode.DRM_PROTECTED: "Protected video",
    ErrorCode.FORMAT_UNAVAILABLE: "Quality unavailable",
    ErrorCode.NETWORK: "Connection failed",
    ErrorCode.STORAGE: "Could not save file",
    ErrorCode.ENGINE: "Download failed",
    ErrorCode.SITE_BLOCKED: "Known malicious site blocked",
    ErrorCode.PROTECTION_UNAVAILABLE: "Site protection unavailable",
}


class MainWindow(QMainWindow):
    def __init__(
        self,
        inspect_video: InspectVideo,
        download_video: DownloadVideo,
        settings: SettingsStore,
        icon_path: Path,
        protection_status: Callable[[], str] | None = None,
    ) -> None:
        super().__init__()
        self._inspect_video = inspect_video
        self._download_video = download_video
        self._settings = settings
        self._protection_status = protection_status
        self._thread_pool = QThreadPool.globalInstance()
        self._video: VideoInfo | None = None
        self._inspected_url: str | None = None
        self._download_worker: DownloadWorker | None = None
        self._inspect_worker: TaskWorker | None = None
        self._thumbnail_workers: list[TaskWorker] = []
        self._last_result: DownloadResult | None = None
        self._busy = False
        self._thumbnail_generation = 0
        self._thumbnail: QImage | None = None
        self._progress_view = ProgressPresenter()
        self._retry_request: tuple[str, str, int] | None = None
        self._reset_after_download = False

        self.setWindowTitle("VideoDownloader")
        self.setWindowIcon(QIcon(str(icon_path)))
        self.setMinimumSize(780, 600)
        self.resize(1080, 740)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QFrame()
        header.setObjectName("topBar")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(18, 8, 18, 8)
        header_layout.setSpacing(0)
        self.back_button = QPushButton("Cancel")
        self.back_button.setObjectName("headerButton")
        self.back_button.setFixedWidth(110)
        set_action_icon(self.back_button, "cancel")
        self.back_button.setVisible(False)
        self.back_button.clicked.connect(self._header_action)
        left = QWidget()
        left_layout = QHBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(self.back_button)
        left.setFixedWidth(110)
        header_layout.addWidget(left)
        header_layout.addStretch(1)
        title = QLabel("VideoDownloader")
        title.setObjectName("appTitle")
        title.setAlignment(Qt.AlignCenter)
        brand_icon = QLabel()
        brand_icon.setPixmap(QIcon(str(Path(__file__).resolve().parents[1] / "assets/brand-mark.svg")).pixmap(24, 24))
        header_layout.addWidget(brand_icon)
        header_layout.addSpacing(8)
        header_layout.addWidget(title)
        header_layout.addStretch(1)
        right = QWidget()
        right.setFixedWidth(110)
        right_layout = QHBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setAlignment(Qt.AlignRight)
        self.settings_button = QPushButton()
        self.settings_button.setObjectName("menuButton")
        set_action_icon(self.settings_button, "menu")
        self.settings_button.setToolTip("Settings")
        self.settings_button.setAccessibleName("Settings")
        self.settings_button.clicked.connect(self._open_settings)
        right_layout.addWidget(self.settings_button)
        header_layout.addWidget(right)
        layout.addWidget(header)

        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_form_page())
        self.pages.addWidget(self._build_progress_page())
        layout.addWidget(self.pages, 1)
        retry_hint = QLabel("If inspection fails, click Inspect link again.")
        retry_hint.setObjectName("hint")
        retry_hint.setAlignment(Qt.AlignCenter)
        retry_hint.setContentsMargins(16, 8, 16, 16)
        layout.addWidget(retry_hint)
        self.setCentralWidget(root)

    def _build_form_page(self) -> QWidget:
        page = QWidget()
        body = QVBoxLayout(page)
        body.setContentsMargins(40, 36, 40, 32)
        body.setSpacing(0)
        heading = QLabel("Download a video")
        heading.setObjectName("pageHeading")
        body.addWidget(heading)
        subtitle = QLabel("Paste the link, choose the resolution and save your video.")
        subtitle.setObjectName("hint")
        body.addSpacing(8)
        body.addWidget(subtitle)
        body.addSpacing(28)

        card = QFrame()
        card.setObjectName("formCard")
        card.setMinimumWidth(560)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 24, 24, 24)
        card_layout.setSpacing(20)
        url_label = QLabel("Video link")
        url_label.setObjectName("fieldLabel")
        self.url_edit = QLineEdit()
        self.url_edit.setObjectName("urlEdit")
        self.url_edit.setPlaceholderText("Paste a video link")
        self.url_edit.setClearButtonEnabled(True)
        self.url_edit.textChanged.connect(self._source_changed)
        self.url_edit.returnPressed.connect(self._primary_action)
        card_layout.addWidget(url_label)
        card_layout.addWidget(self.url_edit)
        card_layout.addSpacing(4)
        card_layout.addWidget(self._separator())

        quality_row = QHBoxLayout()
        quality_row.setContentsMargins(3, 0, 0, 0)
        quality_row.setSpacing(10)
        quality_row.addWidget(QLabel("Resolution"))
        quality_row.addStretch(1)
        self.quality_combo = QComboBox()
        self.quality_combo.setObjectName("qualityCombo")
        self.quality_combo.setMinimumWidth(205)
        self.quality_combo.setEnabled(False)
        self.quality_combo.addItem("Choose a video first", 0)
        quality_row.addWidget(self.quality_combo)
        card_layout.addLayout(quality_row)
        card_layout.addWidget(self._separator())

        folder_row = QHBoxLayout()
        folder_row.setContentsMargins(3, 0, 0, 0)
        folder_row.addWidget(QLabel("Save to"))
        folder_row.addStretch(1)
        self.folder_label = QLabel()
        self.folder_label.setObjectName("folderLabel")
        self.folder_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        folder_row.addWidget(self.folder_label)
        folder_button = QPushButton("Change")
        folder_button.setObjectName("textButton")
        set_action_icon(folder_button, "folder", "link")
        folder_button.clicked.connect(self._open_settings)
        folder_row.addWidget(folder_button)
        card_layout.addLayout(folder_row)
        self._update_folder_label()

        body.addWidget(card)
        body.addSpacing(18)

        self.info_label = QLabel("Paste a link, then click Inspect link")
        self.info_label.setObjectName("hint")
        self.info_label.setAlignment(Qt.AlignLeft)
        self.info_label.setTextFormat(Qt.PlainText)
        self.info_label.setWordWrap(True)
        body.addWidget(self.info_label)
        self.security_label = QLabel()
        self.security_label.setObjectName("hint")
        self.security_label.setWordWrap(True)
        self.security_label.setTextFormat(Qt.PlainText)
        self.security_label.setVisible(self._protection_status is not None)
        if self._protection_status:
            self.security_label.setText(self._protection_status())
        body.addSpacing(8)
        body.addWidget(self.security_label)
        body.addSpacing(16)
        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.download_button = QPushButton("Inspect link")
        self.download_button.setObjectName("primaryButton")
        set_action_icon(self.download_button, "inspect", "primary")
        self.download_button.setMinimumWidth(180)
        self.download_button.clicked.connect(self._primary_action)
        button_row.addWidget(self.download_button)
        body.addLayout(button_row)
        body.addStretch(1)
        return page

    def _build_progress_page(self) -> QWidget:
        page = QWidget()
        body = QVBoxLayout(page)
        body.setContentsMargins(40, 28, 40, 28)
        body.setSpacing(0)
        body.addStretch(1)
        self.progress_title = QLabel("Preparing video")
        self.progress_title.setObjectName("progressTitle")
        self.progress_title.setTextFormat(Qt.PlainText)
        self.progress_title.setAlignment(Qt.AlignCenter)
        self.progress_title.setWordWrap(True)
        body.addWidget(self.progress_title)
        body.addSpacing(16)

        preview_row = QHBoxLayout()
        preview_row.addStretch(1)
        self.preview = QFrame()
        self.preview.setObjectName("preview")
        self.preview.setFixedSize(400, 225)
        self.preview_image = QLabel(self.preview)
        self.preview_image.setGeometry(0, 0, 400, 225)
        self.preview_image.setAlignment(Qt.AlignCenter)
        self.preview_image.setObjectName("previewImage")
        self.play_mark = QLabel("▶", self.preview)
        self.play_mark.setObjectName("playMark")
        self.play_mark.setAlignment(Qt.AlignCenter)
        self.play_mark.setGeometry(168, 80, 64, 64)
        self.play_mark.setAttribute(Qt.WA_TransparentForMouseEvents)
        preview_row.addWidget(self.preview)
        preview_row.addStretch(1)
        body.addLayout(preview_row)
        body.addSpacing(20)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        body.addWidget(self.progress_bar)
        body.addSpacing(8)
        self.progress_details = QLabel("Preparing…")
        self.progress_details.setObjectName("progressDetails")
        self.progress_details.setTextFormat(Qt.PlainText)
        self.progress_details.setAlignment(Qt.AlignCenter)
        body.addWidget(self.progress_details)
        body.addSpacing(10)
        self.progress_heading = QLabel("Downloading")
        self.progress_heading.setObjectName("progressHeading")
        self.progress_heading.setAlignment(Qt.AlignCenter)
        body.addWidget(self.progress_heading)
        body.addSpacing(7)
        self.status_label = QLabel("")
        self.status_label.setObjectName("hint")
        self.status_label.setTextFormat(Qt.PlainText)
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setWordWrap(True)
        body.addWidget(self.status_label)
        body.addSpacing(12)
        self.open_folder_button = QPushButton("Open folder")
        self.open_folder_button.setObjectName("primaryButton")
        set_action_icon(self.open_folder_button, "open-folder", "primary")
        self.open_folder_button.setVisible(False)
        self.open_folder_button.clicked.connect(self._open_result_folder)
        open_row = QHBoxLayout()
        open_row.addStretch(1)
        open_row.addWidget(self.open_folder_button)
        self.retry_button = QPushButton("Retry download")
        set_action_icon(self.retry_button, "download")
        self.retry_button.setVisible(False)
        self.retry_button.clicked.connect(self._retry_download)
        open_row.addWidget(self.retry_button)
        self.new_link_button = QPushButton("Download another video")
        set_action_icon(self.new_link_button, "inspect")
        self.new_link_button.setVisible(False)
        self.new_link_button.clicked.connect(self._reset_to_form)
        open_row.addWidget(self.new_link_button)
        open_row.addStretch(1)
        body.addLayout(open_row)
        body.addStretch(1)
        return page

    @staticmethod
    def _separator() -> QFrame:
        line = QFrame()
        line.setObjectName("separator")
        line.setFixedHeight(1)
        return line

    def _source_changed(self, value: str) -> None:
        self._thumbnail_generation += 1
        self._thumbnail = None
        self._show_thumbnail(None)
        self._video = None
        self._inspected_url = None
        self.quality_combo.clear()
        self.quality_combo.addItem("Choose a video first", 0)
        self.quality_combo.setEnabled(False)
        self.download_button.setText("Inspect link")
        set_action_icon(self.download_button, "inspect", "primary")
        self.info_label.setText("Paste a link, then click Inspect link")
        # Editing is local only. Inspection starts exclusively from the action.

    def _primary_action(self) -> None:
        if self._busy:
            return
        if self._video and self._inspected_url == self.url_edit.text().strip():
            self._download()
        else:
            self._inspect()

    def _inspect(self) -> None:
        if self._busy or self._video is not None:
            return
        try:
            self._inspected_url = validate_public_url(self.url_edit.text())
        except ValueError as exc:
            self._show_error(AppError(ErrorCode.INVALID_LINK, str(exc)))
            return
        self._set_busy(True)
        self.download_button.setText("Inspecting…")
        set_action_icon(self.download_button, "inspect", "primary")
        self.info_label.setText("Checking site reputation and available resolutions…")
        worker = TaskWorker(
            self._inspect_video.execute, self.url_edit.text(), self._settings.proxy_url
        )
        worker.signals.succeeded.connect(self._inspection_succeeded)
        worker.signals.failed.connect(self._operation_failed)
        worker.signals.finished.connect(self._inspection_finished)
        self._inspect_worker = worker
        self._thread_pool.start(worker)

    def _inspection_succeeded(self, video: VideoInfo) -> None:
        self._video = video
        title = sanitize_display_text(video.title, fallback="Untitled video")
        duration = format_duration(video.duration_seconds)
        self.info_label.setText(f"{title}  ·  {duration}")
        self.quality_combo.clear()
        max_quality = video.qualities[0]
        if max_quality.height > 0:
            self.quality_combo.addItem(f"Best · {max_quality.label}", max_quality.height)
        else:
            self.quality_combo.addItem(max_quality.label, max_quality.height)
        for quality in video.qualities[1:-1]:
            self.quality_combo.addItem(quality.label, quality.height)
        if len(video.qualities) > 1:
            min_quality = video.qualities[-1]
            self.quality_combo.addItem(f"Smallest · {min_quality.label}", min_quality.height)
        self.quality_combo.setEnabled(True)
        if video.thumbnail_url:
            generation = self._thumbnail_generation
            worker = TaskWorker(load_thumbnail, video.thumbnail_url, self._settings.proxy_url,
                                video.webpage_url)
            worker.signals.succeeded.connect(
                lambda image, token=generation: self._thumbnail_loaded(image, token)
            )
            worker.signals.finished.connect(
                lambda current=worker: self._thumbnail_workers.remove(current)
            )
            self._thumbnail_workers.append(worker)
            self._thread_pool.start(worker)

    def _thumbnail_loaded(self, image: QImage | None, token: int) -> None:
        if token != self._thumbnail_generation or image is None:
            return
        self._thumbnail = image
        self._show_thumbnail(image)

    def _show_thumbnail(self, image: QImage | None) -> None:
        if image is None or image.isNull():
            self.preview_image.clear()
            return
        pixmap = QPixmap.fromImage(image)
        target = self.preview.size()
        if pixmap.width() >= target.width() and pixmap.height() >= target.height():
            scaled = pixmap.scaled(target, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            x = (scaled.width() - target.width()) // 2
            y = (scaled.height() - target.height()) // 2
            pixmap = scaled.copy(x, y, target.width(), target.height())
        elif pixmap.width() > target.width() or pixmap.height() > target.height():
            pixmap = pixmap.scaled(target, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.preview_image.setPixmap(pixmap)

    def _inspection_finished(self) -> None:
        self._inspect_worker = None
        self._set_busy(False)
        if self._protection_status:
            self.security_label.setText(self._protection_status())
        self.download_button.setText("Download" if self._video else "Inspect link")
        set_action_icon(self.download_button, "download" if self._video else "inspect", "primary")
        if self._video is None:
            self.info_label.setText("Paste a link, then click Inspect link")

    def _download(self) -> None:
        if self._busy or self._video is None:
            return
        height = int(self.quality_combo.currentData())
        source_url = self._inspected_url or self._video.webpage_url
        title = sanitize_display_text(self._video.title, fallback="Your video")
        self._start_download(source_url, title, height)

    def _retry_download(self) -> None:
        if not self._busy and self._retry_request:
            self._start_download(*self._retry_request)

    def _start_download(self, source_url: str, title: str, height: int) -> None:
        self._retry_request = (source_url, title, height)
        self._reset_after_download = False
        self.url_edit.blockSignals(True)
        self.url_edit.clear()
        self.url_edit.blockSignals(False)
        self._video = None
        self._inspected_url = None
        self.quality_combo.clear()
        self.quality_combo.addItem("Choose a video first", 0)
        self.quality_combo.setEnabled(False)
        self._last_result = None
        self._progress_view = ProgressPresenter()
        self._show_thumbnail(self._thumbnail)
        self.progress_title.setText(title)
        self.progress_heading.setText("Downloading")
        self.open_folder_button.setVisible(False)
        self.retry_button.setVisible(False)
        self.new_link_button.setVisible(False)
        self.back_button.setText("Cancel")
        set_action_icon(self.back_button, "cancel")
        self.back_button.setEnabled(True)
        self.back_button.setVisible(True)
        self.settings_button.setVisible(False)
        self.pages.setCurrentIndex(1)
        self._set_busy(True)
        self._update_progress(DownloadProgress(ProgressState.PREPARING, message="Preparing download"))
        worker = DownloadWorker(
            self._download_video.execute,
            source_url,
            self._settings.download_directory,
            height,
            self._settings.proxy_url,
        )
        self._download_worker = worker
        worker.signals.progress.connect(self._update_progress)
        worker.signals.succeeded.connect(self._download_succeeded)
        worker.signals.failed.connect(self._download_failed)
        worker.signals.finished.connect(self._download_finished)
        self._thread_pool.start(worker)

    def _update_progress(self, progress: DownloadProgress) -> None:
        if progress.state in {ProgressState.PREPARING, ProgressState.PROCESSING}:
            self.progress_bar.setRange(0, 0)
            self.progress_details.setText(progress.message or (
                "Preparing…" if progress.state == ProgressState.PREPARING
                else "Finalizing video…"
            ))
            self.progress_heading.setText("Preparing" if progress.state == ProgressState.PREPARING
                                          else ("Validating" if "validat" in progress.message.lower()
                                                else "Processing"))
            self.status_label.clear()
            return
        if progress.state == ProgressState.FINISHED:
            return  # The success signal confirms validation and publication.
        view = self._progress_view.update(progress)
        self.progress_details.setText(view.details)
        self.progress_heading.setText("Downloading")
        self.status_label.clear()
        if view.fraction is None:
            self.progress_bar.setRange(0, 0)
        else:
            self.progress_bar.setRange(0, 1000)
            self.progress_bar.setValue(round(view.fraction * 1000))

    def _download_succeeded(self, result: DownloadResult) -> None:
        if self._reset_after_download:
            return
        self._last_result = result
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setValue(1000)
        self.progress_heading.setText("Completed")
        self.progress_details.setText("Saved · video format verified")
        self.status_label.setText("")
        self.back_button.setText("New link")
        set_action_icon(self.back_button, "back")
        self.back_button.setEnabled(True)
        self.open_folder_button.setVisible(True)
        self.new_link_button.setVisible(True)
        if not result.quality_matches:
            QMessageBox.warning(
                self,
                "Quality changed",
                f"The source delivered {result.actual_height}p instead of "
                f"{result.requested_height}p. The saved file was not relabeled.",
            )

    def _download_failed(self, error: Exception) -> None:
        app_error = self._normalize_error(error)
        if app_error.code == ErrorCode.CANCELLED or self._reset_after_download:
            self._reset_after_download = True
            return
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setValue(0)
        self.progress_heading.setText("Failed")
        self.progress_details.setText("Download stopped")
        self.status_label.setText(sanitize_display_text(app_error.user_message, fallback="Download failed"))
        self.back_button.setText("New link")
        set_action_icon(self.back_button, "back")
        self.back_button.setEnabled(False)
        self.retry_button.setVisible(self._retry_request is not None)
        self.retry_button.setEnabled(False)
        self.new_link_button.setVisible(True)
        self.new_link_button.setEnabled(False)

    def _download_finished(self) -> None:
        self._download_worker = None
        self._set_busy(False)
        if self._protection_status:
            self.security_label.setText(self._protection_status())
        if self.progress_heading.text() == "Failed":
            self.back_button.setEnabled(True)
        self.retry_button.setEnabled(True)
        self.new_link_button.setEnabled(True)
        if self._reset_after_download:
            self._reset_to_form()

    def _header_action(self) -> None:
        if self._last_result is not None:
            self._reset_to_form()
            return
        if self._download_worker is not None:
            answer = QMessageBox.question(
                self, "Cancel download?", "Do you want to cancel this download?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
            # Worker signals can arrive while Qt runs the confirmation dialog.
            # Recheck ownership, then wait for staging cleanup before returning.
            if self._download_worker is None:
                self._reset_to_form()
                return
            self._reset_after_download = True
            self.back_button.setEnabled(False)
            self.status_label.setText("Cancelling…")
            self._download_worker.cancel()
        else:
            self._reset_to_form()

    def _reset_to_form(self) -> None:
        if self._download_worker is not None:
            return
        self._retry_request = None
        self._video = None
        self._inspected_url = None
        self.quality_combo.clear()
        self.quality_combo.addItem("Choose a video first", 0)
        self.quality_combo.setEnabled(False)
        self._last_result = None
        self.progress_title.clear()
        self._thumbnail_generation += 1
        self._thumbnail = None
        self._show_thumbnail(None)
        self.pages.setCurrentIndex(0)
        self.back_button.setVisible(False)
        self.settings_button.setVisible(True)
        self.download_button.setText("Inspect link")
        set_action_icon(self.download_button, "inspect", "primary")
        self.info_label.setText("Paste a link, then click Inspect link")
        self._update_folder_label()
        self.url_edit.setFocus()

    def _open_result_folder(self) -> None:
        if self._last_result is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._last_result.file_path.parent)))

    def _operation_failed(self, error: Exception) -> None:
        self._show_error(self._normalize_error(error))

    @staticmethod
    def _normalize_error(error: Exception) -> AppError:
        if isinstance(error, AppError):
            return error
        return AppError(
            ErrorCode.ENGINE,
            "An unexpected error occurred while processing this source.",
        )

    def _show_error(self, error: AppError) -> None:
        title = ERROR_TITLES.get(error.code, "Download failed")
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Critical)
        dialog.setWindowTitle(title)
        dialog.setText(title)
        dialog.setInformativeText(error.user_message)
        dialog.setDetailedText(f"Error code: {error.code.value}")
        dialog.setStandardButtons(QMessageBox.Ok)
        dialog.exec()

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.url_edit.setEnabled(not busy)
        self.download_button.setEnabled(not busy)
        self.settings_button.setEnabled(not busy)
        self.quality_combo.setEnabled(not busy and self._video is not None)

    def _update_folder_label(self) -> None:
        name = self._settings.download_directory.name or str(self._settings.download_directory)
        self.folder_label.setText(sanitize_display_text(name, fallback="Downloads"))
        self.folder_label.setToolTip(str(self._settings.download_directory))

    def _open_settings(self) -> None:
        previous_proxy = self._settings.proxy_url
        SettingsDialog(self._settings, self).exec()
        self._update_folder_label()
        if previous_proxy != self._settings.proxy_url:
            self._source_changed(self.url_edit.text())

    def closeEvent(self, event) -> None:
        if self._download_worker is not None:
            answer = QMessageBox.question(
                self,
                "Download in progress",
                "Cancel the active download and close?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                event.ignore()
                return
            self._download_worker.cancel()
        event.accept()
