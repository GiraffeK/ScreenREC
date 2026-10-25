import json
import os
import sys
from pathlib import Path
from datetime import datetime

def get_safe_default_save_dir() -> str:
    """Finds a guaranteed writable recording directory."""
    candidates = [
        Path.home() / "Videos" / "Recordings",
        Path.home() / "Videos",
        Path(__file__).resolve().parent / "recordings",
        Path.cwd() / "recordings"
    ]
    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            test_file = candidate / ".write_test"
            test_file.write_text("ok")
            test_file.unlink()
            return str(candidate)
        except Exception:
            continue
    # Ultimate fallback: local recordings folder
    fallback = Path.cwd() / "recordings"
    try:
        fallback.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return str(fallback)

DEFAULT_CONFIG = {
    "save_dir": get_safe_default_save_dir(),
    "filename_pattern": "REC_{date}_{time}.mp4",
    "video_codec": "libx264",  # libx264 (H.264) or libx265 (H.265)
    "quality_mode": "crf",     # 'crf' or 'bitrate'
    "crf": 23,                 # 18 (highest quality) to 28 (lower quality)
    "video_bitrate_kbps": 6000,
    "fps": 30,
    "audio_enabled": True,
    "audio_source": "system",  # 'system' (WASAPI Loopback), 'mic', 'mix', 'mute'
    "audio_auto_gain": True,   # Automatically compensate Windows volume attenuation (100% full volume)
    "audio_codec": "aac",      # 'aac' or 'libmp3lame' (mp3)
    "audio_bitrate_kbps": 192, # 128, 192, 256, 320
    "audio_sample_rate": 44100,
    "record_mode": "fullscreen", # 'fullscreen' or 'region'
    "region_x": 100,
    "region_y": 100,
    "region_width": 1280,
    "region_height": 720,
    "auto_open_editor": True,
    "auto_minimize_on_rec": True
}

class ConfigManager:
    def __init__(self, config_path="config.json"):
        self.config_path = Path(config_path)
        self.config = DEFAULT_CONFIG.copy()
        self.load()

    def load(self):
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    self.config.update(loaded)
            except Exception:
                pass
        
        # Verify save_dir is actually writable, otherwise re-route to safe default
        current_save_dir = Path(self.config.get("save_dir", ""))
        try:
            current_save_dir.mkdir(parents=True, exist_ok=True)
            test_f = current_save_dir / ".write_test"
            test_f.write_text("ok")
            test_f.unlink()
        except Exception:
            safe_dir = get_safe_default_save_dir()
            self.config["save_dir"] = safe_dir

        self.save()

    def save(self):
        try:
            save_dir = Path(self.config.get("save_dir", DEFAULT_CONFIG["save_dir"]))
            try:
                save_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                save_dir = Path(get_safe_default_save_dir())
                self.config["save_dir"] = str(save_dir)

            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
        except Exception:
            pass

    def get(self, key, default=None):
        return self.config.get(key, default if default is not None else DEFAULT_CONFIG.get(key))

    def set(self, key, value):
        self.config[key] = value
        self.save()

    def generate_filepath(self) -> str:
        now = datetime.now()
        date_str = now.strftime("%Y%m%d")
        time_str = now.strftime("%H%M%S")
        pattern = self.get("filename_pattern", "REC_{date}_{time}.mp4")
        
        filename = pattern.replace("{date}", date_str).replace("{time}", time_str)
        if not filename.lower().endswith((".mp4", ".mkv", ".mov")):
            filename += ".mp4"
            
        save_dir = Path(self.get("save_dir"))
        try:
            save_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            save_dir = Path(get_safe_default_save_dir())
            save_dir.mkdir(parents=True, exist_ok=True)
            self.config["save_dir"] = str(save_dir)

        return str(save_dir / filename)
