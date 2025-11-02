import sys
import os
import json
import threading
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QLineEdit, QPushButton,
                             QComboBox, QCheckBox, QProgressBar, QTextEdit,
                             QFileDialog, QGroupBox, QSpinBox, QTabWidget,
                             QListWidget, QMessageBox, QSplitter, QFrame,
                             QScrollArea, QGridLayout, QSlider, QListWidgetItem,
                             QSystemTrayIcon, QMenu, QAction, QToolBar, QStatusBar,
                             QTableWidget, QTableWidgetItem, QHeaderView, QDialog,
                             QDialogButtonBox, QRadioButton, QButtonGroup)
from PyQt5.QtCore import (QThread, pyqtSignal, Qt, QTimer, QSize, QSettings,
                          QUrl, QPropertyAnimation, QEasingCurve, QRect)
from PyQt5.QtGui import (QFont, QIcon, QPixmap, QPalette, QColor, QDesktopServices,
                         QTextCursor, QLinearGradient, QPainter, QBrush)
import yt_dlp
from datetime import datetime
import re
import subprocess
import platform

# ============================================================================
# PART 1: LANGUAGE AND FORMAT DEFINITIONS
# ============================================================================

SUBTITLE_LANGUAGES = {
    'en': 'English',
    'es': 'Spanish',
    'fr': 'French',
    'de': 'German',
    'it': 'Italian',
    'pt': 'Portuguese',
    'ru': 'Russian',
    'ja': 'Japanese',
    'ko': 'Korean',
    'zh': 'Chinese',
    'ar': 'Arabic',
    'hi': 'Hindi',
    'pl': 'Polish',
    'tr': 'Turkish',
    'nl': 'Dutch',
    'vi': 'Vietnamese',
    'id': 'Indonesian',
    'th': 'Thai',
    'uk': 'Ukrainian',
    'cs': 'Czech',
    'el': 'Greek',
    'hu': 'Hungarian',
    'ro': 'Romanian',
    'sv': 'Swedish',
    'fi': 'Finnish',
    'da': 'Danish',
    'no': 'Norwegian',
}

SUBTITLE_FORMATS = ['Auto', 'srt', 'vtt', 'ass', 'json3']


# ============================================================================
# PART 2: DOWNLOAD THREAD
# ============================================================================

class DownloadThread(QThread):
    """Thread to handle video downloading without blocking UI"""
    progress = pyqtSignal(dict)
    finished = pyqtSignal(bool, str, str)
    log_message = pyqtSignal(str)

    def __init__(self, url, options):
        super().__init__()
        self.url = url
        self.options = options
        self._is_cancelled = False
        self.downloaded_file = None

    def progress_hook(self, d):
        """Callback for download progress"""
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
                    self.progress.emit({
                        'percent': percent,
                        'speed': speed,
                        'eta': eta,
                        'downloaded': downloaded,
                        'total': total,
                        'status': 'downloading'
                    })
            except:
                pass
        elif d['status'] == 'finished':
            self.downloaded_file = d.get('filename')
            self.progress.emit({'status': 'processing', 'percent': 100})
            self.log_message.emit("Download complete, processing...")

    def cancel(self):
        """Cancel the download"""
        self._is_cancelled = True

    def run(self):
        """Execute download in separate thread"""
        try:
            self.options['progress_hooks'] = [self.progress_hook]
            self.log_message.emit(f"Starting download: {self.url}")

            with yt_dlp.YoutubeDL(self.options) as ydl:
                try:
                    self.log_message.emit("Checking for yt-dlp updates...")
                    ydl.update()
                    self.log_message.emit("yt-dlp is up to date")
                except:
                    self.log_message.emit("Auto-update skipped")

                info = ydl.extract_info(self.url, download=True)
                title = info.get('title', 'Unknown')
                self.log_message.emit(f"Successfully downloaded: {title}")

            self.finished.emit(True, "Download completed successfully!", self.downloaded_file or "")
        except Exception as e:
            if self._is_cancelled:
                self.finished.emit(False, "Download cancelled by user", "")
            else:
                self.finished.emit(False, f"Error: {str(e)}", "")
                self.log_message.emit(f"Error occurred: {str(e)}")


# ============================================================================
# PART 3: VIDEO INFO THREAD
# ============================================================================

class VideoInfoThread(QThread):
    """Thread to fetch video information without downloading"""
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


# ============================================================================
# PART 4: PLAYLIST INFO THREAD
# ============================================================================

class PlaylistInfoThread(QThread):
    """Thread to fetch playlist information"""
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
                                'duration': entry.get('duration', 0)
                            })
                        self.progress.emit(idx, total)
                    self.info_ready.emit(videos)
                else:
                    self.error.emit("Not a playlist")
        except Exception as e:
            self.error.emit(str(e))


# ============================================================================
# PART 5: BATCH DOWNLOAD THREAD
# ============================================================================

class BatchDownloadThread(QThread):
    """Thread to handle batch downloads"""
    progress = pyqtSignal(int, int, str)
    item_finished = pyqtSignal(bool, str, str)
    all_finished = pyqtSignal(int, int)

    def __init__(self, urls, options_template):
        super().__init__()
        self.urls = urls
        self.options_template = options_template
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        successful = 0
        failed = 0

        for idx, url in enumerate(self.urls, 1):
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


# ============================================================================
# PART 6: SUBTITLE MANAGER
# ============================================================================

class SubtitleManager:
    """Manages subtitle-related operations"""

    def __init__(self):
        self.languages = SUBTITLE_LANGUAGES.copy()
        self.formats = SUBTITLE_FORMATS.copy()

    def get_all_languages(self):
        """Return all available languages"""
        return self.languages.copy()

    def validate_languages(self, lang_list):
        """Validate and return only valid language codes"""
        valid = [l for l in lang_list if l in self.languages]
        return valid if valid else ['en']

    def build_subtitle_options(self, download_all=False, languages=None,
                               auto_generated=True, format_type='auto'):
        """Build subtitle options for yt-dlp"""
        opts = {
            'writesubtitles': True,
            'skip_unavailable_fragments': False,
        }

        if download_all:
            opts['allsubtitles'] = True
        elif languages:
            opts['subtitleslangs'] = self.validate_languages(languages)
        else:
            opts['subtitleslangs'] = ['en']

        if auto_generated:
            opts['writeautomaticsub'] = True

        if format_type and format_type != 'auto':
            opts['subtitlesformat'] = format_type

        return opts


# ============================================================================
# PART 7: LANGUAGE SELECTION WIDGET
# ============================================================================

