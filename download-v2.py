#!/usr/bin/env python3
"""
Video Downloader Pro - Enhanced Edition v3.0
Advanced video downloader with improved code quality and modern UI
"""

import sys, os, json, subprocess, platform, re
from datetime import datetime
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
import yt_dlp


# ==================== WORKER THREADS ====================

class DownloadWorker(QThread):
    """Unified download worker with progress tracking"""
    progress = pyqtSignal(dict)
    finished = pyqtSignal(bool, str, str)
    log = pyqtSignal(str)

    def __init__(self, url, opts):
        super().__init__()
        self.url, self.opts, self.cancelled, self.downloaded_file = url, opts, False, None

    def progress_hook(self, d):
        if self.cancelled:
            raise Exception("Cancelled")
        if d['status'] == 'downloading':
            self.progress.emit(d)
        elif d['status'] == 'finished':
            self.downloaded_file = d.get('filename')
            self.progress.emit({'status': 'processing', 'percent': 100})

    def cancel(self):
        self.cancelled = True

    def run(self):
        try:
            self.opts['progress_hooks'] = [self.progress_hook]
            self.log.emit(f"Starting: {self.url}")
            with yt_dlp.YoutubeDL(self.opts) as ydl:
                info = ydl.extract_info(self.url, download=True)
                title = info.get('title', 'Unknown')
                self.log.emit(f"✓ Downloaded: {title}")
                self.finished.emit(True, f"Download complete: {title}", self.downloaded_file or "")
        except Exception as e:
            msg = "Cancelled" if self.cancelled else str(e)
            self.log.emit(f"✗ Error: {msg}")
            self.finished.emit(False, f"Error: {msg}", "")


class InfoWorker(QThread):
    """Fetch video info without downloading"""
    info_ready = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        try:
            with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True}) as ydl:
                info = ydl.extract_info(self.url, download=False)
                self.info_ready.emit(info)
        except Exception as e:
            self.error.emit(str(e))


class PlaylistWorker(QThread):
    """Fetch playlist information"""
    info_ready = pyqtSignal(list)
    error = pyqtSignal(str)
    progress = pyqtSignal(int, int)

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        try:
            with yt_dlp.YoutubeDL({'quiet': True, 'extract_flat': True}) as ydl:
                info = ydl.extract_info(self.url, download=False)
                if 'entries' in info:
                    videos = []
                    entries = list(info['entries'])
                    for idx, entry in enumerate(entries, 1):
                        if entry:
                            videos.append({
                                'title': entry.get('title', 'Unknown'),
                                'url': entry.get('url', ''),
                                'id': entry.get('id', ''),
                                'duration': entry.get('duration', 0)
                            })
                        self.progress.emit(idx, len(entries))
                    self.info_ready.emit(videos)
                else:
                    self.error.emit("Not a playlist")
        except Exception as e:
            self.error.emit(str(e))


class BatchWorker(QThread):
    """Handle batch downloads"""
    progress = pyqtSignal(int, int, str)
    item_finished = pyqtSignal(bool, str, str)
    all_finished = pyqtSignal(int, int)

    def __init__(self, urls, opts_template):
        super().__init__()
        self.urls, self.opts_template, self.cancelled = urls, opts_template, False

    def cancel(self):
        self.cancelled = True

    def run(self):
        successful, failed = 0, 0
        for idx, url in enumerate(self.urls, 1):
            if self.cancelled:
                break
            self.progress.emit(idx, len(self.urls), url)
            try:
                with yt_dlp.YoutubeDL(self.opts_template.copy()) as ydl:
                    info = ydl.extract_info(url, download=True)
                    self.item_finished.emit(True, url, f"✓ {info.get('title', 'Unknown')}")
                    successful += 1
            except Exception as e:
                self.item_finished.emit(False, url, f"✗ {str(e)}")
                failed += 1
        self.all_finished.emit(successful, failed)


# ==================== CUSTOM WIDGETS ====================

class ModernButton(QPushButton):
    """Enhanced button with modern styling"""
    def __init__(self, text, icon="", variant="primary"):
        super().__init__(f"{icon} {text}" if icon else text)
        self.setVariant(variant)
        self.setCursor(Qt.PointingHandCursor)

    def setVariant(self, variant):
        styles = {
            "primary": ("#2563eb", "#1d4ed8", "#1e40af"),
            "success": ("#16a34a", "#15803d", "#166534"),
            "danger": ("#dc2626", "#b91c1c", "#991b1b"),
            "secondary": ("#64748b", "#475569", "#334155"),
            "info": ("#0891b2", "#0e7490", "#155e75")
        }
        bg, hover, pressed = styles.get(variant, styles["primary"])
        self.setStyleSheet(f"""
            QPushButton {{
                background: {bg}; color: white; border: none;
                border-radius: 6px; padding: 10px 20px;
                font-weight: 600; font-size: 13px;
            }}
            QPushButton:hover {{ background: {hover}; }}
            QPushButton:pressed {{ background: {pressed}; }}
            QPushButton:disabled {{ background: #1e293b; color: #475569; }}
        """)


class InfoCard(QFrame):
    """Modern info display card"""
    def __init__(self, title="", parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            QFrame {
                background: #1e293b;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 15px;
            }
        """)
        layout = QVBoxLayout(self)
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("color: #60a5fa; font-weight: bold; font-size: 14px;")
        layout.addWidget(self.title_label)
        self.content_layout = QVBoxLayout()
        layout.addLayout(self.content_layout)

    def add_info(self, label, value):
        row = QHBoxLayout()
        lbl = QLabel(label)
        lbl.setStyleSheet("color: #94a3b8; font-size: 12px;")
        val = QLabel(str(value))
        val.setStyleSheet("color: #e2e8f0; font-weight: 600;")
        val.setWordWrap(True)
        row.addWidget(lbl)
        row.addWidget(val, 1)
        self.content_layout.addLayout(row)

    def clear_info(self):
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                while item.layout().count():
                    child = item.layout().takeAt(0)
                    if child.widget():
                        child.widget().deleteLater()


# ==================== DIALOGS ====================

class BatchDialog(QDialog):
    """Batch download management dialog"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Batch Download Manager")
        self.setModal(True)
        self.setMinimumSize(700, 500)
        self.urls = []
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        info = QLabel("Enter multiple URLs (one per line):")
        info.setStyleSheet("color: #94a3b8; font-size: 13px; margin-bottom: 10px;")
        layout.addWidget(info)

        self.url_text = QTextEdit()
        self.url_text.setPlaceholderText("https://www.youtube.com/watch?v=...\nhttps://www.youtube.com/watch?v=...")
        self.url_text.setStyleSheet("font-family: 'Consolas', monospace; font-size: 11pt;")
        layout.addWidget(self.url_text)

        btn_layout = QHBoxLayout()
        import_btn = ModernButton("Import from File", "📁", "secondary")
        import_btn.clicked.connect(self.import_urls)
        btn_layout.addWidget(import_btn)
        
        clear_btn = ModernButton("Clear", "🗑", "danger")
        clear_btn.clicked.connect(self.url_text.clear)
        btn_layout.addWidget(clear_btn)
        btn_layout.addStretch()
        
        self.stats_label = QLabel("URLs: 0")
        self.stats_label.setStyleSheet("color: #60a5fa; font-weight: 600;")
        btn_layout.addWidget(self.stats_label)
        layout.addLayout(btn_layout)

        self.url_text.textChanged.connect(self.update_stats)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.validate_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def import_urls(self):
        fname, _ = QFileDialog.getOpenFileName(self, "Import URLs", "", "Text Files (*.txt);;All Files (*)")
        if fname:
            try:
                with open(fname, 'r', encoding='utf-8') as f:
                    self.url_text.setPlainText(f.read())
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Import failed:\n{str(e)}")

    def update_stats(self):
        lines = [line.strip() for line in self.url_text.toPlainText().split('\n') if line.strip()]
        self.stats_label.setText(f"URLs: {len(lines)}")

    def validate_accept(self):
        self.urls = [line.strip() for line in self.url_text.toPlainText().split('\n') if line.strip()]
        if not self.urls:
            QMessageBox.warning(self, "Error", "Please enter at least one URL!")
            return
        self.accept()


