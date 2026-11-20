import os
import sys
import time
import wave
import threading
import subprocess
import tempfile
import ctypes
from ctypes import wintypes
from collections import deque
import numpy as np
import mss
import soundcard as sc
import imageio_ffmpeg
from pathlib import Path
from PyQt6.QtCore import QThread, pyqtSignal

KNOWN_ENCODERS = [
    ("h264_nvenc", "🚀 NVIDIA NVENC H.264 (GPU 硬體加速)"),
    ("hevc_nvenc", "🚀 NVIDIA NVENC H.265 / HEVC (GPU 硬體加速)"),
    ("h264_qsv",   "🚀 Intel QuickSync H.264 (GPU 硬體加速)"),
    ("hevc_qsv",   "🚀 Intel QuickSync H.265 / HEVC (GPU 硬體加速)"),
    ("h264_amf",   "🚀 AMD AMF H.264 (GPU 硬體加速)"),
    ("hevc_amf",   "🚀 AMD AMF H.265 / HEVC (GPU 硬體加速)"),
    ("h264_mf",    "🚀 Windows Media Foundation H.264 (GPU 硬體加速)"),
    ("hevc_mf",    "🚀 Windows Media Foundation H.265 / HEVC (GPU 硬體加速)"),
    ("libx264",    "💻 CPU 軟體編碼 H.264 (libx264 - 高相容)"),
    ("libx265",    "💻 CPU 軟體編碼 H.265 / HEVC (libx265 - 高壓縮)"),
]