class LanguageListWidget(QListWidget):
    """Custom widget for selecting subtitle languages"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSelectionMode(QListWidget.MultiSelection)
        self._populate_languages()

    def _populate_languages(self):
        """Populate list with languages"""
        for code, name in sorted(SUBTITLE_LANGUAGES.items()):
            item = QListWidgetItem(f"{name} ({code})")
            item.setData(1001, code)
            if code == 'en':
                item.setSelected(True)
            self.addItem(item)

    def get_selected_languages(self):
        """Get selected language codes"""
        selected = []
        for i in range(self.count()):
            item = self.item(i)
            if item.isSelected():
                selected.append(item.data(1001))
        return selected if selected else ['en']

    def select_languages(self, codes):
        """Select languages by code"""
        for i in range(self.count()):
            item = self.item(i)
            item.setSelected(item.data(1001) in codes)


# ============================================================================
# PART 8: SUBTITLE DIALOG
# ============================================================================

class SubtitleDownloadDialog(QDialog):
    """Dialog for subtitle download configuration"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Subtitle Download Options")
        self.setModal(True)
        self.setMinimumWidth(600)
        self.setMinimumHeight(500)
        self._init_ui()

    def _init_ui(self):
        """Initialize dialog UI"""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        layout.addWidget(self._create_mode_section())
        layout.addWidget(self._create_language_section())
        layout.addWidget(self._create_autogen_section())
        layout.addWidget(self._create_format_section())
        layout.addWidget(self._create_embed_section())
        layout.addStretch()
        layout.addWidget(self._create_buttons())

    def _create_mode_section(self):
        """Create mode selection section"""
        group = QGroupBox("📥 Download Mode")
        layout = QVBoxLayout()

        self.all_radio = QRadioButton("Download All Available Subtitles")
        self.all_radio.setChecked(True)
        self.all_radio.toggled.connect(self._on_mode_changed)
        layout.addWidget(self.all_radio)

        self.specific_radio = QRadioButton("Download Specific Languages")
        self.specific_radio.toggled.connect(self._on_mode_changed)
        layout.addWidget(self.specific_radio)

        group.setLayout(layout)
        return group

    def _create_language_section(self):
        """Create language selection section"""
        group = QGroupBox("🌐 Language Selection")
        layout = QVBoxLayout()

        info = QLabel("Select languages (active when specific mode is selected):")
        info.setStyleSheet("color: #8b949e; font-size: 9pt;")
        layout.addWidget(info)

        self.lang_list = LanguageListWidget()
        self.lang_list.setEnabled(False)
        layout.addWidget(self.lang_list)

        group.setLayout(layout)
        return group

    def _create_autogen_section(self):
        """Create auto-generated subtitles section"""
        group = QGroupBox("🤖 Auto-Generated Subtitles")
        layout = QVBoxLayout()

        self.autogen_check = QCheckBox("Include Auto-Generated Subtitles")
        self.autogen_check.setChecked(True)
        layout.addWidget(self.autogen_check)

        info = QLabel("Available when platform provides them (YouTube, etc.)")
        info.setStyleSheet("color: #8b949e; font-size: 9pt;")
        layout.addWidget(info)

        group.setLayout(layout)
        return group

    def _create_format_section(self):
        """Create format selection section"""
        group = QGroupBox("📋 Subtitle Format")
        layout = QHBoxLayout()

        layout.addWidget(QLabel("Format:"))
        self.format_combo = QComboBox()
        self.format_combo.addItems(SUBTITLE_FORMATS)
        layout.addWidget(self.format_combo, 1)

        group.setLayout(layout)
        return group

    def _create_embed_section(self):
        """Create embedding options section"""
        group = QGroupBox("📌 Embedding Options")
        layout = QVBoxLayout()

        self.embed_check = QCheckBox("Embed Subtitles into Video (Requires FFmpeg)")
        self.embed_check.setChecked(False)
        layout.addWidget(self.embed_check)

        info = QLabel("Embeds the first language subtitle into the video file")
        info.setStyleSheet("color: #8b949e; font-size: 9pt;")
        layout.addWidget(info)

        group.setLayout(layout)
        return group

    def _create_buttons(self):
        """Create dialog buttons"""
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        return buttons

    def _on_mode_changed(self):
        """Handle mode change"""
        self.lang_list.setEnabled(self.specific_radio.isChecked())

    def get_options(self):
        """Get selected options"""
        return {
            'download_all': self.all_radio.isChecked(),
            'selected_languages': self.lang_list.get_selected_languages(),
            'auto_generated': self.autogen_check.isChecked(),
            'embed': self.embed_check.isChecked(),
            'format': self.format_combo.currentText(),
        }


# ============================================================================
# PART 9: SETTINGS DIALOG
# ============================================================================

