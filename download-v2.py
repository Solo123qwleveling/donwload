import sys
import os
import json
import threading
import hashlib
import requests
from pathlib import Path
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QLineEdit, QPushButton,
                             QComboBox, QCheckBox, QProgressBar, QTextEdit,
                             QFileDialog, QGroupBox, QSpinBox, QTabWidget,
                             QListWidget, QMessageBox, QSplitter, QFrame,
                             QScrollArea, QGridLayout, QSlider, QListWidgetItem,
                             QSystemTrayIcon, QMenu, QAction, QToolBar, QStatusBar,
                             QTableWidget, QTableWidgetItem, QHeaderView, QDialog,
                             QDialogButtonBox, QRadioButton, QButtonGroup, QDoubleSpinBox,
                             QCalendarWidget, QTimeEdit)
from PyQt5.QtCore import (QThread, pyqtSignal, Qt, QTimer, QSize, QSettings,
                          QUrl, QPropertyAnimation, QEasingCurve, QRect, QDateTime)
from PyQt5.QtGui import (QFont, QIcon, QPixmap, QPalette, QColor, QDesktopServices,
                         QTextCursor, QLinearGradient, QPainter, QBrush)
import yt_dlp
from datetime import datetime, timedelta
import re
import subprocess
import platform


class DownloadThread(QThread):
    """Enhanced thread to handle video downloading with resume capability"""
    progress = pyqtSignal(dict)
    finished = pyqtSignal(bool, str, str)
    log_message = pyqtSignal(str)

    def __init__(self, url, options):
        super().__init__()
        self.url = url
        self.options = options
        self._is_cancelled = False
        self._is_paused = False
        self.downloaded_file = None
        self.download_start_time = None
        self.bytes_downloaded_at_pause = 0

    def progress_hook(self, d):
        """Enhanced callback for download progress with more metrics"""
        if self._is_cancelled:
            raise Exception("Download cancelled by user")

        while self._is_paused:
            self.msleep(100)
            if self._is_cancelled:
                raise Exception("Download cancelled by user")

        if d['status'] == 'downloading':
            try:
                downloaded = d.get('downloaded_bytes', 0)
                total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                if total > 0:
                    percent = (downloaded / total) * 100
                    speed = d.get('speed', 0)
                    eta = d.get('eta', 0)

                    # Calculate elapsed time
                    if self.download_start_time is None:
                        self.download_start_time = datetime.now()
                    elapsed = (datetime.now() - self.download_start_time).total_seconds()

                    self.progress.emit({
                        'percent': percent,
                        'speed': speed,
                        'eta': eta,
                        'downloaded': downloaded,
                        'total': total,
                        'elapsed': elapsed,
                        'status': 'downloading'
                    })
            except:
                pass
        elif d['status'] == 'finished':
            self.downloaded_file = d.get('filename')
            self.progress.emit({'status': 'processing', 'percent': 100})
            self.log_message.emit("Download complete, processing...")

    def pause(self):
        """Pause the download"""
        self._is_paused = True
        self.log_message.emit("Download paused")

    def resume(self):
        """Resume the download"""
        self._is_paused = False
        self.log_message.emit("Download resumed")

    def cancel(self):
        """Cancel the download"""
        self._is_cancelled = True
        self.log_message.emit("Download cancelled")

    def run(self):
        """Execute download in separate thread with enhanced error handling"""
        try:
            self.options['progress_hooks'] = [self.progress_hook]
            self.log_message.emit(f"Starting download: {self.url}")
            self.download_start_time = datetime.now()

            with yt_dlp.YoutubeDL(self.options) as ydl:
                if self.options.get('auto_update', False):
                    try:
                        self.log_message.emit("Checking for yt-dlp updates...")
                        ydl.update()
                        self.log_message.emit("yt-dlp is up to date")
                    except:
                        self.log_message.emit("Auto-update skipped")

                info = ydl.extract_info(self.url, download=True)
                title = info.get('title', 'Unknown')
                filesize = info.get('filesize', 0) or info.get('filesize_approx', 0)

                elapsed = (datetime.now() - self.download_start_time).total_seconds()
                self.log_message.emit(f"Successfully downloaded: {title} in {elapsed:.1f}s")

            self.finished.emit(True, "Download completed successfully!", self.downloaded_file or "")
        except Exception as e:
            if self._is_cancelled:
                self.finished.emit(False, "Download cancelled by user", "")
            else:
                error_msg = str(e)
                self.finished.emit(False, f"Error: {error_msg}", "")
                self.log_message.emit(f"Error occurred: {error_msg}")


class VideoInfoThread(QThread):
    """Thread to fetch detailed video information"""
    info_ready = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        try:
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.url, download=False)
                self.info_ready.emit(info)
        except Exception as e:
            self.error.emit(str(e))


class PlaylistInfoThread(QThread):
    """Enhanced thread to fetch playlist information with metadata"""
    info_ready = pyqtSignal(list)
    error = pyqtSignal(str)
    progress = pyqtSignal(int, int)

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        try:
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.url, download=False)
                if 'entries' in info:
                    videos = []
                    total = len(list(info['entries']))
                    for idx, entry in enumerate(info['entries'], 1):
                        if entry:
                            videos.append({
                                'title': entry.get('title', 'Unknown'),
                                'url': entry.get('url', ''),
                                'id': entry.get('id', ''),
                                'duration': entry.get('duration', 0),
                                'uploader': entry.get('uploader', 'Unknown'),
                                'view_count': entry.get('view_count', 0)
                            })
                        self.progress.emit(idx, total)
                    self.info_ready.emit(videos)
                else:
                    self.error.emit("Not a playlist")
        except Exception as e:
            self.error.emit(str(e))


class BatchDownloadThread(QThread):
    """Enhanced thread for batch downloads with pause/resume"""
    progress = pyqtSignal(int, int, str)
    item_finished = pyqtSignal(bool, str, str)
    all_finished = pyqtSignal(int, int)

    def __init__(self, urls, options_template):
        super().__init__()
        self.urls = urls
        self.options_template = options_template
        self._is_cancelled = False
        self._is_paused = False

    def pause(self):
        self._is_paused = True

    def resume(self):
        self._is_paused = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        successful = 0
        failed = 0

        for idx, url in enumerate(self.urls, 1):
            while self._is_paused:
                self.msleep(100)
                if self._is_cancelled:
                    break

            if self._is_cancelled:
                break

            self.progress.emit(idx, len(self.urls), url)

            try:
                options = self.options_template.copy()
                with yt_dlp.YoutubeDL(options) as ydl:
                    info = ydl.extract_info(url, download=True)
                    title = info.get('title', 'Unknown')
                    self.item_finished.emit(True, url, f"Downloaded: {title}")
                    successful += 1
            except Exception as e:
                self.item_finished.emit(False, url, f"Failed: {str(e)}")
                failed += 1

        self.all_finished.emit(successful, failed)