def detect_available_hw_encoders(ffmpeg_exe: str = None) -> list:
    if not ffmpeg_exe:
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

    available = []
    for codec_id, name in KNOWN_ENCODERS:
        if codec_id in ("libx264", "libx265"):
            available.append((codec_id, name))
            continue

        try:
            cmd = [ffmpeg_exe, "-y", "-f", "lavfi", "-i", "nullsrc=size=64x64", "-c:v", codec_id, "-t", "0.05", "-f", "null", "-"]
            res = subprocess.run(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            if res.returncode == 0:
                available.append((codec_id, name))
        except Exception:
            pass

    return available

def list_system_audio_devices():
    """Returns (default_id, default_name, [(id, name), ...]) for all active Windows playback devices."""
    default_id = ""
    default_name = ""
    devices = []
    try:
        def_spk = sc.default_speaker()
        if def_spk:
            default_id = str(def_spk.id)
            default_name = str(def_spk.name)
    except Exception:
        pass

    try:
        for spk in sc.all_speakers():
            devices.append((str(spk.id), str(spk.name)))
    except Exception:
        pass

    return default_id, default_name, devices

def _find_loopback_by_id(target_id: str):
    """Exact WASAPI endpoint ID lookup for a loopback microphone."""
    if not target_id:
        return None
    try:
        m = sc.get_microphone(str(target_id), include_loopback=True)
        if m and getattr(m, 'isloopback', False):
            return m
    except Exception:
        pass

    try:
        for m in sc.all_microphones(include_loopback=True):
            if getattr(m, 'isloopback', False) and str(m.id) == str(target_id):
                return m
    except Exception:
        pass
    return None

def get_system_loopback_mic(preferred_device_id: str = "auto"):
    """Universally resolves Windows playback loopback by exact WASAPI endpoint ID (Bluetooth, USB, Speaker, HDMI)."""
    # 1. If user explicitly locked a specific output device, resolve it by exact ID first
    if preferred_device_id and preferred_device_id != "auto":
        m = _find_loopback_by_id(preferred_device_id)
        if m:
            return m

    # 2. Follow current Windows default speaker using exact endpoint ID (avoids brittle name matching)
    try:
        spk = sc.default_speaker()
        if spk:
            m = _find_loopback_by_id(str(spk.id))
            if m:
                return m
            # Secondary match by exact name only if it is confirmed loopback
            m = sc.get_microphone(spk.name, include_loopback=True)
            if m and getattr(m, 'isloopback', False):
                return m
    except Exception:
        pass

    # 3. Last-resort fallback: first available loopback microphone on any output device
    try:
        for m in sc.all_microphones(include_loopback=True):
            if getattr(m, 'isloopback', False):
                return m
    except Exception:
        pass

    return None

def get_physical_mic():
    """Universally resolves active Windows default physical microphone."""
    try:
        return sc.default_microphone()
    except Exception:
        pass

    # Fallback: search all physical non-loopback microphones
    try:
        for m in sc.all_microphones(include_loopback=True):
            if not getattr(m, 'isloopback', False):
                return m
    except Exception:
        pass

    return None

def get_windows_master_volume_scalar(device_id: str = None) -> float:
    """Directly queries Windows speaker master volume scalar (0.0 to 1.0) via Core Audio for a specific or default device."""
    try:
        ole32 = ctypes.windll.ole32
        ole32.CoInitialize(None)

        class GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", wintypes.DWORD),
                ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD),
                ("Data4", wintypes.BYTE * 8)
            ]
            def __init__(self, guid_str):
                super().__init__()
                ole32.CLSIDFromString(ctypes.c_wchar_p(guid_str), ctypes.byref(self))

        CLSID_MMDeviceEnumerator = GUID("{BCDE0395-E52F-467C-8E3D-C4579291692E}")
        IID_IMMDeviceEnumerator = GUID("{A95664D2-9614-4F35-A746-DE8DB63617E6}")
        IID_IAudioEndpointVolume = GUID("{5CDF2C82-841E-4546-9722-0CF74078229A}")

        enumerator = ctypes.c_void_p()
        hr = ole32.CoCreateInstance(
            ctypes.byref(CLSID_MMDeviceEnumerator),
            None,
            1,
            ctypes.byref(IID_IMMDeviceEnumerator),
            ctypes.byref(enumerator)
        )
        if hr != 0 or not enumerator.value:
            return 1.0

        vtbl = ctypes.cast(ctypes.cast(enumerator.value, ctypes.POINTER(ctypes.c_void_p))[0], ctypes.POINTER(ctypes.c_void_p))

        device = ctypes.c_void_p()
        got_device = False
        if device_id and device_id != "auto":
            # IMMDeviceEnumerator::GetDevice (vtable index 5)
            GetDevice = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_void_p))(vtbl[5])
            if GetDevice(enumerator.value, str(device_id), ctypes.byref(device)) == 0 and device.value:
                got_device = True

        if not got_device:
            # IMMDeviceEnumerator::GetDefaultAudioEndpoint (vtable index 4)
            GetDefaultAudioEndpoint = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p))(vtbl[4])
            if GetDefaultAudioEndpoint(enumerator.value, 0, 0, ctypes.byref(device)) != 0 or not device.value:
                return 1.0

        dev_vtbl = ctypes.cast(ctypes.cast(device.value, ctypes.POINTER(ctypes.c_void_p))[0], ctypes.POINTER(ctypes.c_void_p))
        Activate = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, ctypes.POINTER(GUID), wintypes.DWORD, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))(dev_vtbl[3])

        endpoint_vol = ctypes.c_void_p()
        if Activate(device.value, ctypes.byref(IID_IAudioEndpointVolume), 1, None, ctypes.byref(endpoint_vol)) != 0 or not endpoint_vol.value:
            return 1.0

        vol_vtbl = ctypes.cast(ctypes.cast(endpoint_vol.value, ctypes.POINTER(ctypes.c_void_p))[0], ctypes.POINTER(ctypes.c_void_p))
        GetMasterVolumeLevelScalar = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, ctypes.POINTER(ctypes.c_float))(vol_vtbl[9])

        master_scalar = ctypes.c_float(1.0)
        GetMasterVolumeLevelScalar(endpoint_vol.value, ctypes.byref(master_scalar))
        return float(master_scalar.value)
    except Exception:
        return 1.0