class SettingsDialog(QDialog):
    """Settings dialog for application preferences"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.setMinimumWidth(500)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        theme_group = QGroupBox("Appearance")
        theme_layout = QVBoxLayout()

        self.dark_theme_radio = QRadioButton("Dark Theme (Default)")
        self.dark_theme_radio.setChecked(True)
        theme_layout.addWidget(self.dark_theme_radio)

        self.light_theme_radio = QRadioButton("Light Theme (Coming Soon)")
        self.light_theme_radio.setEnabled(False)
        theme_layout.addWidget(self.light_theme_radio)

        theme_group.setLayout(theme_layout)
        layout.addWidget(theme_group)

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

        notif_group.setLayout(notif_layout)
        layout.addWidget(notif_group)

        update_group = QGroupBox("Updates")
        update_layout = QVBoxLayout()

        self.auto_update_ytdlp = QCheckBox("Automatically update yt-dlp before downloads")
        self.auto_update_ytdlp.setChecked(True)
        update_layout.addWidget(self.auto_update_ytdlp)

        update_group.setLayout(update_layout)
        layout.addWidget(update_group)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


# ============================================================================
# PART 10: ABOUT DIALOG
# ============================================================================

class AboutDialog(QDialog):
    """About dialog"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About Video Downloader Pro")
        self.setModal(True)
        self.setMinimumWidth(400)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        title = QLabel("🎬 Video Downloader Pro")
        title.setFont(QFont("Segoe UI", 18, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #58a6ff; margin: 20px;")
        layout.addWidget(title)

        version = QLabel("Version 2.0 - Advanced Edition with Subtitles")
        version.setAlignment(Qt.AlignCenter)
        version.setStyleSheet("color: #8b949e; margin-bottom: 10px;")
        layout.addWidget(version)

        description = QLabel(
            "A powerful, feature-rich video downloader built with PyQt5 and yt-dlp.\n\n"
            "Features:\n"
            "• Multi-quality video downloads\n"
            "• Audio extraction with quality control\n"
            "• Playlist support with batch downloads\n"
            "• Subtitle downloads in 25+ languages\n"
            "• Real-time progress tracking\n"
            "• Download history and statistics\n"
            "• Python code generator\n\n"
            "Powered by yt-dlp"
        )
        description.setWordWrap(True)
        description.setAlignment(Qt.AlignCenter)
        description.setStyleSheet("color: #c9d1d9; margin: 20px;")
        layout.addWidget(description)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)


# ============================================================================
# PART 11: BATCH DOWNLOAD DIALOG
# ============================================================================

class BatchDownloadDialog(QDialog):
    """Dialog for batch download management"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Batch Download Manager")
        self.setModal(True)
        self.setMinimumSize(700, 500)
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

        clear_btn = QPushButton("🗑 Clear All")
        clear_btn.clicked.connect(self.url_text.clear)
        import_layout.addWidget(clear_btn)
        import_layout.addStretch()

        layout.addLayout(import_layout)

        self.stats_label = QLabel("URLs: 0")
        self.stats_label.setStyleSheet("color: #58a6ff;")
        layout.addWidget(self.stats_label)

        self.url_text.textChanged.connect(self.update_stats)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

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
        self.stats_label.setText(f"URLs: {len(lines)}")

    def validate_and_accept(self):
        text = self.url_text.toPlainText()
        self.urls = [line.strip() for line in text.split('\n') if line.strip()]

        if not self.urls:
            QMessageBox.warning(self, "Error", "Please enter at least one URL!")
            return

        self.accept()

    def get_urls(self):
        return self.urls


# ============================================================================
# PART 12: MAIN APPLICATION
# ============================================================================

class VideoDownloaderApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Video Downloader Pro - Advanced Edition")
        self.setGeometry(100, 100, 1200, 850)

        self.download_thread = None
        self.batch_thread = None
        self.info_thread = None
        self.playlist_thread = None
        self.download_history = []
        self.current_video_info = None
        self.settings_file = os.path.join(os.path.expanduser("~"), ".video_downloader_settings.json")
        self.download_queue = []
        self.subtitle_config = None

        self.subtitle_manager = SubtitleManager()

        self.load_settings()
        self.apply_theme()
        self.create_status_bar()
        self.init_ui()
        self.create_menu_bar()
        self.create_toolbar()
        self.setup_system_tray()
        self.load_history()

        QTimer.singleShot(1000, self.check_ytdlp_version)

    def apply_theme(self):
        """Apply dark theme styling"""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #0d1117;
            }
            QLabel {
                color: #c9d1d9;
                font-size: 11pt;
            }
            QLineEdit, QComboBox, QSpinBox {
                background-color: #161b22;
                color: #c9d1d9;
                border: 2px solid #30363d;
                border-radius: 6px;
                padding: 8px;
                font-size: 10pt;
                selection-background-color: #58a6ff;
            }
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
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
        """)

    def create_menu_bar(self):
        """Create application menu bar"""
        menubar = self.menuBar()

        file_menu = menubar.addMenu("&File")

        new_download_action = QAction("📥 New Download", self)
        new_download_action.setShortcut("Ctrl+N")
        new_download_action.triggered.connect(lambda: self.tabs.setCurrentIndex(0))
        file_menu.addAction(new_download_action)

        batch_download_action = QAction("📚 Batch Download", self)
        batch_download_action.setShortcut("Ctrl+B")
        batch_download_action.triggered.connect(self.show_batch_download_dialog)
        file_menu.addAction(batch_download_action)

        file_menu.addSeparator()

        open_folder_action = QAction("📁 Open Download Folder", self)
        open_folder_action.setShortcut("Ctrl+O")
        open_folder_action.triggered.connect(self.open_download_folder)
        file_menu.addAction(open_folder_action)

        file_menu.addSeparator()

        exit_action = QAction("❌ Exit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        edit_menu = menubar.addMenu("&Edit")

        settings_action = QAction("⚙️ Settings", self)
        settings_action.setShortcut("Ctrl+,")
        settings_action.triggered.connect(self.show_settings_dialog)
        edit_menu.addAction(settings_action)

        view_menu = menubar.addMenu("&View")

        history_action = QAction("📜 History", self)
        history_action.setShortcut("Ctrl+H")
        history_action.triggered.connect(lambda: self.tabs.setCurrentIndex(2))
        view_menu.addAction(history_action)

        log_action = QAction("📋 Log", self)
        log_action.setShortcut("Ctrl+L")
        log_action.triggered.connect(lambda: self.tabs.setCurrentIndex(3))
        view_menu.addAction(log_action)

        tools_menu = menubar.addMenu("&Tools")

        update_ytdlp_action = QAction("🔄 Update yt-dlp", self)
        update_ytdlp_action.triggered.connect(self.update_ytdlp_manual)
        tools_menu.addAction(update_ytdlp_action)

        check_ffmpeg_action = QAction("🔧 Check FFmpeg", self)
        check_ffmpeg_action.triggered.connect(self.check_ffmpeg)
        tools_menu.addAction(check_ffmpeg_action)

        help_menu = menubar.addMenu("&Help")

        about_action = QAction("ℹ️ About", self)
        about_action.triggered.connect(self.show_about_dialog)
        help_menu.addAction(about_action)

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

        folder_action = QAction("📁 Open Folder", self)
        folder_action.triggered.connect(self.open_download_folder)
        toolbar.addAction(folder_action)

        toolbar.addSeparator()

        batch_action = QAction("📚 Batch", self)
        batch_action.triggered.connect(self.show_batch_download_dialog)
        toolbar.addAction(batch_action)

    def create_status_bar(self):
        """Create status bar"""
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)

        self.status_message = QLabel("Ready")
        self.statusBar.addWidget(self.status_message)

        self.statusBar.addPermanentWidget(QLabel("|"))

        self.downloads_count_status = QLabel("Downloads: 0")
        self.statusBar.addPermanentWidget(self.downloads_count_status)

    def setup_system_tray(self):
        """Setup system tray icon"""
        try:
            self.tray_icon = QSystemTrayIcon(self)
            self.tray_icon.setToolTip("Video Downloader Pro")

            tray_menu = QMenu()
            show_action = tray_menu.addAction("Show Window")
            show_action.triggered.connect(self.show)

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
        """Initialize user interface"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)

        title_layout = QHBoxLayout()
        title = QLabel("🎬 Video Downloader Pro")
        title.setFont(QFont("Segoe UI", 20, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #58a6ff; margin-bottom: 10px;")
        title_layout.addWidget(title)

        self.stats_label = QLabel("Ready | Downloads: 0")
        self.stats_label.setStyleSheet("color: #7ee787; font-size: 10pt;")
        self.stats_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        title_layout.addWidget(self.stats_label)

        main_layout.addLayout(title_layout)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        main_layout.addWidget(self.tabs)

        self.create_download_tab()
        self.create_playlist_tab()
        self.create_subtitle_tab()
        self.create_history_tab()
        self.create_log_tab()
        self.create_code_tab()
        self.create_queue_tab()

        self.update_code()
        self.log_message("Application initialized successfully")

    def create_download_tab(self):
        """Create main download tab"""
        download_tab = QWidget()
        download_layout = QVBoxLayout(download_tab)
        download_layout.setSpacing(15)

        url_group = QGroupBox("📎 Video URL & Preview")
        url_main_layout = QVBoxLayout()

        url_input_layout = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Paste YouTube, Vimeo, or any supported video URL here...")
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

        self.add_to_queue_btn = QPushButton("➕ Add to Queue")
        self.add_to_queue_btn.setObjectName("secondaryBtn")
        self.add_to_queue_btn.clicked.connect(self.add_to_queue)
        url_input_layout.addWidget(self.add_to_queue_btn)

        url_main_layout.addLayout(url_input_layout)

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
        info_layout.addWidget(self.video_title_label, 0, 0, 1, 2)

        self.video_duration_label = QLabel("Duration: -")
        info_layout.addWidget(self.video_duration_label, 1, 0)

        self.video_uploader_label = QLabel("Uploader: -")
        info_layout.addWidget(self.video_uploader_label, 1, 1)

        self.video_views_label = QLabel("Views: -")
        info_layout.addWidget(self.video_views_label, 2, 0)

        self.video_size_label = QLabel("Est. Size: -")
        info_layout.addWidget(self.video_size_label, 2, 1)

        url_main_layout.addWidget(self.info_frame)

        url_group.setLayout(url_main_layout)
        download_layout.addWidget(url_group)

        settings_group = QGroupBox("⚙️ Download Settings")
        settings_layout = QVBoxLayout()

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
        self.format_combo.addItems(["mp4", "mkv", "webm", "avi", "mov"])
        self.format_combo.setCurrentText(self.settings.get('format', "mp4"))
        self.format_combo.currentTextChanged.connect(self.update_code)
        quality_format_layout.addWidget(self.format_combo, 0, 3)

        quality_format_layout.addWidget(QLabel("Audio Format:"), 1, 0)
        self.audio_format_combo = QComboBox()
        self.audio_format_combo.addItems(["mp3", "m4a", "opus", "vorbis", "wav", "flac"])
        self.audio_format_combo.setCurrentText(self.settings.get('audio_format', "mp3"))
        quality_format_layout.addWidget(self.audio_format_combo, 1, 1)

        quality_format_layout.addWidget(QLabel("Audio Quality:"), 1, 2)
        self.audio_quality_combo = QComboBox()
        self.audio_quality_combo.addItems(["320 mbps", "256 mbps", "192 mbps", "128 mbps", "96 mbps"])
        self.audio_quality_combo.setCurrentIndex(2)
        quality_format_layout.addWidget(self.audio_quality_combo, 1, 3)

        settings_layout.addLayout(quality_format_layout)

        checkbox_grid = QGridLayout()

        self.audio_only_check = QCheckBox("🎵 Audio Only")
        self.audio_only_check.setChecked(self.settings.get('audio_only', False))
        self.audio_only_check.toggled.connect(self.toggle_audio_only)
        checkbox_grid.addWidget(self.audio_only_check, 0, 0)

        self.embed_thumbnail_check = QCheckBox("🖼️ Embed Thumbnail")
        self.embed_thumbnail_check.setChecked(self.settings.get('embed_thumbnail', False))
        checkbox_grid.addWidget(self.embed_thumbnail_check, 0, 1)

        self.embed_subs_check = QCheckBox("📝 Embed Subtitles")
        checkbox_grid.addWidget(self.embed_subs_check, 0, 2)

        self.download_subs_check = QCheckBox("💬 Download Subtitles")
        checkbox_grid.addWidget(self.download_subs_check, 1, 0)

        self.advanced_subs_btn = QPushButton("⚙️ Subtitle Options")
        self.advanced_subs_btn.setObjectName("secondaryBtn")
        self.advanced_subs_btn.clicked.connect(self.show_subtitle_dialog)
        checkbox_grid.addWidget(self.advanced_subs_btn, 1, 1)

        self.write_description_check = QCheckBox("📄 Save Description")
        checkbox_grid.addWidget(self.write_description_check, 1, 2)

        self.write_thumbnail_check = QCheckBox("🎨 Save Thumbnail")
        checkbox_grid.addWidget(self.write_thumbnail_check, 2, 0)

        settings_layout.addLayout(checkbox_grid)
        settings_group.setLayout(settings_layout)
        download_layout.addWidget(settings_group)

        advanced_group = QGroupBox("🔧 Advanced Options")
        advanced_layout = QGridLayout()

        advanced_layout.addWidget(QLabel("Retries:"), 0, 0)
        self.retries_spin = QSpinBox()
        self.retries_spin.setRange(0, 20)
        self.retries_spin.setValue(self.settings.get('retries', 5))
        advanced_layout.addWidget(self.retries_spin, 0, 1)

        advanced_layout.addWidget(QLabel("Concurrent:"), 0, 2)
        self.concurrent_spin = QSpinBox()
        self.concurrent_spin.setRange(1, 10)
        self.concurrent_spin.setValue(self.settings.get('concurrent', 4))
        self.concurrent_spin.setToolTip("Number of concurrent fragments to download")
        advanced_layout.addWidget(self.concurrent_spin, 0, 3)

        self.ignore_errors_check = QCheckBox("⚠️ Ignore Errors")
        self.ignore_errors_check.setChecked(self.settings.get('ignore_errors', True))
        advanced_layout.addWidget(self.ignore_errors_check, 1, 0)

        self.no_playlist_check = QCheckBox("🚫 No Playlist")
        self.no_playlist_check.setToolTip("Download only single video, ignore playlist")
        advanced_layout.addWidget(self.no_playlist_check, 1, 1)

        self.limit_rate_check = QCheckBox("📊 Limit Rate")
        self.limit_rate_check.toggled.connect(self.toggle_rate_limit)
        advanced_layout.addWidget(self.limit_rate_check, 1, 2)

        self.rate_limit_input = QLineEdit()
        self.rate_limit_input.setPlaceholderText("e.g., 1M, 500K")
        self.rate_limit_input.setEnabled(False)
        advanced_layout.addWidget(self.rate_limit_input, 1, 3)

        advanced_group.setLayout(advanced_layout)
        download_layout.addWidget(advanced_group)

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

        self.cancel_btn = QPushButton("❌ Cancel")
        self.cancel_btn.setObjectName("cancelBtn")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self.cancel_download)
        stats_layout.addWidget(self.cancel_btn)

        progress_layout.addLayout(stats_layout)

        self.speed_label = QLabel("Speed: -")
        self.speed_label.setStyleSheet("color: #8b949e;")
        progress_layout.addWidget(self.speed_label)

        progress_group.setLayout(progress_layout)
        download_layout.addWidget(progress_group)

        download_layout.addStretch()
        self.tabs.addTab(download_tab, "📥 Download")

    def create_playlist_tab(self):
        """Create playlist tab"""
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

        download_selected_btn = QPushButton("⬇ Download Selected")
        download_selected_btn.clicked.connect(self.download_playlist_selected)
        playlist_actions.addWidget(download_selected_btn)

        playlist_group_layout.addLayout(playlist_actions)
        playlist_group.setLayout(playlist_group_layout)
        playlist_layout.addWidget(playlist_group)

        self.tabs.addTab(playlist_tab, "📚 Playlist")

    def create_subtitle_tab(self):
        """Create subtitle management tab"""
        subtitle_tab = QWidget()
        subtitle_layout = QVBoxLayout(subtitle_tab)
        subtitle_layout.setSpacing(15)

        url_group = QGroupBox("📎 Video URL")
        url_layout = QVBoxLayout()

        url_input_layout = QHBoxLayout()
        self.sub_url_input = QLineEdit()
        self.sub_url_input.setPlaceholderText("Paste video URL here...")
        url_input_layout.addWidget(self.sub_url_input)

        fetch_info_btn = QPushButton("🔍 Get Info")
        fetch_info_btn.setObjectName("secondaryBtn")
        fetch_info_btn.clicked.connect(self.fetch_video_info)
        url_input_layout.addWidget(fetch_info_btn)

        url_layout.addLayout(url_input_layout)
        url_group.setLayout(url_layout)
        subtitle_layout.addWidget(url_group)

        settings_group = QGroupBox("⚙️ Subtitle Settings")
        settings_layout = QVBoxLayout()

        path_layout = QHBoxLayout()
        path_layout.addWidget(QLabel("Save to:"))
        self.sub_path_input = QLineEdit()
        self.sub_path_input.setText(self.settings.get('download_path',
                                                      os.path.join(os.path.expanduser("~"), "Downloads")))
        path_layout.addWidget(self.sub_path_input, 1)

        browse_btn = QPushButton("📁 Browse")
        browse_btn.setObjectName("secondaryBtn")
        browse_btn.clicked.connect(self.browse_subtitle_folder)
        path_layout.addWidget(browse_btn)
        settings_layout.addLayout(path_layout)

        lang_layout = QHBoxLayout()
        lang_layout.addWidget(QLabel("Languages:"))
        self.sub_lang_combo = QComboBox()
        self.sub_lang_combo.addItems(["All Available", "English Only", "Custom Selection"])
        lang_layout.addWidget(self.sub_lang_combo, 1)
        settings_layout.addLayout(lang_layout)

        format_layout = QHBoxLayout()
        format_layout.addWidget(QLabel("Format:"))
        self.sub_format_combo = QComboBox()
        self.sub_format_combo.addItems(SUBTITLE_FORMATS)
        format_layout.addWidget(self.sub_format_combo)
        settings_layout.addLayout(format_layout)

        self.sub_auto_gen_check = QCheckBox("🤖 Include Auto-Generated Subtitles")
        self.sub_auto_gen_check.setChecked(True)
        settings_layout.addWidget(self.sub_auto_gen_check)

        settings_group.setLayout(settings_layout)
        subtitle_layout.addWidget(settings_group)

        progress_group = QGroupBox("📊 Download Progress")
        progress_layout = QVBoxLayout()

        self.sub_progress_bar = QProgressBar()
        progress_layout.addWidget(self.sub_progress_bar)

        status_layout = QHBoxLayout()
        self.sub_status_label = QLabel("Ready to download subtitles")
        self.sub_status_label.setStyleSheet("color: #7ee787; font-weight: bold;")
        status_layout.addWidget(self.sub_status_label, 1)

        download_only_btn = QPushButton("💬 Download Subtitles Only")
        download_only_btn.clicked.connect(self.download_subtitles_only)
        status_layout.addWidget(download_only_btn)

        self.sub_cancel_btn = QPushButton("❌ Cancel")
        self.sub_cancel_btn.setObjectName("cancelBtn")
        self.sub_cancel_btn.setEnabled(False)
        self.sub_cancel_btn.clicked.connect(self.cancel_download)
        status_layout.addWidget(self.sub_cancel_btn)

        progress_layout.addLayout(status_layout)
        progress_group.setLayout(progress_layout)
        subtitle_layout.addWidget(progress_group)

        subtitle_layout.addStretch()
        self.tabs.addTab(subtitle_tab, "💬 Subtitles")

    def create_history_tab(self):
        """Create history tab"""
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

        self.history_list = QListWidget()
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

        clear_log_btn = QPushButton("🗑 Clear Log")
        clear_log_btn.setObjectName("secondaryBtn")
        clear_log_btn.clicked.connect(self.clear_log)
        log_header.addWidget(clear_log_btn)

        save_log_btn = QPushButton("💾 Save Log")
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

        copy_code_btn = QPushButton("📋 Copy Code")
        copy_code_btn.setObjectName("secondaryBtn")
        copy_code_btn.clicked.connect(self.copy_code)
        code_header.addWidget(copy_code_btn)

        save_code_btn = QPushButton("💾 Save as File")
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
        """Create queue tab"""
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
        self.queue_table.setColumnCount(4)
        self.queue_table.setHorizontalHeaderLabels(["#", "URL", "Status", "Actions"])
        self.queue_table.horizontalHeader().setStretchLastSection(False)
        self.queue_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.queue_table.setSelectionBehavior(QTableWidget.SelectRows)
        queue_layout.addWidget(self.queue_table)

        queue_actions = QHBoxLayout()

        start_queue_btn = QPushButton("▶️ Start Queue")
        start_queue_btn.clicked.connect(self.start_queue_download)
        queue_actions.addWidget(start_queue_btn)

        clear_queue_btn = QPushButton("🗑 Clear Queue")
        clear_queue_btn.setObjectName("cancelBtn")
        clear_queue_btn.clicked.connect(self.clear_queue)
        queue_actions.addWidget(clear_queue_btn)

        queue_actions.addStretch()
        queue_layout.addLayout(queue_actions)

        self.tabs.addTab(queue_tab, "📋 Queue")

    def on_url_changed(self):
        """Handle URL changes"""
        self.info_frame.setVisible(False)
        self.current_video_info = None

    def toggle_rate_limit(self, checked):
        """Toggle rate limit input"""
        self.rate_limit_input.setEnabled(checked)

    def toggle_audio_only(self, checked):
        """Toggle audio-only mode"""
        self.quality_combo.setEnabled(not checked)
        self.format_combo.setEnabled(not checked)
        self.update_code()

    def load_settings(self):
        """Load settings from file"""
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, 'r') as f:
                    self.settings = json.load(f)
            else:
                self.settings = {}
        except:
            self.settings = {}

    def save_settings(self):
        """Save settings to file"""
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
            }
            with open(self.settings_file, 'w') as f:
                json.dump(settings, f, indent=2)
        except Exception as e:
            self.log_message(f"Failed to save settings: {str(e)}")

    def load_history(self):
        """Load download history"""
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
        """Save download history"""
        history_file = os.path.join(os.path.expanduser("~"), ".video_downloader_history.json")
        try:
            with open(history_file, 'w') as f:
                json.dump(self.download_history, f, indent=2)
        except Exception as e:
            self.log_message(f"Failed to save history: {str(e)}")

    def browse_folder(self):
        """Browse for download folder"""
        folder = QFileDialog.getExistingDirectory(self, "Select Download Folder")
        if folder:
            self.path_input.setText(folder)

    def browse_subtitle_folder(self):
        """Browse for subtitle folder"""
        folder = QFileDialog.getExistingDirectory(self, "Select Subtitle Folder")
        if folder:
            self.sub_path_input.setText(folder)

    def format_bytes(self, bytes_val):
        """Format bytes to readable format"""
        if not bytes_val:
            return "0 B"
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_val < 1024.0:
                return f"{bytes_val:.2f} {unit}"
            bytes_val /= 1024.0
        return f"{bytes_val:.2f} PB"

    def format_duration(self, seconds):
        """Format duration to readable format"""
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
        """Add message to log"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted_msg = f"[{timestamp}] {message}"
        self.log_text.append(formatted_msg)
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum()
        )
        self.status_message.setText(message[:50] + "..." if len(message) > 50 else message)

    def clear_log(self):
        """Clear log"""
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

    def fetch_video_info(self):
        """Fetch video information"""
        url = self.url_input.text().strip() or self.sub_url_input.text().strip()
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
        """Display video information"""
        self.current_video_info = info
        self.fetch_info_btn.setEnabled(True)
        self.fetch_info_btn.setText("🔍 Get Info")

        title = info.get('title', 'Unknown')
        duration = self.format_duration(info.get('duration', 0))
        uploader = info.get('uploader', 'Unknown')
        views = info.get('view_count', 0)
        filesize = info.get('filesize', 0) or info.get('filesize_approx', 0)

        self.video_title_label.setText(f"Title: {title}")
        self.video_duration_label.setText(f"⏱️ Duration: {duration}")
        self.video_uploader_label.setText(f"👤 Uploader: {uploader}")
        self.video_views_label.setText(f"👁️ Views: {views:,}" if views else "👁️ Views: N/A")
        self.video_size_label.setText(f"💾 Est. Size: {self.format_bytes(filesize)}" if filesize else "💾 Est. Size: N/A")

        self.info_frame.setVisible(True)
        self.log_message(f"Info fetched: {title}")

    def info_fetch_error(self, error):
        """Handle info fetch error"""
        self.fetch_info_btn.setEnabled(True)
        self.fetch_info_btn.setText("🔍 Get Info")
        self.log_message(f"Error fetching info: {error}")
        QMessageBox.warning(self, "Error", f"Failed to fetch video info:\n{error}")

    def fetch_playlist_info(self):
        """Fetch playlist information"""
        url = self.playlist_url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "Error", "Please enter a playlist URL!")
            return

        if self.playlist_thread and self.playlist_thread.isRunning():
            return

        self.playlist_list.clear()
        self.log_message(f"Fetching playlist: {url}")

        self.playlist_thread = PlaylistInfoThread(url)
        self.playlist_thread.info_ready.connect(self.display_playlist_info)
        self.playlist_thread.error.connect(self.playlist_fetch_error)
        self.playlist_thread.progress.connect(self.update_playlist_progress)
        self.playlist_thread.start()

    def update_playlist_progress(self, current, total):
        """Update playlist loading progress"""
        self.log_message(f"Loading playlist: {current}/{total} videos")

    def display_playlist_info(self, videos):
        """Display playlist videos"""
        self.playlist_list.clear()
        for i, video in enumerate(videos, 1):
            duration = self.format_duration(video.get('duration', 0))
            item_text = f"{i}. {video['title']} [{duration}]"
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, video)
            self.playlist_list.addItem(item)

        self.log_message(f"Loaded {len(videos)} videos from playlist")
        QMessageBox.information(self, "Success", f"Loaded {len(videos)} videos from playlist!")

    def playlist_fetch_error(self, error):
        """Handle playlist fetch error"""
        self.log_message(f"Error fetching playlist: {error}")
        QMessageBox.warning(self, "Error", f"Failed to fetch playlist:\n{error}")

    def download_playlist_selected(self):
        """Download selected playlist items"""
        selected_items = self.playlist_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Error", "Please select videos to download!")
            return

        urls = []
        for item in selected_items:
            video = item.data(Qt.UserRole)
            if video and video.get('url'):
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
                self.tabs.setCurrentIndex(6)

    def add_to_queue(self):
        """Add URL to queue"""
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "Error", "Please enter a valid URL!")
            return

        self.add_url_to_queue(url)

    def add_url_to_queue(self, url):
        """Add URL to queue table"""
        row_position = self.queue_table.rowCount()
        self.queue_table.insertRow(row_position)

        self.queue_table.setItem(row_position, 0, QTableWidgetItem(str(row_position + 1)))
        self.queue_table.setItem(row_position, 1, QTableWidgetItem(url))
        self.queue_table.setItem(row_position, 2, QTableWidgetItem("⏳ Pending"))

        remove_btn = QPushButton("🗑")
        remove_btn.setObjectName("cancelBtn")
        remove_btn.clicked.connect(lambda: self.remove_from_queue(row_position))
        self.queue_table.setCellWidget(row_position, 3, remove_btn)

        self.download_queue.append({'url': url, 'status': 'pending'})
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

    def update_queue_count(self):
        """Update queue count label"""
        count = len(self.download_queue)
        self.queue_count_label.setText(f"{count} item{'s' if count != 1 else ''}")

    def start_queue_download(self):
        """Start queue download"""
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

        self.log_message(f"Starting batch download of {len(urls)} items")

    def update_batch_progress(self, current, total, url):
        """Update batch progress"""
        self.log_message(f"Downloading {current}/{total}: {url}")

        for i, item in enumerate(self.download_queue):
            if item['url'] == url:
                self.queue_table.setItem(i, 2, QTableWidgetItem(f"⬇️ Downloading ({current}/{total})"))
                break

    def batch_item_finished(self, success, url, message):
        """Handle batch item finish"""
        self.log_message(message)

        for i, item in enumerate(self.download_queue):
            if item['url'] == url:
                if success:
                    self.queue_table.setItem(i, 2, QTableWidgetItem("✅ Completed"))
                    item['status'] = 'completed'
                else:
                    self.queue_table.setItem(i, 2, QTableWidgetItem("❌ Failed"))
                    item['status'] = 'failed'
                break

    def batch_all_finished(self, successful, failed):
        """Handle batch completion"""
        self.log_message(f"Batch download finished: {successful} successful, {failed} failed")
        QMessageBox.information(
            self, "Batch Download Complete",
            f"Batch download finished!\n\nSuccessful: {successful}\nFailed: {failed}"
        )

    def get_quality_value(self):
        """Get quality value"""
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

    def show_subtitle_dialog(self):
        """Show subtitle options dialog"""
        dialog = SubtitleDownloadDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            self.subtitle_config = dialog.get_options()
            self.log_message("Subtitle options configured")
            self.update_code()

    def apply_subtitle_options(self, ydl_opts):
        """Apply subtitle options to download options"""
        if not (self.download_subs_check.isChecked() or hasattr(self, 'subtitle_config')):
            return ydl_opts

        config = self.subtitle_config or {
            'download_all': self.download_subs_check.isChecked(),
            'selected_languages': ['en'],
            'auto_generated': True,
            'embed': self.embed_subs_check.isChecked(),
            'format': 'auto'
        }

        subtitle_opts = self.subtitle_manager.build_subtitle_options(
            download_all=config.get('download_all', True),
            languages=config.get('selected_languages', ['en']),
            auto_generated=config.get('auto_generated', True),
            format_type=config.get('format', 'auto')
        )
        ydl_opts.update(subtitle_opts)

        if config.get('embed', False):
            if 'postprocessors' not in ydl_opts:
                ydl_opts['postprocessors'] = []
            ydl_opts['postprocessors'].append({'key': 'FFmpegEmbedSubtitle'})

        return ydl_opts

    def download_subtitles_only(self):
        """Download only subtitles"""
        url = self.sub_url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "Error", "Please enter a valid URL!")
            return

        output_path = self.sub_path_input.text()
        if not os.path.exists(output_path):
            try:
                os.makedirs(output_path)
            except:
                QMessageBox.warning(self, "Error", "Invalid output path!")
                return

        config = {
            'download_all': self.sub_lang_combo.currentText() == "All Available",
            'selected_languages': ['en'],
            'auto_generated': self.sub_auto_gen_check.isChecked(),
            'embed': False,
            'format': self.sub_format_combo.currentText()
        }

        ydl_opts = {
            'skip_download': True,
            'outtmpl': os.path.join(output_path, '%(title)s.%(ext)s'),
            'quiet': False,
            'no_warnings': False,
        }

        ydl_opts = self.apply_subtitle_options_subs_only(ydl_opts, config)

        self.download_thread = DownloadThread(url, ydl_opts)
        self.download_thread.progress.connect(self.update_progress_subs)
        self.download_thread.finished.connect(self.download_finished_subs)
        self.download_thread.log_message.connect(self.log_message)
        self.download_thread.start()

        self.sub_status_label.setText("Downloading subtitles...")
        self.sub_status_label.setStyleSheet("color: #58a6ff; font-weight: bold;")
        self.sub_cancel_btn.setEnabled(True)
        self.log_message("Starting subtitle-only download")

    def apply_subtitle_options_subs_only(self, ydl_opts, config):
        """Apply subtitle options for subtitle-only downloads"""
        subtitle_opts = self.subtitle_manager.build_subtitle_options(
            download_all=config.get('download_all', True),
            languages=config.get('selected_languages', ['en']),
            auto_generated=config.get('auto_generated', True),
            format_type=config.get('format', 'auto')
        )
        ydl_opts.update(subtitle_opts)
        return ydl_opts

    def update_progress_subs(self, data):
        """Update subtitle download progress"""
        if data['status'] == 'downloading':
            percent = int(data['percent'])
            self.sub_progress_bar.setValue(percent)

    def download_finished_subs(self, success, message, filepath):
        """Handle subtitle download finish"""
        self.sub_cancel_btn.setEnabled(False)

        if success:
            self.sub_progress_bar.setValue(100)
            self.sub_status_label.setText("✅ Subtitles downloaded successfully!")
            self.sub_status_label.setStyleSheet("color: #7ee787; font-weight: bold;")
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
            self.log_message(f"❌ {message}")
            QMessageBox.critical(self, "Error", message)

    def update_history_count(self):
        """Update history count"""
        count = len(self.download_history)
        self.history_count_label.setText(f"{count} download{'s' if count != 1 else ''}")
        self.downloads_count_status.setText(f"Downloads: {count}")

    def update_stats(self):
        """Update statistics"""
        count = len(self.download_history)
        self.stats_label.setText(f"Ready | Downloads: {count}")

    def export_history(self):
        """Export history"""
        if not self.download_history:
            QMessageBox.information(self, "Info", "No history to export!")
            return

        filename, _ = QFileDialog.getSaveFileName(
            self, "Export History",
            f"download_history_{datetime.now().strftime('%Y%m%d')}.txt",
            "Text Files (*.txt);;JSON Files (*.json);;All Files (*)"
        )

        if filename:
            try:
                if filename.endswith('.json'):
                    with open(filename, 'w', encoding='utf-8') as f:
                        json.dump(self.download_history, f, indent=2)
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
        """Clear history"""
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
            QMessageBox.information(self, "Success", "History cleared!")

    def update_code(self):
        """Update generated code"""
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
            postprocessors.append(f"""{{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': '{self.audio_format_combo.currentText()}',
        'preferredquality': '{audio_quality}',
    }}""")
        else:
            postprocessors.append(f"""{{
        'key': 'FFmpegVideoConvertor',
        'preferedformat': '{format_type}',
    }}""")

        if self.embed_thumbnail_check.isChecked():
            postprocessors.append("{'key': 'EmbedThumbnail'}")

        postprocessors_str = ",\n    ".join(postprocessors)

        additional_opts = []
        if self.download_subs_check.isChecked():
            additional_opts.append("'writesubtitles': True,\n    'allsubtitles': True,")
        if self.write_description_check.isChecked():
            additional_opts.append("'writedescription': True,")
        if self.write_thumbnail_check.isChecked():
            additional_opts.append("'writethumbnail': True,")
        if self.no_playlist_check.isChecked():
            additional_opts.append("'noplaylist': True,")
        if self.limit_rate_check.isChecked() and self.rate_limit_input.text():
            additional_opts.append(f"'ratelimit': '{self.rate_limit_input.text()}',")

        additional_opts_str = "\n    ".join(additional_opts)

        code = f"""#!/usr/bin/env python3
\"\"\"
Video Downloader Script
Generated by Video Downloader Pro v2.0
Date: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
\"\"\"

import yt_dlp
import sys

def download_video(url):
    \"\"\"Download video with specified options\"\"\"

    ydl_opts = {{
        'format': '{format_str}',
        'outtmpl': r'{self.path_input.text()}{os.sep}%(title)s.%(ext)s',
        'merge_output_format': '{format_type}',

        # Error handling
        'ignoreerrors': {self.ignore_errors_check.isChecked()},
        'no_warnings': False,
        'quiet': False,
        'retries': {self.retries_spin.value()},
        'fragment_retries': {self.retries_spin.value()},
        'concurrent_fragment_downloads': {self.concurrent_spin.value()},

        # File naming
        'windowsfilenames': True,
        'restrictfilenames': False,

        {additional_opts_str}

        # Post-processing
        'postprocessors': [
        {postprocessors_str}
        ],
    }}

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                print("Checking for yt-dlp updates...")
                ydl.update()
                print("yt-dlp is up to date")
            except Exception as e:
                print(f"Auto-update skipped: {{e}}")

            print(f"Downloading: {{url}}")
            info = ydl.extract_info(url, download=True)
            print(f"\\nSuccessfully downloaded: {{info.get('title', 'Unknown')}}")
            return True
    except Exception as e:
        print(f"Error downloading video: {{e}}")
        return False

if __name__ == "__main__":
    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        url = input("Enter video URL: ")

    success = download_video(url)
    sys.exit(0 if success else 1)
"""
        self.code_text.setText(code)

    def copy_code(self):
        """Copy code to clipboard"""
        clipboard = QApplication.clipboard()
        clipboard.setText(self.code_text.toPlainText())
        self.log_message("Code copied to clipboard")
        self.statusBar.showMessage("Code copied to clipboard", 3000)

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
                QMessageBox.information(self, "Success", f"Code saved to:\n{filename}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save code:\n{str(e)}")

    def show_batch_download_dialog(self):
        """Show batch download dialog"""
        dialog = BatchDownloadDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            urls = dialog.get_urls()
            for url in urls:
                self.add_url_to_queue(url)
            self.tabs.setCurrentIndex(6)
            self.log_message(f"Added {len(urls)} URLs to queue")

    def show_settings_dialog(self):
        """Show settings dialog"""
        dialog = SettingsDialog(self)
        dialog.exec_()

    def show_about_dialog(self):
        """Show about dialog"""
        dialog = AboutDialog(self)
        dialog.exec_()

    def open_download_folder(self):
        """Open download folder"""
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
        """Check FFmpeg installation"""
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
                "• Embedding thumbnails and subtitles\n\n"
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

        self.save_settings()
        self.save_history()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')

    app.setApplicationName("Video Downloader Pro")
    app.setOrganizationName("VDP")
    app.setApplicationVersion("2.0")

    window = VideoDownloaderApp()
    window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()

