"""Tests for RecodeX configuration."""

import pytest
from pathlib import Path
import tempfile
import yaml

from recodex.config import RecodeXConfig, TranscodeProfile, WatchFolder, load_config


def test_transcode_profile_creation():
    """Test creating a transcode profile."""
    profile = TranscodeProfile(
        name="test_profile",
        video_codec="h264",
        audio_codec="aac",
        container="mp4"
    )
    
    assert profile.name == "test_profile"
    assert profile.video_codec == "h264"
    assert profile.audio_codec == "aac"
    assert profile.container == "mp4"
    assert profile.hardware_accel is True  # Default value


def test_watch_folder_creation():
    """Test creating a watch folder configuration."""
    folder = WatchFolder(
        path=Path("/test/path"),
        profile="test_profile"
    )
    
    assert folder.path == Path("/test/path")
    assert folder.profile == "test_profile"
    assert folder.recursive is True  # Default value
    assert ".mp4" in folder.extensions  # Default extensions


def test_config_creation():
    """Test creating a RecodeX configuration."""
    config = RecodeXConfig()
    
    assert config.watch_folders == []
    assert config.profiles == {}
    assert config.database.url == "sqlite:///recodex.db"
    assert config.web.host == "127.0.0.1"
    assert config.web.port == 8000
    assert config.worker.max_workers == 2


def test_default_config_generation():
    """Test generating default configuration."""
    config = RecodeXConfig().get_default_config()
    
    assert len(config.profiles) == 3  # high_quality, balanced, small_file
    assert "high_quality" in config.profiles
    assert "balanced" in config.profiles
    assert "small_file" in config.profiles
    
    # Check high quality profile
    hq_profile = config.profiles["high_quality"]
    assert hq_profile.video_codec == "h265"
    assert hq_profile.container == "mkv"


def test_config_yaml_serialization():
    """Test YAML serialization and deserialization."""
    # Create a config with some data
    config = RecodeXConfig()
    config.profiles["test"] = TranscodeProfile(
        name="test",
        video_codec="h264",
        audio_codec="aac"
    )
    config.watch_folders.append(WatchFolder(
        path=Path("/test"),
        profile="test"
    ))
    
    # Save to temporary file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        temp_path = Path(f.name)
    
    try:
        config.to_yaml(temp_path)
        
        # Load back
        loaded_config = RecodeXConfig.from_yaml(temp_path)
        
        assert len(loaded_config.profiles) == 1
        assert "test" in loaded_config.profiles
        assert len(loaded_config.watch_folders) == 1
        assert str(loaded_config.watch_folders[0].path) == "/test"
        
    finally:
        temp_path.unlink()


def test_load_config_nonexistent_file():
    """Test loading configuration from non-existent file."""
    with tempfile.TemporaryDirectory() as temp_dir:
        non_existent_path = Path(temp_dir) / "non_existent" / "config.yaml"
        config = load_config(non_existent_path)
        
        # Should return default config
        assert len(config.profiles) == 3  # Default profiles