import sys
import os
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QLineEdit, QPushButton,
                             QComboBox, QCheckBox, QProgressBar, QTextEdit,
                             QFileDialog, QGroupBox, QSpinBox, QTabWidget,
                             QListWidget, QMessageBox)
from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtGui import QFont, QIcon
import yt_dlp
from datetime import datetime


class DownloadThread(QThread):
    """Thread to handle video downloading without blocking UI"""
    progress = pyqtSignal(dict)
    finished = pyqtSignal(bool, str)

    def __init__(self, url, options):
        super().__init__()
        self.url = url
        self.options = options

    def progress_hook(self, d):
        """Callback for download progress"""
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
                        'status': 'downloading'
                    })
            except:
                pass
        elif d['status'] == 'finished':
            self.progress.emit({'status': 'processing', 'percent': 100})

    def run(self):
        """Execute download in separate thread"""
        try:
            self.options['progress_hooks'] = [self.progress_hook]

            with yt_dlp.YoutubeDL(self.options) as ydl:
                try:
                    ydl.update()
                except:
                    pass  # Skip auto-update if it fails

                ydl.download([self.url])

            self.finished.emit(True, "Download completed successfully!")
        except Exception as e:
            self.finished.emit(False, f"Error: {str(e)}")


class VideoDownloaderApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Advanced yt-dlp Video Downloader")
        self.setGeometry(100, 100, 900, 700)
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1e1e2e;
            }
            QLabel {
                color: #cdd6f4;
                font-size: 11pt;
            }
            QLineEdit, QComboBox, QSpinBox {
                background-color: #313244;
                color: #cdd6f4;
                border: 2px solid #45475a;
                border-radius: 5px;
                padding: 5px;
                font-size: 10pt;
            }
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
                border: 2px solid #89b4fa;
            }
            QPushButton {
                background-color: #89b4fa;
                color: #1e1e2e;
                border: none;
                border-radius: 5px;
                padding: 8px 15px;
                font-weight: bold;
                font-size: 10pt;
            }
            QPushButton:hover {
                background-color: #b4befe;
            }
            QPushButton:pressed {
                background-color: #74c7ec;
            }
            QPushButton:disabled {
                background-color: #45475a;
                color: #6c7086;
            }
            QCheckBox {
                color: #cdd6f4;
                font-size: 10pt;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 3px;
                border: 2px solid #45475a;
                background-color: #313244;
            }
            QCheckBox::indicator:checked {
                background-color: #89b4fa;
                border: 2px solid #89b4fa;
            }
            QProgressBar {
                border: 2px solid #45475a;
                border-radius: 5px;
                text-align: center;
                background-color: #313244;
                color: #cdd6f4;
            }
            QProgressBar::chunk {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                                  stop:0 #89b4fa, stop:1 #b4befe);
                border-radius: 3px;
            }
            QTextEdit, QListWidget {
                background-color: #313244;
                color: #cdd6f4;
                border: 2px solid #45475a;
                border-radius: 5px;
                padding: 5px;
            }
            QGroupBox {
                color: #89b4fa;
                font-weight: bold;
                font-size: 11pt;
                border: 2px solid #45475a;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
            QTabWidget::pane {
                border: 2px solid #45475a;
                border-radius: 5px;
                background-color: #1e1e2e;
            }
            QTabBar::tab {
                background-color: #313244;
                color: #cdd6f4;
                padding: 8px 20px;
                margin-right: 2px;
                border-top-left-radius: 5px;
                border-top-right-radius: 5px;
            }
            QTabBar::tab:selected {
                background-color: #89b4fa;
                color: #1e1e2e;
            }
        """)

        self.download_thread = None
        self.download_history = []

        self.init_ui()

    def init_ui(self):
        """Initialize the user interface"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # Title
        title = QLabel("🎬 Advanced Video Downloader")
        title.setFont(QFont("Arial", 18, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #89b4fa; margin-bottom: 10px;")
        main_layout.addWidget(title)

        # Tab Widget
        tabs = QTabWidget()
        main_layout.addWidget(tabs)

        # Download Tab
        download_tab = QWidget()
        download_layout = QVBoxLayout(download_tab)

        # URL Input Group
        url_group = QGroupBox("Video URL")
        url_layout = QVBoxLayout()

        url_input_layout = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Enter YouTube or video URL here...")
        url_input_layout.addWidget(self.url_input)

        self.download_btn = QPushButton("⬇ Download")
        self.download_btn.clicked.connect(self.start_download)
        url_input_layout.addWidget(self.download_btn)

        url_layout.addLayout(url_input_layout)
        url_group.setLayout(url_layout)
        download_layout.addWidget(url_group)

        # Settings Group
        settings_group = QGroupBox("Download Settings")
        settings_layout = QVBoxLayout()

        # Output Path
        path_layout = QHBoxLayout()
        path_layout.addWidget(QLabel("Output Path:"))
        self.path_input = QLineEdit()
        self.path_input.setText(os.path.join(os.path.expanduser("~"), "Downloads"))
        path_layout.addWidget(self.path_input)

        browse_btn = QPushButton("📁 Browse")
        browse_btn.clicked.connect(self.browse_folder)
        path_layout.addWidget(browse_btn)
        settings_layout.addLayout(path_layout)

        # Quality and Format
        quality_format_layout = QHBoxLayout()

        quality_format_layout.addWidget(QLabel("Quality:"))
        self.quality_combo = QComboBox()
        self.quality_combo.addItems([
            "Best (4K - 2160p)",
            "2K (1440p)",
            "Full HD (1080p)",
            "HD (720p)",
            "SD (480p)",
            "Low (360p)"
        ])
        self.quality_combo.setCurrentIndex(2)
        quality_format_layout.addWidget(self.quality_combo)

        quality_format_layout.addWidget(QLabel("Format:"))
        self.format_combo = QComboBox()
        self.format_combo.addItems(["mp4", "mkv", "webm", "mp3", "m4a"])
        quality_format_layout.addWidget(self.format_combo)

        settings_layout.addLayout(quality_format_layout)

        # Checkboxes
        checkbox_layout = QHBoxLayout()
        self.audio_only_check = QCheckBox("Audio Only")
        self.audio_only_check.toggled.connect(self.toggle_audio_only)
        checkbox_layout.addWidget(self.audio_only_check)

        self.embed_thumbnail_check = QCheckBox("Embed Thumbnail")
        checkbox_layout.addWidget(self.embed_thumbnail_check)

        self.embed_subs_check = QCheckBox("Embed Subtitles")
        checkbox_layout.addWidget(self.embed_subs_check)

        checkbox_layout.addStretch()
        settings_layout.addLayout(checkbox_layout)

        settings_group.setLayout(settings_layout)
        download_layout.addWidget(settings_group)

        # Advanced Settings Group
        advanced_group = QGroupBox("Advanced Options")
        advanced_layout = QHBoxLayout()

        advanced_layout.addWidget(QLabel("Retries:"))
        self.retries_spin = QSpinBox()
        self.retries_spin.setRange(0, 10)
        self.retries_spin.setValue(3)
        advanced_layout.addWidget(self.retries_spin)

        self.ignore_errors_check = QCheckBox("Ignore Errors")
        self.ignore_errors_check.setChecked(True)
        advanced_layout.addWidget(self.ignore_errors_check)

        advanced_layout.addStretch()
        advanced_group.setLayout(advanced_layout)
        download_layout.addWidget(advanced_group)

        # Progress Group
        progress_group = QGroupBox("Download Progress")
        progress_layout = QVBoxLayout()

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.progress_bar)

        self.status_label = QLabel("Ready to download")
        self.status_label.setStyleSheet("color: #a6e3a1;")
        progress_layout.addWidget(self.status_label)

        progress_group.setLayout(progress_layout)
        download_layout.addWidget(progress_group)

        download_layout.addStretch()
        tabs.addTab(download_tab, "📥 Download")

        # History Tab
        history_tab = QWidget()
        history_layout = QVBoxLayout(history_tab)

        history_label = QLabel("Download History")
        history_label.setFont(QFont("Arial", 12, QFont.Bold))
        history_layout.addWidget(history_label)

        self.history_list = QListWidget()
        history_layout.addWidget(self.history_list)

        clear_history_btn = QPushButton("🗑 Clear History")
        clear_history_btn.clicked.connect(self.clear_history)
        history_layout.addWidget(clear_history_btn)

        tabs.addTab(history_tab, "📜 History")

        # Code Generator Tab
        code_tab = QWidget()
        code_layout = QVBoxLayout(code_tab)

        code_label = QLabel("Generated Python Code")
        code_label.setFont(QFont("Arial", 12, QFont.Bold))
        code_layout.addWidget(code_label)

        self.code_text = QTextEdit()
        self.code_text.setReadOnly(True)
        self.code_text.setFont(QFont("Courier", 9))
        code_layout.addWidget(self.code_text)

        copy_code_btn = QPushButton("📋 Copy Code")
        copy_code_btn.clicked.connect(self.copy_code)
        code_layout.addWidget(copy_code_btn)

        tabs.addTab(code_tab, "💻 Code")

        # Generate initial code
        self.update_code()

    def browse_folder(self):
        """Open folder browser dialog"""
        folder = QFileDialog.getExistingDirectory(self, "Select Download Folder")
        if folder:
            self.path_input.setText(folder)

    def toggle_audio_only(self, checked):
        """Enable/disable quality selection based on audio only mode"""
        self.quality_combo.setEnabled(not checked)
        if checked:
            self.format_combo.setCurrentText("mp3")
        else:
            self.format_combo.setCurrentText("mp4")
        self.update_code()

    def get_quality_value(self):
        """Get quality value from combo box"""
        quality_map = {
            "Best (4K - 2160p)": "2160",
            "2K (1440p)": "1440",
            "Full HD (1080p)": "1080",
            "HD (720p)": "720",
            "SD (480p)": "480",
            "Low (360p)": "360"
        }
        return quality_map[self.quality_combo.currentText()]

    def update_code(self):
        """Update the generated code display"""
        quality = self.get_quality_value()
        format_type = self.format_combo.currentText()
        audio_only = self.audio_only_check.isChecked()

        if audio_only:
            format_str = "bestaudio/best"
        else:
            format_str = f"bestvideo[height<={quality}]+bestaudio/best[height<={quality}]"

        code = f"""import yt_dlp

url = "YOUR_VIDEO_URL"

ydl_opts = {{
    'format': '{format_str}',
    'outtmpl': r'{self.path_input.text()}\\%(title)s.%(ext)s',
    'merge_output_format': '{format_type}',
    'ignoreerrors': {self.ignore_errors_check.isChecked()},
    'noprogress': False,
    'no_warnings': False,
    'quiet': False,
    'retries': {self.retries_spin.value()},
    'windowsfilenames': True,
    'postprocessors': [{{
        'key': '{'FFmpegExtractAudio' if audio_only else 'FFmpegVideoConvertor'}',
        '{'preferredcodec' if audio_only else 'preferedformat'}': '{format_type}',
    }}],
}}

with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    try:
        ydl.update()
    except Exception as e:
        print("Auto-update skipped:", e)
    ydl.download([url])
"""
        self.code_text.setText(code)

    def copy_code(self):
        """Copy generated code to clipboard"""
        clipboard = QApplication.clipboard()
        clipboard.setText(self.code_text.toPlainText())
        QMessageBox.information(self, "Success", "Code copied to clipboard!")

    def start_download(self):
        """Start the download process"""
        url = self.url_input.text().strip()

        if not url:
            QMessageBox.warning(self, "Error", "Please enter a valid URL!")
            return

        if self.download_thread and self.download_thread.isRunning():
            QMessageBox.warning(self, "Error", "A download is already in progress!")
            return

        # Prepare download options
        quality = self.get_quality_value()
        format_type = self.format_combo.currentText()
        audio_only = self.audio_only_check.isChecked()

        if audio_only:
            format_str = "bestaudio/best"
        else:
            format_str = f"bestvideo[height<={quality}]+bestaudio/best[height<={quality}]"

        postprocessors = []
        if audio_only:
            postprocessors.append({
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3' if format_type == 'mp3' else format_type,
                'preferredquality': '192',
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

        ydl_opts = {
            'format': format_str,
            'outtmpl': os.path.join(self.path_input.text(), '%(title)s.%(ext)s'),
            'merge_output_format': format_type,
            'ignoreerrors': self.ignore_errors_check.isChecked(),
            'noprogress': False,
            'no_warnings': False,
            'quiet': False,
            'retries': self.retries_spin.value(),
            'windowsfilenames': True,
            'postprocessors': postprocessors,
        }

        if self.embed_subs_check.isChecked():
            ydl_opts['writesubtitles'] = True
            ydl_opts['subtitleslangs'] = ['en']

        # Start download thread
        self.download_thread = DownloadThread(url, ydl_opts)
        self.download_thread.progress.connect(self.update_progress)
        self.download_thread.finished.connect(self.download_finished)
        self.download_thread.start()

        # Update UI
        self.download_btn.setEnabled(False)
        self.download_btn.setText("⏳ Downloading...")
        self.progress_bar.setValue(0)
        self.status_label.setText("Initializing download...")
        self.status_label.setStyleSheet("color: #89b4fa;")

    def update_progress(self, data):
        """Update progress bar and status"""
        if data['status'] == 'downloading':
            percent = int(data['percent'])
            self.progress_bar.setValue(percent)

            speed = data.get('speed', 0)
            eta = data.get('eta', 0)

            speed_str = f"{speed / 1024 / 1024:.2f} MB/s" if speed else "N/A"
            eta_str = f"{eta}s" if eta else "N/A"

            self.status_label.setText(f"Downloading: {percent}% | Speed: {speed_str} | ETA: {eta_str}")
        elif data['status'] == 'processing':
            self.progress_bar.setValue(100)
            self.status_label.setText("Processing video...")

    def download_finished(self, success, message):
        """Handle download completion"""
        self.download_btn.setEnabled(True)
        self.download_btn.setText("⬇ Download")

        if success:
            self.progress_bar.setValue(100)
            self.status_label.setText(message)
            self.status_label.setStyleSheet("color: #a6e3a1;")

            # Add to history
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            quality = self.quality_combo.currentText()
            format_type = self.format_combo.currentText().upper()
            history_entry = f"[{timestamp}] {self.url_input.text()} | {quality} | {format_type}"
            self.history_list.addItem(history_entry)
            self.download_history.append(history_entry)

            QMessageBox.information(self, "Success", message)
        else:
            self.progress_bar.setValue(0)
            self.status_label.setText("Download failed!")
            self.status_label.setStyleSheet("color: #f38ba8;")
            QMessageBox.critical(self, "Error", message)

    def clear_history(self):
        """Clear download history"""
        self.history_list.clear()
        self.download_history.clear()
        QMessageBox.information(self, "Success", "History cleared!")


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    window = VideoDownloaderApp()
    window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()