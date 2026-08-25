import json
import os
from pathlib import Path
from datetime import datetime

DEFAULT_CONFIG = {
    "save_dir": str(Path.home() / "Videos" / "Recordings"),
    "filename_pattern": "REC_{date}_{time}.mp4",
    "video_codec": "libx264",  # libx264 (H.264) or libx265 (H.265)
    "quality_mode": "crf",     # 'crf' or 'bitrate'
    "crf": 23,                 # 18 (highest quality) to 28 (lower quality)
    "video_bitrate_kbps": 6000,
    "fps": 30,
    "audio_enabled": True,
    "audio_source": "system",  # 'system' (WASAPI Loopback), 'mic', 'mix', 'mute'
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
            except Exception as e:
                print(f"Error loading config: {e}")
        self.save()

    def save(self):
        try:
            save_dir = Path(self.config.get("save_dir", DEFAULT_CONFIG["save_dir"]))
            save_dir.mkdir(parents=True, exist_ok=True)
            
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving config: {e}")

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
        save_dir.mkdir(parents=True, exist_ok=True)
        return str(save_dir / filename)