class ScheduleDownloadDialog(QDialog):
    """Dialog for scheduling downloads"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Schedule Download")
        self.setModal(True)
        self.setMinimumWidth(400)
        self.scheduled_time = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        info = QLabel("Schedule this download for a specific time:")
        info.setStyleSheet("color: #8b949e; margin-bottom: 10px;")
        layout.addWidget(info)

        datetime_group = QGroupBox("Date & Time")
        datetime_layout = QVBoxLayout()

        self.calendar = QCalendarWidget()
        self.calendar.setMinimumDate(QDateTime.currentDateTime().date())
        datetime_layout.addWidget(self.calendar)

        time_layout = QHBoxLayout()
        time_layout.addWidget(QLabel("Time:"))
        self.time_edit = QTimeEdit()
        self.time_edit.setDisplayFormat("HH:mm")
        self.time_edit.setTime(QDateTime.currentDateTime().time())
        time_layout.addWidget(self.time_edit)
        time_layout.addStretch()

        datetime_layout.addLayout(time_layout)
        datetime_group.setLayout(datetime_layout)
        layout.addWidget(datetime_group)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_scheduled_datetime(self):
        """Get the scheduled datetime"""
        date = self.calendar.selectedDate()
        time = self.time_edit.time()
        return QDateTime(date, time)


class SettingsDialog(QDialog):
    """Enhanced settings dialog"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.setMinimumWidth(600)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Theme selection
        theme_group = QGroupBox("Appearance")
        theme_layout = QVBoxLayout()

        self.dark_theme_radio = QRadioButton("Dark Theme")
        self.dark_theme_radio.setChecked(True)
        theme_layout.addWidget(self.dark_theme_radio)

        self.light_theme_radio = QRadioButton("Light Theme (Coming Soon)")
        self.light_theme_radio.setEnabled(False)
        theme_layout.addWidget(self.light_theme_radio)

        theme_group.setLayout(theme_layout)
        layout.addWidget(theme_group)

        # Performance settings
        perf_group = QGroupBox("Performance")
        perf_layout = QGridLayout()

        perf_layout.addWidget(QLabel("Max Concurrent Downloads:"), 0, 0)
        self.max_concurrent_spin = QSpinBox()
        self.max_concurrent_spin.setRange(1, 10)
        self.max_concurrent_spin.setValue(3)
        perf_layout.addWidget(self.max_concurrent_spin, 0, 1)

        perf_layout.addWidget(QLabel("Memory Buffer (MB):"), 1, 0)
        self.buffer_spin = QSpinBox()
        self.buffer_spin.setRange(1, 1024)
        self.buffer_spin.setValue(64)
        perf_layout.addWidget(self.buffer_spin, 1, 1)

        perf_group.setLayout(perf_layout)
        layout.addWidget(perf_group)

        # Notifications
        notif_group = QGroupBox("Notifications")
        notif_layout = QVBoxLayout()

        self.notif_on_complete = QCheckBox("Show notification when download completes")
        self.notif_on_complete.setChecked(True)
        notif_layout.addWidget(self.notif_on_complete)

        self.notif_on_error = QCheckBox("Show notification on errors")
        self.notif_on_error.setChecked(True)
        notif_layout.addWidget(self.notif_on_error)

        self.sound_on_complete = QCheckBox("Play sound on completion")
        notif_layout.addWidget(self.sound_on_complete)

        self.minimize_to_tray = QCheckBox("Minimize to system tray")
        notif_layout.addWidget(self.minimize_to_tray)

        notif_group.setLayout(notif_layout)
        layout.addWidget(notif_group)

        # Auto-update
        update_group = QGroupBox("Updates")
        update_layout = QVBoxLayout()

        self.auto_update_ytdlp = QCheckBox("Automatically update yt-dlp before downloads")
        self.auto_update_ytdlp.setChecked(True)
        update_layout.addWidget(self.auto_update_ytdlp)

        self.check_updates_startup = QCheckBox("Check for application updates on startup")
        self.check_updates_startup.setChecked(True)
        update_layout.addWidget(self.check_updates_startup)

        update_group.setLayout(update_layout)
        layout.addWidget(update_group)

        # Network settings
        network_group = QGroupBox("Network")
        network_layout = QGridLayout()

        network_layout.addWidget(QLabel("Connection Timeout (s):"), 0, 0)
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(5, 300)
        self.timeout_spin.setValue(30)
        network_layout.addWidget(self.timeout_spin, 0, 1)

        network_layout.addWidget(QLabel("Max Retries:"), 1, 0)
        self.max_retries_spin = QSpinBox()
        self.max_retries_spin.setRange(1, 50)
        self.max_retries_spin.setValue(10)
        network_layout.addWidget(self.max_retries_spin, 1, 1)

        self.use_proxy_check = QCheckBox("Use Proxy")
        network_layout.addWidget(self.use_proxy_check, 2, 0)

        self.proxy_input = QLineEdit()
        self.proxy_input.setPlaceholderText("http://proxy:port")
        self.proxy_input.setEnabled(False)
        network_layout.addWidget(self.proxy_input, 2, 1)
        self.use_proxy_check.toggled.connect(self.proxy_input.setEnabled)

        network_group.setLayout(network_layout)
        layout.addWidget(network_group)

        # Storage settings
        storage_group = QGroupBox("Storage")
        storage_layout = QVBoxLayout()

        self.auto_cleanup_check = QCheckBox("Auto-cleanup incomplete downloads")
        self.auto_cleanup_check.setChecked(True)
        storage_layout.addWidget(self.auto_cleanup_check)

        self.auto_organize_check = QCheckBox("Auto-organize downloads by date")
        storage_layout.addWidget(self.auto_organize_check)

        disk_space_layout = QHBoxLayout()
        disk_space_layout.addWidget(QLabel("Minimum Free Space (GB):"))
        self.min_space_spin = QDoubleSpinBox()
        self.min_space_spin.setRange(0.1, 1000)
        self.min_space_spin.setValue(1.0)
        self.min_space_spin.setSingleStep(0.5)
        disk_space_layout.addWidget(self.min_space_spin)
        disk_space_layout.addStretch()
        storage_layout.addLayout(disk_space_layout)

        storage_group.setLayout(storage_layout)
        layout.addWidget(storage_group)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class AboutDialog(QDialog):
    """Enhanced about dialog"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About Video Downloader Pro")
        self.setModal(True)
        self.setMinimumWidth(500)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        title = QLabel("🎬 Video Downloader Pro")
        title.setFont(QFont("Segoe UI", 20, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #58a6ff; margin: 20px;")
        layout.addWidget(title)

        version = QLabel("Version 3.0 - Ultimate Edition")
        version.setAlignment(Qt.AlignCenter)
        version.setStyleSheet("color: #8b949e; margin-bottom: 10px; font-size: 12pt;")
        layout.addWidget(version)

        description = QLabel(
            "A powerful, feature-rich video downloader built with PyQt5 and yt-dlp.\n\n"
            "✨ New Features in v3.0:\n"
            "• Scheduled downloads with calendar picker\n"
            "• Advanced format selection with codec info\n"
            "• Bandwidth management and speed limits\n"
            "• Resume capability for interrupted downloads\n"
            "• Duplicate detection and smart naming\n"
            "• Network proxy support\n"
            "• Auto-organization by date\n"
            "• Enhanced statistics and analytics\n"
            "• Playlist metadata extraction\n"
            "• Custom filename templates\n\n"
            "⚡ Core Features:\n"
            "• Multi-quality video downloads (8K-240p)\n"
            "• Audio extraction (MP3/M4A/OPUS/FLAC)\n"
            "• Playlist & batch downloads\n"
            "• Real-time progress tracking\n"
            "• Download queue management\n"
            "• Python code generator\n"
            "• Download history & statistics\n\n"
            "Powered by yt-dlp & FFmpeg"
        )
        description.setWordWrap(True)
        description.setAlignment(Qt.AlignLeft)
        description.setStyleSheet("color: #c9d1d9; margin: 20px; font-size: 10pt;")
        layout.addWidget(description)

        links_layout = QHBoxLayout()

        github_btn = QPushButton("🔗 yt-dlp GitHub")
        github_btn.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl("https://github.com/yt-dlp/yt-dlp")))
        links_layout.addWidget(github_btn)

        ffmpeg_btn = QPushButton("🔗 FFmpeg")
        ffmpeg_btn.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl("https://ffmpeg.org/")))
        links_layout.addWidget(ffmpeg_btn)

        layout.addLayout(links_layout)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)


class BatchDownloadDialog(QDialog):
    """Enhanced batch download dialog"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Batch Download Manager")
        self.setModal(True)
        self.setMinimumSize(800, 600)
        self.urls = []
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        info = QLabel("Add multiple URLs (one per line) for batch downloading:")
        info.setStyleSheet("color: #8b949e; margin-bottom: 10px;")
        layout.addWidget(info)

        self.url_text = QTextEdit()
        self.url_text.setPlaceholderText(
            "https://www.youtube.com/watch?v=...\n"
            "https://www.youtube.com/watch?v=...\n"
            "https://www.youtube.com/watch?v=..."
        )
        layout.addWidget(self.url_text)

        import_layout = QHBoxLayout()
        import_btn = QPushButton("📁 Import from File")
        import_btn.clicked.connect(self.import_urls)
        import_layout.addWidget(import_btn)

        paste_btn = QPushButton("📋 Paste from Clipboard")
        paste_btn.clicked.connect(self.paste_from_clipboard)
        import_layout.addWidget(paste_btn)

        clear_btn = QPushButton("🗑 Clear All")
        clear_btn.clicked.connect(self.url_text.clear)
        import_layout.addWidget(clear_btn)

        dedupe_btn = QPushButton("🔍 Remove Duplicates")
        dedupe_btn.clicked.connect(self.remove_duplicates)
        import_layout.addWidget(dedupe_btn)

        import_layout.addStretch()
        layout.addLayout(import_layout)

        self.stats_label = QLabel("URLs: 0 | Duplicates: 0")
        self.stats_label.setStyleSheet("color: #58a6ff;")
        layout.addWidget(self.stats_label)

        self.url_text.textChanged.connect(self.update_stats)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def paste_from_clipboard(self):
        """Paste URLs from clipboard"""
        clipboard = QApplication.clipboard()
        text = clipboard.text()
        if text:
            current = self.url_text.toPlainText()
            if current:
                self.url_text.setPlainText(current + "\n" + text)
            else:
                self.url_text.setPlainText(text)

    def remove_duplicates(self):
        """Remove duplicate URLs"""
        text = self.url_text.toPlainText()
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        unique_lines = list(dict.fromkeys(lines))
        self.url_text.setPlainText('\n'.join(unique_lines))

    def import_urls(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, "Import URLs", "",
            "Text Files (*.txt);;All Files (*)"
        )
        if filename:
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    content = f.read()
                    self.url_text.setPlainText(content)
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to import file:\n{str(e)}")

    def update_stats(self):
        text = self.url_text.toPlainText()
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        unique = len(set(lines))
        duplicates = len(lines) - unique
        self.stats_label.setText(f"URLs: {len(lines)} | Unique: {unique} | Duplicates: {duplicates}")

    def validate_and_accept(self):
        text = self.url_text.toPlainText()
        self.urls = [line.strip() for line in text.split('\n') if line.strip()]

        if not self.urls:
            QMessageBox.warning(self, "Error", "Please enter at least one URL!")
            return

        self.accept()

    def get_urls(self):
        return self.urls