def get_device_native_format(device_id: str = None):
    """Auto-detects native WASAPI mix format (sample_rate, channels) via IAudioClient::GetMixFormat."""
    try:
        ole32 = ctypes.windll.ole32
        ole32.CoInitialize(None)

        class GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", wintypes.DWORD),
                ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD),
                ("Data4", wintypes.BYTE * 8),
            ]
            def __init__(self, guid_str):
                super().__init__()
                ole32.CLSIDFromString(ctypes.c_wchar_p(guid_str), ctypes.byref(self))

        class WAVEFORMATEX(ctypes.Structure):
            _fields_ = [
                ("wFormatTag", wintypes.WORD),
                ("nChannels", wintypes.WORD),
                ("nSamplesPerSec", wintypes.DWORD),
                ("nAvgBytesPerSec", wintypes.DWORD),
                ("nBlockAlign", wintypes.WORD),
                ("wBitsPerSample", wintypes.WORD),
                ("cbSize", wintypes.WORD),
            ]

        CLSID_MMDeviceEnumerator = GUID("{BCDE0395-E52F-467C-8E3D-C4579291692E}")
        IID_IMMDeviceEnumerator = GUID("{A95664D2-9614-4F35-A746-DE8DB63617E6}")
        IID_IAudioClient = GUID("{1CB9AD4C-DBFA-4C32-B178-C2F568A703B2}")

        enumerator = ctypes.c_void_p()
        hr = ole32.CoCreateInstance(
            ctypes.byref(CLSID_MMDeviceEnumerator),
            None,
            1,
            ctypes.byref(IID_IMMDeviceEnumerator),
            ctypes.byref(enumerator),
        )
        if hr != 0 or not enumerator.value:
            return 48000, 2

        vtbl = ctypes.cast(ctypes.cast(enumerator.value, ctypes.POINTER(ctypes.c_void_p))[0], ctypes.POINTER(ctypes.c_void_p))
        device = ctypes.c_void_p()
        got_device = False
        if device_id and device_id != "auto":
            GetDevice = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_void_p))(vtbl[5])
            if GetDevice(enumerator.value, str(device_id), ctypes.byref(device)) == 0 and device.value:
                got_device = True

        if not got_device:
            GetDefaultAudioEndpoint = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p))(vtbl[4])
            if GetDefaultAudioEndpoint(enumerator.value, 0, 0, ctypes.byref(device)) != 0 or not device.value:
                return 48000, 2

        dev_vtbl = ctypes.cast(ctypes.cast(device.value, ctypes.POINTER(ctypes.c_void_p))[0], ctypes.POINTER(ctypes.c_void_p))
        Activate = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, ctypes.POINTER(GUID), wintypes.DWORD, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))(dev_vtbl[3])

        audio_client = ctypes.c_void_p()
        if Activate(device.value, ctypes.byref(IID_IAudioClient), 23, None, ctypes.byref(audio_client)) != 0 or not audio_client.value:
            return 48000, 2

        ac_vtbl = ctypes.cast(ctypes.cast(audio_client.value, ctypes.POINTER(ctypes.c_void_p))[0], ctypes.POINTER(ctypes.c_void_p))
        GetMixFormat = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, ctypes.POINTER(ctypes.POINTER(WAVEFORMATEX)))(ac_vtbl[8])

        pwfx = ctypes.POINTER(WAVEFORMATEX)()
        if GetMixFormat(audio_client.value, ctypes.byref(pwfx)) != 0 or not pwfx:
            return 48000, 2

        sr = int(pwfx.contents.nSamplesPerSec)
        ch = int(pwfx.contents.nChannels)
        ole32.CoTaskMemFree(pwfx)
        if sr < 8000 or sr > 192000:
            sr = 48000
        # Normalize surround/multi-channel to stereo for universal MP4/AAC playback
        rec_ch = 2 if ch >= 2 else 1
        return sr, rec_ch
    except Exception:
        return 48000, 2

def get_all_system_loopback_mics():
    """Returns all active Windows playback loopback microphones, ordered with the default speaker first."""
    mics = []
    seen_ids = set()

    # Put default speaker loopback first
    try:
        def_spk = sc.default_speaker()
        if def_spk:
            m = _find_loopback_by_id(str(def_spk.id))
            if m:
                mics.append(m)
                seen_ids.add(str(m.id))
    except Exception:
        pass

    # Add all other active playback loopback devices (HDMI TV, Bluetooth, USB, Notebook Speaker, etc.)
    try:
        for m in sc.all_microphones(include_loopback=True):
            if getattr(m, 'isloopback', False) and str(m.id) not in seen_ids:
                mics.append(m)
                seen_ids.add(str(m.id))
    except Exception:
        pass

    return mics

