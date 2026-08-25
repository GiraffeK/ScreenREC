import os
import sys
from pathlib import Path
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QIcon
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QPushButton, QLabel, QComboBox, QSpinBox, QSlider, QCheckBox,
    QGroupBox, QFileDialog, QLineEdit, QMessageBox, QFrame, QStyle,
    QScrollArea
)

from config import ConfigManager
from area_selector import AreaSelectorOverlay
from recorder import ScreenRecorderThread, detect_available_hw_encoders
from editor import VideoEditorWidget

DARK_STYLESHEET = """
QMainWindow {
    background-color: #121212;
    color: #E0E0E0;
}
QWidget {
    font-family: 'Segoe UI', 'Microsoft JhengHei', sans-serif;
    color: #E0E0E0;
}
QTabWidget::pane {
    border: 1px solid #2C2C2C;
    background-color: #1E1E1E;
    border-radius: 6px;
}
QTabBar::tab {
    background-color: #2D2D2D;
    color: #AAA;
    padding: 8px 16px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    font-weight: bold;
}
QTabBar::tab:selected {
    background-color: #0288D1;
    color: #FFF;
}
QGroupBox {
    border: 1px solid #333;
    border-radius: 6px;
    margin-top: 12px;
    font-weight: bold;
    color: #00E676;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
}
QPushButton {
    background-color: #2979FF;
    color: white;
    border: none;
    border-radius: 4px;
    padding: 6px 12px;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #2962FF;
}
QPushButton:disabled {
    background-color: #424242;
    color: #757575;
}
QComboBox, QSpinBox, QLineEdit {
    background-color: #2C2C2C;
    border: 1px solid #444;
    border-radius: 4px;
    color: #FFF;
    padding: 6px;
}
QComboBox QAbstractItemView {
    background-color: #1E1E1E;
    color: #FFFFFF;
    selection-background-color: #0288D1;
    selection-color: #FFFFFF;
    border: 1px solid #0288D1;
    outline: none;
    padding: 4px;
}
QComboBox QAbstractItemView::item {
    min-height: 28px;
    padding: 4px 8px;
    background-color: #1E1E1E;
    color: #FFFFFF;
}
QComboBox QAbstractItemView::item:selected, QComboBox QAbstractItemView::item:hover {
    background-color: #0288D1;
    color: #FFFFFF;
}
QSlider::groove:horizontal {
    border: 1px solid #444;
    height: 6px;
    background: #2C2C2C;
    border-radius: 3px;
}
QSlider::sub-page:horizontal {
    background: #0288D1;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background: #00E676;
    width: 16px;
    margin-top: -5px;
    margin-bottom: -5px;
    border-radius: 8px;
}
QScrollArea {
    border: none;
    background-color: transparent;
}
"""

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Screen Recorder & Video Trimmer 螢幕錄影與影片剪輯器")
        self.resize(850, 680)
        self.setMinimumSize(360, 260)
        self.setStyleSheet(DARK_STYLESHEET)

        self.config = ConfigManager()
        self.recorder_thread = None
        self.available_encoders = []

        self.init_ui()
        self.detect_encoders()
        self.load_config_to_ui()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Tab Widget
        self.tabs = QTabWidget()
        
        # Tab 1: REC Control
        rec_content = QWidget()
        self.setup_rec_tab(rec_content)
        scroll_rec = QScrollArea()
        scroll_rec.setWidgetResizable(True)
        scroll_rec.setWidget(rec_content)

        # Tab 2: Settings
        settings_content = QWidget()
        self.setup_settings_tab(settings_content)
        scroll_settings = QScrollArea()
        scroll_settings.setWidgetResizable(True)
        scroll_settings.setWidget(settings_content)

        # Tab 3: Video Editor
        self.editor_widget = VideoEditorWidget(self.config)

        self.tabs.addTab(scroll_rec, "🔴 螢幕錄影主頁")
        self.tabs.addTab(scroll_settings, "⚙ 畫質與硬體加速設定")
        self.tabs.addTab(self.editor_widget, "✂ 影片掐頭去尾編輯器")

        main_layout.addWidget(self.tabs)

    def detect_encoders(self):
        self.available_encoders = detect_available_hw_encoders()
        self.combo_vcodec.clear()
        for codec_id, display_name in self.available_encoders:
            self.combo_vcodec.addItem(display_name, userData=codec_id)

    def setup_rec_tab(self, parent_widget):
        layout = QVBoxLayout(parent_widget)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Region Selection Box
        region_group = QGroupBox("📍 錄影範圍設定 (REC Region)")
        region_layout = QVBoxLayout(region_group)

        mode_layout = QHBoxLayout()
        self.combo_mode = QComboBox()
        self.combo_mode.addItems(["全螢幕錄影 (Full Screen)", "自訂區域錄影 (Custom Region)"])
        self.combo_mode.currentIndexChanged.connect(self.on_mode_changed)

        self.btn_select_area = QPushButton("🎯 畫面上拖曳與四角縮放選擇錄影區域")
        self.btn_select_area.setStyleSheet("background-color: #00897B; color: white;")
        self.btn_select_area.setEnabled(False)
        self.btn_select_area.clicked.connect(self.start_area_selection)

        mode_layout.addWidget(QLabel("錄影模式:"))
        mode_layout.addWidget(self.combo_mode, 1)
        mode_layout.addWidget(self.btn_select_area)
        region_layout.addLayout(mode_layout)

        # Region Coordinate Info
        self.lbl_region_info = QLabel("座標區域: 全螢幕")
        self.lbl_region_info.setStyleSheet("color: #00E676; font-size: 13px; font-weight: bold;")
        region_layout.addWidget(self.lbl_region_info)

        layout.addWidget(region_group)

        # Status Display Box
        status_group = QGroupBox("📊 錄影狀態")
        status_layout = QVBoxLayout(status_group)

        self.lbl_status = QLabel("就緒 (Ready)")
        self.lbl_status.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_status.setStyleSheet("color: #4FC3F7; margin: 15px;")
        status_layout.addWidget(self.lbl_status)

        layout.addWidget(status_group)

        # Record Action Buttons
        btn_layout = QHBoxLayout()
        self.btn_start = QPushButton("🔴 開始錄影 (REC)")
        self.btn_start.setFixedHeight(48)
        self.btn_start.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        self.btn_start.setStyleSheet("background-color: #D32F2F; color: white; border-radius: 6px;")

        self.btn_pause = QPushButton("⏸ 暫停")
        self.btn_pause.setFixedHeight(48)
        self.btn_pause.setFont(QFont("Segoe UI", 11))
        self.btn_pause.setEnabled(False)

        self.btn_stop = QPushButton("⏹ 停止錄影並儲存")
        self.btn_stop.setFixedHeight(48)
        self.btn_stop.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        self.btn_stop.setStyleSheet("background-color: #388E3C; color: white; border-radius: 6px;")
        self.btn_stop.setEnabled(False)

        btn_layout.addWidget(self.btn_start, 2)
        btn_layout.addWidget(self.btn_pause, 1)
        btn_layout.addWidget(self.btn_stop, 2)
        layout.addLayout(btn_layout)

        # Options
        self.chk_auto_minimize = QCheckBox("開始錄影時自動最小化視窗 (Minimize window on REC)")
        self.chk_auto_minimize.setChecked(True)
        self.chk_auto_minimize.toggled.connect(lambda v: self.config.set("auto_minimize_on_rec", v))
        layout.addWidget(self.chk_auto_minimize)

        self.chk_auto_editor = QCheckBox("錄影結束後自動進入影片掐頭去尾編輯器 (Auto Open Trimmer)")
        self.chk_auto_editor.setChecked(True)
        self.chk_auto_editor.toggled.connect(lambda v: self.config.set("auto_open_editor", v))
        layout.addWidget(self.chk_auto_editor)

        layout.addStretch(1)

        self.btn_start.clicked.connect(self.start_recording)
        self.btn_pause.clicked.connect(self.toggle_pause)
        self.btn_stop.clicked.connect(self.stop_recording)

    def setup_settings_tab(self, parent_widget):
        layout = QVBoxLayout(parent_widget)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # 1. Video Settings Group
        v_group = QGroupBox("🎬 影片編碼與 GPU 硬體加速設定 (Video & HW Acceleration)")
        v_layout = QVBoxLayout(v_group)

        codec_layout = QHBoxLayout()
        self.combo_vcodec = QComboBox()
        codec_layout.addWidget(QLabel("影片編碼器 (可選 GPU 硬體加速):"))
        codec_layout.addWidget(self.combo_vcodec, 1)
        v_layout.addLayout(codec_layout)

        # Quality Mode & Bitrate/CRF
        crf_layout = QHBoxLayout()
        self.combo_qmode = QComboBox()
        self.combo_qmode.addItems(["CRF (品質優先)", "Bitrate (指定位元率)"])
        self.combo_qmode.currentIndexChanged.connect(self.on_qmode_changed)

        self.lbl_crf_val = QLabel("CRF: 23")
        self.slider_crf = QSlider(Qt.Orientation.Horizontal)
        self.slider_crf.setRange(18, 28)
        self.slider_crf.setValue(23)
        self.slider_crf.valueChanged.connect(lambda v: self.lbl_crf_val.setText(f"CRF: {v} (越小畫質越高)"))

        crf_layout.addWidget(QLabel("品質控制:"))
        crf_layout.addWidget(self.combo_qmode)
        crf_layout.addWidget(self.slider_crf, 1)
        crf_layout.addWidget(self.lbl_crf_val)
        v_layout.addLayout(crf_layout)

        # Bitrate & FPS
        bitrate_layout = QHBoxLayout()
        self.spin_vbitrate = QSpinBox()
        self.spin_vbitrate.setRange(1000, 25000)
        self.spin_vbitrate.setSingleStep(500)
        self.spin_vbitrate.setSuffix(" kbps")
        self.spin_vbitrate.setValue(6000)

        self.spin_fps = QSpinBox()
        self.spin_fps.setRange(15, 60)
        self.spin_fps.setValue(30)
        self.spin_fps.setSuffix(" FPS")

        bitrate_layout.addWidget(QLabel("目標位元率:"))
        bitrate_layout.addWidget(self.spin_vbitrate)
        bitrate_layout.addWidget(QLabel("  錄製幀率 (FPS):"))
        bitrate_layout.addWidget(self.spin_fps)
        v_layout.addLayout(bitrate_layout)

        layout.addWidget(v_group)

        # 2. Audio Settings Group
        a_group = QGroupBox("🎵 音訊品質與來源設定 (WASAPI System Audio Loopback)")
        a_layout = QVBoxLayout(a_group)

        self.chk_audio_enable = QCheckBox("啟用音訊錄製 (Enable Audio Recording)")
        self.chk_audio_enable.setChecked(True)
        a_layout.addWidget(self.chk_audio_enable)

        source_layout = QHBoxLayout()
        self.combo_audio_source = QComboBox()
        self.combo_audio_source.addItem("🖥 系統聲音 (自動跟隨 Windows 當前播放裝置: 藍牙/USB/喇叭)", userData="system")
        self.combo_audio_source.addItem("🎙 麥克風 (Microphone)", userData="mic")
        self.combo_audio_source.addItem("🎛 系統聲音 + 麥克風 (System + Mic)", userData="mix")
        self.combo_audio_source.addItem("🔇 靜音 (Mute)", userData="mute")

        source_layout.addWidget(QLabel("音訊來源:"))
        source_layout.addWidget(self.combo_audio_source, 1)
        a_layout.addLayout(source_layout)

        audio_fmt_layout = QHBoxLayout()
        self.combo_acodec = QComboBox()
        self.combo_acodec.addItems(["AAC (標準品質)", "MP3 (libmp3lame)"])
        
        self.combo_abitrate = QComboBox()
        self.combo_abitrate.addItems(["128 kbps", "192 kbps (推薦)", "256 kbps", "320 kbps (最高)"])
        self.combo_abitrate.setCurrentIndex(1)

        self.combo_sample_rate = QComboBox()
        self.combo_sample_rate.addItems(["44100 Hz (44.1 kHz)", "48000 Hz (48 kHz)"])

        audio_fmt_layout.addWidget(QLabel("音訊編碼:"))
        audio_fmt_layout.addWidget(self.combo_acodec)
        audio_fmt_layout.addWidget(QLabel("音訊 Bitrate:"))
        audio_fmt_layout.addWidget(self.combo_abitrate)
        audio_fmt_layout.addWidget(QLabel("採樣率:"))
        audio_fmt_layout.addWidget(self.combo_sample_rate)
        a_layout.addLayout(audio_fmt_layout)

        layout.addWidget(a_group)

        # 3. Path & File Name Settings Group
        p_group = QGroupBox("📁 預設儲存位置與檔名設定 (Save Directory & Filename)")
        p_layout = QVBoxLayout(p_group)

        dir_layout = QHBoxLayout()
        self.txt_save_dir = QLineEdit()
        self.btn_browse_dir = QPushButton("📂 瀏覽...")
        self.btn_browse_dir.clicked.connect(self.browse_save_directory)
        dir_layout.addWidget(self.txt_save_dir, 1)
        dir_layout.addWidget(self.btn_browse_dir)
        p_layout.addLayout(dir_layout)

        filename_layout = QHBoxLayout()
        self.txt_filename_pattern = QLineEdit()
        filename_layout.addWidget(QLabel("檔名範本:"))
        filename_layout.addWidget(self.txt_filename_pattern, 1)
        p_layout.addLayout(filename_layout)

        lbl_tip = QLabel("提示：檔名範本可用標籤 {date} (年月日) 與 {time} (時分秒)，例如 REC_{date}_{time}.mp4")
        lbl_tip.setStyleSheet("color: #888; font-size: 11px;")
        p_layout.addWidget(lbl_tip)

        layout.addWidget(p_group)

        # Save Settings Button
        self.btn_save_settings = QPushButton("💾 儲存所有設定 (Save Settings)")
        self.btn_save_settings.setFixedHeight(38)
        self.btn_save_settings.setStyleSheet("background-color: #0288D1; font-size: 14px; font-weight: bold;")
        self.btn_save_settings.clicked.connect(self.save_settings_from_ui)
        layout.addWidget(self.btn_save_settings)

    def load_config_to_ui(self):
        mode = self.config.get("record_mode", "fullscreen")
        self.combo_mode.setCurrentIndex(0 if mode == "fullscreen" else 1)
        self.on_mode_changed(self.combo_mode.currentIndex())

        saved_vcodec = self.config.get("video_codec", "libx264")
        found_idx = 0
        for i in range(self.combo_vcodec.count()):
            if self.combo_vcodec.itemData(i) == saved_vcodec:
                found_idx = i
                break
        self.combo_vcodec.setCurrentIndex(found_idx)

        qmode = self.config.get("quality_mode", "crf")
        self.combo_qmode.setCurrentIndex(0 if qmode == "crf" else 1)
        self.on_qmode_changed(self.combo_qmode.currentIndex())

        self.slider_crf.setValue(int(self.config.get("crf", 23)))
        self.spin_vbitrate.setValue(int(self.config.get("video_bitrate_kbps", 6000)))
        self.spin_fps.setValue(int(self.config.get("fps", 30)))

        # Audio
        self.chk_audio_enable.setChecked(bool(self.config.get("audio_enabled", True)))
        
        audio_src = self.config.get("audio_source", "system")
        found_src_idx = 0
        for i in range(self.combo_audio_source.count()):
            if self.combo_audio_source.itemData(i) == audio_src:
                found_src_idx = i
                break
        self.combo_audio_source.setCurrentIndex(found_src_idx)

        acodec = self.config.get("audio_codec", "aac")
        self.combo_acodec.setCurrentIndex(0 if acodec == "aac" else 1)
        
        abitrate = self.config.get("audio_bitrate_kbps", 192)
        abitrate_map = {128: 0, 192: 1, 256: 2, 320: 3}
        self.combo_abitrate.setCurrentIndex(abitrate_map.get(abitrate, 1))

        srate = self.config.get("audio_sample_rate", 44100)
        self.combo_sample_rate.setCurrentIndex(0 if srate == 44100 else 1)

        # Path & Options
        self.txt_save_dir.setText(self.config.get("save_dir"))
        self.txt_filename_pattern.setText(self.config.get("filename_pattern"))
        self.chk_auto_minimize.setChecked(bool(self.config.get("auto_minimize_on_rec", True)))
        self.chk_auto_editor.setChecked(bool(self.config.get("auto_open_editor", True)))

        self.update_region_info_label()

    def save_settings_from_ui(self):
        selected_vcodec = self.combo_vcodec.currentData() or "libx264"
        self.config.set("video_codec", selected_vcodec)
        self.config.set("quality_mode", "crf" if self.combo_qmode.currentIndex() == 0 else "bitrate")
        self.config.set("crf", self.slider_crf.value())
        self.config.set("video_bitrate_kbps", self.spin_vbitrate.value())
        self.config.set("fps", self.spin_fps.value())

        self.config.set("audio_enabled", self.chk_audio_enable.isChecked())
        self.config.set("audio_source", self.combo_audio_source.currentData() or "system")
        self.config.set("audio_codec", "aac" if self.combo_acodec.currentIndex() == 0 else "libmp3lame")
        
        abitrate_vals = [128, 192, 256, 320]
        self.config.set("audio_bitrate_kbps", abitrate_vals[self.combo_abitrate.currentIndex()])
        self.config.set("audio_sample_rate", 44100 if self.combo_sample_rate.currentIndex() == 0 else 48000)

        self.config.set("save_dir", self.txt_save_dir.text().strip())
        self.config.set("filename_pattern", self.txt_filename_pattern.text().strip())

        QMessageBox.information(self, "成功", "所有設定已成功儲存！")

    def on_mode_changed(self, index):
        if index == 0:
            self.config.set("record_mode", "fullscreen")
            self.btn_select_area.setEnabled(False)
        else:
            self.config.set("record_mode", "region")
            self.btn_select_area.setEnabled(True)
        self.update_region_info_label()

    def on_qmode_changed(self, index):
        if index == 0:
            self.slider_crf.setEnabled(True)
            self.spin_vbitrate.setEnabled(False)
        else:
            self.slider_crf.setEnabled(False)
            self.spin_vbitrate.setEnabled(True)

    def start_area_selection(self):
        self.overlay = AreaSelectorOverlay()
        self.overlay.area_selected.connect(self.on_area_selected)
        self.overlay.start_rec_requested.connect(self.on_area_start_rec)
        self.overlay.show()

    def on_area_selected(self, x, y, w, h):
        self.config.set("region_x", x)
        self.config.set("region_y", y)
        self.config.set("region_width", w)
        self.config.set("region_height", h)
        self.update_region_info_label()

    def on_area_start_rec(self, x, y, w, h):
        self.on_area_selected(x, y, w, h)
        self.start_recording()

    def update_region_info_label(self):
        mode = self.config.get("record_mode", "fullscreen")
        if mode == "fullscreen":
            self.lbl_region_info.setText("座標區域: 🖥 全螢幕錄製 (Full Screen)")
        else:
            rx = self.config.get("region_x")
            ry = self.config.get("region_y")
            rw = self.config.get("region_width")
            rh = self.config.get("region_height")
            self.lbl_region_info.setText(f"座標區域: 🎯 X:{rx}, Y:{ry} | 寬:{rw}px, 高:{rh}px")

    def browse_save_directory(self):
        dir_path = QFileDialog.getExistingDirectory(self, "選擇預設儲存目錄", self.txt_save_dir.text())
        if dir_path:
            self.txt_save_dir.setText(dir_path)

    def start_recording(self):
        self.btn_start.setEnabled(False)
        self.btn_pause.setEnabled(True)
        self.btn_stop.setEnabled(True)
        self.combo_mode.setEnabled(False)
        self.btn_select_area.setEnabled(False)

        self.lbl_status.setText("🔴 錄影中 00:00:00")
        self.lbl_status.setStyleSheet("color: #FF5252; margin: 15px;")

        self.recorder_thread = ScreenRecorderThread(self.config)
        self.recorder_thread.duration_updated.connect(self.on_duration_update)
        self.recorder_thread.recording_stopped.connect(self.on_recording_stopped)
        self.recorder_thread.recording_error.connect(self.on_recording_error)
        self.recorder_thread.start()

        # Minimize main window automatically if option is checked
        if self.config.get("auto_minimize_on_rec", True):
            self.showMinimized()

    def toggle_pause(self):
        if not self.recorder_thread:
            return
        if self.recorder_thread.is_paused:
            self.recorder_thread.resume()
            self.btn_pause.setText("⏸ 暫停")
            self.lbl_status.setStyleSheet("color: #FF5252; margin: 15px;")
        else:
            self.recorder_thread.pause()
            self.btn_pause.setText("▶ 繼續錄影")
            self.lbl_status.setText("⏸ 已暫停錄影")
            self.lbl_status.setStyleSheet("color: #FFC107; margin: 15px;")

    def stop_recording(self):
        if self.recorder_thread:
            self.lbl_status.setText("⏳ 正在停止錄影並合併影音檔案，請稍候...")
            self.lbl_status.setStyleSheet("color: #FF9800; margin: 15px;")
            self.btn_pause.setEnabled(False)
            self.btn_stop.setEnabled(False)
            self.recorder_thread.stop()

    def on_duration_update(self, seconds):
        mins = seconds // 60
        secs = seconds % 60
        hrs = mins // 60
        mins = mins % 60
        self.lbl_status.setText(f"🔴 錄影中 {hrs:02d}:{mins:02d}:{secs:02d}")

    def on_recording_stopped(self, filepath):
        # Restore window if minimized
        self.showNormal()
        self.activateWindow()

        self.btn_start.setEnabled(True)
        self.btn_pause.setEnabled(False)
        self.btn_pause.setText("⏸ 暫停")
        self.btn_stop.setEnabled(False)
        self.combo_mode.setEnabled(True)
        if self.combo_mode.currentIndex() == 1:
            self.btn_select_area.setEnabled(True)

        self.lbl_status.setText("✅ 錄影完成！檔案已儲存")
        self.lbl_status.setStyleSheet("color: #4CAF50; margin: 15px;")

        if self.config.get("auto_open_editor", True):
            self.editor_widget.load_video(filepath)
            self.tabs.setCurrentIndex(2)
        else:
            QMessageBox.information(
                self, "錄影完成", 
                f"螢幕錄影已順利儲存至:\n{filepath}"
            )

    def on_recording_error(self, err_msg):
        # Restore window if minimized
        self.showNormal()
        self.activateWindow()

        self.btn_start.setEnabled(True)
        self.btn_pause.setEnabled(False)
        self.btn_stop.setEnabled(False)
        self.combo_mode.setEnabled(True)

        self.lbl_status.setText("❌ 錄影發生錯誤")
        self.lbl_status.setStyleSheet("color: #F44336; margin: 15px;")
        QMessageBox.critical(self, "錄影錯誤", err_msg)