class FormatSelectorDialog(QDialog):
    """Advanced format selector with codec information"""

    def __init__(self, formats, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Format")
        self.setModal(True)
        self.setMinimumSize(900, 500)
        self.formats = formats
        self.selected_format = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        info = QLabel("Select the format you want to download:")
        info.setStyleSheet("color: #8b949e; margin-bottom: 10px;")
        layout.addWidget(info)

        self.format_table = QTableWidget()
        self.format_table.setColumnCount(7)
        self.format_table.setHorizontalHeaderLabels([
            "Quality", "Extension", "Video Codec", "Audio Codec",
            "FPS", "Size", "Format ID"
        ])
        self.format_table.horizontalHeader().setStretchLastSection(True)
        self.format_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.format_table.setSelectionMode(QTableWidget.SingleSelection)

        for fmt in self.formats:
            row = self.format_table.rowCount()
            self.format_table.insertRow(row)

            quality = f"{fmt.get('height', '?')}p" if fmt.get('height') else "Audio only"
            self.format_table.setItem(row, 0, QTableWidgetItem(quality))
            self.format_table.setItem(row, 1, QTableWidgetItem(fmt.get('ext', 'N/A')))
            self.format_table.setItem(row, 2, QTableWidgetItem(fmt.get('vcodec', 'N/A')))
            self.format_table.setItem(row, 3, QTableWidgetItem(fmt.get('acodec', 'N/A')))
            self.format_table.setItem(row, 4, QTableWidgetItem(str(fmt.get('fps', 'N/A'))))

            filesize = fmt.get('filesize', 0) or fmt.get('filesize_approx', 0)
            size_str = self.format_bytes(filesize) if filesize else "Unknown"
            self.format_table.setItem(row, 5, QTableWidgetItem(size_str))
            self.format_table.setItem(row, 6, QTableWidgetItem(str(fmt.get('format_id', 'N/A'))))

        layout.addWidget(self.format_table)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def format_bytes(self, bytes_val):
        if not bytes_val:
            return "0 B"
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_val < 1024.0:
                return f"{bytes_val:.2f} {unit}"
            bytes_val /= 1024.0
        return f"{bytes_val:.2f} PB"

    def get_selected_format(self):
        selected = self.format_table.selectedItems()
        if selected:
            row = selected[0].row()
            return self.formats[row]
        return None


class VideoDownloaderApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Video Downloader Pro v3.0 - Ultimate Edition")
        self.setGeometry(100, 100, 1300, 900)

        self.download_thread = None
        self.batch_thread = None
        self.info_thread = None
        self.playlist_thread = None
        self.download_history = []
        self.current_video_info = None
        self.settings_file = os.path.join(os.path.expanduser("~"), ".video_downloader_settings.json")
        self.download_queue = []
        self.scheduled_downloads = []
        self.download_statistics = {
            'total_downloads': 0,
            'total_bytes': 0,
            'total_time': 0,
            'successful_downloads': 0,
            'failed_downloads': 0
        }

        self.load_settings()
        self.load_statistics()
        self.apply_theme()
        self.create_status_bar()
        self.init_ui()
        self.create_menu_bar()
        self.create_toolbar()
        self.setup_system_tray()
        self.load_history()

        # Setup timers
        self.schedule_timer = QTimer(self)
        self.schedule_timer.timeout.connect(self.check_scheduled_downloads)
        self.schedule_timer.start(60000)  # Check every minute

        QTimer.singleShot(1000, self.check_ytdlp_version)

    def load_statistics(self):
        """Load download statistics"""
        stats_file = os.path.join(os.path.expanduser("~"), ".video_downloader_stats.json")
        try:
            if os.path.exists(stats_file):
                with open(stats_file, 'r') as f:
                    self.download_statistics = json.load(f)
        except:
            pass

    def save_statistics(self):
        """Save download statistics"""
        stats_file = os.path.join(os.path.expanduser("~"), ".video_downloader_stats.json")
        try:
            with open(stats_file, 'w') as f:
                json.dump(self.download_statistics, f, indent=2)
        except Exception as e:
            self.log_message(f"Failed to save statistics: {str(e)}")

    def check_scheduled_downloads(self):
        """Check if any scheduled downloads should start"""
        current_time = QDateTime.currentDateTime()
        downloads_to_start = []

        for scheduled in self.scheduled_downloads[:]:
            if scheduled['datetime'] <= current_time:
                downloads_to_start.append(scheduled)
                self.scheduled_downloads.remove(scheduled)

        for download in downloads_to_start:
            self.log_message(f"Starting scheduled download: {download['url']}")
            self.url_input.setText(download['url'])
            self.start_download()

    def apply_theme(self):
        """Apply modern dark theme with improved styling"""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #0d1117;
            }
            QLabel {
                color: #c9d1d9;
                font-size: 11pt;
            }
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTimeEdit {
                background-color: #161b22;
                color: #c9d1d9;
                border: 2px solid #30363d;
                border-radius: 6px;
                padding: 8px;
                font-size: 10pt;
                selection-background-color: #58a6ff;
            }
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {
                border: 2px solid #58a6ff;
            }
            QPushButton {
                background-color: #238636;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 10px 20px;
                font-weight: bold;
                font-size: 10pt;
            }
            QPushButton:hover {
                background-color: #2ea043;
            }
            QPushButton:pressed {
                background-color: #1a7f37;
            }
            QPushButton:disabled {
                background-color: #21262d;
                color: #484f58;
            }
            QPushButton#cancelBtn {
                background-color: #da3633;
            }
            QPushButton#cancelBtn:hover {
                background-color: #f85149;
            }
            QPushButton#pauseBtn {
                background-color: #d29922;
            }
            QPushButton#pauseBtn:hover {
                background-color: #e3b341;
            }
            QPushButton#secondaryBtn {
                background-color: #21262d;
                border: 1px solid #30363d;
            }
            QPushButton#secondaryBtn:hover {
                background-color: #30363d;
            }
            QCheckBox {
                color: #c9d1d9;
                font-size: 10pt;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 20px;
                height: 20px;
                border-radius: 4px;
                border: 2px solid #30363d;
                background-color: #161b22;
            }
            QCheckBox::indicator:checked {
                background-color: #58a6ff;
                border: 2px solid #58a6ff;
            }
            QProgressBar {
                border: 2px solid #30363d;
                border-radius: 6px;
                text-align: center;
                background-color: #161b22;
                color: #c9d1d9;
                font-weight: bold;
                min-height: 25px;
            }
            QProgressBar::chunk {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                                  stop:0 #1f6feb, stop:1 #58a6ff);
                border-radius: 4px;
            }
            QTextEdit, QListWidget {
                background-color: #161b22;
                color: #c9d1d9;
                border: 2px solid #30363d;
                border-radius: 6px;
                padding: 8px;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 9pt;
            }
            QGroupBox {
                color: #58a6ff;
                font-weight: bold;
                font-size: 11pt;
                border: 2px solid #30363d;
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 8px;
                background-color: #0d1117;
            }
            QTabWidget::pane {
                border: 2px solid #30363d;
                border-radius: 8px;
                background-color: #0d1117;
                top: -2px;
            }
            QTabBar::tab {
                background-color: #161b22;
                color: #8b949e;
                padding: 10px 24px;
                margin-right: 4px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                font-weight: bold;
            }
            QTabBar::tab:selected {
                background-color: #0d1117;
                color: #58a6ff;
                border-bottom: 3px solid #58a6ff;
            }
            QTabBar::tab:hover {
                background-color: #21262d;
                color: #c9d1d9;
            }
            QMenuBar {
                background-color: #161b22;
                color: #c9d1d9;
                border-bottom: 1px solid #30363d;
            }
            QMenuBar::item:selected {
                background-color: #21262d;
            }
            QMenu {
                background-color: #161b22;
                color: #c9d1d9;
                border: 1px solid #30363d;
            }
            QMenu::item:selected {
                background-color: #21262d;
            }
            QToolBar {
                background-color: #161b22;
                border-bottom: 1px solid #30363d;
                spacing: 5px;
                padding: 5px;
            }
            QStatusBar {
                background-color: #161b22;
                color: #8b949e;
                border-top: 1px solid #30363d;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #21262d;
            }
            QListWidget::item:selected {
                background-color: #1f6feb;
                color: #ffffff;
            }
            QListWidget::item:hover {
                background-color: #21262d;
            }
            QTableWidget {
                background-color: #161b22;
                color: #c9d1d9;
                gridline-color: #30363d;
                border: 2px solid #30363d;
                border-radius: 6px;
            }
            QTableWidget::item {
                padding: 5px;
            }
            QHeaderView::section {
                background-color: #21262d;
                color: #c9d1d9;
                padding: 8px;
                border: none;
                border-bottom: 2px solid #30363d;
                font-weight: bold;
            }
            QRadioButton {
                color: #c9d1d9;
                spacing: 8px;
            }
            QRadioButton::indicator {
                width: 18px;
                height: 18px;
                border-radius: 9px;
                border: 2px solid #30363d;
                background-color: #161b22;
            }
            QRadioButton::indicator:checked {
                background-color: #58a6ff;
                border: 2px solid #58a6ff;
            }
            QCalendarWidget QWidget {
                background-color: #161b22;
                color: #c9d1d9;
            }
            QCalendarWidget QTableView {
                background-color: #161b22;
                selection-background-color: #58a6ff;
            }
        """)

    def create_menu_bar(self):
        """Create application menu bar"""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")

        new_download_action = QAction("📥 New Download", self)
        new_download_action.setShortcut("Ctrl+N")
        new_download_action.triggered.connect(lambda: self.tabs.setCurrentIndex(0))
        file_menu.addAction(new_download_action)

        batch_download_action = QAction("📚 Batch Download", self)
        batch_download_action.setShortcut("Ctrl+B")
        batch_download_action.triggered.connect(self.show_batch_download_dialog)
        file_menu.addAction(batch_download_action)

        schedule_action = QAction("⏰ Schedule Download", self)
        schedule_action.setShortcut("Ctrl+T")
        schedule_action.triggered.connect(self.schedule_download)
        file_menu.addAction(schedule_action)

        file_menu.addSeparator()

        open_folder_action = QAction("📁 Open Download Folder", self)
        open_folder_action.setShortcut("Ctrl+O")
        open_folder_action.triggered.connect(self.open_download_folder)
        file_menu.addAction(open_folder_action)

        file_menu.addSeparator()

        export_menu = file_menu.addMenu("💾 Export")
        export_menu.addAction("Export History", self.export_history)
        export_menu.addAction("Export Statistics", self.export_statistics)
        export_menu.addAction("Export Queue", self.export_queue)

        file_menu.addSeparator()

        exit_action = QAction("❌ Exit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Edit menu
        edit_menu = menubar.addMenu("&Edit")

        settings_action = QAction(⚙️ Settings", self)
        settings_action.setShortcut("Ctrl+,")
        settings_action.triggered.connect(self.show_settings_dialog)
        edit_menu.addAction(settings_action)

        edit_menu.addSeparator()

        clear_menu = edit_menu.addMenu("🗑 Clear")
        clear_menu.addAction("Clear History", self.clear_history)
        clear_menu.addAction("Clear Queue", self.clear_queue)
        clear_menu.addAction("Clear Log", self.clear_log)

        # View menu
        view_menu = menubar.addMenu("&View")

        history_action = QAction("📜 History", self)
        history_action.setShortcut("Ctrl+H")
        history_action.triggered.connect(lambda: self.tabs.setCurrentIndex(2))
        view_menu.addAction(history_action)

        stats_action = QAction("📊 Statistics", self)
        stats_action.setShortcut("Ctrl+S")
        stats_action.triggered.connect(lambda: self.tabs.setCurrentIndex(6))
        view_menu.addAction(stats_action)

        log_action = QAction("📋 Log", self)
        log_action.setShortcut("Ctrl+L")
        log_action.triggered.connect(lambda: self.tabs.setCurrentIndex(3))
        view_menu.addAction(log_action)

        # Tools menu
        tools_menu = menubar.addMenu("&Tools")

        update_ytdlp_action = QAction("🔄 Update yt-dlp", self)
        update_ytdlp_action.triggered.connect(self.update_ytdlp_manual)
        tools_menu.addAction(update_ytdlp_action)

        check_ffmpeg_action = QAction("🔧 Check FFmpeg", self)
        check_ffmpeg_action.triggered.connect(self.check_ffmpeg)
        tools_menu.addAction(check_ffmpeg_action)

        tools_menu.addSeparator()

        format_selector_action = QAction("🎞️ Advanced Format Selector", self)
        format_selector_action.triggered.connect(self.show_format_selector)
        tools_menu.addAction(format_selector_action)

        tools_menu.addSeparator()

        duplicate_finder_action = QAction("🔍 Find Duplicate Files", self)
        duplicate_finder_action.triggered.connect(self.find_duplicates)
        tools_menu.addAction(duplicate_finder_action)

        disk_space_action = QAction("💾 Check Disk Space", self)
        disk_space_action.triggered.connect(self.check_disk_space)
        tools_menu.addAction(disk_space_action)

        # Help menu
        help_menu = menubar.addMenu("&Help")

        about_action = QAction("ℹ️ About", self)
        about_action.triggered.connect(self.show_about_dialog)
        help_menu.addAction(about_action)

        docs_action = QAction("📖 yt-dlp Documentation", self)
        docs_action.triggered.connect(lambda: QDesktopServices.openUrl(
            QUrl("https://github.com/yt-dlp/yt-dlp#readme")))
        help_menu.addAction(docs_action)

        help_menu.addSeparator()

        keyboard_shortcuts_action = QAction("⌨️ Keyboard Shortcuts", self)
        keyboard_shortcuts_action.triggered.connect(self.show_shortcuts)
        help_menu.addAction(keyboard_shortcuts_action)

    def create_toolbar(self):
        """Create application toolbar"""
        toolbar = QToolBar("Main Toolbar")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(24, 24))
        self.addToolBar(toolbar)

        download_action = QAction("⬇️ Download", self)
        download_action.triggered.connect(self.start_download)
        toolbar.addAction(download_action)

        toolbar.addSeparator()

        info_action = QAction("🔍 Get Info", self)
        info_action.triggered.connect(self.fetch_video_info)
        toolbar.addAction(info_action)

        toolbar.addSeparator()

        folder_action = QAction("📁 Folder", self)
        folder_action.triggered.connect(self.open_download_folder)
        toolbar.addAction(folder_action)

        toolbar.addSeparator()

        batch_action = QAction("📚 Batch", self)
        batch_action.triggered.connect(self.show_batch_download_dialog)
        toolbar.addAction(batch_action)

        toolbar.addSeparator()

        schedule_action = QAction("⏰ Schedule", self)
        schedule_action.triggered.connect(self.schedule_download)
        toolbar.addAction(schedule_action)

    def create_status_bar(self):
        """Create enhanced status bar"""
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)

        self.status_message = QLabel("Ready")
        self.statusBar.addWidget(self.status_message)

        self.statusBar.addPermanentWidget(QLabel("|"))

        self.downloads_count_status = QLabel("Downloads: 0")
        self.statusBar.addPermanentWidget(self.downloads_count_status)

        self.statusBar.addPermanentWidget(QLabel("|"))

        self.network_status = QLabel("🌐 Online")
        self.statusBar.addPermanentWidget(self.network_status)

    def setup_system_tray(self):
        """Setup system tray icon"""
        try:
            self.tray_icon = QSystemTrayIcon(self)
            self.tray_icon.setToolTip("Video Downloader Pro v3.0")

            tray_menu = QMenu()
            show_action = tray_menu.addAction("Show Window")
            show_action.triggered.connect(self.show)

            tray_menu.addSeparator()

            new_download_action = tray_menu.addAction("New Download")
            new_download_action.triggered.connect(lambda: (self.show(), self.tabs.setCurrentIndex(0)))

            tray_menu.addSeparator()

            quit_action = tray_menu.addAction("Quit")
            quit_action.triggered.connect(self.close)

            self.tray_icon.setContextMenu(tray_menu)
            self.tray_icon.activated.connect(self.tray_icon_activated)
        except:
            self.tray_icon = None

    def tray_icon_activated(self, reason):
        """Handle tray icon activation"""
        if reason == QSystemTrayIcon.DoubleClick:
            self.show()
            self.activateWindow()

    def init_ui(self):
        """Initialize the enhanced user interface"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # Modern Title with Statistics
        title_layout = QHBoxLayout()
        title = QLabel("🎬 Video Downloader Pro v3.0")
        title.setFont(QFont("Segoe UI", 20, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #58a6ff; margin-bottom: 10px;")
        title_layout.addWidget(title)

        self.stats_label = QLabel("Ready | Downloads: 0")
        self.stats_label.setStyleSheet("color: #7ee787; font-size: 10pt;")
        self.stats_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        title_layout.addWidget(self.stats_label)

        main_layout.addLayout(title_layout)

        # Tab Widget
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        main_layout.addWidget(self.tabs)

        self.create_download_tab()
        self.create_playlist_tab()
        self.create_history_tab()
        self.create_log_tab()
        self.create_code_tab()
        self.create_queue_tab()
        self.create_statistics_tab()

        self.update_code()
        self.log_message("Application initialized successfully - v3.0 Ultimate Edition")

    def create_download_tab(self):
        """Create the enhanced main download tab"""
        download_tab = QWidget()
        download_layout = QVBoxLayout(download_tab)
        download_layout.setSpacing(15)

        # URL Input Group
        url_group = QGroupBox("📎 Video URL & Preview")
        url_main_layout = QVBoxLayout()

        url_input_layout = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Paste YouTube, Vimeo, TikTok, Twitter, or any supported video URL...")
        self.url_input.textChanged.connect(self.on_url_changed)
        self.url_input.returnPressed.connect(self.fetch_video_info)
        url_input_layout.addWidget(self.url_input)

        self.fetch_info_btn = QPushButton("🔍 Get Info")
        self.fetch_info_btn.setObjectName("secondaryBtn")
        self.fetch_info_btn.clicked.connect(self.fetch_video_info)
        url_input_layout.addWidget(self.fetch_info_btn)

        self.download_btn = QPushButton("⬇ Download")
        self.download_btn.clicked.connect(self.start_download)
        url_input_layout.addWidget(self.download_btn)

        self.add_to_queue_btn = QPushButton("➕ Queue")
        self.add_to_queue_btn.setObjectName("secondaryBtn")
        self.add_to_queue_btn.clicked.connect(self.add_to_queue)
        url_input_layout.addWidget(self.add_to_queue_btn)

        url_main_layout.addLayout(url_input_layout)

        # Video Info Display
        self.info_frame = QFrame()
        self.info_frame.setStyleSheet("""
            QFrame {
                background-color: #161b22;
                border: 1px solid #30363d;
                border-radius: 6px;
                padding: 10px;
            }
        """)
        self.info_frame.setVisible(False)
        info_layout = QGridLayout(self.info_frame)

        self.video_title_label = QLabel("Title: -")
        self.video_title_label.setWordWrap(True)
        self.video_title_label.setStyleSheet("color: #58a6ff; font-weight: bold;")
        info_layout.addWidget(self.video_title_label, 0, 0, 1, 3)

        self.video_duration_label = QLabel("Duration: -")
        info_layout.addWidget(self.video_duration_label, 1, 0)

        self.video_uploader_label = QLabel("Uploader: -")
        info_layout.addWidget(self.video_uploader_label, 1, 1)

        self.video_upload_date_label = QLabel("Upload Date: -")
        info_layout.addWidget(self.video_upload_date_label, 1, 2)

        self.video_views_label = QLabel("Views: -")
        info_layout.addWidget(self.video_views_label, 2, 0)

        self.video_likes_label = QLabel("Likes: -")
        info_layout.addWidget(self.video_likes_label, 2, 1)

        self.video_size_label = QLabel("Est. Size: -")
        info_layout.addWidget(self.video_size_label, 2, 2)

        url_main_layout.addWidget(self.info_frame)
        url_group.setLayout(url_main_layout)
        download_layout.addWidget(url_group)

        # Settings Group
        settings_group = QGroupBox("⚙️ Download Settings")
        settings_layout = QVBoxLayout()

        # Output Path
        path_layout = QHBoxLayout()
        path_layout.addWidget(QLabel("Save to:"))
        self.path_input = QLineEdit()
        self.path_input.setText(self.settings.get('download_path',
                                                  os.path.join(os.path.expanduser("~"), "Downloads")))
        path_layout.addWidget(self.path_input, 1)

        browse_btn = QPushButton("📁 Browse")
        browse_btn.setObjectName("secondaryBtn")
        browse_btn.clicked.connect(self.browse_folder)
        path_layout.addWidget(browse_btn)
        settings_layout.addLayout(path_layout)

        # Filename template
        filename_layout = QHBoxLayout()
        filename_layout.addWidget(QLabel("Filename:"))
        self.filename_template = QLineEdit()
        self.filename_template.setPlaceholderText("%(title)s.%(ext)s")
        self.filename_template.setText(self.settings.get('filename_template', '%(title)s.%(ext)s'))
        self.filename_template.setToolTip("Available: %(title)s, %(id)s, %(ext)s, %(uploader)s, %(upload_date)s")
        filename_layout.addWidget(self.filename_template)
        settings_layout.addLayout(filename_layout)

        # Quality and Format
        quality_format_layout = QGridLayout()

        quality_format_layout.addWidget(QLabel("Quality:"), 0, 0)
        self.quality_combo = QComboBox()
        self.quality_combo.addItems([
            "Best Available (Auto)",
            "8K (4320p)",
            "4K (2160p)",
            "2K (1440p)",
            "Full HD (1080p)",
            "HD (720p)",
            "SD (480p)",
            "Low (360p)",
            "Mobile (240p)"
        ])
        self.quality_combo.setCurrentText(self.settings.get('quality', "Full HD (1080p)"))
        self.quality_combo.currentTextChanged.connect(self.update_code)
        quality_format_layout.addWidget(self.quality_combo, 0, 1)

        quality_format_layout.addWidget(QLabel("Format:"), 0, 2)
        self.format_combo = QComboBox()
        self.format_combo.addItems(["mp4", "mkv", "webm", "avi", "mov", "flv"])
        self.format_combo.setCurrentText(self.settings.get('format', "mp4"))
        self.format_combo.currentTextChanged.connect(self.update_code)
        quality_format_layout.addWidget(self.format_combo, 0, 3)

        quality_format_layout.addWidget(QLabel("Audio Format:"), 1, 0)
        self.audio_format_combo = QComboBox()
        self.audio_format_combo.addItems(["mp3", "m4a", "opus", "vorbis", "wav", "flac", "aac"])
        self.audio_format_combo.setCurrentText(self.settings.get('audio_format', "mp3"))
        quality_format_layout.addWidget(self.audio_format_combo, 1, 1)

        quality_format_layout.addWidget(QLabel("Audio Quality:"), 1, 2)
        self.audio_quality_combo = QComboBox()
        self.audio_quality_combo.addItems(["320 kbps", "256 kbps", "192 kbps", "128 kbps", "96 kbps", "64 kbps"])
        self.audio_quality_combo.setCurrentIndex(2)
        quality_format_layout.addWidget(self.audio_quality_combo, 1, 3)

        settings_layout.addLayout(quality_format_layout)

        # Checkboxes
        checkbox_grid = QGridLayout()

        self.audio_only_check = QCheckBox("🎵 Audio Only")
        self.audio_only_check.setChecked(self.settings.get('audio_only', False))
        self.audio_only_check.toggled.connect(self.toggle_audio_only)
        checkbox_grid.addWidget(self.audio_only_check, 0, 0)

        self.embed_thumbnail_check = QCheckBox("🖼️ Embed Thumbnail")
        self.embed_thumbnail_check.setChecked(self.settings.get('embed_thumbnail', False))
        checkbox_grid.addWidget(self.embed_thumbnail_check, 0, 1)

        self.embed_subs_check = QCheckBox("📝 Embed Subtitles")
        self.embed_subs_check.setChecked(self.settings.get('embed_subs', False))
        checkbox_grid.addWidget(self.embed_subs_check, 0, 2)

        self.download_subs_check = QCheckBox("💬 All Subtitles")
        checkbox_grid.addWidget(self.download_subs_check, 1, 0)

        self.write_description_check = QCheckBox("📄 Description")
        checkbox_grid.addWidget(self.write_description_check, 1, 1)

        self.write_thumbnail_check = QCheckBox("🎨 Thumbnail")
        checkbox_grid.addWidget(self.write_thumbnail_check, 1, 2)

        self.write_metadata_check = QCheckBox("📋 Metadata")
        self.write_metadata_check.setToolTip("Save video metadata to JSON file")
        checkbox_grid.addWidget(self.write_metadata_check, 2, 0)

        self.write_comments_check = QCheckBox("💭 Comments")
        self.write_comments_check.setToolTip("Save video comments")
        checkbox_grid.addWidget(self.write_comments_check, 2, 1)

        self.sponsorblock_check = QCheckBox("⏭️ SponsorBlock")
        self.sponsorblock_check.setToolTip("Skip sponsor segments")
        checkbox_grid.addWidget(self.sponsorblock_check, 2, 2)

        settings_layout.addLayout(checkbox_grid)
        settings_group.setLayout(settings_layout)
        download_layout.addWidget(settings_group)

        # Advanced Settings
        advanced_group = QGroupBox("🔧 Advanced Options")
        advanced_layout = QGridLayout()

        advanced_layout.addWidget(QLabel("Retries:"), 0, 0)
        self.retries_spin = QSpinBox()
        self.retries_spin.setRange(0, 50)
        self.retries_spin.setValue(self.settings.get('retries', 10))
        advanced_layout.addWidget(self.retries_spin, 0, 1)

        advanced_layout.addWidget(QLabel("Concurrent:"), 0, 2)
        self.concurrent_spin = QSpinBox()
        self.concurrent_spin.setRange(1, 16)
        self.concurrent_spin.setValue(self.settings.get('concurrent', 4))
        self.concurrent_spin.setToolTip("Number of concurrent fragments")
        advanced_layout.addWidget(self.concurrent_spin, 0, 3)

        advanced_layout.addWidget(QLabel("Timeout (s):"), 1, 0)
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(5, 300)
        self.timeout_spin.setValue(30)
        advanced_layout.addWidget(self.timeout_spin, 1, 1)

        self.ignore_errors_check = QCheckBox("⚠️ Ignore Errors")
        self.ignore_errors_check.setChecked(self.settings.get('ignore_errors', True))
        advanced_layout.addWidget(self.ignore_errors_check, 1, 2, 1, 2)

        self.no_playlist_check = QCheckBox("🚫 No Playlist")
        self.no_playlist_check.setToolTip("Download only single video")
        advanced_layout.addWidget(self.no_playlist_check, 2, 0)

        self.geo_bypass_check = QCheckBox("🌍 Geo-Bypass")
        self.geo_bypass_check.setToolTip("Bypass geographic restrictions")
        self.geo_bypass_check.setChecked(True)
        advanced_layout.addWidget(self.geo_bypass_check, 2, 1)

        self.limit_rate_check = QCheckBox("📊 Limit Rate")
        self.limit_rate_check.toggled.connect(self.toggle_rate_limit)
        advanced_layout.addWidget(self.limit_rate_check, 2, 2)

        self.rate_limit_input = QLineEdit()
        self.rate_limit_input.setPlaceholderText("e.g., 1M, 500K")
        self.rate_limit_input.setEnabled(False)
        advanced_layout.addWidget(self.rate_limit_input, 2, 3)

        advanced_group.setLayout(advanced_layout)
        download_layout.addWidget(advanced_group)

        # Progress Group
        progress_group = QGroupBox("📊 Download Progress")
        progress_layout = QVBoxLayout()

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        progress_layout.addWidget(self.progress_bar)

        stats_layout = QHBoxLayout()
        self.status_label = QLabel("Ready to download")
        self.status_label.setStyleSheet("color: #7ee787; font-weight: bold;")
        stats_layout.addWidget(self.status_label, 1)

        self.pause_btn = QPushButton("⏸️ Pause")
        self.pause_btn.setObjectName("pauseBtn")
        self.pause_btn.setEnabled(False)
        self.pause_btn.clicked.connect(self.pause_download)
        stats_layout.addWidget(self.pause_btn)

        self.cancel_btn = QPushButton("❌ Cancel")
        self.cancel_btn.setObjectName("cancelBtn")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self.cancel_download)
        stats_layout.addWidget(self.cancel_btn)

        progress_layout.addLayout(stats_layout)

        # Enhanced download stats
        stats_grid = QHBoxLayout()
        self.speed_label = QLabel("Speed: -")
        self.speed_label.setStyleSheet("color: #8b949e;")
        stats_grid.addWidget(self.speed_label)

        self.eta_label = QLabel("ETA: -")
        self.eta_label.setStyleSheet("color: #8b949e;")
        stats_grid.addWidget(self.eta_label)

        self.size_label = QLabel("Size: -")
        self.size_label.setStyleSheet("color: #8b949e;")
        stats_grid.addWidget(self.size_label)

        progress_layout.addLayout(stats_grid)

        progress_group.setLayout(progress_layout)
        download_layout.addWidget(progress_group)

        download_layout.addStretch()
        self.tabs.addTab(download_tab, "📥 Download")

    def create_playlist_tab(self):
        """Create enhanced playlist management tab"""
        playlist_tab = QWidget()
        playlist_layout = QVBoxLayout(playlist_tab)

        playlist_group = QGroupBox("📚 Playlist Manager")
        playlist_group_layout = QVBoxLayout()

        playlist_url_layout = QHBoxLayout()
        self.playlist_url_input = QLineEdit()
        self.playlist_url_input.setPlaceholderText("Enter playlist URL...")
        playlist_url_layout.addWidget(self.playlist_url_input)

        fetch_playlist_btn = QPushButton("🔍 Load Playlist")
        fetch_playlist_btn.clicked.connect(self.fetch_playlist_info)
        playlist_url_layout.addWidget(fetch_playlist_btn)

        playlist_group_layout.addLayout(playlist_url_layout)

        # Playlist info
        self.playlist_info_label = QLabel("No playlist loaded")
        self.playlist_info_label.setStyleSheet("color: #8b949e;")
        playlist_group_layout.addWidget(self.playlist_info_label)

        self.playlist_list = QListWidget()
        self.playlist_list.setSelectionMode(QListWidget.MultiSelection)
        playlist_group_layout.addWidget(self.playlist_list)

        playlist_actions = QHBoxLayout()
        select_all_btn = QPushButton("✓ Select All")
        select_all_btn.setObjectName("secondaryBtn")
        select_all_btn.clicked.connect(lambda: self.playlist_list.selectAll())
        playlist_actions.addWidget(select_all_btn)

        clear_selection_btn = QPushButton("✗ Clear Selection")
        clear_selection_btn.setObjectName("secondaryBtn")
        clear_selection_btn.clicked.connect(lambda: self.playlist_list.clearSelection())
        playlist_actions.addWidget(clear_selection_btn)

        reverse_selection_btn = QPushButton("🔄 Reverse")
        reverse_selection_btn.setObjectName("secondaryBtn")
        reverse_selection_btn.clicked.connect(self.reverse_playlist_selection)
        playlist_actions.addWidget(reverse_selection_btn)

        download_selected_btn = QPushButton("⬇ Download Selected")
        download_selected_btn.clicked.connect(self.download_playlist_selected)
        playlist_actions.addWidget(download_selected_btn)

        playlist_group_layout.addLayout(playlist_actions)
        playlist_group.setLayout(playlist_group_layout)
        playlist_layout.addWidget(playlist_group)

        self.tabs.addTab(playlist_tab, "📚 Playlist")

    def create_history_tab(self):
        """Create enhanced download history tab"""
        history_tab = QWidget()
        history_layout = QVBoxLayout(history_tab)

        history_header = QHBoxLayout()
        history_label = QLabel("📜 Download History")
        history_label.setFont(QFont("Segoe UI", 14, QFont.Bold))
        history_label.setStyleSheet("color: #58a6ff;")
        history_header.addWidget(history_label)

        self.history_count_label = QLabel("0 downloads")
        self.history_count_label.setStyleSheet("color: #8b949e;")
        history_header.addWidget(self.history_count_label)
        history_header.addStretch()

        history_layout.addLayout(history_header)

        # Search bar
        search_layout = QHBoxLayout()
        self.history_search = QLineEdit()
        self.history_search.setPlaceholderText("🔍 Search history...")
        self.history_search.textChanged.connect(self.filter_history)
        search_layout.addWidget(self.history_search)
        history_layout.addLayout(search_layout)

        self.history_list = QListWidget()
        self.history_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.history_list.customContextMenuRequested.connect(self.show_history_context_menu)
        history_layout.addWidget(self.history_list)

        history_actions = QHBoxLayout()

        export_history_btn = QPushButton("💾 Export History")
        export_history_btn.setObjectName("secondaryBtn")
        export_history_btn.clicked.connect(self.export_history)
        history_actions.addWidget(export_history_btn)

        clear_history_btn = QPushButton("🗑 Clear History")
        clear_history_btn.setObjectName("cancelBtn")
        clear_history_btn.clicked.connect(self.clear_history)
        history_actions.addWidget(clear_history_btn)

        history_actions.addStretch()
        history_layout.addLayout(history_actions)

        self.tabs.addTab(history_tab, "📜 History")

    def create_log_tab(self):
        """Create log tab"""
        log_tab = QWidget()
        log_layout = QVBoxLayout(log_tab)

        log_header = QHBoxLayout()
        log_label = QLabel("📋 Download Log")
        log_label.setFont(QFont("Segoe UI", 14, QFont.Bold))
        log_label.setStyleSheet("color: #58a6ff;")
        log_header.addWidget(log_label)
        log_header.addStretch()

        self.auto_scroll_check = QCheckBox("Auto-scroll")
        self.auto_scroll_check.setChecked(True)
        log_header.addWidget(self.auto_scroll_check)

        clear_log_btn = QPushButton("🗑 Clear")
        clear_log_btn.setObjectName("secondaryBtn")
        clear_log_btn.clicked.connect(self.clear_log)
        log_header.addWidget(clear_log_btn)

        save_log_btn = QPushButton("💾 Save")
        save_log_btn.setObjectName("secondaryBtn")
        save_log_btn.clicked.connect(self.save_log)
        log_header.addWidget(save_log_btn)

        log_layout.addLayout(log_header)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        log_layout.addWidget(self.log_text)

        self.tabs.addTab(log_tab, "📋 Log")

    def create_code_tab(self):
        """Create code generator tab"""
        code_tab = QWidget()
        code_layout = QVBoxLayout(code_tab)

        code_header = QHBoxLayout()
        code_label = QLabel("💻 Python Code Generator")
        code_label.setFont(QFont("Segoe UI", 14, QFont.Bold))
        code_label.setStyleSheet("color: #58a6ff;")
        code_header.addWidget(code_label)
        code_header.addStretch()

        copy_code_btn = QPushButton("📋 Copy")
        copy_code_btn.setObjectName("secondaryBtn")
        copy_code_btn.clicked.connect(self.copy_code)
        code_header.addWidget(copy_code_btn)

        save_code_btn = QPushButton("💾 Save")
        save_code_btn.setObjectName("secondaryBtn")
        save_code_btn.clicked.connect(self.save_code)
        code_header.addWidget(save_code_btn)

        code_layout.addLayout(code_header)

        self.code_text = QTextEdit()
        self.code_text.setReadOnly(True)
        self.code_text.setFont(QFont("Consolas", 10))
        code_layout.addWidget(self.code_text)

        self.tabs.addTab(code_tab, "💻 Code")

    def create_queue_tab(self):
        """Create enhanced download queue tab"""
        queue_tab = QWidget()
        queue_layout = QVBoxLayout(queue_tab)

        queue_header = QHBoxLayout()
        queue_label = QLabel("📋 Download Queue")
        queue_label.setFont(QFont("Segoe UI", 14, QFont.Bold))
        queue_label.setStyleSheet("color: #58a6ff;")
        queue_header.addWidget(queue_label)

        self.queue_count_label = QLabel("0 items")
        self.queue_count_label.setStyleSheet("color: #8b949e;")
        queue_header.addWidget(self.queue_count_label)
        queue_header.addStretch()

        queue_layout.addLayout(queue_header)

        self.queue_table = QTableWidget()
        self.queue_table.setColumnCount(5)
        self.queue_table.setHorizontalHeaderLabels(["#", "URL", "Priority", "Status", "Actions"])
        self.queue_table.horizontalHeader().setStretchLastSection(False)
        self.queue_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.queue_table.setSelectionBehavior(QTableWidget.SelectRows)
        queue_layout.addWidget(self.queue_table)

        queue_actions = QHBoxLayout()

        start_queue_btn = QPushButton("▶️ Start Queue")
        start_queue_btn.clicked.connect(self.start_queue_download)
        queue_actions.addWidget(start_queue_btn)

        self.pause_queue_btn = QPushButton("⏸️ Pause Queue")
        self.pause_queue_btn.setObjectName("pauseBtn")
        self.pause_queue_btn.setEnabled(False)
        self.pause_queue_btn.clicked.connect(self.pause_queue)
        queue_actions.addWidget(self.pause_queue_btn)

        clear_completed_btn = QPushButton("✓ Clear Completed")
        clear_completed_btn.setObjectName("secondaryBtn")
        clear_completed_btn.clicked.connect(self.clear_completed_queue)
        queue_actions.addWidget(clear_completed_btn)

        clear_queue_btn = QPushButton("🗑 Clear All")
        clear_queue_btn.setObjectName("cancelBtn")
        clear_queue_btn.clicked.connect(self.clear_queue)
        queue_actions.addWidget(clear_queue_btn)

        queue_actions.addStretch()
        queue_layout.addLayout(queue_actions)

        self.tabs.addTab(queue_tab, "📋 Queue")

    def create_statistics_tab(self):
        """Create statistics and analytics tab"""
        stats_tab = QWidget()
        stats_layout = QVBoxLayout(stats_tab)

        stats_header = QLabel("📊 Download Statistics & Analytics")
        stats_header.setFont(QFont("Segoe UI", 14, QFont.Bold))
        stats_header.setStyleSheet("color: #58a6ff; margin-bottom: 10px;")
        stats_layout.addWidget(stats_header)

        # Overview stats
        overview_group = QGroupBox("📈 Overview")
        overview_layout = QGridLayout()

        self.total_downloads_label = QLabel("Total Downloads: 0")
        self.total_downloads_label.setStyleSheet("font-size: 12pt; color: #7ee787;")
        overview_layout.addWidget(self.total_downloads_label, 0, 0)

        self.successful_downloads_label = QLabel("Successful: 0")
        self.successful_downloads_label.setStyleSheet("font-size: 12pt; color: #7ee787;")
        overview_layout.addWidget(self.successful_downloads_label, 0, 1)

        self.failed_downloads_label = QLabel("Failed: 0")
        self.failed_downloads_label.setStyleSheet("font-size: 12pt; color: #f85149;")
        overview_layout.addWidget(self.failed_downloads_label, 0, 2)

        self.total_size_label = QLabel("Total Size: 0 B")
        self.total_size_label.setStyleSheet("font-size: 12pt; color: #58a6ff;")
        overview_layout.addWidget(self.total_size_label, 1, 0)

        self.total_time_label = QLabel("Total Time: 0s")
        self.total_time_label.setStyleSheet("font-size: 12pt; color: #58a6ff;")
        overview_layout.addWidget(self.total_time_label, 1, 1)

        self.avg_speed_label = QLabel("Avg Speed: 0 B/s")
        self.avg_speed_label.setStyleSheet("font-size: 12pt; color: #58a6ff;")
        overview_layout.addWidget(self.avg_speed_label, 1, 2)

        overview_group.setLayout(overview_layout)
        stats_layout.addWidget(overview_group)

        # Recent activity
        recent_group = QGroupBox("🕐 Recent Activity (Last 24h)")
        recent_layout = QVBoxLayout()

        self.recent_downloads_label = QLabel("Downloads: 0")
        recent_layout.addWidget(self.recent_downloads_label)

        self.recent_size_label = QLabel("Data Downloaded: 0 B")
        recent_layout.addWidget(self.recent_size_label)

        recent_group.setLayout(recent_layout)
        stats_layout.addWidget(recent_group)

        # Buttons
        stats_actions = QHBoxLayout()

        refresh_stats_btn = QPushButton("🔄 Refresh Statistics")
        refresh_stats_btn.setObjectName("secondaryBtn")
        refresh_stats_btn.clicked.connect(self.update_statistics_display)
        stats_actions.addWidget(refresh_stats_btn)

        export_stats_btn = QPushButton("💾 Export Statistics")
        export_stats_btn.setObjectName("secondaryBtn")
        export_stats_btn.clicked.connect(self.export_statistics)
        stats_actions.addWidget(export_stats_btn)

        reset_stats_btn = QPushButton("🗑 Reset Statistics")
        reset_stats_btn.setObjectName("cancelBtn")
        reset_stats_btn.clicked.connect(self.reset_statistics)
        stats_actions.addWidget(reset_stats_btn)

        stats_actions.addStretch()
        stats_layout.addLayout(stats_actions)

        stats_layout.addStretch()
        self.tabs.addTab(stats_tab, "📊 Statistics")

    # ===== HELPER METHODS =====

    def on_url_changed(self):
        """Handle URL input changes"""
        self.info_frame.setVisible(False)
        self.current_video_info = None

    def toggle_rate_limit(self, checked):
        """Toggle rate limit input"""
        self.rate_limit_input.setEnabled(checked)

    def load_settings(self):
        """Load user settings from file"""
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, 'r') as f:
                    self.settings = json.load(f)
            else:
                self.settings = {}
        except:
            self.settings = {}

    def save_settings(self):
        """Save user settings to file"""
        try:
            settings = {
                'download_path': self.path_input.text(),
                'quality': self.quality_combo.currentText(),
                'format': self.format_combo.currentText(),
                'audio_format': self.audio_format_combo.currentText(),
                'audio_only': self.audio_only_check.isChecked(),
                'embed_thumbnail': self.embed_thumbnail_check.isChecked(),
                'embed_subs': self.embed_subs_check.isChecked(),
                'retries': self.retries_spin.value(),
                'concurrent': self.concurrent_spin.value(),
                'ignore_errors': self.ignore_errors_check.isChecked(),
                'filename_template': self.filename_template.text(),
            }
            with open(self.settings_file, 'w') as f:
                json.dump(settings, f, indent=2)
        except Exception as e:
            self.log_message(f"Failed to save settings: {str(e)}")

    def load_history(self):
        """Load download history from file"""
        history_file = os.path.join(os.path.expanduser("~"), ".video_downloader_history.json")
        try:
            if os.path.exists(history_file):
                with open(history_file, 'r') as f:
                    self.download_history = json.load(f)
                    for entry in self.download_history:
                        self.history_list.addItem(entry)
                    self.update_history_count()
        except:
            pass

    def save_history(self):
        """Save download history to file"""
        history_file = os.path.join(os.path.expanduser("~"), ".video_downloader_history.json")
        try:
            with open(history_file, 'w') as f:
                json.dump(self.download_history, f, indent=2)
        except Exception as e:
            self.log_message(f"Failed to save history: {str(e)}")

    def browse_folder(self):
        """Open folder browser dialog"""
        folder = QFileDialog.getExistingDirectory(self, "Select Download Folder")
        if folder:
            self.path_input.setText(folder)

    def toggle_audio_only(self, checked):
        """Enable/disable quality selection based on audio only mode"""
        self.quality_combo.setEnabled(not checked)
        self.format_combo.setEnabled(not checked)
        self.update_code()

    def get_quality_value(self):
        """Get quality value from combo box"""
        quality_map = {
            "Best Available (Auto)": "best",
            "8K (4320p)": "4320",
            "4K (2160p)": "2160",
            "2K (1440p)": "1440",
            "Full HD (1080p)": "1080",
            "HD (720p)": "720",
            "SD (480p)": "480",
            "Low (360p)": "360",
            "Mobile (240p)": "240"
        }
        return quality_map[self.quality_combo.currentText()]

    def format_bytes(self, bytes_val):
        """Format bytes to human readable format"""
        if not bytes_val:
            return "0 B"
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_val < 1024.0:
                return f"{bytes_val:.2f} {unit}"
            bytes_val /= 1024.0
        return f"{bytes_val:.2f} PB"

    def format_duration(self, seconds):
        """Format duration in seconds to readable format"""
        if not seconds:
            return "Unknown"
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        if hours > 0:
            return f"{hours}h {minutes}m {secs}s"
        elif minutes > 0:
            return f"{minutes}m {secs}s"
        else:
            return f"{secs}s"

    def log_message(self, message):
        """Add message to log with auto-scroll"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted_msg = f"[{timestamp}] {message}"
        self.log_text.append(formatted_msg)

        if self.auto_scroll_check.isChecked():
            self.log_text.verticalScrollBar().setValue(
                self.log_text.verticalScrollBar().maximum()
            )

        short_msg = message[:50] + "..." if len(message) > 50 else message
        self.status_message.setText(short_msg)

    def clear_log(self):
        """Clear the log"""
        self.log_text.clear()
        self.log_message("Log cleared")

    def save_log(self):
        """Save log to file"""
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save Log",
            f"download_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            "Text Files (*.txt);;All Files (*)"
        )
        if filename:
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(self.log_text.toPlainText())
                self.log_message(f"Log saved to: {filename}")
                QMessageBox.information(self, "Success", f"Log saved to:\n{filename}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save log:\n{str(e)}")

    # ===== VIDEO INFO METHODS =====

    def fetch_video_info(self):
        """Fetch detailed video information"""
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "Error", "Please enter a valid URL!")
            return

        if self.info_thread and self.info_thread.isRunning():
            return

        self.fetch_info_btn.setEnabled(False)
        self.fetch_info_btn.setText("⏳ Fetching...")
        self.log_message(f"Fetching info for: {url}")

        self.info_thread = VideoInfoThread(url)
        self.info_thread.info_ready.connect(self.display_video_info)
        self.info_thread.error.connect(self.info_fetch_error)
        self.info_thread.start()

    def display_video_info(self, info):
        """Display enhanced video information"""
        self.current_video_info = info
        self.fetch_info_btn.setEnabled(True)
        self.fetch_info_btn.setText("🔍 Get Info")

        title = info.get('title', 'Unknown')
        duration = self.format_duration(info.get('duration', 0))
        uploader = info.get('uploader', 'Unknown')
        upload_date = info.get('upload_date', '')
        if upload_date:
            try:
                upload_date = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:8]}"
            except:
                pass
        views = info.get('view_count', 0)
        likes = info.get('like_count', 0)
        filesize = info.get('filesize', 0) or info.get('filesize_approx', 0)

        self.video_title_label.setText(f"Title: {title}")
        self.video_duration_label.setText(f"⏱️ {duration}")
        self.video_uploader_label.setText(f"👤 {uploader}")
        self.video_upload_date_label.setText(f"📅 {upload_date if upload_date else 'N/A'}")
        self.video_views_label.setText(f"👁️ {views:,}" if views else "👁️ N/A")
        self.video_likes_label.setText(f"👍 {likes:,}" if likes else "👍 N/A")
        self.video_size_label.setText(f"💾 {self.format_bytes(filesize)}" if filesize else "💾 N/A")

        self.info_frame.setVisible(True)
        self.log_message(f"Info fetched: {title}")

    def info_fetch_error(self, error):
        """Handle info fetch error"""
        self.fetch_info_btn.setEnabled(True)
        self.fetch_info_btn.setText("🔍 Get Info")
        self.log_message(f"Error fetching info: {error}")
        QMessageBox.warning(self, "Error", f"Failed to fetch video info:\n{error}")

    # ===== PLAYLIST METHODS =====

    def fetch_playlist_info(self):
        """Fetch enhanced playlist information"""
        url = self.playlist_url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "Error", "Please enter a playlist URL!")
            return

        if self.playlist_thread and self.playlist_thread.isRunning():
            return

        self.playlist_list.clear()
        self.playlist_info_label.setText("Loading playlist...")
        self.log_message(f"Fetching playlist: {url}")

        self.playlist_thread = PlaylistInfoThread(url)
        self.playlist_thread.info_ready.connect(self.display_playlist_info)
        self.playlist_thread.error.connect(self.playlist_fetch_error)
        self.playlist_thread.progress.connect(self.update_playlist_progress)
        self.playlist_thread.start()

    def update_playlist_progress(self, current, total):
        """Update playlist loading progress"""
        self.playlist_info_label.setText(f"Loading: {current}/{total} videos")

    def display_playlist_info(self, videos):
        """Display enhanced playlist videos"""
        self.playlist_list.clear()
        total_duration = 0

        for i, video in enumerate(videos, 1):
            duration = video.get('duration', 0)
            total_duration += duration
            duration_str = self.format_duration(duration)
            uploader = video.get('uploader', 'Unknown')
            views = video.get('view_count', 0)
            views_str = f"{views:,}" if views else "N/A"

            item_text = f"{i}. {video['title']} | {duration_str} | 👤 {uploader} | 👁️ {views_str}"
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, video)
            self.playlist_list.addItem(item)

        total_duration_str = self.format_duration(total_duration)
        self.playlist_info_label.setText(
            f"Loaded {len(videos)} videos | Total Duration: {total_duration_str}"
        )

        self.log_message(f"Loaded {len(videos)} videos from playlist")
        QMessageBox.information(self, "Success",
                                f"Loaded {len(videos)} videos!\nTotal Duration: {total_duration_str}")

    def playlist_fetch_error(self, error):
        """Handle playlist fetch error"""
        self.playlist_info_label.setText("Failed to load playlist")
        self.log_message(f"Error fetching playlist: {error}")
        QMessageBox.warning(self, "Error", f"Failed to fetch playlist:\n{error}")

    def reverse_playlist_selection(self):
        """Reverse playlist selection"""
        for i in range(self.playlist_list.count()):
            item = self.playlist_list.item(i)
            item.setSelected(not item.isSelected())

    def download_playlist_selected(self):
        """Download selected videos from playlist"""
        selected_items = self.playlist_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Error", "Please select videos to download!")
            return

        urls = []
        for item in selected_items:
            video = item.data(Qt.UserRole)
            if video and video.get('id'):
                urls.append(f"https://www.youtube.com/watch?v={video['id']}")

        if urls:
            reply = QMessageBox.question(
                self, "Confirm Download",
                f"Add {len(urls)} videos to download queue?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                for url in urls:
                    self.add_url_to_queue(url)
                self.tabs.setCurrentIndex(5)

    # ===== QUEUE METHODS =====

    def add_to_queue(self):
        """Add current URL to download queue"""
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "Error", "Please enter a valid URL!")
            return

        self.add_url_to_queue(url)

    def add_url_to_queue(self, url, priority="Normal"):
        """Add URL to queue table"""
        row_position = self.queue_table.rowCount()
        self.queue_table.insertRow(row_position)

        self.queue_table.setItem(row_position, 0, QTableWidgetItem(str(row_position + 1)))
        self.queue_table.setItem(row_position, 1, QTableWidgetItem(url))

        priority_combo = QComboBox()
        priority_combo.addItems(["High", "Normal", "Low"])
        priority_combo.setCurrentText(priority)
        self.queue_table.setCellWidget(row_position, 2, priority_combo)

        self.queue_table.setItem(row_position, 3, QTableWidgetItem("⏳ Pending"))

        remove_btn = QPushButton("🗑")
        remove_btn.setObjectName("cancelBtn")
        remove_btn.clicked.connect(lambda: self.remove_from_queue(row_position))
        self.queue_table.setCellWidget(row_position, 4, remove_btn)

        self.download_queue.append({'url': url, 'status': 'pending', 'priority': priority})
        self.update_queue_count()
        self.log_message(f"Added to queue: {url}")

    def remove_from_queue(self, row):
        """Remove item from queue"""
        if 0 <= row < len(self.download_queue):
            url = self.download_queue[row]['url']
            del self.download_queue[row]
            self.queue_table.removeRow(row)
            self.update_queue_count()
            self.log_message(f"Removed from queue: {url}")

            for i in range(self.queue_table.rowCount()):
                self.queue_table.setItem(i, 0, QTableWidgetItem(str(i + 1)))

    def clear_queue(self):
        """Clear download queue"""
        if not self.download_queue:
            return

        reply = QMessageBox.question(
            self, "Clear Queue",
            "Are you sure you want to clear the download queue?",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self.download_queue.clear()
            self.queue_table.setRowCount(0)
            self.update_queue_count()
            self.log_message("Queue cleared")

    def clear_completed_queue(self):
        """Clear completed items from queue"""
        rows_to_remove = []
        for i, item in enumerate(self.download_queue):
            if item['status'] == 'completed':
                rows_to_remove.append(i)

        for i in reversed(rows_to_remove):
            del self.download_queue[i]
            self.queue_table.removeRow(i)

        for i in range(self.queue_table.rowCount()):
            self.queue_table.setItem(i, 0, QTableWidgetItem(str(i + 1)))

        self.update_queue_count()
        self.log_message(f"Cleared {len(rows_to_remove)} completed items")

    def update_queue_count(self):
        """Update queue count label"""
        count = len(self.download_queue)
        pending = sum(1 for item in self.download_queue if item['status'] == 'pending')
        self.queue_count_label.setText(f"{count} items ({pending} pending)")

    def start_queue_download(self):
        """Start downloading queue"""
        if not self.download_queue:
            QMessageBox.information(self, "Info", "Queue is empty!")
            return

        if self.batch_thread and self.batch_thread.isRunning():
            QMessageBox.warning(self, "Error", "Batch download already in progress!")
            return

        urls = [item['url'] for item in self.download_queue if item['status'] == 'pending']
        if not urls:
            QMessageBox.information(self, "Info", "No pending downloads in queue!")
            return

        options = self.get_download_options()

        self.batch_thread = BatchDownloadThread(urls, options)
        self.batch_thread.progress.connect(self.update_batch_progress)
        self.batch_thread.item_finished.connect(self.batch_item_finished)
        self.batch_thread.all_finished.connect(self.batch_all_finished)
        self.batch_thread.start()

        self.pause_queue_btn.setEnabled(True)
        self.log_message(f"Starting batch download of {len(urls)} items")

    def pause_queue(self):
        """Pause/resume queue download"""
        if self.batch_thread and self.batch_thread.isRunning():
            if self.batch_thread._is_paused:
                self.batch_thread.resume()
                self.pause_queue_btn.setText("⏸️ Pause Queue")
                self.log_message("Queue resumed")
            else:
                self.batch_thread.pause()
                self.pause_queue_btn.setText("▶️ Resume Queue")
                self.log_message("Queue paused")

    def update_batch_progress(self, current, total, url):
        """Update batch download progress"""
        self.log_message(f"Downloading {current}/{total}: {url}")

        for i, item in enumerate(self.download_queue):
            if item['url'] == url:
                self.queue_table.setItem(i, 3, QTableWidgetItem(f"⬇️ Downloading ({current}/{total})"))
                break

    def batch_item_finished(self, success, url, message):
        """Handle individual batch item finish"""
        self.log_message(message)

        for i, item in enumerate(self.download_queue):
            if item['url'] == url:
                if success:
                    self.queue_table.setItem(i, 3, QTableWidgetItem("✅ Completed"))
                    item['status'] = 'completed'
                else:
                    self.queue_table.setItem(i, 3, QTableWidgetItem("❌ Failed"))
                    item['status'] = 'failed'
                break

    def batch_all_finished(self, successful, failed):
        """Handle batch download completion"""
        self.pause_queue_btn.setEnabled(False)
        self.pause_queue_btn.setText("⏸️ Pause Queue")
        self.log_message(f"Batch download finished: {successful} successful, {failed} failed")
        QMessageBox.information(
            self, "Batch Download Complete",
            f"Batch download finished!\n\nSuccessful: {successful}\nFailed: {failed}"
        )

    # ===== DOWNLOAD METHODS =====

    def get_download_options(self):
        """Get enhanced download options"""
        quality = self.get_quality_value()
        format_type = self.format_combo.currentText()
        audio_only = self.audio_only_check.isChecked()
        audio_quality = self.audio_quality_combo.currentText().split()[0]

        if audio_only:
            format_str = "bestaudio/best"
        else:
            if quality == "best":
                format_str = "bestvideo+bestaudio/best"
            else:
                format_str = f"bestvideo[height<={quality}]+bestaudio/best[height<={quality}]"

        postprocessors = []
        if audio_only:
            postprocessors.append({
                'key': 'FFmpegExtractAudio',
                'preferredcodec': self.audio_format_combo.currentText(),
                'preferredquality': audio_quality,
            })
        else:
            postprocessors.append({
                'key': 'FFmpegVideoConvertor',
                'preferedformat': format_type,
            })

        if self.embed_thumbnail_check.isChecked():
            postprocessors.append({'key': 'EmbedThumbnail'})

        if self.embed_subs_check.isChecked():
            postprocessors.append({'key': 'FFmpegEmbedSubtitle'})

        if self.sponsorblock_check.isChecked():
            postprocessors.append({
                'key': 'SponsorBlock',
                'categories': ['sponsor', 'intro', 'outro', 'selfpromo']
            })

        filename_template = self.filename_template.text() or '%(title)s.%(ext)s'

        ydl_opts = {
            'format': format_str,
            'outtmpl': os.path.join(self.path_input.text(), filename_template),
            'merge_output_format': format_type,
            'ignoreerrors': self.ignore_errors_check.isChecked(),
            'no_warnings': False,
            'quiet': False,
            'retries': self.retries_spin.value(),
            'fragment_retries': self.retries_spin.value(),
            'concurrent_fragment_downloads': self.concurrent_spin.value(),
            'windowsfilenames': True,
            'postprocessors': postprocessors,
            'socket_timeout': self.timeout_spin.value(),
            'geo_bypass': self.geo_bypass_check.isChecked(),
            'auto_update': True,
        }

        if self.download_subs_check.isChecked():
            ydl_opts['writesubtitles'] = True
            ydl_opts['allsubtitles'] = True

        if self.write_description_check.isChecked():
            ydl_opts['writedescription'] = True

        if self.write_thumbnail_check.isChecked():
            ydl_opts['writethumbnail'] = True

        if self.write_metadata_check.isChecked():
            ydl_opts['writeinfojson'] = True

        if self.write_comments_check.isChecked():
            ydl_opts['writecomments'] = True
            ydl_opts['getcomments'] = True

        if self.no_playlist_check.isChecked():
            ydl_opts['noplaylist'] = True

        if self.limit_rate_check.isChecked() and self.rate_limit_input.text():
            ydl_opts['ratelimit'] = self.rate_limit_input.text()

        return ydl_opts

    def start_download(self):
        """Start the enhanced download process"""
        url = self.url_input.text().strip()

        if not url:
            QMessageBox.warning(self, "Error", "Please enter a valid URL!")
            return

        if self.download_thread and self.download_thread.isRunning():
            QMessageBox.warning(self, "Error", "A download is already in progress!")
            return

        output_path = self.path_input.text()
        if not os.path.exists(output_path):
            try:
                os.makedirs(output_path)
            except:
                QMessageBox.warning(self, "Error", "Invalid output path!")
                return

        ydl_opts = self.get_download_options()

        self.download_thread = DownloadThread(url, ydl_opts)
        self.download_thread.progress.connect(self.update_progress)
        self.download_thread.finished.connect(self.download_finished)
        self.download_thread.log_message.connect(self.log_message)
        self.download_thread.start()

        self.download_btn.setEnabled(False)
        self.download_btn.setText("⏳ Downloading...")
        self.pause_btn.setEnabled(True)
        self.cancel_btn.setEnabled(True)
        self.progress_bar.setValue(0)
        self.status_label.setText("Initializing download...")
        self.status_label.setStyleSheet("color: #58a6ff; font-weight: bold;")

        self.save_settings()

    def pause_download(self):
        """Pause/resume download"""
        if self.download_thread and self.download_thread.isRunning():
            if self.download_thread._is_paused:
                self.download_thread.resume()
                self.pause_btn.setText("⏸️ Pause")
                self.status_label.setText("Download resumed")
            else:
                self.download_thread.pause()
                self.pause_btn.setText("▶️ Resume")
                self.status_label.setText("Download paused")

    def cancel_download(self):
        """Cancel ongoing download"""
        if self.download_thread and self.download_thread.isRunning():
            reply = QMessageBox.question(
                self, "Cancel Download",
                "Are you sure you want to cancel the download?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.download_thread.cancel()
                self.log_message("Download cancelled by user")

    def update_progress(self, data):
        """Update enhanced progress display"""
        if data['status'] == 'downloading':
            percent = int(data['percent'])
            self.progress_bar.setValue(percent)

            speed = data.get('speed', 0)
            eta = data.get('eta', 0)
            downloaded = data.get('downloaded', 0)
            total = data.get('total', 0)
            elapsed = data.get('elapsed', 0)

            speed_str = self.format_bytes(speed) + "/s" if speed else "N/A"
            eta_str = f"{eta}s" if eta else "N/A"
            downloaded_str = self.format_bytes(downloaded)
            total_str = self.format_bytes(total) if total else "N/A"

            self.status_label.setText(f"Downloading: {percent}%")
            self.speed_label.setText(f"Speed: {speed_str}")
            self.eta_label.setText(f"ETA: {eta_str}")
            self.size_label.setText(f"Size: {downloaded_str} / {total_str}")

        elif data['status'] == 'processing':
            self.progress_bar.setValue(100)
            self.status_label.setText("Processing and merging files...")
            self.speed_label.setText("Almost done...")

    def download_finished(self, success, message, filepath):
        """Handle enhanced download completion"""
        self.download_btn.setEnabled(True)
        self.download_btn.setText("⬇ Download")
        self.pause_btn.setEnabled(False)
        self.pause_btn.setText("⏸️ Pause")
        self.cancel_btn.setEnabled(False)

        if success:
            self.progress_bar.setValue(100)
            self.status_label.setText("✅ " + message)
            self.status_label.setStyleSheet("color: #7ee787; font-weight: bold;")
            self.speed_label.setText("Completed!")

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            quality = self.quality_combo.currentText()
            format_type = self.format_combo.currentText().upper()
            video_title = self.current_video_info.get('title', 'Unknown') if self.current_video_info else 'Unknown'

            history_entry = f"[{timestamp}] {video_title} | {quality} | {format_type}"
            self.history_list.insertItem(0, history_entry)
            self.download_history.insert(0, history_entry)

            if len(self.download_history) > 100:
                self.download_history = self.download_history[:100]
                self.history_list.takeItem(100)

            self.download_statistics['total_downloads'] += 1
            self.download_statistics['successful_downloads'] += 1
            if self.current_video_info:
                filesize = self.current_video_info.get('filesize', 0) or self.current_video_info.get('filesize_approx',
                                                                                                     0)
                self.download_statistics['total_bytes'] += filesize

            self.save_history()
            self.save_statistics()
            self.update_history_count()
            self.update_stats()
            self.update_statistics_display()

            self.log_message(f"✅ {message}")

            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Information)
            msg_box.setWindowTitle("Success")
            msg_box.setText(f"{message}\n\nSaved to: {self.path_input.text()}")
            msg_box.setStandardButtons(QMessageBox.Ok | QMessageBox.Open)
            msg_box.button(QMessageBox.Open).setText("Open Folder")

            result = msg_box.exec_()
            if result == QMessageBox.Open:
                self.open_download_folder()

        else:
            self.progress_bar.setValue(0)
            self.status_label.setText("❌ Download failed")
            self.status_label.setStyleSheet("color: #f85149; font-weight: bold;")
            self.speed_label.setText("-")
            self.download_statistics['total_downloads'] += 1
            self.download_statistics['failed_downloads'] += 1
            self.save_statistics()
            self.update_statistics_display()
            self.log_message(f"❌ {message}")
            QMessageBox.critical(self, "Error", message)

    # ===== HISTORY METHODS =====

    def update_history_count(self):
        """Update history count label"""
        count = len(self.download_history)
        self.history_count_label.setText(f"{count} download{'s' if count != 1 else ''}")
        self.downloads_count_status.setText(f"Downloads: {count}")

    def update_stats(self):
        """Update statistics label"""
        count = len(self.download_history)
        self.stats_label.setText(f"Ready | Downloads: {count}")

    def filter_history(self, text):
        """Filter history based on search text"""
        for i in range(self.history_list.count()):
            item = self.history_list.item(i)
            item.setHidden(text.lower() not in item.text().lower())

    def show_history_context_menu(self, position):
        """Show context menu for history items"""
        item = self.history_list.itemAt(position)
        if item:
            menu = QMenu()
            copy_action = menu.addAction("📋 Copy")
            delete_action = menu.addAction("🗑 Delete")

            action = menu.exec_(self.history_list.mapToGlobal(position))

            if action == copy_action:
                clipboard = QApplication.clipboard()
                clipboard.setText(item.text())
            elif action == delete_action:
                row = self.history_list.row(item)
                self.history_list.takeItem(row)
                del self.download_history[row]
                self.save_history()
                self.update_history_count()

    def export_history(self):
        """Export history to file"""
        if not self.download_history:
            QMessageBox.information(self, "Info", "No history to export!")
            return

        filename, _ = QFileDialog.getSaveFileName(
            self, "Export History",
            f"download_history_{datetime.now().strftime('%Y%m%d')}.txt",
            "Text Files (*.txt);;JSON Files (*.json);;CSV Files (*.csv);;All Files (*)"
        )

        if filename:
            try:
                if filename.endswith('.json'):
                    with open(filename, 'w', encoding='utf-8') as f:
                        json.dump(self.download_history, f, indent=2)
                elif filename.endswith('.csv'):
                    with open(filename, 'w', encoding='utf-8') as f:
                        f.write("Timestamp,Title,Quality,Format\n")
                        for entry in self.download_history:
                            f.write(entry.replace(' | ', ',') + '\n')
                else:
                    with open(filename, 'w', encoding='utf-8') as f:
                        f.write("Download History\n")
                        f.write("=" * 80 + "\n\n")
                        for entry in self.download_history:
                            f.write(entry + "\n")

                self.log_message(f"History exported to: {filename}")
                QMessageBox.information(self, "Success", f"History exported to:\n{filename}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to export history:\n{str(e)}")

    def clear_history(self):
        """Clear download history"""
        if not self.download_history:
            QMessageBox.information(self, "Info", "History is already empty!")
            return

        reply = QMessageBox.question(
            self, "Clear History",
            "Are you sure you want to clear all download history?",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self.history_list.clear()
            self.download_history.clear()
            self.save_history()
            self.update_history_count()
            self.update_stats()
            self.log_message("History cleared")

    # ===== STATISTICS METHODS =====

    def update_statistics_display(self):
        """Update statistics display"""
        stats = self.download_statistics

        self.total_downloads_label.setText(f"Total Downloads: {stats['total_downloads']}")
        self.successful_downloads_label.setText(f"Successful: {stats['successful_downloads']}")
        self.failed_downloads_label.setText(f"Failed: {stats['failed_downloads']}")
        self.total_size_label.setText(f"Total Size: {self.format_bytes(stats['total_bytes'])}")
        self.total_time_label.setText(f"Total Time: {self.format_duration(stats['total_time'])}")

        avg_speed = stats['total_bytes'] / stats['total_time'] if stats['total_time'] > 0 else 0
        self.avg_speed_label.setText(f"Avg Speed: {self.format_bytes(avg_speed)}/s")

    def export_statistics(self):
        """Export statistics"""
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export Statistics",
            f"download_stats_{datetime.now().strftime('%Y%m%d')}.json",
            "JSON Files (*.json);;All Files (*)"
        )

        if filename:
            try:
                with open(filename, 'w') as f:
                    json.dump(self.download_statistics, f, indent=2)
                self.log_message(f"Statistics exported to: {filename}")
                QMessageBox.information(self, "Success", f"Statistics exported to:\n{filename}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to export statistics:\n{str(e)}")

    def reset_statistics(self):
        """Reset statistics"""
        reply = QMessageBox.question(
            self, "Reset Statistics",
            "Are you sure you want to reset all statistics?",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self.download_statistics = {
                'total_downloads': 0,
                'total_bytes': 0,
                'total_time': 0,
                'successful_downloads': 0,
                'failed_downloads': 0
            }
            self.save_statistics()
            self.update_statistics_display()
            self.log_message("Statistics reset")

    # ===== CODE GENERATOR =====

    def update_code(self):
        """Update generated code"""
        quality = self.get_quality_value()
        format_type = self.format_combo.currentText()
        audio_only = self.audio_only_check.isChecked()

        code = f"""#!/usr/bin/env python3