def _open_recorder_with_fallback(mic, preferred_sr: int, preferred_ch: int = 2):
    """Opens a soundcard recorder with automatic native-format and fallback resolution."""
    sr_candidates = []
    if preferred_sr and preferred_sr > 0:
        sr_candidates.append(preferred_sr)
    for fallback_sr in (48000, 44100):
        if fallback_sr not in sr_candidates:
            sr_candidates.append(fallback_sr)
    ch_candidates = [preferred_ch, 1] if preferred_ch > 1 else [1, 2]

    last_err = None
    for sr in sr_candidates:
        for ch in ch_candidates:
            try:
                cm = mic.recorder(samplerate=sr, channels=ch)
                rec = cm.__enter__()
                return cm, rec, sr, ch
            except Exception as e:
                last_err = e
    raise last_err if last_err else RuntimeError("無法開啟音訊錄製裝置")

def _normalize_channels(data: np.ndarray, target_ch: int) -> np.ndarray:
    """Converts float audio array (frames, ch) to target_ch (1 or 2) cleanly."""
    if data.ndim == 1:
        data = data[:, np.newaxis]
    cur_ch = data.shape[1]
    if cur_ch == target_ch:
        return data
    if target_ch == 2 and cur_ch == 1:
        return np.repeat(data, 2, axis=1)
    if target_ch == 1 and cur_ch >= 2:
        return np.mean(data, axis=1, keepdims=True)
    return data[:, :target_ch]

class _DeviceCaptureWorker(threading.Thread):
    """Lightweight per-endpoint audio worker for Method B multi-output auto-detect & seamless mixing."""
    def __init__(self, mic, target_sr: int, target_ch: int, auto_gain: bool = True, is_loopback: bool = True):
        super().__init__(daemon=True)
        self.mic = mic
        self.device_id = str(mic.id)
        self.device_name = str(mic.name)
        self.target_sr = target_sr
        self.target_ch = target_ch
        self.auto_gain = auto_gain and is_loopback
        self.is_loopback = is_loopback

        self.is_running = True
        self.is_paused = False
        self.ready = False
        self.failed = False
        self.ever_had_signal = False
        self.error_message = ""
        self.queue = deque(maxlen=32)
        self.lock = threading.Lock()

    def stop(self):
        self.is_running = False

    def pop_chunk(self):
        with self.lock:
            if self.queue:
                return self.queue.popleft()
        return None

    def run(self):
        try:
            cm, rec, _, _ = _open_recorder_with_fallback(self.mic, self.target_sr, self.target_ch)
            self.ready = True
            try:
                last_vol_time = 0.0
                vol_scalar = 1.0
                while self.is_running:
                    if not self.is_paused:
                        float_data = rec.record(numframes=1024)
                        float_data = _normalize_channels(float_data, self.target_ch)
                        peak = float(np.max(np.abs(float_data))) if float_data.size > 0 else 0.0
                        if peak > 1e-6:
                            self.ever_had_signal = True
                            if self.auto_gain:
                                now = time.time()
                                if now - last_vol_time >= 0.5:
                                    vol_scalar = max(get_windows_master_volume_scalar(self.device_id), 0.01)
                                    last_vol_time = now
                                float_data = float_data / vol_scalar
                        with self.lock:
                            self.queue.append(float_data)
                    else:
                        time.sleep(0.05)
            finally:
                cm.__exit__(None, None, None)
        except Exception as e:
            self.failed = True
            self.error_message = str(e)

