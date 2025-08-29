"""Test for job management and reprocessing functionality."""

import asyncio
import tempfile
import pytest
from pathlib import Path
from datetime import datetime

from recodex.database import DatabaseManager, TranscodeRecord


@pytest.mark.asyncio
async def test_job_list_methods():
    """Test that we can get pending, completed, and failed job lists."""
    # Create a temporary database
    with tempfile.NamedTemporaryFile(suffix=".db") as temp_db:
        db_url = f"sqlite:///{temp_db.name}"
        db_manager = DatabaseManager(db_url)
        await db_manager.initialize()
        
        # Create some test records
        test_records = [
            TranscodeRecord(
                input_path="/test/input1.mp4",
                output_path="/test/output1.mp4",
                profile_name="test_profile",
                status="pending"
            ),
            TranscodeRecord(
                input_path="/test/input2.mp4",
                output_path="/test/output2.mp4",
                profile_name="test_profile",
                status="completed",
                completed_at=datetime.utcnow(),
                processing_time=60.0,
                original_size=1000000,
                final_size=500000
            ),
            TranscodeRecord(
                input_path="/test/input3.mp4",
                output_path="/test/output3.mp4",
                profile_name="test_profile",
                status="failed",
                error_message="Test error"
            )
        ]
        
        # Add records to database
        for record in test_records:
            await db_manager.add_record(record)
        
        # Test getting job lists
        pending_jobs = await db_manager.get_pending_jobs()
        completed_jobs = await db_manager.get_completed_jobs()
        failed_jobs = await db_manager.get_failed_jobs()
        
        assert len(pending_jobs) == 1
        assert len(completed_jobs) == 1
        assert len(failed_jobs) == 1
        
        assert pending_jobs[0].status == "pending"
        assert completed_jobs[0].status == "completed"
        assert failed_jobs[0].status == "failed"
        
        await db_manager.close()


@pytest.mark.asyncio
async def test_job_reprocessing():
    """Test that we can reprocess completed and failed jobs."""
    # Create a temporary database
    with tempfile.NamedTemporaryFile(suffix=".db") as temp_db:
        db_url = f"sqlite:///{temp_db.name}"
        db_manager = DatabaseManager(db_url)
        await db_manager.initialize()
        
        # Create a completed job
        completed_record = TranscodeRecord(
            input_path="/test/input.mp4",
            output_path="/test/output.mp4",
            profile_name="test_profile",
            status="completed",
            completed_at=datetime.utcnow(),
            processing_time=60.0,
            original_size=1000000,
            final_size=500000
        )
        
        await db_manager.add_record(completed_record)
        
        # Get the record ID
        completed_jobs = await db_manager.get_completed_jobs()
        job_id = completed_jobs[0].id
        
        # Test reprocessing
        reprocess_result = await db_manager.reprocess_job(job_id)
        
        assert reprocess_result["status"] == "pending"
        assert reprocess_result["input_path"] == "/test/input.mp4"
        assert reprocess_result["output_path"] == "/test/output.mp4"
        assert reprocess_result["profile_name"] == "test_profile"
        
        # Check that a new pending job was created
        pending_jobs = await db_manager.get_pending_jobs()
        assert len(pending_jobs) == 1
        assert pending_jobs[0].id == reprocess_result["id"]
        assert pending_jobs[0].status == "pending"
        
        await db_manager.close()


@pytest.mark.asyncio
async def test_reprocess_invalid_job():
    """Test that reprocessing fails for invalid job states."""
    # Create a temporary database
    with tempfile.NamedTemporaryFile(suffix=".db") as temp_db:
        db_url = f"sqlite:///{temp_db.name}"
        db_manager = DatabaseManager(db_url)
        await db_manager.initialize()
        
        # Create a pending job (should not be reprocessable)
        pending_record = TranscodeRecord(
            input_path="/test/input.mp4",
            output_path="/test/output.mp4",
            profile_name="test_profile",
            status="pending"
        )
        
        await db_manager.add_record(pending_record)
        
        # Get the record ID
        pending_jobs = await db_manager.get_pending_jobs()
        job_id = pending_jobs[0].id
        
        # Test reprocessing should fail
        with pytest.raises(ValueError, match="cannot be reprocessed"):
            await db_manager.reprocess_job(job_id)
        
        # Test reprocessing non-existent job
        with pytest.raises(ValueError, match="not found"):
            await db_manager.reprocess_job(99999)
        
        await db_manager.close()