# ============================================================================
# INSTALLATION & USAGE GUIDE
# ============================================================================

"""
INSTALLATION REQUIREMENTS:

1. Install Python 3.8+
   Download from: https://www.python.org/downloads/

2. Install required packages:
   pip install PyQt5 yt-dlp

3. Install FFmpeg (optional but recommended):
   - Windows: https://ffmpeg.org/download.html
   - macOS: brew install ffmpeg
   - Linux: sudo apt-get install ffmpeg

4. Run the application:
   python download-v2.py


FEATURES BREAKDOWN:

VIDEO DOWNLOADING:
- Choose quality (240p to 8K)
- Select format (MP4, MKV, WebM, AVI, MOV)
- Download audio only with quality selection
- Embed thumbnails
- Save descriptions
- Rate limiting option
- Retry configuration

SUBTITLE DOWNLOADING:
- Download in 25+ languages
- Auto-generated subtitles support
- Multiple formats (SRT, VTT, ASS, JSON3)
- Embed subtitles into video
- Download subtitles only (no video)
- Custom language selection

PLAYLIST MANAGEMENT:
- Load entire playlists
- Multi-select videos
- Batch download from playlists
- Progress tracking

QUEUE SYSTEM:
- Add multiple URLs to queue
- Batch process downloads
- Track individual download status
- Remove items from queue

HISTORY & LOGGING:
- Track all downloads
- Export history as TXT or JSON
- View detailed logs
- Save logs to file

CODE GENERATION:
- Generate Python scripts automatically
- Copy code to clipboard
- Save as standalone script


KEYBOARD SHORTCUTS:

Ctrl+N  - New Download
Ctrl+B  - Batch Download
Ctrl+O  - Open Download Folder
Ctrl+,  - Settings
Ctrl+H  - View History
Ctrl+L  - View Log
Ctrl+Q  - Exit


EXAMPLE USAGE:

1. Basic Video Download:
   - Paste URL in URL field
   - Click "Get Info" to preview
   - Select quality and format
   - Click "Download"

2. Download with Subtitles:
   - Paste URL
   - Check "Download Subtitles"
   - Click "Subtitle Options" for advanced settings
   - Select languages and format
   - Click "Download"

3. Subtitle Only:
   - Go to "Subtitles" tab
   - Paste URL
   - Select languages and format
   - Click "Download Subtitles Only"

4. Batch Download:
   - Click "Batch Download" button
   - Paste multiple URLs (one per line)
   - Click "Ok"
   - URLs added to queue
   - Go to Queue tab
   - Click "Start Queue"

5. Generate Script:
   - Configure all options
   - Go to "Code" tab
   - Copy code or save as file
   - Use standalone script


SUBTITLE LANGUAGES SUPPORTED:

English, Spanish, French, German, Italian, Portuguese, Russian, Japanese,
Korean, Chinese, Arabic, Hindi, Polish, Turkish, Dutch, Vietnamese,
Indonesian, Thai, Ukrainian, Czech, Greek, Hungarian, Romanian, Swedish,
Finnish, Danish, Norwegian


TROUBLESHOOTING:

1. "yt-dlp not found"
   - Install: pip install --upgrade yt-dlp
   - Or: Check Tools > Update yt-dlp

2. "FFmpeg not found"
   - Required for merging/embedding
   - Download from ffmpeg.org
   - Add to system PATH

3. Download fails
   - Check URL is valid and accessible
   - Try updating yt-dlp (Tools > Update yt-dlp)
   - Check internet connection
   - Try different quality setting

4. Subtitles not downloading
   - Check platform supports subtitles (YouTube, Vimeo, etc)
   - Try "All Available" languages option
   - Ensure "Auto-Generated" is checked if needed

5. Cannot embed subtitles
   - Requires FFmpeg installed
   - Install FFmpeg and add to PATH
   - Verify with Tools > Check FFmpeg


FILE LOCATIONS:

Settings: ~/.video_downloader_settings.json
History: ~/.video_downloader_history.json
Downloads: ~/Downloads (default, customizable)


TIPS:

- Use queue for batch processing
- Generate scripts for repeated operations
- Export history for record keeping
- Check FFmpeg status if embedding fails
- Update yt-dlp regularly for site support
- Use quality limits for bandwidth control
- Embed thumbnails for better video info
- Save descriptions for reference


API REFERENCE (FOR DEVELOPERS):

SubtitleManager():
  - get_all_languages(): Returns dict of supported languages
  - validate_languages(lang_list): Validates language codes
  - build_subtitle_options(): Creates yt-dlp options

LanguageListWidget(parent):
  - get_selected_languages(): Returns selected language codes
  - select_languages(codes): Programmatically select languages

SubtitleDownloadDialog(parent):
  - get_options(): Returns user-selected options

VideoDownloaderApp():
  - show_subtitle_dialog(): Show subtitle configuration
  - download_subtitles_only(): Download subtitles without video
  - apply_subtitle_options(): Apply options to download


COMMAND LINE USAGE (Generated Scripts):

python download_video.py "https://www.youtube.com/watch?v=..."

Or without URL argument:
python download_video.py
(Then enter URL when prompted)


LICENSE & CREDITS:

Built with:
- PyQt5: https://pypi.org/project/PyQt5/
- yt-dlp: https://github.com/yt-dlp/yt-dlp
- FFmpeg: https://ffmpeg.org/

This is a free, open-source tool for downloading videos
in compliance with applicable laws and platform terms of service.


VERSION HISTORY:

v2.0 - Advanced Edition (Current)
  ✅ Complete subtitle support
  ✅ Multi-language subtitle downloads
  ✅ Subtitle embedding
  ✅ Enhanced UI with 7 tabs
  ✅ Batch queue system
  ✅ Code generation
  ✅ History tracking
  ✅ System tray integration

v1.0 - Initial Release
  • Basic video downloading
  • Quality/format selection
  • Playlist support


FUTURE ENHANCEMENTS:

- Video preview/thumbnail
- Playlist auto-download scheduling
- Download speed limiting per item
- Subtitle translation
- Automatic proxy rotation
- Download notifications
- Advanced filtering options
- Cloud storage integration
- Metadata editing
- Video quality comparison


SUPPORT:

For issues or suggestions:
1. Check the troubleshooting section above
2. Verify yt-dlp is up to date
3. Ensure FFmpeg is installed
4. Check internet connection
5. Try a different URL to test

Common platform support:
- YouTube ✅
- Vimeo ✅
- DailyMotion ✅
- Twitch ✅
- Instagram ✅
- TikTok ✅
- Facebook ✅
- And 500+ more...

Visit: https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md
"""
{message}
")
QMessageBox.information(self, "Success", f"{message}\n\nSaved to: {self.sub_path_input.text()}")
else:
self.sub_progress_bar.setValue(0)
self.sub_status_label.setText("❌ Download failed")
self.sub_status_label.setStyleSheet("color: #f85149; font-weight: bold;")
self.log_message(f"❌ {message}")
QMessageBox.critical(self, "Error", message)


