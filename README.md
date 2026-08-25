# Screen Recorder & Video Trimmer

一款功能齊全、支援 GPU 硬體加速與 WASAPI 音訊 Loopback 追蹤的桌面螢幕錄影與影片掐頭去尾剪輯軟體（基於 Python 3.12 + PyQt6 + MSS + SoundCard + FFmpeg）。

---

## 🌟 核心功能特色

- **🎯 指定 REC 錄影範圍**
  - **全螢幕錄影**（全螢幕擷取）
  - **互動式自訂區域錄影**：全螢幕半透明遮罩選取器，支援 **8 個控制節點 (4 角 + 4 邊拖曳縮放)**、整體平移位置與浮動控制列。
  - **高 DPI 螢幕精確對齊**：自動偵測 `DevicePixelRatio`，精確換算實體像素座標，解決高縮放螢幕（如 125%、150%）錄影區域偏差問題。

- **🚀 影片格式與 GPU 硬體加速**
  - 支援 **H.264** 與 **H.265 / HEVC** 編碼。
  - 自動檢測並支援 **NVIDIA NVENC** (`h264_nvenc`, `hevc_nvenc`)、**Intel QuickSync** (`h264_qsv`)、**AMD AMF** (`h264_amf`) 及 **Windows Media Foundation** (`h264_mf`) 硬體加速。
  - 提供 **CRF 品質優先模式** (18~28 可調) 與 **Bitrate 位元率控制模式** (1000~25000 kbps) 及 15~60 FPS 設定。

- **🎵 音訊品質與 WASAPI 系統聲音自動追蹤**
  - **WASAPI System Audio Loopback**：自動跟隨 Windows 當前預設輸出裝置，不論使用的是 **藍牙耳機、USB 耳機/音效卡、電腦喇叭或 HDMI 顯示器喇叭**，皆能自動錄製立體聲系統音訊。
  - 支援 **系統聲音**、**麥克風**、**系統聲音 + 麥克風 (自動混音)** 及 **靜音** 4 種音訊來源。
  - 支援 **AAC** 與 **MP3** 音訊編碼、128k~320k Bitrate 與 44.1k/48k 採樣率。

- **📁 預設儲存與動態檔名**
  - 自訂預設儲存資料夾與動態檔名樣板 (如 `REC_{date}_{time}.mp4`)。

- **✂ 影片掐頭去尾編輯器 (Video Trimmer)**
  - 內建影片播放與剪輯介面，錄影結束後預設自動載入。
  - 設定剪裁起點 ([) 與終點 (])。
  - 支援 **極速無損 Stream Copy 導出 (`-c copy`)**，免重新編碼，1 秒內完成剪裁。

- **🎨 現代化 UI 設計**
  - 支援高對比深色主題 (Dark Mode)，選單與按鈕視覺清晰。
  - 支援微型視窗 (Mini Mode)，可將主視窗任意縮小不受限制。

---

## 🛠 安裝與需求

### 系統需求
- Windows 10 / 11
- Python 3.10+

### 安裝依賴庫

```powershell
pip install PyQt6 mss soundcard sounddevice numpy pillow imageio-ffmpeg
```

---

## 🚀 啟動軟體

在命令列終端機中執行：

```powershell
python main.py
```

---

## 📂 專案檔案架構

- `main.py`: 應用程式啟動點。
- `main_window.py`: 主視窗 GUI 介面與分頁整合。
- `config.py`: 設定檔持久化管理器 (`config.json`)。
- `area_selector.py`: 8 節點互動式區域選取器遮罩。
- `recorder.py`: 錄影與 WASAPI 音訊 Loopback 錄製引擎。
- `editor.py`: 影片掐頭去尾編輯器。