class SettingsDialog(QDialog):
    """Enhanced settings dialog"""
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.setMinimumWidth(500)
        self.settings = settings
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Appearance
        appearance_group = QGroupBox("🎨 Appearance")
        appearance_layout = QVBoxLayout()
        self.theme_dark = QRadioButton("Dark Theme (Active)")
        self.theme_dark.setChecked(True)
        appearance_layout.addWidget(self.theme_dark)
        appearance_group.setLayout(appearance_layout)
        layout.addWidget(appearance_group)

        # Notifications
        notif_group = QGroupBox("🔔 Notifications")
        notif_layout = QVBoxLayout()
        self.notif_complete = QCheckBox("Show notification on completion")
        self.notif_complete.setChecked(self.settings.get('notif_complete', True))
        notif_layout.addWidget(self.notif_complete)
        self.notif_error = QCheckBox("Show notification on errors")
        self.notif_error.setChecked(self.settings.get('notif_error', True))
        notif_layout.addWidget(self.notif_error)
        notif_group.setLayout(notif_layout)
        layout.addWidget(notif_group)

        # Auto-update
        update_group = QGroupBox("🔄 Updates")
        update_layout = QVBoxLayout()
        self.auto_update = QCheckBox("Auto-update yt-dlp before downloads")
        self.auto_update.setChecked(self.settings.get('auto_update', True))
        update_layout.addWidget(self.auto_update)
        update_group.setLayout(update_layout)
        layout.addWidget(update_group)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.save_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def save_and_accept(self):
        self.settings['notif_complete'] = self.notif_complete.isChecked()
        self.settings['notif_error'] = self.notif_error.isChecked()
        self.settings['auto_update'] = self.auto_update.isChecked()
        self.accept()


