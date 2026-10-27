import os
import sys
from pathlib import Path
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QIcon, QGuiApplication
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
    color: #FFFFFF;
}
QWidget {
    font-family: 'Segoe UI', 'Microsoft JhengHei', sans-serif;
    color: #FFFFFF;
    background-color: transparent;
}
QLabel {
    color: #FFFFFF;
    font-size: 11px;
}
QTabWidget::pane {
    border: 1px solid #333333;
    background-color: #1E1E1E;
    border-radius: 4px;
}
QTabBar::tab {
    background-color: #2D2D2D;
    color: #CCCCCC;
    padding: 5px 12px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    font-weight: bold;
    font-size: 11px;
    margin-right: 2px;
}
QTabBar::tab:selected {
    background-color: #0288D1;
    color: #FFFFFF;
}
QTabBar::tab:hover {
    background-color: #383838;
    color: #FFFFFF;
}
QGroupBox {
    border: 1px solid #383838;
    border-radius: 5px;
    margin-top: 10px;
    font-weight: bold;
    font-size: 11px;
    color: #00E676;
    padding-top: 6px;
    background-color: #1A1A1A;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
    background-color: #1A1A1A;
}
QPushButton {
    background-color: #1976D2;
    color: #FFFFFF;
    border: none;
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 11px;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #2196F3;
}
QPushButton:pressed {
    background-color: #0D47A1;
}
QPushButton:disabled {
    background-color: #333333;
    color: #666666;
}
QComboBox, QSpinBox, QLineEdit {
    background-color: #262626;
    border: 1px solid #4FC3F7;
    border-radius: 4px;
    color: #FFFFFF;
    padding: 3px 6px;
    font-size: 11px;
    min-height: 22px;
}
QComboBox:focus, QSpinBox:focus, QLineEdit:focus {
    border: 1px solid #00E676;
    background-color: #2E2E2E;
}
QComboBox QAbstractItemView {
    background-color: #1E1E1E;
    color: #FFFFFF;
    selection-background-color: #0288D1;
    selection-color: #FFFFFF;
    border: 1px solid #0288D1;
    outline: none;
    padding: 2px;
}
QComboBox QAbstractItemView::item {
    min-height: 24px;
    padding: 3px 6px;
    background-color: #1E1E1E;
    color: #FFFFFF;
}
QComboBox QAbstractItemView::item:selected, QComboBox QAbstractItemView::item:hover {
    background-color: #0288D1;
    color: #FFFFFF;
}
QCheckBox {
    color: #FFFFFF;
    font-size: 11px;
    spacing: 6px;
}
QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border: 1px solid #4FC3F7;
    border-radius: 3px;
    background-color: #262626;
}
QCheckBox::indicator:checked {
    background-color: #0288D1;
    border: 1px solid #00E676;
}
QSlider::groove:horizontal {
    border: 1px solid #444;
    height: 5px;
    background: #2C2C2C;
    border-radius: 2px;
}
QSlider::sub-page:horizontal {
    background: #0288D1;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: #00E676;
    width: 14px;
    margin-top: -5px;
    margin-bottom: -5px;
    border-radius: 7px;
}
QScrollArea {
    border: none;
    background-color: transparent;
}
QScrollBar:vertical {
    border: none;
    background: #1A1A1A;
    width: 8px;
    margin: 0px;
}
QScrollBar::handle:vertical {
    background: #444444;
    min-height: 20px;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover {
    background: #0288D1;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
"""

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Screen Recorder 螢幕錄影")
        self.resize(420, 320)
        self.setMinimumSize(320, 180)
        self.setStyleSheet(DARK_STYLESHEET)

        self.config = ConfigManager()
        self.recorder_thread = None
        self.available_encoders = []
        self.is_mini_mode = False

        self.init_ui()
        self.detect_encoders()
        self.load_config_to_ui()

    def init_ui(self):
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_root_layout = QVBoxLayout(self.central_widget)
        self.main_root_layout.setContentsMargins(0, 0, 0, 0)
        self.main_root_layout.setSpacing(0)

        # 1. Normal View Container (Tabs)
        self.normal_view = QWidget()
        normal_layout = QVBoxLayout(self.normal_view)
        normal_layout.setContentsMargins(4, 4, 4, 4)
        normal_layout.setSpacing(4)

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

        self.tabs.addTab(scroll_rec, "🔴 螢幕錄影")
        self.tabs.addTab(scroll_settings, "⚙ 畫質設定")
        self.tabs.addTab(self.editor_widget, "✂ 影片剪輯")

        normal_layout.addWidget(self.tabs)
        self.main_root_layout.addWidget(self.normal_view)

        # 2. Mini Floating Bar Container
        self.mini_view = QWidget()
        mini_layout = QHBoxLayout(self.mini_view)
        mini_layout.setContentsMargins(6, 4, 6, 4)
        mini_layout.setSpacing(6)

        self.mini_lbl_status = QLabel("就緒 (Ready)")
        self.mini_lbl_status.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.mini_lbl_status.setStyleSheet("color: #4FC3F7; min-width: 85px;")

        self.mini_btn_start = QPushButton("🔴 REC")
        self.mini_btn_start.setFixedHeight(28)
        self.mini_btn_start.setStyleSheet("background-color: #D32F2F; color: white; padding: 2px 8px;")
        self.mini_btn_start.clicked.connect(self.start_recording)

        self.mini_btn_pause = QPushButton("⏸")
        self.mini_btn_pause.setFixedSize(30, 28)
        self.mini_btn_pause.setEnabled(False)
        self.mini_btn_pause.clicked.connect(self.toggle_pause)

        self.mini_btn_stop = QPushButton("⏹")
        self.mini_btn_stop.setFixedSize(30, 28)
        self.mini_btn_stop.setStyleSheet("background-color: #388E3C; color: white;")
        self.mini_btn_stop.setEnabled(False)
        self.mini_btn_stop.clicked.connect(self.stop_recording)

        self.btn_expand = QPushButton("🗖 展開")
        self.btn_expand.setFixedHeight(28)
        self.btn_expand.setStyleSheet("background-color: #0288D1; color: white; padding: 2px 8px;")
        self.btn_expand.clicked.connect(self.toggle_mini_mode)

        mini_layout.addWidget(self.mini_lbl_status)
        mini_layout.addWidget(self.mini_btn_start)
        mini_layout.addWidget(self.mini_btn_pause)
        mini_layout.addWidget(self.mini_btn_stop)
        mini_layout.addWidget(self.btn_expand)

        self.main_root_layout.addWidget(self.mini_view)
        self.mini_view.hide()

    def toggle_mini_mode(self):
        if not self.is_mini_mode:
            self.is_mini_mode = True
            self.normal_view.hide()
            self.mini_view.show()
            self.setWindowTitle("ScreenRecorder (懸浮條)")
            self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
            self.setMinimumSize(280, 40)
            self.resize(340, 48)
            self.show()
        else:
            self.is_mini_mode = False
            self.mini_view.hide()
            self.normal_view.show()
            self.setWindowTitle("Screen Recorder 螢幕錄影")
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowStaysOnTopHint)
            self.setMinimumSize(320, 180)
            self.resize(420, 320)
            self.show()

    def detect_encoders(self):
        self.available_encoders = detect_available_hw_encoders()
        self.combo_vcodec.clear()
        for codec_id, display_name in self.available_encoders:
            self.combo_vcodec.addItem(display_name, userData=codec_id)

    def setup_rec_tab(self, parent_widget):
        layout = QVBoxLayout(parent_widget)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Region Selection Box
        region_group = QGroupBox("📍 錄影範圍設定 (REC Region)")
        region_layout = QVBoxLayout(region_group)
        region_layout.setContentsMargins(6, 6, 6, 6)
        region_layout.setSpacing(4)

        mode_layout = QHBoxLayout()
        self.combo_mode = QComboBox()
        self.populate_record_modes()
        self.combo_mode.currentIndexChanged.connect(self.on_mode_changed)

        self.btn_select_area = QPushButton("🎯 畫面選取區域")
        self.btn_select_area.setStyleSheet("background-color: #00897B; color: white;")
        self.btn_select_area.setEnabled(False)
        self.btn_select_area.clicked.connect(self.start_area_selection)

        mode_layout.addWidget(QLabel("模式:"))
        mode_layout.addWidget(self.combo_mode, 1)
        mode_layout.addWidget(self.btn_select_area)
        region_layout.addLayout(mode_layout)

        # Region Coordinate Info
        self.lbl_region_info = QLabel("座標區域: 全螢幕")
        self.lbl_region_info.setStyleSheet("color: #00E676; font-size: 11px; font-weight: bold;")
        region_layout.addWidget(self.lbl_region_info)

        layout.addWidget(region_group)

        # Status Display Box
        status_group = QGroupBox("📊 錄影狀態")
        status_layout = QVBoxLayout(status_group)
        status_layout.setContentsMargins(6, 6, 6, 6)
        status_layout.setSpacing(4)

        self.lbl_status = QLabel("就緒 (Ready)")
        self.lbl_status.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_status.setStyleSheet("color: #4FC3F7; margin: 4px;")
        status_layout.addWidget(self.lbl_status)

        layout.addWidget(status_group)

        # Record Action Buttons
        btn_layout = QHBoxLayout()
        self.btn_start = QPushButton("🔴 開始錄影")
        self.btn_start.setFixedHeight(34)
        self.btn_start.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.btn_start.setStyleSheet("background-color: #D32F2F; color: white; border-radius: 4px;")

        self.btn_pause = QPushButton("⏸ 暫停")
        self.btn_pause.setFixedHeight(34)
        self.btn_pause.setFont(QFont("Segoe UI", 10))
        self.btn_pause.setEnabled(False)

        self.btn_stop = QPushButton("⏹ 停止並儲存")
        self.btn_stop.setFixedHeight(34)
        self.btn_stop.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.btn_stop.setStyleSheet("background-color: #388E3C; color: white; border-radius: 4px;")
        self.btn_stop.setEnabled(False)

        btn_layout.addWidget(self.btn_start, 2)
        btn_layout.addWidget(self.btn_pause, 1)
        btn_layout.addWidget(self.btn_stop, 2)
        layout.addLayout(btn_layout)

        # Toggle Mini Floating Bar Button
        self.btn_toggle_mini = QPushButton("🗗 切換為懸浮微型條 (Mini Floating Bar)")
        self.btn_toggle_mini.setFixedHeight(28)
        self.btn_toggle_mini.setStyleSheet("background-color: #263238; color: #80D8FF; border: 1px solid #00B0FF; border-radius: 4px; font-weight: bold;")
        self.btn_toggle_mini.clicked.connect(self.toggle_mini_mode)
        layout.addWidget(self.btn_toggle_mini)

        # Options
        self.chk_auto_minimize = QCheckBox("開始錄影時自動最小化視窗")
        self.chk_auto_minimize.setChecked(True)
        self.chk_auto_minimize.toggled.connect(lambda v: self.config.set("auto_minimize_on_rec", v))
        layout.addWidget(self.chk_auto_minimize)

        self.chk_auto_editor = QCheckBox("錄影結束後自動進入影片剪輯器")
        self.chk_auto_editor.setChecked(True)
        self.chk_auto_editor.toggled.connect(lambda v: self.config.set("auto_open_editor", v))
        layout.addWidget(self.chk_auto_editor)

        layout.addStretch(1)

        self.btn_start.clicked.connect(self.start_recording)
        self.btn_pause.clicked.connect(self.toggle_pause)
        self.btn_stop.clicked.connect(self.stop_recording)

    def setup_settings_tab(self, parent_widget):
        layout = QVBoxLayout(parent_widget)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # 1. Video Settings Group
        v_group = QGroupBox("🎬 影片編碼與 GPU 加速")
        v_layout = QVBoxLayout(v_group)
        v_layout.setContentsMargins(6, 6, 6, 6)
        v_layout.setSpacing(4)

        codec_layout = QHBoxLayout()
        self.combo_vcodec = QComboBox()
        lbl_vcodec = QLabel("編碼器:")
        codec_layout.addWidget(lbl_vcodec)
        codec_layout.addWidget(self.combo_vcodec, 1)
        v_layout.addLayout(codec_layout)

        # Quality Mode & Bitrate/CRF
        crf_layout = QHBoxLayout()
        self.combo_qmode = QComboBox()
        self.combo_qmode.addItems(["CRF (品質優先)", "Bitrate (指定位元率)"])
        self.combo_qmode.currentIndexChanged.connect(self.on_qmode_changed)

        self.lbl_crf_val = QLabel("CRF: 23")
        self.lbl_crf_val.setStyleSheet("color: #80D8FF; font-weight: bold;")
        self.slider_crf = QSlider(Qt.Orientation.Horizontal)
        self.slider_crf.setRange(18, 28)
        self.slider_crf.setValue(23)
        self.slider_crf.valueChanged.connect(lambda v: self.lbl_crf_val.setText(f"CRF: {v}"))

        crf_layout.addWidget(QLabel("品質:"))
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

        bitrate_layout.addWidget(QLabel("位元率:"))
        bitrate_layout.addWidget(self.spin_vbitrate)
        bitrate_layout.addWidget(QLabel("幀率:"))
        bitrate_layout.addWidget(self.spin_fps)
        v_layout.addLayout(bitrate_layout)

        layout.addWidget(v_group)

        # 2. Audio Settings Group
        a_group = QGroupBox("🎵 音訊品質與來源 (WASAPI Loopback)")
        a_layout = QVBoxLayout(a_group)
        a_layout.setContentsMargins(6, 6, 6, 6)
        a_layout.setSpacing(4)

        self.chk_audio_enable = QCheckBox("啟用音訊錄製 (Audio Recording)")
        self.chk_audio_enable.setChecked(True)
        a_layout.addWidget(self.chk_audio_enable)

        source_layout = QHBoxLayout()
        self.combo_audio_source = QComboBox()
        self.combo_audio_source.addItem("🖥 系統聲音 (跟隨播放裝置: 藍牙/USB/喇叭)", userData="system")
        self.combo_audio_source.addItem("🎙 麥克風 (Microphone)", userData="mic")
        self.combo_audio_source.addItem("🎛 系統聲音 + 麥克風 (System + Mic)", userData="mix")
        self.combo_audio_source.addItem("🔇 靜音 (Mute)", userData="mute")

        source_layout.addWidget(QLabel("來源:"))
        source_layout.addWidget(self.combo_audio_source, 1)
        a_layout.addLayout(source_layout)

        audio_fmt_layout = QHBoxLayout()
        self.combo_acodec = QComboBox()
        self.combo_acodec.addItems(["AAC", "MP3"])
        
        self.combo_abitrate = QComboBox()
        self.combo_abitrate.addItems(["128k", "192k (推薦)", "256k", "320k"])
        self.combo_abitrate.setCurrentIndex(1)

        self.combo_sample_rate = QComboBox()
        self.combo_sample_rate.addItems(["44.1 kHz", "48 kHz"])

        audio_fmt_layout.addWidget(QLabel("格式:"))
        audio_fmt_layout.addWidget(self.combo_acodec)
        audio_fmt_layout.addWidget(QLabel("位元率:"))
        audio_fmt_layout.addWidget(self.combo_abitrate)
        audio_fmt_layout.addWidget(QLabel("採樣率:"))
        audio_fmt_layout.addWidget(self.combo_sample_rate)
        a_layout.addLayout(audio_fmt_layout)

        self.chk_audio_auto_gain = QCheckBox("🔊 反轉 Windows 音量衰減，保持錄音 100% 滿格音量")
        self.chk_audio_auto_gain.setStyleSheet("color: #00E676; font-weight: bold; font-size: 11px;")
        a_layout.addWidget(self.chk_audio_auto_gain)

        layout.addWidget(a_group)

        # 3. Path & File Name Settings Group
        p_group = QGroupBox("📁 儲存位置與檔名")
        p_layout = QVBoxLayout(p_group)
        p_layout.setContentsMargins(6, 6, 6, 6)
        p_layout.setSpacing(4)

        dir_layout = QHBoxLayout()
        self.txt_save_dir = QLineEdit()
        self.btn_browse_dir = QPushButton("📂 瀏覽...")
        self.btn_browse_dir.setFixedHeight(24)
        self.btn_browse_dir.clicked.connect(self.browse_save_directory)
        dir_layout.addWidget(self.txt_save_dir, 1)
        dir_layout.addWidget(self.btn_browse_dir)
        p_layout.addLayout(dir_layout)

        filename_layout = QHBoxLayout()
        self.txt_filename_pattern = QLineEdit()
        filename_layout.addWidget(QLabel("檔名範本:"))
        filename_layout.addWidget(self.txt_filename_pattern, 1)
        p_layout.addLayout(filename_layout)

        lbl_tip = QLabel("提示：檔名可用 {date} (年月日) 與 {time} (時分秒)")
        lbl_tip.setStyleSheet("color: #B0BEC5; font-size: 10px;")
        p_layout.addWidget(lbl_tip)

        layout.addWidget(p_group)

        # Save Settings Button
        self.btn_save_settings = QPushButton("💾 儲存所有設定 (Save Settings)")
        self.btn_save_settings.setFixedHeight(32)
        self.btn_save_settings.setStyleSheet("background-color: #0288D1; font-size: 12px; font-weight: bold;")
        self.btn_save_settings.clicked.connect(self.save_settings_from_ui)
        layout.addWidget(self.btn_save_settings)

    def load_config_to_ui(self):
        mode = self.config.get("record_mode", "fullscreen")
        found_idx = 0
        for i in range(self.combo_mode.count()):
            if self.combo_mode.itemData(i) == mode:
                found_idx = i
                break
        self.combo_mode.setCurrentIndex(found_idx)
        self.on_mode_changed(found_idx)

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
        self.chk_audio_auto_gain.setChecked(bool(self.config.get("audio_auto_gain", True)))

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
        self.config.set("audio_auto_gain", self.chk_audio_auto_gain.isChecked())

        self.config.set("save_dir", self.txt_save_dir.text().strip())
        self.config.set("filename_pattern", self.txt_filename_pattern.text().strip())

        QMessageBox.information(self, "成功", "所有設定已成功儲存！")

    def populate_record_modes(self):
        self.combo_mode.clear()
        screens = QGuiApplication.screens()
        try:
            import mss
            with mss.mss() as sct:
                monitors = sct.monitors
        except Exception:
            monitors = []

        if len(screens) <= 1:
            self.combo_mode.addItem("🖥 全螢幕錄影", "fullscreen")
        else:
            for idx, screen in enumerate(screens):
                mon = monitors[idx + 1] if idx + 1 < len(monitors) else None
                res_str = f"{mon['width']}x{mon['height']}" if mon else f"{screen.geometry().width()}x{screen.geometry().height()}"
                s_name = screen.name()
                label = f"🖥 全螢幕 - 螢幕 {idx + 1} ({res_str} {s_name})"
                self.combo_mode.addItem(label, f"fullscreen_{idx+1}")
            if len(monitors) > 0:
                all_mon = monitors[0]
                self.combo_mode.addItem(f"🖥 全螢幕 - 所有跨螢幕合併 ({all_mon['width']}x{all_mon['height']})", "fullscreen_all")
        
        self.combo_mode.addItem("🎯 自訂區域錄影", "region")

    def on_mode_changed(self, index):
        mode_data = self.combo_mode.itemData(index) or "fullscreen"
        self.config.set("record_mode", mode_data)
        if mode_data == "region":
            self.btn_select_area.setEnabled(True)
        else:
            self.btn_select_area.setEnabled(False)
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
        # Ensure combo is set to region
        for i in range(self.combo_mode.count()):
            if self.combo_mode.itemData(i) == "region":
                self.combo_mode.setCurrentIndex(i)
                break
        self.update_region_info_label()

    def on_area_start_rec(self, x, y, w, h):
        self.on_area_selected(x, y, w, h)
        self.start_recording()

    def update_region_info_label(self):
        mode = self.config.get("record_mode", "fullscreen")
        if mode == "region":
            rx = self.config.get("region_x", 0)
            ry = self.config.get("region_y", 0)
            rw = self.config.get("region_width", 1280)
            rh = self.config.get("region_height", 720)
            self.lbl_region_info.setText(f"座標: X:{rx}, Y:{ry} | 寬:{rw}px, 高:{rh}px")
        elif mode == "fullscreen_all":
            self.lbl_region_info.setText("座標區域: 🖥 所有跨螢幕合併錄製")
        elif mode.startswith("fullscreen_"):
            try:
                m_idx = mode.split("_")[1]
                self.lbl_region_info.setText(f"座標區域: 🖥 全螢幕錄製 (螢幕 {m_idx})")
            except Exception:
                self.lbl_region_info.setText("座標區域: 🖥 全螢幕錄製")
        else:
            self.lbl_region_info.setText("座標區域: 🖥 全螢幕錄製")

    def browse_save_directory(self):
        dir_path = QFileDialog.getExistingDirectory(
            self, "選擇預設儲存目錄", self.txt_save_dir.text(),
            options=QFileDialog.Option.DontUseNativeDialog
        )
        if dir_path:
            self.txt_save_dir.setText(dir_path)

    def start_recording(self):
        try:
            self.config.generate_filepath()
        except Exception as e:
            QMessageBox.critical(self, "目錄錯誤", f"無法存取錄影儲存目錄:\n{e}\n請至設定分頁更換儲存目錄。")
            return

        self.btn_start.setEnabled(False)
        self.btn_pause.setEnabled(True)
        self.btn_stop.setEnabled(True)
        self.combo_mode.setEnabled(False)
        self.btn_select_area.setEnabled(False)

        self.mini_btn_start.setEnabled(False)
        self.mini_btn_pause.setEnabled(True)
        self.mini_btn_stop.setEnabled(True)

        self.lbl_status.setText("🔴 錄影中 00:00:00")
        self.lbl_status.setStyleSheet("color: #FF5252; margin: 4px;")
        self.mini_lbl_status.setText("🔴 00:00:00")
        self.mini_lbl_status.setStyleSheet("color: #FF5252; min-width: 85px;")

        self.recorder_thread = ScreenRecorderThread(self.config)
        self.recorder_thread.duration_updated.connect(self.on_duration_update)
        self.recorder_thread.recording_stopped.connect(self.on_recording_stopped)
        self.recorder_thread.recording_error.connect(self.on_recording_error)
        self.recorder_thread.start()

        # Minimize main window automatically if option is checked and not in mini mode
        if self.config.get("auto_minimize_on_rec", True) and not self.is_mini_mode:
            self.showMinimized()

    def toggle_pause(self):
        if not self.recorder_thread:
            return
        if self.recorder_thread.is_paused:
            self.recorder_thread.resume()
            self.btn_pause.setText("⏸ 暫停")
            self.mini_btn_pause.setText("⏸")
            self.lbl_status.setStyleSheet("color: #FF5252; margin: 4px;")
            self.mini_lbl_status.setStyleSheet("color: #FF5252; min-width: 85px;")
        else:
            self.recorder_thread.pause()
            self.btn_pause.setText("▶ 繼續錄影")
            self.mini_btn_pause.setText("▶")
            self.lbl_status.setText("⏸ 已暫停錄影")
            self.lbl_status.setStyleSheet("color: #FFC107; margin: 4px;")
            self.mini_lbl_status.setText("⏸ 已暫停")
            self.mini_lbl_status.setStyleSheet("color: #FFC107; min-width: 85px;")

    def stop_recording(self):
        if not self.recorder_thread or not self.recorder_thread.isRunning():
            self.lbl_status.setText("就緒 (Ready)")
            self.lbl_status.setStyleSheet("color: #4FC3F7; margin: 4px;")
            self.mini_lbl_status.setText("就緒")
            self.mini_lbl_status.setStyleSheet("color: #4FC3F7; min-width: 85px;")
            self.btn_start.setEnabled(True)
            self.btn_pause.setEnabled(False)
            self.btn_stop.setEnabled(False)
            self.mini_btn_start.setEnabled(True)
            self.mini_btn_pause.setEnabled(False)
            self.mini_btn_stop.setEnabled(False)
            self.combo_mode.setEnabled(True)
            return

        self.lbl_status.setText("⏳ 正在停止並合併檔案...")
        self.lbl_status.setStyleSheet("color: #FF9800; margin: 4px;")
        self.mini_lbl_status.setText("⏳ 處理中...")
        self.mini_lbl_status.setStyleSheet("color: #FF9800; min-width: 85px;")
        self.btn_pause.setEnabled(False)
        self.btn_stop.setEnabled(False)
        self.mini_btn_pause.setEnabled(False)
        self.mini_btn_stop.setEnabled(False)
        self.recorder_thread.stop()

    def on_duration_update(self, seconds):
        mins = seconds // 60
        secs = seconds % 60
        hrs = mins // 60
        mins = mins % 60
        time_str = f"{hrs:02d}:{mins:02d}:{secs:02d}"
        self.lbl_status.setText(f"🔴 錄影中 {time_str}")
        self.mini_lbl_status.setText(f"🔴 {time_str}")

    def on_recording_stopped(self, filepath):
        if self.is_mini_mode:
            self.toggle_mini_mode()
        else:
            self.showNormal()
            self.activateWindow()

        self.btn_start.setEnabled(True)
        self.btn_pause.setEnabled(False)
        self.btn_pause.setText("⏸ 暫停")
        self.btn_stop.setEnabled(False)
        self.mini_btn_start.setEnabled(True)
        self.mini_btn_pause.setEnabled(False)
        self.mini_btn_pause.setText("⏸")
        self.mini_btn_stop.setEnabled(False)
        self.combo_mode.setEnabled(True)
        if self.combo_mode.currentData() == "region":
            self.btn_select_area.setEnabled(True)

        self.lbl_status.setText("✅ 錄影完成！已儲存")
        self.lbl_status.setStyleSheet("color: #4CAF50; margin: 4px;")
        self.mini_lbl_status.setText("✅ 完成")
        self.mini_lbl_status.setStyleSheet("color: #4CAF50; min-width: 85px;")

        if self.config.get("auto_open_editor", True):
            self.editor_widget.load_video(filepath)
            self.tabs.setCurrentIndex(2)
        else:
            QMessageBox.information(
                self, "錄影完成", 
                f"螢幕錄影已順利儲存至:\n{filepath}"
            )

    def on_recording_error(self, err_msg):
        if self.is_mini_mode:
            self.toggle_mini_mode()
        else:
            self.showNormal()
            self.activateWindow()

        self.btn_start.setEnabled(True)
        self.btn_pause.setEnabled(False)
        self.btn_stop.setEnabled(False)
        self.mini_btn_start.setEnabled(True)
        self.mini_btn_pause.setEnabled(False)
        self.mini_btn_stop.setEnabled(False)
        self.combo_mode.setEnabled(True)

        self.lbl_status.setText("❌ 錄影發生錯誤")
        self.lbl_status.setStyleSheet("color: #F44336; margin: 4px;")
        self.mini_lbl_status.setText("❌ 錯誤")
        self.mini_lbl_status.setStyleSheet("color: #F44336; min-width: 85px;")
        QMessageBox.critical(self, "錄影錯誤", err_msg)
