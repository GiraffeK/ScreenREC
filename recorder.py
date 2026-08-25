import os
import sys
import time
import wave
import threading
import subprocess
import tempfile
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

class AudioCaptureThread(threading.Thread):
    def __init__(self, sample_rate=44100, source="system"):
        super().__init__()
        self.sample_rate = sample_rate
        self.source = source
        self.is_running = True
        self.is_paused = False
        self.audio_frames = []

    def stop(self):
        self.is_running = False

    def pause(self):
        self.is_paused = True

    def resume(self):
        self.is_paused = False

    def run(self):
        if self.source == "mute":
            return

        try:
            if self.source == "system":
                # Dynamically fetch Windows currently active default output device (Bluetooth / USB / Speaker)
                spk = sc.default_speaker()
                mic = sc.get_microphone(spk.name, include_loopback=True)
                with mic.recorder(samplerate=self.sample_rate, channels=2) as rec:
                    while self.is_running:
                        if not self.is_paused:
                            float_data = rec.record(numframes=1024)
                            pcm16 = np.clip(float_data * 32767, -32768, 32767).astype(np.int16)
                            self.audio_frames.append(pcm16)
                        else:
                            time.sleep(0.05)

            elif self.source == "mic":
                mic = sc.default_microphone()
                with mic.recorder(samplerate=self.sample_rate, channels=2) as rec:
                    while self.is_running:
                        if not self.is_paused:
                            float_data = rec.record(numframes=1024)
                            pcm16 = np.clip(float_data * 32767, -32768, 32767).astype(np.int16)
                            self.audio_frames.append(pcm16)
                        else:
                            time.sleep(0.05)

            elif self.source == "mix":
                spk = sc.default_speaker()
                sys_loopback = sc.get_microphone(spk.name, include_loopback=True)
                mic = sc.default_microphone()
                
                with sys_loopback.recorder(samplerate=self.sample_rate, channels=2) as rec_sys, \
                     mic.recorder(samplerate=self.sample_rate, channels=2) as rec_mic:
                    while self.is_running:
                        if not self.is_paused:
                            data_sys = rec_sys.record(numframes=1024)
                            data_mic = rec_mic.record(numframes=1024)
                            min_len = min(len(data_sys), len(data_mic))
                            mixed_float = data_sys[:min_len] + data_mic[:min_len]
                            pcm16 = np.clip(mixed_float * 32767, -32768, 32767).astype(np.int16)
                            self.audio_frames.append(pcm16)
                        else:
                            time.sleep(0.05)

        except Exception as e:
            print(f"Audio capture thread error: {e}")

class ScreenRecorderThread(QThread):
    recording_started = pyqtSignal()
    recording_stopped = pyqtSignal(str) # output filepath
    recording_error = pyqtSignal(str)
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
                    rx = max(0, int(self.config.get("region_x", 0)))
                    ry = max(0, int(self.config.get("region_y", 0)))
                    rw = max(100, int(self.config.get("region_width", 1280)))
                    rh = max(100, int(self.config.get("region_height", 720)))
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
                "-pix_fmt", "yuv420p"
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

            # Setup Audio thread using soundcard for active System Audio Loopback / Mic
            audio_enabled = self.config.get("audio_enabled", True)
            audio_source = self.config.get("audio_source", "system")
            sample_rate = int(self.config.get("audio_sample_rate", 44100))

            if audio_enabled and audio_source != "mute":
                self.audio_thread = AudioCaptureThread(sample_rate=sample_rate, source=audio_source)
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
            if self.audio_thread and self.audio_thread.audio_frames:
                try:
                    audio_data = np.concatenate(self.audio_thread.audio_frames, axis=0)
                    with wave.open(self.temp_audio_path, 'wb') as wf:
                        wf.setnchannels(2)
                        wf.setsampwidth(2)
                        wf.setframerate(sample_rate)
                        wf.writeframes(audio_data.tobytes())
                    has_audio_data = True
                except Exception as e:
                    print(f"Error writing audio file: {e}")

            # Remux Video + Audio
            if has_audio_data and os.path.exists(self.temp_audio_path):
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
                    "-ar", str(sample_rate),
                    self.output_filepath
                ]

                subprocess.run(
                    merge_cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                )
                self.cleanup_temp_files()
            else:
                if os.path.exists(self.temp_video_path):
                    if os.path.exists(self.output_filepath):
                        os.remove(self.output_filepath)
                    os.rename(self.temp_video_path, self.output_filepath)

            if os.path.exists(self.output_filepath):
                self.recording_stopped.emit(self.output_filepath)
            else:
                self.recording_error.emit("錄影檔案儲存失敗。")

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
