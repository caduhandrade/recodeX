"""Configuration management for RecodeX."""

from pathlib import Path
from typing import Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict
from pydantic_settings import BaseSettings
import yaml


class TranscodeProfile(BaseModel):
    """Configuration for a transcoding profile."""
    
    name: str
    video_codec: str = "h264"  # h264, h265, av1
    video_bitrate: Optional[str] = None  # e.g., "2M", "1500k"
    video_crf: Optional[int] = 23  # Constant Rate Factor (0-51)
    audio_codec: str = "copy"  # copy, aac, opus, ac3
    audio_bitrate: Optional[str] = None
    audio_normalize: bool = False
    subtitles: str = "copy"  # copy, embed, none
    container: str = "mp4"  # mp4, mkv
    hardware_accel: bool = True
    preset: str = "medium"  # ultrafast, superfast, veryfast, faster, fast, medium, slow, slower, veryslow


class WatchFolder(BaseModel):
    """Configuration for a watch folder."""
    
    path: Path
    profile: str
    recursive: bool = True
    extensions: List[str] = Field(default_factory=lambda: [
        ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".m4v", ".webm"
    ])
    output_path: Optional[Path] = None
    delete_original: bool = False


class DatabaseConfig(BaseModel):
    """Database configuration."""
    
    url: str = "sqlite:///recodex.db"
    echo: bool = False


class WebConfig(BaseModel):
    """Web interface configuration."""
    
    host: str = "127.0.0.1"
    port: int = 8000
    reload: bool = False


class WorkerConfig(BaseModel):
    """Worker configuration."""
    
    max_workers: int = 2
    temp_dir: Optional[Path] = None
    dry_run: bool = False


class RecodeXConfig(BaseSettings):
    """Main configuration for RecodeX."""
    
    # Core settings
    watch_folders: List[WatchFolder] = Field(default_factory=list)
    profiles: Dict[str, TranscodeProfile] = Field(default_factory=dict)
    
    # Component configs
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    web: WebConfig = Field(default_factory=WebConfig)
    worker: WorkerConfig = Field(default_factory=WorkerConfig)
    
    # Logging
    log_level: str = "INFO"
    log_file: Optional[Path] = None
    
    model_config = ConfigDict(env_prefix="RECODEX_", env_nested_delimiter="__")
    
    @classmethod
    def from_yaml(cls, path: Path) -> "RecodeXConfig":
        """Load configuration from YAML file."""
        if not path.exists():
            return cls()
        
        with open(path, "r") as f:
            data = yaml.safe_load(f) or {}
        
        return cls(**data)
    
    def to_yaml(self, path: Path) -> None:
        """Save configuration to YAML file."""
        data = self.model_dump(mode="json")
        
        # Convert Path objects to strings for YAML serialization
        def convert_paths(obj):
            if isinstance(obj, dict):
                return {k: convert_paths(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_paths(item) for item in obj]
            elif isinstance(obj, Path):
                return str(obj)
            return obj
        
        data = convert_paths(data)
        
        with open(path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
    
    def get_default_config(self) -> "RecodeXConfig":
        """Create a default configuration."""
        default_profiles = {
            "high_quality": TranscodeProfile(
                name="High Quality",
                video_codec="h265",
                video_crf=20,
                audio_codec="copy",
                container="mkv",
                preset="slow"
            ),
            "balanced": TranscodeProfile(
                name="Balanced",
                video_codec="h264",
                video_crf=23,
                audio_codec="aac",
                audio_bitrate="128k",
                container="mp4",
                preset="medium"
            ),
            "small_file": TranscodeProfile(
                name="Small File",
                video_codec="h265",
                video_crf=28,
                audio_codec="aac",
                audio_bitrate="96k",
                container="mp4",
                preset="slower"
            )
        }
        
        return RecodeXConfig(profiles=default_profiles)


def get_config_path() -> Path:
    """Get the default configuration file path."""
    return Path.home() / ".config" / "recodex" / "config.yaml"


def load_config(config_path: Optional[Path] = None) -> RecodeXConfig:
    """Load configuration from file or create default."""
    if config_path is None:
        config_path = get_config_path()
    
    if config_path.exists():
        return RecodeXConfig.from_yaml(config_path)
    else:
        # Create default config
        config = RecodeXConfig().get_default_config()
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config.to_yaml(config_path)
        return config