\"\"\"
Video Downloader Script
Generated by Video Downloader Pro v3.0
Date: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
\"\"\"

import yt_dlp
import sys

def download_video(url):
    ydl_opts = {{
        'format': '{"bestaudio/best" if audio_only else f"bestvideo[height<={quality}]+bestaudio/best"}',
        'outtmpl': r'{self.path_input.text()}{os.sep}{self.filename_template.text() or "%(title)s.%(ext)s"}',
        'merge_output_format': '{format_type}',
        'retries': {self.retries_spin.value()},
        'concurrent_fragment_downloads': {self.concurrent_spin.value()},
    }}

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
            print("Download completed!")
            return True
    except Exception as e:
        print(f"Error: {{e}}")
        return False

if __name__ == "__main__":
    url = input("Enter URL: ") if len(sys.argv) < 2 else sys.argv[1]
    download_video(url)
"""
        self.code_text.setText(code)

    def copy_code(self):
        """Copy code to clipboard"""
        clipboard = QApplication.clipboard()
        clipboard.setText(self.code_text.toPlainText())
        self.log_message("Code copied to clipboard")
        self.statusBar.showMessage("Code copied!", 3000)

    def save_code(self):
        """Save code to file"""
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save Python Script",
            "download_video.py",
            "Python Files (*.py);;All Files (*)"
        )
        if filename:
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(self.code_text.toPlainText())
                self.log_message(f"Code saved to: {filename}")
                QMessageBox.information(self, "Success", f"Code saved!")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save: {str(e)}")

    # ===== ADDITIONAL FEATURES =====

    def schedule_download(self):
        """Schedule a download"""
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "Error", "Please enter a URL first!")
            return

        dialog = ScheduleDownloadDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            scheduled_time = dialog.get_scheduled_datetime()
            self.scheduled_downloads.append({'url': url, 'datetime': scheduled_time})
            self.log_message(f"Scheduled download: {url} at {scheduled_time.toString()}")
            QMessageBox.information(self, "Success",
                                    f"Download scheduled for {scheduled_time.toString('yyyy-MM-dd HH:mm')}")

    def show_format_selector(self):
        """Show advanced format selector"""
        if not self.current_video_info:
            QMessageBox.warning(self, "Error", "Please fetch video info first!")
            return

        formats = self.current_video_info.get('formats', [])
        if not formats:
            QMessageBox.warning(self, "Error", "No formats available!")
            return

        dialog = FormatSelectorDialog(formats, self)
        if dialog.exec_() == QDialog.Accepted:
            selected = dialog.get_selected_format()
            if selected:
                self.log_message(f"Selected format: {selected.get('format_id')}")

    def find_duplicates(self):
        """Find duplicate files in download folder"""
        folder = self.path_input.text()
        if not os.path.exists(folder):
            QMessageBox.warning(self, "Error", "Download folder does not exist!")
            return

        self.log_message("Scanning for duplicates...")
        files_hash = {}
        duplicates = []

        for root, dirs, files in os.walk(folder):
            for filename in files:
                filepath = os.path.join(root, filename)
                try:
                    with open(filepath, 'rb') as f:
                        file_hash = hashlib.md5(f.read()).hexdigest()

                    if file_hash in files_hash:
                        duplicates.append((filepath, files_hash[file_hash]))
                    else:
                        files_hash[file_hash] = filepath
                except:
                    pass

        if duplicates:
            msg = f"Found {len(duplicates)} duplicate files:\n\n"
            for dup, original in duplicates[:10]:
                msg += f"• {os.path.basename(dup)}\n"
            if len(duplicates) > 10:
                msg += f"\n... and {len(duplicates) - 10} more"
            QMessageBox.information(self, "Duplicates Found", msg)
        else:
            QMessageBox.information(self, "No Duplicates", "No duplicate files found!")

        self.log_message(f"Duplicate scan complete: {len(duplicates)} found")

    def check_disk_space(self):
        """Check available disk space"""
        try:
            import shutil
            path = self.path_input.text()
            total, used, free = shutil.disk_usage(path)

            QMessageBox.information(self, "Disk Space",
                                    f"Drive: {path}\n\n"
                                    f"Total: {self.format_bytes(total)}\n"
                                    f"Used: {self.format_bytes(used)}\n"
                                    f"Free: {self.format_bytes(free)}\n\n"
                                    f"Free %: {(free / total) * 100:.1f}%")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to check disk space:\n{str(e)}")

    def show_shortcuts(self):
        """Show keyboard shortcuts"""
        shortcuts = """
