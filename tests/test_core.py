"""Tests for RecodeX core functionality."""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock

from recodex.core import HardwareAcceleration, MediaInfo, TranscodeJob, TranscodeEngine
from recodex.config import TranscodeProfile


def test_hardware_acceleration_detection():
    """Test hardware acceleration detection."""
    # Test the detection methods (they may return False in test environment)
    nvidia = HardwareAcceleration.detect_nvidia()
    intel = HardwareAcceleration.detect_intel_qsv()
    amd = HardwareAcceleration.detect_amd_amf()
    vaapi = HardwareAcceleration.detect_vaapi()
    
    # Results should be boolean
    assert isinstance(nvidia, bool)
    assert isinstance(intel, bool)
    assert isinstance(amd, bool)
    assert isinstance(vaapi, bool)
    
    # Test get_available_accelerations
    accelerations = HardwareAcceleration.get_available_accelerations()
    assert isinstance(accelerations, dict)
    assert "nvenc" in accelerations
    assert "qsv" in accelerations
    assert "amf" in accelerations
    assert "vaapi" in accelerations


def test_transcode_job_creation():
    """Test creating a transcode job."""
    profile = TranscodeProfile(
        name="test",
        video_codec="h264",
        audio_codec="aac"
    )
    
    job = TranscodeJob(
        input_path=Path("/input.mp4"),
        output_path=Path("/output.mp4"),
        profile=profile
    )
    
    assert job.input_path == Path("/input.mp4")
    assert job.output_path == Path("/output.mp4")
    assert job.profile == profile
    assert job.status == "pending"
    assert job.progress == 0.0


def test_transcode_job_calculations():
    """Test transcode job calculation methods."""
    profile = TranscodeProfile(name="test")
    job = TranscodeJob(Path("/input.mp4"), Path("/output.mp4"), profile)
    
    # Test with no data
    assert job.get_duration() is None
    assert job.get_compression_ratio() is None
    assert job.get_space_saved() is None
    
    # Test with data
    job.start_time = 100.0
    job.end_time = 150.0
    job.original_size = 1000000
    job.final_size = 500000
    
    assert job.get_duration() == 50.0
    assert job.get_compression_ratio() == 2.0
    assert job.get_space_saved() == 500000


@pytest.mark.asyncio
async def test_media_info_with_mock():
    """Test MediaInfo with mocked ffprobe."""
    # Create a temporary file
    with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as f:
        temp_path = Path(f.name)
    
    try:
        media_info = MediaInfo(temp_path)
        
        # Mock ffmpeg.probe
        mock_info = {
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "h264",
                    "width": 1920,
                    "height": 1080
                },
                {
                    "codec_type": "audio",
                    "codec_name": "aac"
                }
            ],
            "format": {
                "duration": "120.5",
                "bit_rate": "2000000"
            }
        }
        
        with patch('ffmpeg.probe', return_value=mock_info):
            info = await media_info.get_info()
            assert info == mock_info
            
            codec = await media_info.get_video_codec()
            assert codec == "h264"
            
            audio_codec = await media_info.get_audio_codec()
            assert audio_codec == "aac"
            
            duration = await media_info.get_duration()
            assert duration == 120.5
            
            bitrate = await media_info.get_bitrate()
            assert bitrate == 2000000
            
            resolution = await media_info.get_resolution()
            assert resolution == (1920, 1080)
    
    finally:
        temp_path.unlink()


@pytest.mark.asyncio
async def test_needs_transcoding():
    """Test needs_transcoding logic."""
    with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as f:
        temp_path = Path(f.name)
    
    try:
        media_info = MediaInfo(temp_path)
        
        # Mock file info with H.264 video
        mock_info = {
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "h264",
                    "width": 1920,
                    "height": 1080
                }
            ],
            "format": {
                "bit_rate": "5000000"  # 5 Mbps
            }
        }
        
        with patch('ffmpeg.probe', return_value=mock_info):
            # Profile wants H.265 - should need transcoding
            h265_profile = TranscodeProfile(
                name="h265_profile",
                video_codec="h265"
            )
            
            needs_transcode = await media_info.needs_transcoding(h265_profile)
            assert needs_transcode is True
            
            # Profile wants H.264 - should not need transcoding
            h264_profile = TranscodeProfile(
                name="h264_profile",
                video_codec="h264"
            )
            
            needs_transcode = await media_info.needs_transcoding(h264_profile)
            assert needs_transcode is False
    
    finally:
        temp_path.unlink()


def test_transcode_engine_creation():
    """Test creating a transcode engine."""
    engine = TranscodeEngine()
    
    # Should have hardware acceleration info
    assert isinstance(engine.hardware_accel, dict)
    assert "nvenc" in engine.hardware_accel


def test_transcode_engine_video_options():
    """Test video encoding options generation."""
    engine = TranscodeEngine()
    
    # Test H.264 profile
    h264_profile = TranscodeProfile(
        name="h264_test",
        video_codec="h264",
        video_crf=23,
        preset="medium",
        hardware_accel=False  # Force software encoding for predictable results
    )
    
    options = engine._get_video_options(h264_profile)
    
    assert options["c:v"] == "libx264"
    assert options["crf"] == "23"
    assert options["preset"] == "medium"


def test_transcode_engine_audio_options():
    """Test audio encoding options generation."""
    engine = TranscodeEngine()
    
    # Test copy audio
    copy_profile = TranscodeProfile(
        name="copy_test",
        audio_codec="copy"
    )
    
    options = engine._get_audio_options(copy_profile)
    assert options["c:a"] == "copy"
    
    # Test AAC encoding
    aac_profile = TranscodeProfile(
        name="aac_test",
        audio_codec="aac",
        audio_bitrate="128k",
        audio_normalize=True
    )
    
    options = engine._get_audio_options(aac_profile)
    assert options["c:a"] == "aac"
    assert options["b:a"] == "128k"
    assert options["af"] == "loudnorm"


@pytest.mark.asyncio
async def test_transcode_job_dry_run():
    """Test transcode job execution (mocked)."""
    # This test would require extensive mocking of ffmpeg
    # For now, we'll just test the job creation and basic properties
    
    profile = TranscodeProfile(
        name="test_profile",
        video_codec="h264",
        audio_codec="aac"
    )
    
    with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as input_file:
        input_path = Path(input_file.name)
        input_file.write(b"fake video data")
    
    with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as output_file:
        output_path = Path(output_file.name)
    
    try:
        job = TranscodeJob(input_path, output_path, profile)
        engine = TranscodeEngine()
        
        # Mock the ffmpeg execution
        with patch.object(engine, '_run_ffmpeg') as mock_ffmpeg:
            # Mock successful completion
            mock_process = Mock()
            mock_process.returncode = 0
            mock_ffmpeg.return_value = mock_process
            
            # Mock temp file creation
            with patch('pathlib.Path.replace'):
                result = await engine.transcode(job)
            
            # Job should be marked as completed
            assert result is True
            assert job.status == "completed"
            assert job.start_time is not None
    
    finally:
        input_path.unlink()
        if output_path.exists():
            output_path.unlink()