def get_download_options(self):
    """Get download options"""
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

    ydl_opts = {
        'format': format_str,
        'outtmpl': os.path.join(self.path_input.text(), '%(title)s.%(ext)s'),
        'merge_output_format': format_type,
        'ignoreerrors': self.ignore_errors_check.isChecked(),
        'no_warnings': False,
        'quiet': False,
        'retries': self.retries_spin.value(),
        'fragment_retries': self.retries_spin.value(),
        'concurrent_fragment_downloads': self.concurrent_spin.value(),
        'windowsfilenames': True,
        'postprocessors': postprocessors,
    }

    if self.write_description_check.isChecked():
        ydl_opts['writedescription'] = True

    if self.write_thumbnail_check.isChecked():
        ydl_opts['writethumbnail'] = True

    if self.no_playlist_check.isChecked():
        ydl_opts['noplaylist'] = True

    if self.limit_rate_check.isChecked() and self.rate_limit_input.text():
        ydl_opts['ratelimit'] = self.rate_limit_input.text()

    ydl_opts = self.apply_subtitle_options(ydl_opts)

    return ydl_opts


def start_download(self):
    """Start download"""
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
    self.cancel_btn.setEnabled(True)
    self.progress_bar.setValue(0)
    self.status_label.setText("Initializing download...")
    self.status_label.setStyleSheet("color: #58a6ff; font-weight: bold;")
    self.speed_label.setText("Speed: Calculating...")

    self.save_settings()


def cancel_download(self):
    """Cancel download"""
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
    """Update progress"""
    if data['status'] == 'downloading':
        percent = int(data['percent'])
        self.progress_bar.setValue(percent)

        speed = data.get('speed', 0)
        eta = data.get('eta', 0)
        downloaded = data.get('downloaded', 0)
        total = data.get('total', 0)

        speed_str = self.format_bytes(speed) + "/s" if speed else "N/A"
        eta_str = f"{eta}s" if eta else "N/A"
        downloaded_str = self.format_bytes(downloaded)
        total_str = self.format_bytes(total) if total else "N/A"

        self.status_label.setText(f"Downloading: {percent}% ({downloaded_str} / {total_str})")
        self.speed_label.setText(f"Speed: {speed_str} | ETA: {eta_str}")

    elif data['status'] == 'processing':
        self.progress_bar.setValue(100)
        self.status_label.setText("Processing and merging files...")
        self.speed_label.setText("Almost done...")


def download_finished(self, success, message, filepath):
    """Handle download completion"""
    self.download_btn.setEnabled(True)
    self.download_btn.setText("⬇ Download")
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

        self.save_history()
        self.update_history_count()
        self.update_stats()

        self.log_message(f"✅