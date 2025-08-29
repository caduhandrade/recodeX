"""Test for profile lookup fix."""

import asyncio
from pathlib import Path
import pytest

from recodex.config import RecodeXConfig, WatchFolder, TranscodeProfile
from recodex.monitoring import MediaFileHandler


def test_profile_lookup_by_name():
    """Test that profile lookup works with profile names."""
    # Create a config with default profiles
    config = RecodeXConfig().get_default_config()
    
    # Create a watch folder with profile name (legacy configuration)
    watch_folder = WatchFolder(
        path=Path("/test/movies"),
        profile="Small File"  # This is the profile NAME, not the key
    )
    
    # Create a mock job queue
    job_queue = asyncio.Queue()
    
    # Create MediaFileHandler instance
    handler = MediaFileHandler(watch_folder, job_queue, config.profiles)
    
    # Test profile lookup by name
    profile = handler._find_profile("Small File")
    assert profile is not None
    assert profile.name == "Small File"
    assert profile.video_codec == "h265"
    assert profile.video_crf == 28


def test_profile_lookup_by_key():
    """Test that profile lookup works with profile keys."""
    # Create a config with default profiles
    config = RecodeXConfig().get_default_config()
    
    # Create a watch folder with profile key (new configuration)
    watch_folder = WatchFolder(
        path=Path("/test/tv"),
        profile="balanced"  # This is the profile KEY
    )
    
    # Create a mock job queue
    job_queue = asyncio.Queue()
    
    # Create MediaFileHandler instance
    handler = MediaFileHandler(watch_folder, job_queue, config.profiles)
    
    # Test profile lookup by key
    profile = handler._find_profile("balanced")
    assert profile is not None
    assert profile.name == "Balanced"
    assert profile.video_codec == "h264"
    assert profile.video_crf == 23


def test_profile_lookup_nonexistent():
    """Test that profile lookup returns None for non-existent profiles."""
    # Create a config with default profiles
    config = RecodeXConfig().get_default_config()
    
    # Create a watch folder with non-existent profile
    watch_folder = WatchFolder(
        path=Path("/test/nothing"),
        profile="Non Existent Profile"
    )
    
    # Create a mock job queue
    job_queue = asyncio.Queue()
    
    # Create MediaFileHandler instance
    handler = MediaFileHandler(watch_folder, job_queue, config.profiles)
    
    # Test profile lookup for non-existent profile
    profile = handler._find_profile("Non Existent Profile")
    assert profile is None


def test_profile_lookup_case_sensitivity():
    """Test that profile lookup is case sensitive."""
    # Create a config with default profiles
    config = RecodeXConfig().get_default_config()
    
    # Create a watch folder
    watch_folder = WatchFolder(
        path=Path("/test/case"),
        profile="balanced"
    )
    
    # Create a mock job queue
    job_queue = asyncio.Queue()
    
    # Create MediaFileHandler instance
    handler = MediaFileHandler(watch_folder, job_queue, config.profiles)
    
    # Test exact match
    profile = handler._find_profile("balanced")
    assert profile is not None
    
    # Test case mismatch
    profile = handler._find_profile("Balanced")
    assert profile is not None  # Should work because it matches profile.name
    
    # Test complete mismatch
    profile = handler._find_profile("BALANCED")
    assert profile is None