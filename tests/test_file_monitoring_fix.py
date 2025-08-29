"""Test for the file monitoring asyncio fix."""

import asyncio
import tempfile
import pytest
from pathlib import Path
from unittest.mock import Mock, patch

from recodex.config import WatchFolder, TranscodeProfile
from recodex.monitoring import MediaFileHandler


@pytest.mark.asyncio
async def test_file_handler_async_task_creation():
    """Test that MediaFileHandler can handle file events without crashing."""
    # Create temporary directory
    with tempfile.TemporaryDirectory() as temp_dir:
        watch_path = Path(temp_dir)
        
        # Create watch folder configuration
        watch_folder = WatchFolder(
            path=watch_path,
            profile="test_profile",
            extensions=[".mp4", ".mkv"],
            recursive=False
        )
        
        # Create test profile
        profile = TranscodeProfile(
            name="Test Profile",
            video_codec="h264",
            audio_codec="aac",
            container="mp4"
        )
        profiles = {"test_profile": profile}
        
        # Create job queue and event loop
        job_queue = asyncio.Queue()
        event_loop = asyncio.get_running_loop()
        
        # Create handler
        handler = MediaFileHandler(watch_folder, job_queue, profiles, event_loop)
        
        # Mock the _process_new_file method to avoid file processing logic
        async def mock_process_file(file_path):
            """Mock coroutine for _process_new_file."""
            pass
        
        handler._process_new_file = mock_process_file
        
        # Create a mock event
        mock_event = Mock()
        mock_event.is_directory = False
        mock_event.src_path = str(watch_path / "test.mp4")
        
        # Test that on_created doesn't raise an exception
        # This would previously fail with "RuntimeWarning: coroutine was never awaited"
        try:
            handler.on_created(mock_event)
            # Give time for the coroutine to be scheduled
            await asyncio.sleep(0.1)
            assert True, "on_created should not raise an exception"
        except Exception as e:
            pytest.fail(f"on_created raised an exception: {e}")
        
        # Test on_moved as well
        mock_event.dest_path = mock_event.src_path
        try:
            handler.on_moved(mock_event)
            await asyncio.sleep(0.1)
            assert True, "on_moved should not raise an exception"
        except Exception as e:
            pytest.fail(f"on_moved raised an exception: {e}")


@pytest.mark.asyncio
async def test_event_loop_reference():
    """Test that the MediaFileHandler correctly stores the event loop reference."""
    # Create minimal test setup
    watch_folder = WatchFolder(
        path=Path("/tmp"),
        profile="test",
        extensions=[".mp4"]
    )
    
    job_queue = asyncio.Queue()
    event_loop = asyncio.get_running_loop()
    profiles = {}
    
    # Create handler
    handler = MediaFileHandler(watch_folder, job_queue, profiles, event_loop)
    
    # Verify event loop is stored
    assert handler.event_loop is event_loop
    assert hasattr(handler, 'event_loop')


@pytest.mark.asyncio
async def test_future_result_handling():
    """Test that MediaFileHandler properly handles Future results from run_coroutine_threadsafe."""
    # Create temporary directory
    with tempfile.TemporaryDirectory() as temp_dir:
        watch_path = Path(temp_dir)
        
        # Create watch folder configuration
        watch_folder = WatchFolder(
            path=watch_path,
            profile="test_profile",
            extensions=[".mp4", ".mkv"],
            recursive=False
        )
        
        # Create test profile
        profile = TranscodeProfile(
            name="Test Profile",
            video_codec="h264",
            audio_codec="aac",
            container="mp4"
        )
        profiles = {"test_profile": profile}
        
        # Create job queue and event loop
        job_queue = asyncio.Queue()
        event_loop = asyncio.get_running_loop()
        
        # Create handler
        handler = MediaFileHandler(watch_folder, job_queue, profiles, event_loop)
        
        # Mock the _process_new_file method to simulate an exception
        async def mock_process_file_with_error(file_path):
            """Mock coroutine that raises an exception."""
            raise ValueError("Test exception")
        
        handler._process_new_file = mock_process_file_with_error
        
        # Track if the future callback was called
        callback_called = asyncio.Event()
        original_callback = handler._handle_future_result
        
        def tracking_callback(future):
            original_callback(future)
            callback_called.set()
        
        handler._handle_future_result = tracking_callback
        
        # Create a mock event
        mock_event = Mock()
        mock_event.is_directory = False
        mock_event.src_path = str(watch_path / "test.mp4")
        
        # Test that on_created properly handles the future even with exceptions
        handler.on_created(mock_event)
        
        # Wait for the callback to be called
        await asyncio.wait_for(callback_called.wait(), timeout=2.0)
        
        assert callback_called.is_set(), "Future callback should have been called"


def test_handler_initialization():
    """Test that MediaFileHandler requires event_loop parameter."""
    watch_folder = WatchFolder(
        path=Path("/tmp"),
        profile="test",
        extensions=[".mp4"]
    )
    
    job_queue = asyncio.Queue()
    event_loop = asyncio.new_event_loop()
    profiles = {}
    
    # Should work with event_loop parameter
    handler = MediaFileHandler(watch_folder, job_queue, profiles, event_loop)
    assert handler.event_loop is event_loop
    
    # Should fail without event_loop parameter (this tests the old signature)
    with pytest.raises(TypeError):
        MediaFileHandler(watch_folder, job_queue, profiles)