class AboutDialog(QDialog):
    """About information dialog"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About")
        self.setModal(True)
        self.setMinimumWidth(450)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        title = QLabel("🎬 Video Downloader Pro")
        title.setFont(QFont("Segoe UI", 20, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #60a5fa; margin: 20px;")
        layout.addWidget(title)

        version = QLabel("Version 3.0 - Enhanced Edition")
        version.setAlignment(Qt.AlignCenter)
        version.setStyleSheet("color: #94a3b8; margin-bottom: 15px;")
        layout.addWidget(version)

        desc = QLabel(
            "A powerful video downloader with modern UI\n\n"
            "Features:\n"
            "• Multi-quality downloads (8K to 240p)\n"
            "• Audio extraction with quality control\n"
            "• Playlist support & batch downloads\n"
            "• Real-time progress tracking\n"
            "• Download history & queue management\n"
            "• Python code generator\n\n"
            "Powered by yt-dlp"
        )
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignCenter)
        desc.setStyleSheet("color: #cbd5e1; margin: 15px;")
        layout.addWidget(desc)

        github_btn = ModernButton("yt-dlp GitHub", "🔗", "info")
        github_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://github.com/yt-dlp/yt-dlp")))
        layout.addWidget(github_btn)

        close_btn = ModernButton("Close", "", "secondary")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)


# ==================== MAIN APPLICATION ====================

class VideoDownloader(QMainWindow):
    """Main application window"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Video Downloader Pro v3.0")
        self.setGeometry(100, 100, 1200, 850)
        
        # Initialize state
        self.workers = {'download': None, 'info': None, 'playlist': None, 'batch': None}
        self.history = []
        self.queue = []
        self.current_video_info = None
        self.settings = {}
        
        # File paths
        self.config_file = os.path.join(os.path.expanduser("~"), ".vdl_config.json")
        self.history_file = os.path.join(os.path.expanduser("~"), ".vdl_history.json")
        
        # Load data
        self.load_config()
        self.load_history()
        
        # Setup UI
        self.apply_theme()
        self.init_ui()
        self.create_menubar()
        self.create_statusbar()
        
        # Auto-check updates
        QTimer.singleShot(1000, self.check_ytdlp_version)

    def apply_theme(self):
        """Apply modern dark theme"""
        self.setStyleSheet("""
            QMainWindow, QWidget { background: #0f172a; color: #e2e8f0; }
            QLabel { color: #e2e8f0; font-size: 13px; }
            QLineEdit, QComboBox, QSpinBox, QTextEdit {
                background: #1e293b; color: #e2e8f0;
                border: 2px solid #334155; border-radius: 6px;
                padding: 8px; font-size: 13px;
            }
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QTextEdit:focus {
                border-color: #3b82f6;
            }
            QCheckBox { color: #e2e8f0; font-size: 13px; spacing: 8px; }
            QCheckBox::indicator {
                width: 20px; height: 20px; border: 2px solid #334155;
                border-radius: 4px; background: #1e293b;
            }
            QCheckBox::indicator:checked { background: #3b82f6; border-color: #3b82f6; }
            QProgressBar {
                border: 2px solid #334155; border-radius: 6px;
                text-align: center; background: #1e293b;
                color: #e2e8f0; font-weight: 600; min-height: 28px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #3b82f6, stop:1 #60a5fa);
                border-radius: 4px;
            }
            QTextEdit, QListWidget {
                background: #1e293b; color: #e2e8f0;
                border: 2px solid #334155; border-radius: 6px;
                padding: 8px; font-family: 'Consolas', monospace;
            }
            QListWidget::item { padding: 8px; border-bottom: 1px solid #334155; }
            QListWidget::item:selected { background: #3b82f6; color: white; }
            QListWidget::item:hover { background: #1e293b; }
            QGroupBox {
                color: #60a5fa; font-weight: 600; font-size: 14px;
                border: 2px solid #334155; border-radius: 8px;
                margin-top: 12px; padding-top: 15px;
            }
            QGroupBox::title {
                subcontrol-origin: margin; left: 15px;
                padding: 0 8px; background: #0f172a;
            }
            QTabWidget::pane {
                border: 2px solid #334155; border-radius: 8px;
                background: #0f172a; top: -2px;
            }
            QTabBar::tab {
                background: #1e293b; color: #64748b;
                padding: 12px 24px; margin-right: 4px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                font-weight: 600; font-size: 13px;
            }
            QTabBar::tab:selected {
                background: #0f172a; color: #60a5fa;
                border-bottom: 3px solid #60a5fa;
            }
            QTabBar::tab:hover:!selected { background: #334155; color: #cbd5e1; }
            QMenuBar {
                background: #1e293b; color: #e2e8f0;
                border-bottom: 1px solid #334155; padding: 5px;
            }
            QMenuBar::item:selected { background: #334155; }
            QMenu {
                background: #1e293b; color: #e2e8f0;
                border: 1px solid #334155;
            }
            QMenu::item:selected { background: #334155; }
            QStatusBar {
                background: #1e293b; color: #94a3b8;
                border-top: 1px solid #334155;
            }
            QTableWidget {
                background: #1e293b; color: #e2e8f0;
                gridline-color: #334155; border: 2px solid #334155;
                border-radius: 6px;
            }
            QHeaderView::section {
                background: #334155; color: #e2e8f0;
                padding: 8px; border: none;
                border-bottom: 2px solid #475569; font-weight: 600;
            }
            QRadioButton { color: #e2e8f0; spacing: 8px; }
            QRadioButton::indicator {
                width: 18px; height: 18px; border-radius: 9px;
                border: 2px solid #334155; background: #1e293b;
            }
            QRadioButton::indicator:checked {
                background: #60a5fa; border-color: #60a5fa;
            }
            QScrollBar:vertical {
                background: #1e293b; width: 12px; border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background: #475569; border-radius: 6px;
            }
            QScrollBar::handle:vertical:hover { background: #64748b; }
        """)

    def init_ui(self):
        """Initialize main UI"""
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(15)
        layout.setContentsMargins(25, 25, 25, 25)

        # Header
        header_layout = QHBoxLayout()
        title = QLabel("🎬 Video Downloader Pro")
        title.setFont(QFont("Segoe UI", 22, QFont.Bold))
        title.setStyleSheet("color: #60a5fa; margin-bottom: 10px;")
        header_layout.addWidget(title)
        
        self.stats_label = QLabel("Ready • Downloads: 0")
        self.stats_label.setStyleSheet("color: #34d399; font-size: 13px; font-weight: 600;")
        self.stats_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        header_layout.addWidget(self.stats_label)
        layout.addLayout(header_layout)

        # Tabs
        self.tabs = QTabWidget()
        self.tabs.addTab(self.create_download_tab(), "📥 Download")
        self.tabs.addTab(self.create_playlist_tab(), "📚 Playlist")
        self.tabs.addTab(self.create_history_tab(), "📜 History")
        self.tabs.addTab(self.create_log_tab(), "📋 Log")
        self.tabs.addTab(self.create_code_tab(), "💻 Code")
        self.tabs.addTab(self.create_queue_tab(), "📋 Queue")
        layout.addWidget(self.tabs)

        self.update_code()

    def create_download_tab(self):
        """Create main download tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(15)

        # URL section
        url_group = QGroupBox("📎 Video URL & Information")
        url_layout = QVBoxLayout()
        
        url_input_layout = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Paste video URL here (YouTube, Vimeo, etc.)...")
        self.url_input.setMinimumHeight(42)
        self.url_input.returnPressed.connect(self.fetch_info)
        url_input_layout.addWidget(self.url_input)
        
        self.fetch_btn = ModernButton("Get Info", "🔍", "info")
        self.fetch_btn.clicked.connect(self.fetch_info)
        url_input_layout.addWidget(self.fetch_btn)
        
        self.download_btn = ModernButton("Download", "⬇", "success")
        self.download_btn.clicked.connect(self.start_download)
        url_input_layout.addWidget(self.download_btn)
        
        self.queue_btn = ModernButton("Add to Queue", "➕", "secondary")
        self.queue_btn.clicked.connect(self.add_to_queue)
        url_input_layout.addWidget(self.queue_btn)
        
        url_layout.addLayout(url_input_layout)

        # Info card
        self.info_card = InfoCard("Video Information")
        self.info_card.setVisible(False)
        url_layout.addWidget(self.info_card)
        
        url_group.setLayout(url_layout)
        layout.addWidget(url_group)

        # Settings
        settings_group = QGroupBox("⚙️ Download Settings")
        settings_layout = QVBoxLayout()

        # Path
        path_layout = QHBoxLayout()
        path_layout.addWidget(QLabel("Save to:"))
        self.path_input = QLineEdit(self.settings.get('path', os.path.expanduser("~/Downloads")))
        path_layout.addWidget(self.path_input, 1)
        browse_btn = ModernButton("Browse", "📁", "secondary")
        browse_btn.clicked.connect(self.browse_folder)
        path_layout.addWidget(browse_btn)
        settings_layout.addLayout(path_layout)

        # Quality & Format
        quality_layout = QGridLayout()
        quality_layout.addWidget(QLabel("Quality:"), 0, 0)
        self.quality = QComboBox()
        self.quality.addItems(["Best", "8K (4320p)", "4K (2160p)", "2K (1440p)", 
                               "1080p", "720p", "480p", "360p", "240p"])
        self.quality.currentTextChanged.connect(self.update_code)
        quality_layout.addWidget(self.quality, 0, 1)

        quality_layout.addWidget(QLabel("Format:"), 0, 2)
        self.format = QComboBox()
        self.format.addItems(["mp4", "mkv", "webm", "avi", "mov"])
        self.format.currentTextChanged.connect(self.update_code)
        quality_layout.addWidget(self.format, 0, 3)

        quality_layout.addWidget(QLabel("Audio Format:"), 1, 0)
        self.audio_format = QComboBox()
        self.audio_format.addItems(["mp3", "m4a", "opus", "vorbis", "wav", "flac"])
        quality_layout.addWidget(self.audio_format, 1, 1)

        quality_layout.addWidget(QLabel("Audio Quality:"), 1, 2)
        self.audio_quality = QComboBox()
        self.audio_quality.addItems(["320 kbps", "256 kbps", "192 kbps", "128 kbps", "96 kbps"])
        self.audio_quality.setCurrentIndex(2)
        quality_layout.addWidget(self.audio_quality, 1, 3)

        settings_layout.addLayout(quality_layout)

        # Options
        options_layout = QGridLayout()
        self.audio_only = QCheckBox("🎵 Audio Only")
        self.audio_only.toggled.connect(self.toggle_audio_only)
        options_layout.addWidget(self.audio_only, 0, 0)
        
        self.embed_thumb = QCheckBox("🖼️ Embed Thumbnail")
        options_layout.addWidget(self.embed_thumb, 0, 1)
        
        self.embed_subs = QCheckBox("📝 Embed Subtitles")
        options_layout.addWidget(self.embed_subs, 0, 2)
        
        self.download_subs = QCheckBox("💬 Download All Subs")
        options_layout.addWidget(self.download_subs, 1, 0)
        
        self.write_desc = QCheckBox("📄 Save Description")
        options_layout.addWidget(self.write_desc, 1, 1)
        
        self.write_thumb = QCheckBox("🎨 Save Thumbnail")
        options_layout.addWidget(self.write_thumb, 1, 2)
        
        settings_layout.addLayout(options_layout)
        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)

        # Advanced
        advanced_group = QGroupBox("🔧 Advanced Options")
        advanced_layout = QGridLayout()
        
        advanced_layout.addWidget(QLabel("Retries:"), 0, 0)
        self.retries = QSpinBox()
        self.retries.setRange(0, 20)
        self.retries.setValue(self.settings.get('retries', 5))
        advanced_layout.addWidget(self.retries, 0, 1)
        
        advanced_layout.addWidget(QLabel("Concurrent:"), 0, 2)
        self.concurrent = QSpinBox()
        self.concurrent.setRange(1, 10)
        self.concurrent.setValue(self.settings.get('concurrent', 4))
        advanced_layout.addWidget(self.concurrent, 0, 3)
        
        self.ignore_errors = QCheckBox("⚠️ Ignore Errors")
        self.ignore_errors.setChecked(True)
        advanced_layout.addWidget(self.ignore_errors, 1, 0)
        
        self.no_playlist = QCheckBox("🚫 No Playlist")
        advanced_layout.addWidget(self.no_playlist, 1, 1)
        
        self.limit_rate = QCheckBox("📊 Limit Rate")
        self.limit_rate.toggled.connect(lambda c: self.rate_input.setEnabled(c))
        advanced_layout.addWidget(self.limit_rate, 1, 2)
        
        self.rate_input = QLineEdit()
        self.rate_input.setPlaceholderText("e.g., 1M, 500K")
        self.rate_input.setEnabled(False)
        advanced_layout.addWidget(self.rate_input, 1, 3)
        
        advanced_group.setLayout(advanced_layout)
        layout.addWidget(advanced_group)

        # Progress
        progress_group = QGroupBox("📊 Download Progress")
        progress_layout = QVBoxLayout()
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.progress_bar)
        
        status_layout = QHBoxLayout()
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: #34d399; font-weight: 600;")
        status_layout.addWidget(self.status_label, 1)
        
        self.cancel_btn = ModernButton("Cancel", "❌", "danger")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self.cancel_download)
        status_layout.addWidget(self.cancel_btn)
        progress_layout.addLayout(status_layout)
        
        self.speed_label = QLabel("Speed: -")
        self.speed_label.setStyleSheet("color: #94a3b8;")
        progress_layout.addWidget(self.speed_label)
        
        progress_group.setLayout(progress_layout)
        layout.addWidget(progress_group)

        layout.addStretch()
        return tab

    def create_playlist_tab(self):
        """Create playlist management tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        playlist_group = QGroupBox("📚 Playlist Manager")
        playlist_layout = QVBoxLayout()

        url_layout = QHBoxLayout()
        self.playlist_url = QLineEdit()
        self.playlist_url.setPlaceholderText("Enter playlist URL...")
        self.playlist_url.setMinimumHeight(42)
        url_layout.addWidget(self.playlist_url)
        
        load_btn = ModernButton("Load Playlist", "🔍", "info")
        load_btn.clicked.connect(self.load_playlist)
        url_layout.addWidget(load_btn)
        playlist_layout.addLayout(url_layout)

        self.playlist_list = QListWidget()
        self.playlist_list.setSelectionMode(QListWidget.MultiSelection)
        playlist_layout.addWidget(self.playlist_list)

        actions = QHBoxLayout()
        select_all = ModernButton("Select All", "✓", "secondary")
        select_all.clicked.connect(self.playlist_list.selectAll)
        actions.addWidget(select_all)
        
        clear_sel = ModernButton("Clear Selection", "✗", "secondary")
        clear_sel.clicked.connect(self.playlist_list.clearSelection)
        actions.addWidget(clear_sel)
        
        download_sel = ModernButton("Download Selected", "⬇", "success")
        download_sel.clicked.connect(self.download_playlist_selected)
        actions.addWidget(download_sel)
        playlist_layout.addLayout(actions)

        playlist_group.setLayout(playlist_layout)
        layout.addWidget(playlist_group)
        return tab

    def create_history_tab(self):
        """Create history tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        header = QHBoxLayout()
        label = QLabel("📜 Download History")
        label.setFont(QFont("Segoe UI", 16, QFont.Bold))
        label.setStyleSheet("color: #60a5fa;")
        header.addWidget(label)
        
        self.history_count = QLabel("0 downloads")
        self.history_count.setStyleSheet("color: #94a3b8;")
        header.addWidget(self.history_count)
        header.addStretch()
        layout.addLayout(header)

        self.history_list = QListWidget()
        layout.addWidget(self.history_list)

        actions = QHBoxLayout()
        export_btn = ModernButton("Export", "💾", "secondary")
        export_btn.clicked.connect(self.export_history)
        actions.addWidget(export_btn)
        
        clear_btn = ModernButton("Clear", "🗑", "danger")
        clear_btn.clicked.connect(self.clear_history)
        actions.addWidget(clear_btn)
        actions.addStretch()
        layout.addLayout(actions)

        return tab

    def create_log_tab(self):
        """Create log tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        header = QHBoxLayout()
        label = QLabel("📋 Activity Log")
        label.setFont(QFont("Segoe UI", 16, QFont.Bold))
        label.setStyleSheet("color: #60a5fa;")
        header.addWidget(label)
        header.addStretch()
        
        clear_btn = ModernButton("Clear", "🗑", "secondary")
        clear_btn.clicked.connect(self.clear_log)
        header.addWidget(clear_btn)
        
        save_btn = ModernButton("Save", "💾", "secondary")
        save_btn.clicked.connect(self.save_log)
        header.addWidget(save_btn)
        layout.addLayout(header)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        layout.addWidget(self.log_text)

        return tab

    def create_code_tab(self):
        """Create code generator tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        header = QHBoxLayout()
        label = QLabel("💻 Python Code Generator")
        label.setFont(QFont("Segoe UI", 16, QFont.Bold))
        label.setStyleSheet("color: #60a5fa;")
        header.addWidget(label)
        header.addStretch()
        
        copy_btn = ModernButton("Copy", "📋", "secondary")
        copy_btn.clicked.connect(self.copy_code)
        header.addWidget(copy_btn)
        
        save_btn = ModernButton("Save", "💾", "secondary")
        save_btn.clicked.connect(self.save_code)
        header.addWidget(save_btn)
        layout.addLayout(header)

        self.code_text = QTextEdit()
        self.code_text.setReadOnly(True)
        self.code_text.setFont(QFont("Consolas", 10))
        layout.addWidget(self.code_text)

        return tab

    def create_queue_tab(self):
        """Create queue tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        header = QHBoxLayout()
        label = QLabel("📋 Download Queue")
        label.setFont(QFont("Segoe UI", 16, QFont.Bold))
        label.setStyleSheet("color: #60a5fa;")
        header.addWidget(label)
        
        self.queue_count = QLabel("0 items")
        self.queue_count.setStyleSheet("color: #94a3b8;")
        header.addWidget(self.queue_count)
        header.addStretch()
        layout.addLayout(header)

        self.queue_table = QTableWidget()
        self.queue_table.setColumnCount(4)
        self.queue_table.setHorizontalHeaderLabels(["#", "URL", "Status", "Actions"])
        self.queue_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        layout.addWidget(self.queue_table)

        actions = QHBoxLayout()
        start_btn = ModernButton("Start Queue", "▶️", "success")
        start_btn.clicked.connect(self.start_queue)
        actions.addWidget(start_btn)
        
        clear_btn = ModernButton("Clear Queue", "🗑", "danger")
        clear_btn.clicked.connect(self.clear_queue)
        actions.addWidget(clear_btn)
        actions.addStretch()
        layout.addLayout(actions)

        return tab

    def create_menubar(self):
        """Create menu bar"""
        menubar = self.menuBar()

        # File
        file_menu = menubar.addMenu("&File")
        file_menu.addAction("📥 New Download", lambda: self.tabs.setCurrentIndex(0), "Ctrl+N")
        file_menu.addAction("📚 Batch Download", self.show_batch_dialog, "Ctrl+B")
        file_menu.addSeparator()
        file_menu.addAction("📁 Open Folder", self.open_folder, "Ctrl+O")
        file_menu.addSeparator()
        file_menu.addAction("❌ Exit", self.close, "Ctrl+Q")

        # Edit
        edit_menu = menubar.addMenu("&Edit")
        edit_menu.addAction("⚙️ Settings", self.show_settings, "Ctrl+,")

        # View
        view_menu = menubar.addMenu("&View")
        view_menu.addAction("📜 History", lambda: self.tabs.setCurrentIndex(2), "Ctrl+H")
        view_menu.addAction("📋 Log", lambda: self.tabs.setCurrentIndex(3), "Ctrl+L")

        # Tools
        tools_menu = menubar.addMenu("&Tools")
        tools_menu.addAction("🔄 Update yt-dlp", self.update_ytdlp)
        tools_menu.addAction("🔧 Check FFmpeg", self.check_ffmpeg)

        # Help
        help_menu = menubar.addMenu("&Help")
        help_menu.addAction("ℹ️ About", self.show_about)
        help_menu.addAction("📖 Documentation", lambda: QDesktopServices.openUrl(
            QUrl("https://github.com/yt-dlp/yt-dlp#readme")))

    def create_statusbar(self):
        """Create status bar"""
        self.statusbar = self.statusBar()
        self.status_msg = QLabel("Ready")
        self.statusbar.addWidget(self.status_msg)
        self.statusbar.addPermanentWidget(QLabel("|"))
        self.downloads_status = QLabel("Downloads: 0")
        self.statusbar.addPermanentWidget(self.downloads_status)

    # ==================== HELPER METHODS ====================

    def fmt_bytes(self, b):
        """Format bytes to human readable"""
        if not b: return "0 B"
        for u in ['B', 'KB', 'MB', 'GB', 'TB']:
            if b < 1024: return f"{b:.2f} {u}"
            b /= 1024
        return f"{b:.2f} PB"

    def fmt_duration(self, s):
        """Format duration"""
        if not s: return "Unknown"
        h, m, s = int(s//3600), int((s%3600)//60), int(s%60)
        return f"{h}h {m}m {s}s" if h else f"{m}m {s}s" if m else f"{s}s"

    def log(self, msg):
        """Add log message"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {msg}")
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum())
        self.status_msg.setText(msg[:50] + "..." if len(msg) > 50 else msg)

    def get_quality_value(self):
        """Get quality value"""
        quality_map = {
            "Best": "best", "8K (4320p)": "4320", "4K (2160p)": "2160",
            "2K (1440p)": "1440", "1080p": "1080", "720p": "720",
            "480p": "480", "360p": "360", "240p": "240"
        }
        return quality_map[self.quality.currentText()]

    def get_options(self):
        """Get download options"""
        quality = self.get_quality_value()
        audio_only = self.audio_only.isChecked()
        
        if audio_only:
            format_str = "bestaudio/best"
            postprocessors = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': self.audio_format.currentText(),
                'preferredquality': self.audio_quality.currentText().split()[0]
            }]
        else:
            format_str = "bestvideo+bestaudio/best" if quality == "best" else \
                        f"bestvideo[height<={quality}]+bestaudio/best[height<={quality}]"
            postprocessors = [{'key': 'FFmpegVideoConvertor', 
                             'preferedformat': self.format.currentText()}]

        if self.embed_thumb.isChecked():
            postprocessors.append({'key': 'EmbedThumbnail'})
        if self.embed_subs.isChecked():
            postprocessors.append({'key': 'FFmpegEmbedSubtitle'})

        opts = {
            'format': format_str,
            'outtmpl': os.path.join(self.path_input.text(), '%(title)s.%(ext)s'),
            'merge_output_format': self.format.currentText(),
            'ignoreerrors': self.ignore_errors.isChecked(),
            'retries': self.retries.value(),
            'fragment_retries': self.retries.value(),
            'concurrent_fragment_downloads': self.concurrent.value(),
            'postprocessors': postprocessors,
            'quiet': False,
            'no_warnings': False,
        }

        if self.download_subs.isChecked():
            opts['writesubtitles'] = True
            opts['allsubtitles'] = True
        if self.embed_subs.isChecked():
            opts['writesubtitles'] = True
            opts['subtitleslangs'] = ['en']
        if self.write_desc.isChecked():
            opts['writedescription'] = True
        if self.write_thumb.isChecked():
            opts['writethumbnail'] = True
        if self.no_playlist.isChecked():
            opts['noplaylist'] = True
        if self.limit_rate.isChecked() and self.rate_input.text():
            opts['ratelimit'] = self.rate_input.text()

        return opts

    # ==================== DOWNLOAD METHODS ====================

    def fetch_info(self):
        """Fetch video info"""
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "Error", "Enter a URL!")
            return

        if self.workers['info'] and self.workers['info'].isRunning():
            return

        self.fetch_btn.setEnabled(False)
        self.fetch_btn.setText("⏳ Fetching...")
        self.log(f"Fetching info: {url}")

        self.workers['info'] = InfoWorker(url)
        self.workers['info'].info_ready.connect(self.display_info)
        self.workers['info'].error.connect(self.info_error)
        self.workers['info'].start()

    def display_info(self, info):
        """Display video info"""
        self.current_video_info = info
        self.fetch_btn.setEnabled(True)
        self.fetch_btn.setText("🔍 Get Info")

        self.info_card.clear_info()
        self.info_card.add_info("📺 Title:", info.get('title', 'Unknown'))
        self.info_card.add_info("⏱️ Duration:", self.fmt_duration(info.get('duration', 0)))
        self.info_card.add_info("👤 Uploader:", info.get('uploader', 'Unknown'))
        
        views = info.get('view_count', 0)
        self.info_card.add_info("👁️ Views:", f"{views:,}" if views else "N/A")
        
        size = info.get('filesize', 0) or info.get('filesize_approx', 0)
        self.info_card.add_info("💾 Size:", self.fmt_bytes(size) if size else "N/A")
        
        self.info_card.setVisible(True)
        self.log(f"✓ Info: {info.get('title', 'Unknown')}")

    def info_error(self, error):
        """Handle info error"""
        self.fetch_btn.setEnabled(True)
        self.fetch_btn.setText("🔍 Get Info")
        self.log(f"✗ Info error: {error}")
        QMessageBox.warning(self, "Error", f"Failed to fetch info:\n{error}")

    def start_download(self):
        """Start download"""
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "Error", "Enter a URL!")
            return

        if self.workers['download'] and self.workers['download'].isRunning():
            QMessageBox.warning(self, "Error", "Download in progress!")
            return

        path = self.path_input.text()
        if not os.path.exists(path):
            try:
                os.makedirs(path)
            except:
                QMessageBox.warning(self, "Error", "Invalid path!")
                return

        opts = self.get_options()
        self.workers['download'] = DownloadWorker(url, opts)
        self.workers['download'].progress.connect(self.update_progress)
        self.workers['download'].finished.connect(self.download_finished)
        self.workers['download'].log.connect(self.log)
        self.workers['download'].start()

        self.download_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.progress_bar.setValue(0)
        self.status_label.setText("Downloading...")
        self.save_config()

    def cancel_download(self):
        """Cancel download"""
        if self.workers['download'] and self.workers['download'].isRunning():
            if QMessageBox.question(self, "Cancel", "Cancel download?",
                                   QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
                self.workers['download'].cancel()
                self.log("Download cancelled")

    def update_progress(self, data):
        """Update progress"""
        if data.get('status') == 'downloading':
            try:
                total = data.get('total_bytes') or data.get('total_bytes_estimate', 0)
                downloaded = data.get('downloaded_bytes', 0)
                if total > 0:
                    percent = int((downloaded / total) * 100)
                    self.progress_bar.setValue(percent)
                    speed = data.get('speed', 0)
                    eta = data.get('eta', 0)
                    speed_str = f"{self.fmt_bytes(speed)}/s" if speed else "..."
                    eta_str = f"{eta}s" if eta else "..."
                    self.status_label.setText(
                        f"Downloading: {percent}% ({self.fmt_bytes(downloaded)}/{self.fmt_bytes(total)})")
                    self.speed_label.setText(f"Speed: {speed_str} • ETA: {eta_str}")
            except:
                pass
        elif data.get('status') == 'processing':
            self.progress_bar.setValue(100)
            self.status_label.setText("Processing...")
            self.speed_label.setText("Almost done...")

    def download_finished(self, success, msg, filepath):
        """Handle download finish"""
        self.download_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)

        if success:
            self.progress_bar.setValue(100)
            self.status_label.setText("✅ " + msg)
            self.status_label.setStyleSheet("color: #34d399; font-weight: 600;")
            self.speed_label.setText("Completed!")

            # Add to history
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            title = self.current_video_info.get('title', 'Unknown') if self.current_video_info else 'Unknown'
            entry = f"[{timestamp}] {title} • {self.quality.currentText()} • {self.format.currentText().upper()}"
            self.history.insert(0, entry)
            self.history = self.history[:100]
            self.update_history_display()
            self.save_history()
            self.update_stats()

            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Information)
            msg_box.setWindowTitle("Success")
            msg_box.setText(f"{msg}\n\nSaved to: {self.path_input.text()}")
            msg_box.setStandardButtons(QMessageBox.Ok | QMessageBox.Open)
            msg_box.button(QMessageBox.Open).setText("Open Folder")
            if msg_box.exec_() == QMessageBox.Open:
                self.open_folder()
        else:
            self.progress_bar.setValue(0)
            self.status_label.setText("❌ Failed")
            self.status_label.setStyleSheet("color: #f87171; font-weight: 600;")
            self.speed_label.setText("-")
            QMessageBox.critical(self, "Error", msg)

    def toggle_audio_only(self, checked):
        """Toggle audio only mode"""
        self.quality.setEnabled(not checked)
        self.format.setEnabled(not checked)
        self.update_code()

    # ==================== PLAYLIST METHODS ====================

    def load_playlist(self):
        """Load playlist"""
        url = self.playlist_url.text().strip()
        if not url:
            QMessageBox.warning(self, "Error", "Enter playlist URL!")
            return

        if self.workers['playlist'] and self.workers['playlist'].isRunning():
            return

        self.playlist_list.clear()
        self.log(f"Loading playlist: {url}")

        self.workers['playlist'] = PlaylistWorker(url)
        self.workers['playlist'].info_ready.connect(self.display_playlist)
        self.workers['playlist'].error.connect(self.playlist_error)
        self.workers['playlist'].progress.connect(
            lambda c, t: self.log(f"Loading: {c}/{t} videos"))
        self.workers['playlist'].start()

    def display_playlist(self, videos):
        """Display playlist"""
        self.playlist_list.clear()
        for i, v in enumerate(videos, 1):
            item_text = f"{i}. {v['title']} [{self.fmt_duration(v.get('duration', 0))}]"
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, v)
            self.playlist_list.addItem(item)
        self.log(f"✓ Loaded {len(videos)} videos")
        QMessageBox.information(self, "Success", f"Loaded {len(videos)} videos!")

    def playlist_error(self, error):
        """Handle playlist error"""
        self.log(f"✗ Playlist error: {error}")
        QMessageBox.warning(self, "Error", f"Failed:\n{error}")

    def download_playlist_selected(self):
        """Download selected playlist videos"""
        items = self.playlist_list.selectedItems()
        if not items:
            QMessageBox.warning(self, "Error", "Select videos!")
            return

        urls = []
        for item in items:
            v = item.data(Qt.UserRole)
            if v and v.get('id'):
                urls.append(f"https://www.youtube.com/watch?v={v['id']}")

        if urls and QMessageBox.question(self, "Confirm", 
                f"Add {len(urls)} videos to queue?",
                QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            for url in urls:
                self.add_url_to_queue(url)
            self.tabs.setCurrentIndex(5)

    # ==================== QUEUE METHODS ====================

    def add_to_queue(self):
        """Add current URL to queue"""
        url = self.url_input.text().strip()
        if url:
            self.add_url_to_queue(url)

    def add_url_to_queue(self, url):
        """Add URL to queue table"""
        row = self.queue_table.rowCount()
        self.queue_table.insertRow(row)
        self.queue_table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
        self.queue_table.setItem(row, 1, QTableWidgetItem(url))
        self.queue_table.setItem(row, 2, QTableWidgetItem("⏳ Pending"))
        
        remove_btn = ModernButton("🗑", "", "danger")
        remove_btn.clicked.connect(lambda: self.remove_from_queue(row))
        self.queue_table.setCellWidget(row, 3, remove_btn)
        
        self.queue.append({'url': url, 'status': 'pending'})
        self.update_queue_count()
        self.log(f"Added to queue: {url}")

    def remove_from_queue(self, row):
        """Remove from queue"""
        if 0 <= row < len(self.queue):
            del self.queue[row]
            self.queue_table.removeRow(row)
            self.update_queue_count()
            for i in range(self.queue_table.rowCount()):
                self.queue_table.setItem(i, 0, QTableWidgetItem(str(i + 1)))

    def clear_queue(self):
        """Clear queue"""
        if self.queue and QMessageBox.question(self, "Clear", "Clear queue?",
                QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            self.queue.clear()
            self.queue_table.setRowCount(0)
            self.update_queue_count()
            self.log("Queue cleared")

    def update_queue_count(self):
        """Update queue count"""
        self.queue_count.setText(f"{len(self.queue)} item{'s' if len(self.queue) != 1 else ''}")

    def start_queue(self):
        """Start queue download"""
        if not self.queue:
            QMessageBox.information(self, "Info", "Queue is empty!")
            return

        if self.workers['batch'] and self.workers['batch'].isRunning():
            QMessageBox.warning(self, "Error", "Batch in progress!")
            return

        urls = [item['url'] for item in self.queue if item['status'] == 'pending']
        if not urls:
            QMessageBox.information(self, "Info", "No pending downloads!")
            return

        self.workers['batch'] = BatchWorker(urls, self.get_options())
        self.workers['batch'].progress.connect(self.batch_progress)
        self.workers['batch'].item_finished.connect(self.batch_item_finished)
        self.workers['batch'].all_finished.connect(self.batch_all_finished)
        self.workers['batch'].start()
        self.log(f"Starting batch: {len(urls)} items")

    def batch_progress(self, current, total, url):
        """Update batch progress"""
        self.log(f"Downloading {current}/{total}: {url}")
        for i, item in enumerate(self.queue):
            if item['url'] == url:
                self.queue_table.setItem(i, 2, QTableWidgetItem(f"⬇️ Downloading ({current}/{total})"))

    def batch_item_finished(self, success, url, msg):
        """Handle batch item finish"""
        self.log(msg)
        for i, item in enumerate(self.queue):
            if item['url'] == url:
                status = "✅ Completed" if success else "❌ Failed"
                self.queue_table.setItem(i, 2, QTableWidgetItem(status))
                item['status'] = 'completed' if success else 'failed'

    def batch_all_finished(self, successful, failed):
        """Handle batch finish"""
        self.log(f"Batch finished: {successful} OK, {failed} failed")
        QMessageBox.information(self, "Complete",
            f"Batch finished!\n\nSuccessful: {successful}\nFailed: {failed}")

    # ==================== HISTORY METHODS ====================

    def update_history_display(self):
        """Update history list"""
        self.history_list.clear()
        for entry in self.history:
            self.history_list.addItem(entry)
        self.history_count.setText(f"{len(self.history)} download{'s' if len(self.history) != 1 else ''}")

    def export_history(self):
        """Export history"""
        if not self.history:
            QMessageBox.information(self, "Info", "No history!")
            return

        fname, _ = QFileDialog.getSaveFileName(self, "Export History",
            f"history_{datetime.now().strftime('%Y%m%d')}.txt",
            "Text Files (*.txt);;JSON Files (*.json)")

        if fname:
            try:
                with open(fname, 'w', encoding='utf-8') as f:
                    if fname.endswith('.json'):
                        json.dump(self.history, f, indent=2)
                    else:
                        f.write("Download History\n" + "="*80 + "\n\n")
                        f.write("\n".join(self.history))
                self.log(f"✓ Exported: {fname}")
                QMessageBox.information(self, "Success", f"Exported to:\n{fname}")
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def clear_history(self):
        """Clear history"""
        if self.history and QMessageBox.question(self, "Clear", "Clear history?",
                QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            self.history.clear()
            self.update_history_display()
            self.save_history()
            self.update_stats()
            self.log("History cleared")

    # ==================== LOG METHODS ====================

    def clear_log(self):
        """Clear log"""
        self.log_text.clear()
        self.log("Log cleared")

    def save_log(self):
        """Save log"""
        fname, _ = QFileDialog.getSaveFileName(self, "Save Log",
            f"log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            "Text Files (*.txt)")
        if fname:
            try:
                with open(fname, 'w', encoding='utf-8') as f:
                    f.write(self.log_text.toPlainText())
                self.log(f"✓ Log saved: {fname}")
                QMessageBox.information(self, "Success", f"Saved to:\n{fname}")
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    # ==================== CODE GENERATOR ====================

    def update_code(self):
        """Update generated code"""
        quality = self.get_quality_value()
        audio_only = self.audio_only.isChecked()
        
        if audio_only:
            format_str = "bestaudio/best"
            pp = f"""[
        {{'key': 'FFmpegExtractAudio',
         'preferredcodec': '{self.audio_format.currentText()}',
         'preferredquality': '{self.audio_quality.currentText().split()[0]}'}}"""
        else:
            format_str = "bestvideo+bestaudio/best" if quality == "best" else \
                        f"bestvideo[height<={quality}]+bestaudio/best[height<={quality}]"
            pp = f"""[
        {{'key': 'FFmpegVideoConvertor',
         'preferedformat': '{self.format.currentText()}'}}"""

        if self.embed_thumb.isChecked():
            pp += ",\n        {'key': 'EmbedThumbnail'}"
        if self.embed_subs.isChecked():
            pp += ",\n        {'key': 'FFmpegEmbedSubtitle'}"
        pp += "\n    ]"

        extra_opts = []
        if self.download_subs.isChecked():
            extra_opts.append("'writesubtitles': True,\n        'allsubtitles': True,")
        if self.write_desc.isChecked():
            extra_opts.append("'writedescription': True,")
        if self.write_thumb.isChecked():
            extra_opts.append("'writethumbnail': True,")
        if self.no_playlist.isChecked():
            extra_opts.append("'noplaylist': True,")
        if self.limit_rate.isChecked() and self.rate_input.text():
            extra_opts.append(f"'ratelimit': '{self.rate_input.text()}',")

        extra_str = "\n        ".join(extra_opts)

        code = f'''#!/usr/bin/env python3
"""
Video Downloader Script
Generated by Video Downloader Pro v3.0
Date: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
"""

import yt_dlp
import sys

def download_video(url):
    """Download video with specified options"""
    
    ydl_opts = {{
        'format': '{format_str}',
        'outtmpl': r'{self.path_input.text()}{os.sep}%(title)s.%(ext)s',
        'merge_output_format': '{self.format.currentText()}',
        
        # Error handling
        'ignoreerrors': {str(self.ignore_errors.isChecked())},
        'no_warnings': False,
        'quiet': False,
        'retries': {self.retries.value()},
        'fragment_retries': {self.retries.value()},
        'concurrent_fragment_downloads': {self.concurrent.value()},
        
        # File naming
        'windowsfilenames': True,
        
        {extra_str}
        
        # Post-processing
        'postprocessors': {pp},
    }}
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            print(f"Downloading: {{url}}")
            info = ydl.extract_info(url, download=True)
            print(f"\\n✓ Downloaded: {{info.get('title', 'Unknown')}}")
            return True
    except Exception as e:
        print(f"✗ Error: {{e}}")
        return False

if __name__ == "__main__":
    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        url = input("Enter video URL: ")
    
    success = download_video(url)
    sys.exit(0 if success else 1)
'''
        self.code_text.setText(code)

    def copy_code(self):
        """Copy code to clipboard"""
        QApplication.clipboard().setText(self.code_text.toPlainText())
        self.log("✓ Code copied")
        self.statusbar.showMessage("Code copied to clipboard", 3000)

    def save_code(self):
        """Save code to file"""
        fname, _ = QFileDialog.getSaveFileName(self, "Save Script",
            "download_video.py", "Python Files (*.py)")
        if fname:
            try:
                with open(fname, 'w', encoding='utf-8') as f:
                    f.write(self.code_text.toPlainText())
                self.log(f"✓ Code saved: {fname}")
                QMessageBox.information(self, "Success", f"Saved to:\n{fname}")
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    # ==================== MENU ACTIONS ====================

    def show_batch_dialog(self):
        """Show batch download dialog"""
        dialog = BatchDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            urls = dialog.urls
            for url in urls:
                self.add_url_to_queue(url)
            self.tabs.setCurrentIndex(5)
            self.log(f"✓ Added {len(urls)} URLs to queue")

    def show_settings(self):
        """Show settings dialog"""
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec_() == QDialog.Accepted:
            self.save_config()

    def show_about(self):
        """Show about dialog"""
        AboutDialog(self).exec_()

    def browse_folder(self):
        """Browse for folder"""
        folder = QFileDialog.getExistingDirectory(self, "Select Folder")
        if folder:
            self.path_input.setText(folder)

    def open_folder(self):
        """Open download folder"""
        path = self.path_input.text()
        if os.path.exists(path):
            system = platform.system()
            try:
                if system == 'Windows':
                    os.startfile(path)
                elif system == 'Darwin':
                    subprocess.Popen(['open', path])
                else:
                    subprocess.Popen(['xdg-open', path])
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to open folder:\n{str(e)}")
        else:
            QMessageBox.warning(self, "Error", "Folder does not exist!")

    def check_ytdlp_version(self):
        """Check yt-dlp version"""
        try:
            result = subprocess.run(['yt-dlp', '--version'],
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                self.log(f"yt-dlp version: {result.stdout.strip()}")
        except:
            self.log("Could not check yt-dlp version")

    def update_ytdlp(self):
        """Update yt-dlp"""
        self.log("Updating yt-dlp...")
        try:
            result = subprocess.run(['yt-dlp', '-U'],
                                  capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                QMessageBox.information(self, "Success", "yt-dlp updated!")
                self.log("✓ yt-dlp updated")
            else:
                QMessageBox.warning(self, "Error", f"Update failed:\n{result.stderr}")
                self.log(f"✗ Update failed: {result.stderr}")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
            self.log(f"✗ Update error: {str(e)}")

    def check_ffmpeg(self):
        """Check FFmpeg"""
        try:
            result = subprocess.run(['ffmpeg', '-version'],
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                version = result.stdout.split('\n')[0]
                QMessageBox.information(self, "FFmpeg", f"✓ FFmpeg is installed:\n{version}")
                self.log(f"✓ FFmpeg: {version}")
        except FileNotFoundError:
            QMessageBox.critical(self, "FFmpeg Not Found",
                "FFmpeg is not installed!\n\n"
                "FFmpeg is required for:\n"
                "• Merging video and audio\n"
                "• Format conversion\n"
                "• Thumbnail embedding\n\n"
                "Download: https://ffmpeg.org")
            self.log("✗ FFmpeg not found")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    # ==================== CONFIG/DATA METHODS ====================

    def update_stats(self):
        """Update statistics"""
        count = len(self.history)
        self.stats_label.setText(f"Ready • Downloads: {count}")
        self.downloads_status.setText(f"Downloads: {count}")

    def load_config(self):
        """Load configuration"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.settings = data.get('settings', {})
        except:
            self.settings = {}

    def save_config(self):
        """Save configuration"""
        try:
            self.settings.update({
                'path': self.path_input.text(),
                'retries': self.retries.value(),
                'concurrent': self.concurrent.value(),
            })
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump({'settings': self.settings}, f, indent=2)
        except Exception as e:
            self.log(f"✗ Save config failed: {str(e)}")

    def load_history(self):
        """Load history"""
        try:
            if os.path.exists(self.history_file):
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    self.history = json.load(f)
                    self.update_history_display()
                    self.update_stats()
        except:
            self.history = []

    def save_history(self):
        """Save history"""
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self.history[:100], f, indent=2)
        except Exception as e:
            self.log(f"✗ Save history failed: {str(e)}")

    def closeEvent(self, event):
        """Handle close event"""
        # Check for active downloads
        if self.workers['download'] and self.workers['download'].isRunning():
            reply = QMessageBox.question(self, "Exit",
                "Download in progress. Exit anyway?",
                QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.No:
                event.ignore()
                return
            self.workers['download'].cancel()
            self.workers['download'].wait(3000)

        # Save data
        self.save_config()
        self.save_history()
        event.accept()


# ==================== MAIN ====================

def main():
    """Main entry point"""
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    app.setApplicationName("Video Downloader Pro")
    app.setOrganizationName("VDP")
    app.setApplicationVersion("3.0")
    
    window = VideoDownloader()
    window.show()
    
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()