Keyboard Shortcuts:

Ctrl+N - New Download
Ctrl+B - Batch Download  
Ctrl+T - Schedule Download
Ctrl+O - Open Download Folder
Ctrl+H - View History
Ctrl+L - View Log
Ctrl+S - View Statistics
Ctrl+, - Settings
Ctrl+Q - Quit

Tab Navigation:
Use Tab/Shift+Tab to navigate between fields
Enter in URL field - Fetch video info
"""
        QMessageBox.information(self, "Keyboard Shortcuts", shortcuts)

    def export_queue(self):
        """Export download queue"""
        if not self.download_queue:
            QMessageBox.information(self, "Info", "Queue is empty!")
            return

        filename, _ = QFileDialog.getSaveFileName(
            self, "Export Queue",
            f"download_queue_{datetime.now().strftime('%Y%m%d')}.txt",
            "Text Files (*.txt);;JSON Files (*.json);;All Files (*)"
        )

        if filename:
            try:
                if filename.endswith('.json'):
                    with open(filename, 'w', encoding='utf-8') as f:
                        json.dump(self.download_queue, f, indent=2)
                else:
                    with open(filename, 'w', encoding='utf-8') as f:
                        f.write("Download Queue\n")
                        f.write("=" * 80 + "\n\n")
                        for i, item in enumerate(self.download_queue, 1):
                            f.write(f"{i}. {item['url']} [{item['status']}]\n")

                self.log_message(f"Queue exported to: {filename}")
                QMessageBox.information(self, "Success", f"Queue exported!")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to export: {str(e)}")

    def show_settings_dialog(self):
        """Show settings dialog"""
        dialog = SettingsDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            self.log_message("Settings updated")

    def show_about_dialog(self):
        """Show about dialog"""
        dialog = AboutDialog(self)
        dialog.exec_()

    def show_batch_download_dialog(self):
        """Show batch download dialog"""
        dialog = BatchDownloadDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            urls = dialog.get_urls()
            for url in urls:
                self.add_url_to_queue(url)
            self.tabs.setCurrentIndex(5)
            self.log_message(f"Added {len(urls)} URLs to queue")

    def open_download_folder(self):
        """Open download folder in file explorer"""
        path = self.path_input.text()
        if os.path.exists(path):
            if platform.system() == 'Windows':
                os.startfile(path)
            elif platform.system() == 'Darwin':
                subprocess.Popen(['open', path])
            else:
                subprocess.Popen(['xdg-open', path])
        else:
            QMessageBox.warning(self, "Error", "Download folder does not exist!")

    def check_ytdlp_version(self):
        """Check yt-dlp version"""
        try:
            result = subprocess.run(['yt-dlp', '--version'],
                                    capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                version = result.stdout.strip()
                self.log_message(f"yt-dlp version: {version}")
                self.statusBar.showMessage(f"yt-dlp v{version}", 5000)
        except:
            self.log_message("Could not check yt-dlp version")

    def update_ytdlp_manual(self):
        """Manually update yt-dlp"""
        self.log_message("Updating yt-dlp...")
        try:
            result = subprocess.run(['yt-dlp', '-U'],
                                    capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                QMessageBox.information(self, "Success", "yt-dlp updated successfully!")
                self.log_message("yt-dlp updated successfully")
            else:
                QMessageBox.warning(self, "Error", f"Update failed:\n{result.stderr}")
                self.log_message(f"Update failed: {result.stderr}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to update:\n{str(e)}")
            self.log_message(f"Update error: {str(e)}")

    def check_ffmpeg(self):
        """Check if FFmpeg is installed"""
        try:
            result = subprocess.run(['ffmpeg', '-version'],
                                    capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                version_line = result.stdout.split('\n')[0]
                QMessageBox.information(self, "FFmpeg", f"FFmpeg is installed:\n{version_line}")
                self.log_message(f"FFmpeg check: {version_line}")
            else:
                QMessageBox.warning(self, "FFmpeg", "FFmpeg is not properly installed")
        except FileNotFoundError:
            QMessageBox.critical(
                self, "FFmpeg Not Found",
                "FFmpeg is not installed or not in PATH.\n\n"
                "FFmpeg is required for:\n"
                "• Merging video and audio\n"
                "• Converting formats\n"
                "• Embedding thumbnails\n\n"
                "Download from: https://ffmpeg.org/download.html"
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to check FFmpeg:\n{str(e)}")

    def closeEvent(self, event):
        """Handle application close"""
        if self.download_thread and self.download_thread.isRunning():
            reply = QMessageBox.question(
                self, "Exit",
                "A download is in progress. Are you sure you want to exit?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.No:
                event.ignore()
                return
            else:
                self.download_thread.cancel()
                self.download_thread.wait(3000)

        if self.batch_thread and self.batch_thread.isRunning():
            self.batch_thread.cancel()
            self.batch_thread.wait(3000)

        self.save_settings()
        self.save_history()
        self.save_statistics()
        event.accept()


def main():
    """Main application entry point"""
    app = QApplication(sys.argv)
    app.setStyle('Fusion')

    # Set application metadata
    app.setApplicationName("Video Downloader Pro")
    app.setOrganizationName("VDP")
    app.setApplicationVersion("3.0")

    # Create and show main window
    window = VideoDownloaderApp()
    window.show()

    sys.exit(app.exec_())


if __name__ == '__main__':
    main()