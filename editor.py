import os
import sys
import time
import subprocess
import imageio_ffmpeg
from pathlib import Path
from config import get_safe_default_save_dir
from PyQt6.QtCore import Qt, QUrl, QTime, QThread, pyqtSignal
from PyQt6.QtGui import QIcon, QFont, QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QFileDialog, QSlider, QGroupBox, QComboBox, QMessageBox, 
    QProgressBar, QSplitter
)
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget

class VideoExportThread(QThread):
    export_finished = pyqtSignal(str) # output filepath
    export_error = pyqtSignal(str)    # error message

    def __init__(self, cmd, output_path):
        super().__init__()
        self.cmd = cmd
        self.output_path = output_path

    def run(self):
        try:
            res = subprocess.run(
                self.cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=180,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            if res.returncode == 0 and os.path.exists(self.output_path) and os.path.getsize(self.output_path) > 0:
                self.export_finished.emit(self.output_path)
            else:
                err_msg = res.stderr.decode('utf-8', errors='ignore') if res.stderr else "未知錯誤"
                self.export_error.emit(f"FFmpeg 導出失敗 (代碼 {res.returncode}):\n{err_msg}")
        except subprocess.TimeoutExpired:
            self.export_error.emit("匯出逾時（超過 3 分鐘），已強制中止。")
        except Exception as e:
            self.export_error.emit(f"導出過程發生異常: {str(e)}")

class VideoEditorWidget(QWidget):
    def __init__(self, config):
        super().__init__()
        self.config = config
        self.ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        
        self.video_path = None
        self.duration_ms = 0
        self.start_ms = 0
        self.end_ms = 0
        self.export_thread = None

        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)

        self.init_ui()
        self.setup_connections()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # 1. Top File Selection Bar
        file_bar = QHBoxLayout()
        self.btn_open_file = QPushButton("📁 開啟影片檔案")
        self.btn_open_file.setFixedHeight(36)
        self.lbl_file_path = QLabel("尚未選擇影片檔")
        self.lbl_file_path.setStyleSheet("color: #AAA; font-style: italic;")
        file_bar.addWidget(self.btn_open_file)
        file_bar.addWidget(self.lbl_file_path, 1)
        layout.addLayout(file_bar)

        # 2. Video Player Display Area
        self.video_widget = QVideoWidget()
        self.video_widget.setStyleSheet("background-color: #000; border-radius: 8px;")
        self.video_widget.setMinimumHeight(100)
        self.player.setVideoOutput(self.video_widget)
        layout.addWidget(self.video_widget, 1)

        # 3. Playback Seek Bar & Time Display
        seek_layout = QHBoxLayout()
        self.btn_play_pause = QPushButton("▶ 播放")
        self.btn_play_pause.setFixedWidth(80)
        self.btn_play_pause.setEnabled(False)

        self.slider_seek = QSlider(Qt.Orientation.Horizontal)
        self.slider_seek.setRange(0, 0)
        self.slider_seek.setEnabled(False)

        self.lbl_time = QLabel("00:00:00 / 00:00:00")
        self.lbl_time.setFont(QFont("Consolas", 10))

        seek_layout.addWidget(self.btn_play_pause)
        seek_layout.addWidget(self.slider_seek, 1)
        seek_layout.addWidget(self.lbl_time)
        layout.addLayout(seek_layout)

        # 4. Trimming Control Group Box (掐頭去尾編輯器)
        trim_group = QGroupBox("✂ 掐頭去尾區段選擇")
        trim_layout = QVBoxLayout(trim_group)

        trim_btn_layout = QHBoxLayout()
        self.btn_set_start = QPushButton("[ 設為剪裁起點 (Start)")
        self.btn_set_start.setStyleSheet("background-color: #1b5e20; color: white;")
        self.btn_set_start.setEnabled(False)

        self.btn_set_end = QPushButton("] 設為剪裁終點 (End)")
        self.btn_set_end.setStyleSheet("background-color: #b71c1c; color: white;")
        self.btn_set_end.setEnabled(False)

        self.btn_reset_trim = QPushButton("🔄 重置範圍")
        self.btn_reset_trim.setEnabled(False)

        self.btn_preview_trim = QPushButton("👁 預覽剪裁區段")
        self.btn_preview_trim.setEnabled(False)

        trim_btn_layout.addWidget(self.btn_set_start)
        trim_btn_layout.addWidget(self.btn_set_end)
        trim_btn_layout.addWidget(self.btn_reset_trim)
        trim_btn_layout.addWidget(self.btn_preview_trim)
        trim_layout.addLayout(trim_btn_layout)

        # Trim Status Label
        self.lbl_trim_info = QLabel("尚未設定剪裁範圍 (預設保留整段影片)")
        self.lbl_trim_info.setStyleSheet("color: #00E676; font-weight: bold;")
        self.lbl_trim_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        trim_layout.addWidget(self.lbl_trim_info)

        layout.addWidget(trim_group)

        # 5. Export Controls
        export_layout = QHBoxLayout()
        
        self.combo_export_mode = QComboBox()
        self.combo_export_mode.addItems([
            "極速無損導出 (Stream Copy, 免重新編碼)",
            "重新編碼導出 (Re-encode with H.264/H.265)"
        ])
        self.combo_export_mode.setFixedHeight(38)

        self.btn_export = QPushButton("⚡ 立即極速匯出 (免選路徑，1秒完成)")
        self.btn_export.setFixedHeight(38)
        self.btn_export.setStyleSheet("background-color: #2E7D32; color: white; font-weight: bold; font-size: 13px; border-radius: 6px;")
        self.btn_export.setEnabled(False)

        self.btn_export_as = QPushButton("📁 另存新檔...")
        self.btn_export_as.setFixedHeight(38)
        self.btn_export_as.setStyleSheet("background-color: #0288D1; color: white; font-weight: bold; font-size: 13px; border-radius: 6px;")
        self.btn_export_as.setEnabled(False)

        export_layout.addWidget(QLabel("導出模式:"))
        export_layout.addWidget(self.combo_export_mode)
        export_layout.addWidget(self.btn_export, 2)
        export_layout.addWidget(self.btn_export_as, 1)
        layout.addLayout(export_layout)

    def setup_connections(self):
        self.btn_open_file.clicked.connect(self.choose_file)
        self.btn_play_pause.clicked.connect(self.toggle_play_pause)
        
        self.slider_seek.sliderMoved.connect(self.set_position)
        
        self.player.positionChanged.connect(self.on_position_changed)
        self.player.durationChanged.connect(self.on_duration_changed)

        self.btn_set_start.clicked.connect(self.set_start_point)
        self.btn_set_end.clicked.connect(self.set_end_point)
        self.btn_reset_trim.clicked.connect(self.reset_trim_points)
        self.btn_preview_trim.clicked.connect(self.preview_trim)
        self.btn_export.clicked.connect(self.export_quick)
        self.btn_export_as.clicked.connect(self.export_save_as)

    def load_video(self, file_path: str):
        if not os.path.exists(file_path):
            return
        self.video_path = file_path
        self.lbl_file_path.setText(os.path.basename(file_path))
        self.player.setSource(QUrl.fromLocalFile(file_path))
        
        self.btn_play_pause.setEnabled(True)
        self.slider_seek.setEnabled(True)
        self.btn_set_start.setEnabled(True)
        self.btn_set_end.setEnabled(True)
        self.btn_reset_trim.setEnabled(True)
        self.btn_preview_trim.setEnabled(True)
        self.btn_export.setEnabled(True)
        self.btn_export_as.setEnabled(True)

    def choose_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "開啟影片檔案", 
            get_safe_default_save_dir(), 
            "影片檔案 (*.mp4 *.mkv *.mov *.avi *.webm)",
            options=QFileDialog.Option.DontUseNativeDialog
        )
        if path:
            self.load_video(path)

    def toggle_play_pause(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            self.btn_play_pause.setText("▶ 播放")
        else:
            self.player.play()
            self.btn_play_pause.setText("⏸ 暫停")

    def set_position(self, position):
        self.player.setPosition(position)

    def on_position_changed(self, position):
        if not self.slider_seek.isSliderDown():
            self.slider_seek.setValue(position)
        self.update_time_label()

    def on_duration_changed(self, duration):
        self.duration_ms = duration
        self.slider_seek.setRange(0, duration)
        self.start_ms = 0
        self.end_ms = duration
        self.update_trim_info()
        self.update_time_label()

    def set_start_point(self):
        current_pos = self.player.position()
        if current_pos < self.end_ms:
            self.start_ms = current_pos
            self.update_trim_info()
        else:
            QMessageBox.warning(self, "警告", "剪裁起點不能大於或等於終點！")

    def set_end_point(self):
        current_pos = self.player.position()
        if current_pos > self.start_ms:
            self.end_ms = current_pos
            self.update_trim_info()
        else:
            QMessageBox.warning(self, "警告", "剪裁終點不能小於或等於起點！")

    def reset_trim_points(self):
        self.start_ms = 0
        self.end_ms = self.duration_ms
        self.update_trim_info()

    def preview_trim(self):
        self.player.setPosition(self.start_ms)
        self.player.play()
        self.btn_play_pause.setText("⏸ 暫停")

    def update_trim_info(self):
        start_str = self.format_time(self.start_ms)
        end_str = self.format_time(self.end_ms)
        trim_duration_str = self.format_time(max(0, self.end_ms - self.start_ms))
        
        self.lbl_trim_info.setText(
            f"✂ 保留區段：{start_str}  ➔  {end_str}  |  剪裁後總長度：{trim_duration_str}"
        )

    def update_time_label(self):
        current_str = self.format_time(self.player.position())
        duration_str = self.format_time(self.duration_ms)
        self.lbl_time.setText(f"{current_str} / {duration_str}")

    @staticmethod
    def format_time(ms: int) -> str:
        seconds = (ms // 1000) % 60
        minutes = (ms // (1000 * 60)) % 60
        hours = (ms // (1000 * 60 * 60))
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def export_quick(self):
        """Instant export directly to safe recordings directory without any blocking dialogs."""
        if not self._check_valid_trim():
            return

        safe_dir = get_safe_default_save_dir()
        src_name = os.path.splitext(os.path.basename(self.video_path))[0]
        timestamp = time.strftime("%H%M%S")
        candidate = os.path.join(safe_dir, f"{src_name}_trimmed.mp4")
        if os.path.exists(candidate):
            candidate = os.path.join(safe_dir, f"{src_name}_trimmed_{timestamp}.mp4")

        self._start_export_thread(candidate)

    def export_save_as(self):
        """Allows user to select custom file location using safe non-native Qt dialog."""
        if not self._check_valid_trim():
            return

        safe_dir = get_safe_default_save_dir()
        src_name = os.path.splitext(os.path.basename(self.video_path))[0]
        default_output = os.path.join(safe_dir, f"{src_name}_trimmed.mp4")

        # Explicitly use DontUseNativeDialog to bypass Windows shell/COM lockups
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "另存剪裁後的影片",
            default_output,
            "MP4 影片 (*.mp4)",
            options=QFileDialog.Option.DontUseNativeDialog
        )
        if not save_path:
            return

        if os.path.abspath(save_path) == os.path.abspath(self.video_path):
            QMessageBox.warning(self, "錯誤", "匯出目標不能覆蓋正在編輯的原始檔案！請指定新的檔名。")
            return

        self._start_export_thread(save_path)

    def _check_valid_trim(self) -> bool:
        if not self.video_path or not os.path.exists(self.video_path):
            QMessageBox.warning(self, "錯誤", "找不到來源影片檔案！")
            return False

        if self.start_ms >= self.end_ms:
            QMessageBox.warning(self, "錯誤", "剪裁區段不合法！起點必須小於終點。")
            return False

        # Pause playback to release any locks
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            self.btn_play_pause.setText("▶ 播放")

        return True

    def _start_export_thread(self, save_path: str):
        # Guard: test directory write permission
        target_dir = os.path.dirname(os.path.abspath(save_path))
        try:
            os.makedirs(target_dir, exist_ok=True)
            test_probe = os.path.join(target_dir, ".write_probe")
            with open(test_probe, "w") as f:
                f.write("ok")
            os.remove(test_probe)
        except Exception as e:
            QMessageBox.critical(self, "目錄存取錯誤", f"無法寫入選擇的資料夾（存取權限受限）:\n{e}\n請更換至其他資料夾。")
            return

        start_sec = self.start_ms / 1000.0
        end_sec = self.end_ms / 1000.0

        mode = self.combo_export_mode.currentIndex()

        cmd = [self.ffmpeg_exe, "-y", "-ss", f"{start_sec:.3f}", "-to", f"{end_sec:.3f}", "-i", self.video_path]

        if mode == 0:
            # Stream Copy (Lossless fast cut)
            cmd.extend(["-c", "copy", "-avoid_negative_ts", "make_zero"])
        else:
            # Re-encode
            v_codec = self.config.get("video_codec", "libx264")
            a_codec = self.config.get("audio_codec", "aac")
            crf = self.config.get("crf", 23)
            cmd.extend(["-c:v", v_codec, "-preset", "veryfast", "-crf", str(crf), "-c:a", a_codec, "-b:a", "192k"])

        cmd.append(save_path)

        # UI state: Non-blocking asynchronous background execution
        self.btn_export.setEnabled(False)
        self.btn_export_as.setEnabled(False)
        self.btn_export.setText("⏳ 正在匯出中，請稍候...")
        self.btn_export.setStyleSheet("background-color: #FF9800; color: white; font-weight: bold; font-size: 13px; border-radius: 6px;")

        self.export_thread = VideoExportThread(cmd, save_path)
        self.export_thread.export_finished.connect(self.on_export_finished)
        self.export_thread.export_error.connect(self.on_export_error)
        self.export_thread.start()

    def on_export_finished(self, save_path):
        self.reset_export_btn()
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("匯出成功")
        msg_box.setIcon(QMessageBox.Icon.Information)
        msg_box.setText(f"🎉 掐頭去尾影片已成功匯出！\n\n路徑：\n{save_path}")
        btn_folder = msg_box.addButton("📂 開啟所在資料夾", QMessageBox.ButtonRole.ActionRole)
        msg_box.addButton("確定", QMessageBox.ButtonRole.AcceptRole)
        msg_box.exec()
        if msg_box.clickedButton() == btn_folder:
            try:
                subprocess.Popen(f'explorer /select,"{os.path.abspath(save_path)}"', shell=True)
            except Exception:
                pass

    def on_export_error(self, err_msg):
        self.reset_export_btn()
        QMessageBox.critical(self, "匯出失敗", err_msg)

    def reset_export_btn(self):
        self.btn_export.setEnabled(True)
        self.btn_export_as.setEnabled(True)
        self.btn_export.setText("⚡ 立即極速匯出 (免選路徑，1秒完成)")
        self.btn_export.setStyleSheet("background-color: #2E7D32; color: white; font-weight: bold; font-size: 13px; border-radius: 6px;")
        self.btn_export_as.setText("📁 另存新檔...")
        self.btn_export_as.setStyleSheet("background-color: #0288D1; color: white; font-weight: bold; font-size: 13px; border-radius: 6px;")