class AudioCaptureThread(threading.Thread):
    def __init__(self, sample_rate=0, source="system", auto_gain=True, output_device_id="auto"):
        super().__init__(daemon=True)
        self.sample_rate = int(sample_rate) if sample_rate else 0  # 0 = auto-detect native format
        self.actual_sample_rate = self.sample_rate if self.sample_rate > 0 else 48000
        self.actual_channels = 2
        self.source = source
        self.auto_gain = auto_gain
        self.output_device_id = output_device_id
        self.is_running = True
        self.is_paused = False
        self.audio_frames = []
        self.resolved_device_name = ""
        self.error_message = ""
        self._workers = []

    def stop(self):
        self.is_running = False
        for w in self._workers:
            w.stop()

    def pause(self):
        self.is_paused = True
        for w in self._workers:
            w.is_paused = True

    def resume(self):
        self.is_paused = False
        for w in self._workers:
            w.is_paused = False

    def run(self):
        if self.source == "mute":
            return

        try:
            # Resolve playback loopback device(s)
            loopback_mics = []
            if self.source in ("system", "mix"):
                if self.output_device_id and self.output_device_id != "auto":
                    m = get_system_loopback_mic(self.output_device_id)
                    if m:
                        loopback_mics = [m]
                else:
                    # Method B: Auto-detect & monitor ALL active Windows playback outputs simultaneously
                    loopback_mics = get_all_system_loopback_mics()

            physical_mic = get_physical_mic() if self.source in ("mic", "mix") else None

            # Fallback if requested category has no devices
            if self.source == "system" and not loopback_mics and physical_mic is None:
                fallback_mic = get_physical_mic()
                if fallback_mic:
                    physical_mic = fallback_mic

            if self.source == "mic" and not physical_mic:
                loopback_mics = get_all_system_loopback_mics()

            if not loopback_mics and not physical_mic:
                self.error_message = "找不到任何可用的音訊錄製裝置"
                return

            # Auto-detect native sample rate & channels from primary target device
            primary_dev_id = str(loopback_mics[0].id) if loopback_mics else (str(physical_mic.id) if physical_mic else None)
            native_sr, native_ch = get_device_native_format(primary_dev_id)
            target_sr = self.sample_rate if self.sample_rate > 0 else native_sr
            # Use stereo when mixing multiple endpoints; otherwise match device's native mono/stereo
            use_multi_worker = (len(loopback_mics) >= 2) or (bool(loopback_mics) and bool(physical_mic))
            target_ch = 2 if use_multi_worker else native_ch

            # Fast path: single device capture (1 speaker OR 1 physical mic)
            if not use_multi_worker:
                single_mic = loopback_mics[0] if loopback_mics else physical_mic
                is_loopback = bool(loopback_mics)
                self.resolved_device_name = str(single_mic.name)
                dev_id = str(single_mic.id)

                cm, rec, actual_sr, actual_ch = _open_recorder_with_fallback(single_mic, target_sr, target_ch)
                self.actual_sample_rate = actual_sr
                self.actual_channels = actual_ch
                try:
                    last_vol_time = 0.0
                    vol_scalar = 1.0
                    while self.is_running:
                        if not self.is_paused:
                            float_data = rec.record(numframes=1024)
                            if is_loopback and self.auto_gain:
                                peak = float(np.max(np.abs(float_data))) if float_data.size > 0 else 0.0
                                if peak > 1e-6:
                                    now = time.time()
                                    if now - last_vol_time >= 0.5:
                                        vol_scalar = max(get_windows_master_volume_scalar(dev_id), 0.01)
                                        last_vol_time = now
                                    float_data = float_data / vol_scalar
                            pcm16 = np.clip(float_data * 32767, -32768, 32767).astype(np.int16)
                            self.audio_frames.append(pcm16)
                        else:
                            time.sleep(0.05)
                finally:
                    cm.__exit__(None, None, None)
                return

            # Method B Multi-Endpoint Auto-Detect & Seamless Mixing
            self.actual_sample_rate = target_sr
            self.actual_channels = target_ch
            self._workers = []

            for m in loopback_mics:
                w = _DeviceCaptureWorker(m, target_sr, target_ch, auto_gain=self.auto_gain, is_loopback=True)
                self._workers.append(w)
                w.start()

            if physical_mic:
                w_mic = _DeviceCaptureWorker(physical_mic, target_sr, target_ch, auto_gain=False, is_loopback=False)
                self._workers.append(w_mic)
                w_mic.start()

            # Wait briefly for at least one worker to become ready
            wait_deadline = time.perf_counter() + 1.0
            while time.perf_counter() < wait_deadline and self.is_running:
                if any(w.ready for w in self._workers):
                    break
                if all(w.failed for w in self._workers):
                    break
                time.sleep(0.02)

            active_workers = [w for w in self._workers if not w.failed]
            if not active_workers:
                errs = "; ".join(f"{w.device_name}: {w.error_message}" for w in self._workers if w.error_message)
                self.error_message = f"所有音訊裝置皆無法開啟 ({errs})"
                return

            self.resolved_device_name = " + ".join(w.device_name for w in active_workers)

            chunk_sec = 1024.0 / float(target_sr)
            next_tick = time.perf_counter()
            while self.is_running:
                if not self.is_paused:
                    mixed = None
                    for w in active_workers:
                        chunk = w.pop_chunk()
                        if chunk is not None:
                            if mixed is None:
                                mixed = chunk.astype(np.float32, copy=True)
                            else:
                                min_len = min(len(mixed), len(chunk))
                                mixed[:min_len] += chunk[:min_len]
                    if mixed is not None:
                        pcm16 = np.clip(mixed * 32767, -32768, 32767).astype(np.int16)
                        self.audio_frames.append(pcm16)

                    next_tick += chunk_sec
                    sleep_s = next_tick - time.perf_counter()
                    if sleep_s > 0:
                        time.sleep(sleep_s)
                    elif sleep_s < -0.2:
                        # Re-anchor clock if system stalled
                        next_tick = time.perf_counter()
                else:
                    time.sleep(0.05)
                    next_tick = time.perf_counter()

            # Stop and join all workers cleanly
            for w in self._workers:
                w.stop()
            for w in self._workers:
                w.join(timeout=1.5)

            # Update resolved_device_name to highlight which device(s) actually produced sound
            active_signal_names = [w.device_name for w in active_workers if w.ever_had_signal]
            if active_signal_names:
                self.resolved_device_name = " + ".join(active_signal_names)

        except Exception as e:
            self.error_message = f"音訊錄製異常 ({self.resolved_device_name or self.source}): {e}"

