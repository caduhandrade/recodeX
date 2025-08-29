"""Integration test for the web API endpoints."""

import asyncio
import tempfile
import pytest
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock

from fastapi.testclient import TestClient
from recodex.web import WebDashboard
from recodex.config import RecodeXConfig
from recodex.database import DatabaseManager, TranscodeRecord


@pytest.mark.asyncio
async def test_web_api_endpoints():
    """Test that the new web API endpoints work correctly."""
    # Create a temporary database
    with tempfile.NamedTemporaryFile(suffix=".db") as temp_db:
        db_url = f"sqlite:///{temp_db.name}"
        db_manager = DatabaseManager(db_url)
        await db_manager.initialize()
        
        # Create test records
        test_records = [
            TranscodeRecord(
                input_path="/test/pending.mp4",
                output_path="/test/pending_out.mp4",
                profile_name="test_profile",
                status="pending"
            ),
            TranscodeRecord(
                input_path="/test/completed.mp4",
                output_path="/test/completed_out.mp4",
                profile_name="test_profile",
                status="completed",
                completed_at=datetime.utcnow(),
                processing_time=60.0,
                original_size=1000000,
                final_size=500000
            ),
            TranscodeRecord(
                input_path="/test/failed.mp4",
                output_path="/test/failed_out.mp4",
                profile_name="test_profile",
                status="failed",
                error_message="Test error"
            )
        ]
        
        # Add records to database
        for record in test_records:
            await db_manager.add_record(record)
        
        # Create mock service with database
        mock_service = Mock()
        mock_service.db_manager = db_manager
        mock_service.worker_manager = None
        
        # Create config and web dashboard
        config = RecodeXConfig()
        dashboard = WebDashboard(config, mock_service)
        
        # Create test client
        client = TestClient(dashboard.app)
        
        # Test pending jobs endpoint
        response = client.get("/api/jobs/pending")
        assert response.status_code == 200
        pending_jobs = response.json()
        assert len(pending_jobs) == 1
        assert pending_jobs[0]["status"] == "pending"
        assert pending_jobs[0]["input_path"] == "/test/pending.mp4"
        
        # Test completed jobs endpoint
        response = client.get("/api/jobs/completed")
        assert response.status_code == 200
        completed_jobs = response.json()
        assert len(completed_jobs) == 1
        assert completed_jobs[0]["status"] == "completed"
        assert completed_jobs[0]["input_path"] == "/test/completed.mp4"
        assert completed_jobs[0]["processing_time"] == 60.0
        
        # Test failed jobs endpoint
        response = client.get("/api/jobs/failed")
        assert response.status_code == 200
        failed_jobs = response.json()
        assert len(failed_jobs) == 1
        assert failed_jobs[0]["status"] == "failed"
        assert failed_jobs[0]["input_path"] == "/test/failed.mp4"
        assert failed_jobs[0]["error_message"] == "Test error"
        
        # Test reprocessing completed job
        completed_job_id = completed_jobs[0]["id"]
        response = client.post(f"/api/jobs/{completed_job_id}/reprocess")
        assert response.status_code == 200
        reprocess_result = response.json()
        assert reprocess_result["status"] == "success"
        assert "new_job" in reprocess_result
        
        # Verify new pending job was created
        response = client.get("/api/jobs/pending")
        assert response.status_code == 200
        pending_jobs = response.json()
        assert len(pending_jobs) == 2  # Original pending + reprocessed
        
        # Test reprocessing invalid job (should fail)
        response = client.post("/api/jobs/99999/reprocess")
        assert response.status_code == 400
        
        await db_manager.close()


def test_web_dashboard_creation():
    """Test that WebDashboard can be created successfully."""
    mock_service = Mock()
    config = RecodeXConfig()
    
    dashboard = WebDashboard(config, mock_service)
    assert dashboard.app is not None
    assert dashboard.config is config
    assert dashboard.service is mock_service