class ScreenRecorderThread(QThread):
    recording_started = pyqtSignal()
    recording_stopped = pyqtSignal(str) # output filepath
    recording_error = pyqtSignal(str)
    audio_warning = pyqtSignal(str)
    duration_updated = pyqtSignal(int)  # elapsed seconds

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.is_running = False
        self.is_paused = False
        self.ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        
        self.temp_video_path = None
        self.temp_audio_path = None
        self.output_filepath = None
        self.ffmpeg_process = None
        self.audio_thread = None

    def pause(self):
        self.is_paused = True
        if self.audio_thread:
            self.audio_thread.pause()

    def resume(self):
        self.is_paused = False
        if self.audio_thread:
            self.audio_thread.resume()

    def stop(self):
        self.is_running = False
        if self.audio_thread:
            self.audio_thread.stop()

    def run(self):
        try:
            self.is_running = True
            self.is_paused = False
            self.output_filepath = self.config.generate_filepath()
            
            temp_dir = tempfile.gettempdir()
            timestamp = int(time.time() * 1000)
            self.temp_video_path = os.path.join(temp_dir, f"temp_video_{timestamp}.mp4")
            self.temp_audio_path = os.path.join(temp_dir, f"temp_audio_{timestamp}.wav")

            # Capture area calculation
            mode = self.config.get("record_mode", "fullscreen")
            with mss.mss() as sct:
                if mode == "region":
                    rx = int(self.config.get("region_x", 0))
                    ry = int(self.config.get("region_y", 0))
                    rw = max(100, int(self.config.get("region_width", 1280)))
                    rh = max(100, int(self.config.get("region_height", 720)))
                elif mode == "fullscreen_all":
                    monitor = sct.monitors[0]
                    rx, ry, rw, rh = monitor["left"], monitor["top"], monitor["width"], monitor["height"]
                elif mode.startswith("fullscreen_"):
                    try:
                        m_idx = int(mode.split("_")[1])
                        monitor = sct.monitors[m_idx] if m_idx < len(sct.monitors) else sct.monitors[1]
                    except Exception:
                        monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
                    rx, ry, rw, rh = monitor["left"], monitor["top"], monitor["width"], monitor["height"]
                else:
                    monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
                    rx, ry, rw, rh = monitor["left"], monitor["top"], monitor["width"], monitor["height"]

            # Ensure even dimensions
            rw = rw if rw % 2 == 0 else rw - 1
            rh = rh if rh % 2 == 0 else rh - 1
            
            fps = int(self.config.get("fps", 30))
            frame_interval = 1.0 / fps

            v_codec = self.config.get("video_codec", "libx264")
            quality_mode = self.config.get("quality_mode", "crf")
            crf = self.config.get("crf", 23)
            bitrate_kbps = self.config.get("video_bitrate_kbps", 6000)

            ffmpeg_cmd = [
                self.ffmpeg_exe,
                "-y",
                "-f", "rawvideo",
                "-vcodec", "rawvideo",
                "-s", f"{rw}x{rh}",
                "-pix_fmt", "bgra",
                "-r", str(fps),
                "-i", "-", # Stdin input
                "-c:v", v_codec,
                "-pix_fmt", "yuv420p",
                "-g", str(fps),            # Emit keyframe every 1s for accurate trimming
                "-keyint_min", str(fps)
            ]

            # Hardware acceleration encoder flags tuning
            if "nvenc" in v_codec:
                ffmpeg_cmd.extend(["-preset", "p1", "-rc", "constqp", "-qp", str(crf)])
            elif "qsv" in v_codec:
                ffmpeg_cmd.extend(["-preset", "veryfast", "-global_quality", str(crf)])
            elif "amf" in v_codec:
                ffmpeg_cmd.extend(["-usage", "lowlatency", "-rc", "cqp", "-qp_p", str(crf), "-qp_i", str(crf)])
            elif "mf" in v_codec:
                ffmpeg_cmd.extend(["-b:v", f"{bitrate_kbps}k"])
            else:
                # CPU libx264 / libx265
                ffmpeg_cmd.extend(["-preset", "ultrafast"])
                if quality_mode == "crf":
                    ffmpeg_cmd.extend(["-crf", str(crf)])
                else:
                    ffmpeg_cmd.extend(["-b:v", f"{bitrate_kbps}k", "-maxrate", f"{int(bitrate_kbps * 1.2)}k", "-bufsize", f"{bitrate_kbps * 2}k"])

            ffmpeg_cmd.append(self.temp_video_path)

            self.ffmpeg_process = subprocess.Popen(
                ffmpeg_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )

            # Setup Audio thread with universal fallback resolution
            audio_enabled = self.config.get("audio_enabled", True)
            audio_source = self.config.get("audio_source", "system")
            sample_rate = int(self.config.get("audio_sample_rate", 0))
            auto_gain = bool(self.config.get("audio_auto_gain", True))
            output_device_id = self.config.get("audio_output_device_id", "auto")

            if audio_enabled and audio_source != "mute":
                self.audio_thread = AudioCaptureThread(
                    sample_rate=sample_rate,
                    source=audio_source,
                    auto_gain=auto_gain,
                    output_device_id=output_device_id
                )
                self.audio_thread.start()

            self.recording_started.emit()

            monitor = {"left": rx, "top": ry, "width": rw, "height": rh}
            start_time = time.time()
            last_duration_emit = start_time
            elapsed_recorded_sec = 0

            with mss.mss() as sct:
                while self.is_running:
                    loop_start = time.time()

                    if not self.is_paused:
                        try:
                            img = sct.grab(monitor)
                            raw_bytes = img.raw

                            self.ffmpeg_process.stdin.write(raw_bytes)
                        except (IOError, ValueError, BrokenPipeError, mss.exception.ScreenShotError):
                            break

                        now = time.time()
                        if now - last_duration_emit >= 1.0:
                            elapsed_recorded_sec += 1
                            self.duration_updated.emit(elapsed_recorded_sec)
                            last_duration_emit = now

                    elapsed = time.time() - loop_start
                    sleep_time = frame_interval - elapsed
                    if sleep_time > 0:
                        time.sleep(sleep_time)

            # Stop audio thread and join
            if self.audio_thread:
                self.audio_thread.stop()
                self.audio_thread.join(timeout=3)

            # Close video stdin and wait for FFmpeg to finish encoding (5s timeout safety)
            if self.ffmpeg_process:
                if self.ffmpeg_process.stdin:
                    try:
                        self.ffmpeg_process.stdin.close()
                    except Exception:
                        pass
                try:
                    self.ffmpeg_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.ffmpeg_process.kill()
                    self.ffmpeg_process.wait()

            # Save recorded audio frames to temp WAV
            has_audio_data = False
            actual_sr = getattr(self.audio_thread, "actual_sample_rate", sample_rate) if self.audio_thread else sample_rate
            if self.audio_thread and self.audio_thread.error_message:
                self.audio_warning.emit(self.audio_thread.error_message)

            if self.audio_thread and self.audio_thread.audio_frames:
                try:
                    audio_data = np.concatenate(self.audio_thread.audio_frames, axis=0)
                    auto_gain = bool(self.config.get("audio_auto_gain", True))
                    max_peak = int(np.max(np.abs(audio_data))) if audio_data.size > 0 else 0
                    if max_peak == 0 and not self.audio_thread.error_message:
                        dev_name = self.audio_thread.resolved_device_name or "系統預設裝置"
                        self.audio_warning.emit(
                            f"未偵測到聲音訊號（目前錄製裝置：{dev_name}）。\n"
                            "若您外接電視/多螢幕，請至「⚙ 畫質設定」手動指定正確的系統聲音裝置，並確認該裝置未靜音。"
                        )
                    if auto_gain and audio_data.size > 0:
                        if 100 < max_peak < 22000:
                            # Normalize audio to -1 dBFS (approx 29000/32767) with max 10x safety boost
                            boost = min(29000.0 / max_peak, 10.0)
                            audio_data = np.clip(audio_data.astype(np.float32) * boost, -32768, 32767).astype(np.int16)

                    ch = 2 if audio_data.ndim > 1 and audio_data.shape[1] >= 2 else 1
                    with wave.open(self.temp_audio_path, 'wb') as wf:
                        wf.setnchannels(ch)
                        wf.setsampwidth(2)
                        wf.setframerate(actual_sr)
                        wf.writeframes(audio_data.tobytes())
                    has_audio_data = True
                except Exception as e:
                    self.audio_warning.emit(f"音訊暫存檔寫入失敗: {e}")
            elif audio_enabled and audio_source != "mute" and self.audio_thread and not self.audio_thread.error_message:
                dev_name = self.audio_thread.resolved_device_name or "未知裝置"
                self.audio_warning.emit(f"未擷取到任何音訊資料（裝置：{dev_name}），影片已以無聲模式儲存。")

            # Remux Video + Audio
            merged_success = False
            if has_audio_data and os.path.exists(self.temp_audio_path) and os.path.exists(self.temp_video_path):
                a_codec = self.config.get("audio_codec", "aac")
                a_bitrate = self.config.get("audio_bitrate_kbps", 192)

                merge_cmd = [
                    self.ffmpeg_exe,
                    "-y",
                    "-i", self.temp_video_path,
                    "-i", self.temp_audio_path,
                    "-c:v", "copy",
                    "-c:a", a_codec,
                    "-b:a", f"{a_bitrate}k",
                    "-ar", str(actual_sr),
                    self.output_filepath
                ]

                try:
                    subprocess.run(
                        merge_cmd,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=30,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                        check=True
                    )
                    merged_success = True
                except Exception:
                    merged_success = False

            if not merged_success and os.path.exists(self.temp_video_path):
                try:
                    import shutil
                    if os.path.exists(self.output_filepath):
                        os.remove(self.output_filepath)
                    shutil.copy2(self.temp_video_path, self.output_filepath)
                except Exception:
                    pass

            self.cleanup_temp_files()

            if os.path.exists(self.output_filepath) and os.path.getsize(self.output_filepath) > 0:
                self.recording_stopped.emit(self.output_filepath)
            else:
                self.recording_error.emit("錄影檔案儲存失敗，請檢查儲存目錄權限。")

        except Exception as e:
            self.recording_error.emit(f"錄影發生錯誤: {str(e)}")
            self.cleanup_temp_files()

    def cleanup_temp_files(self):
        for path in (self.temp_video_path, self.temp_audio_path):
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass
