#!/usr/bin/env python3
"""
Simple script to start RecodeX web interface for demonstration.
"""

import asyncio
import tempfile
from pathlib import Path
from datetime import datetime

from recodex.config import RecodeXConfig
from recodex.web import WebDashboard
from recodex.database import DatabaseManager, TranscodeRecord
from recodex.workers import RecodeXService
import uvicorn


async def setup_demo_data():
    """Setup demo data for the web interface."""
    # Create temporary database
    db_file = Path("/tmp/demo_recodex.db")
    if db_file.exists():
        db_file.unlink()
    
    db_url = f"sqlite:///{db_file}"
    db_manager = DatabaseManager(db_url)
    await db_manager.initialize()
    
    # Create sample jobs for demonstration
    jobs = [
        TranscodeRecord(
            input_path="/demo/video1.mp4",
            output_path="/demo/video1_compressed.mp4",
            profile_name="high_quality",
            status="pending",
            original_size=5000000
        ),
        TranscodeRecord(
            input_path="/demo/video2.mkv",
            output_path="/demo/video2_compressed.mp4", 
            profile_name="mobile",
            status="pending",
            original_size=3000000
        ),
        TranscodeRecord(
            input_path="/demo/movie1.avi",
            output_path="/demo/movie1_compressed.mp4",
            profile_name="high_quality",
            status="completed",
            completed_at=datetime.utcnow(),
            processing_time=120.5,
            original_size=15000000,
            final_size=8000000,
            original_codec="xvid",
            final_codec="h264"
        ),
        TranscodeRecord(
            input_path="/demo/movie2.wmv",
            output_path="/demo/movie2_compressed.mp4",
            profile_name="streaming",
            status="completed", 
            completed_at=datetime.utcnow(),
            processing_time=95.2,
            original_size=12000000,
            final_size=6500000,
            original_codec="wmv3",
            final_codec="h264"
        ),
        TranscodeRecord(
            input_path="/demo/corrupted.mp4",
            output_path="/demo/corrupted_compressed.mp4",
            profile_name="high_quality",
            status="failed",
            error_message="Input file is corrupted or unreadable",
            original_size=8000000
        ),
        TranscodeRecord(
            input_path="/demo/unsupported.flv",
            output_path="/demo/unsupported_compressed.mp4",
            profile_name="mobile",
            status="failed", 
            error_message="Codec not supported by hardware acceleration",
            original_size=2500000
        )
    ]
    
    # Add jobs to database
    for job in jobs:
        await db_manager.add_record(job)
    
    print(f"✅ Created demo database with {len(jobs)} sample jobs")
    await db_manager.close()
    return db_file


def main():
    """Start the web interface with demo data."""
    print("🎬 Starting RecodeX Web Interface Demo")
    print("=" * 50)
    
    # Setup demo data
    db_file = asyncio.run(setup_demo_data())
    
    # Create minimal config for web interface
    config = RecodeXConfig()
    
    # Create mock service with database
    class MockService:
        def __init__(self, db_file):
            self.db_manager = DatabaseManager(f"sqlite:///{db_file}")
            self.worker_manager = None
            self.config_path = None
            
        def get_status(self):
            return {
                "service_running": True,
                "ffmpeg_running": True,
                "active_jobs_count": 0,
                "file_monitor": {
                    "running": True,
                    "watch_folders": 2,
                    "queue_size": 2
                },
                "workers": [
                    {
                        "worker_id": 1,
                        "running": True,
                        "current_job": None
                    },
                    {
                        "worker_id": 2, 
                        "running": True,
                        "current_job": None
                    }
                ]
            }
        
        async def get_statistics(self):
            return {
                "total_processed": 2,
                "total_space_saved": 12500000,
                "total_original_size": 27000000,
                "average_compression_ratio": 1.86,
                "average_processing_time": 107.85
            }
    
    service = MockService(db_file)
    
    # Initialize database
    asyncio.run(service.db_manager.initialize())
    
    # Create web dashboard
    dashboard = WebDashboard(config, service)
    
    print("🌐 Starting web server on http://localhost:8000")
    print("\nTo see the improvements:")
    print("1. Open http://localhost:8000 in your browser")
    print("2. Navigate to the job management tabs")
    print("3. Try the 'Reprocess' buttons on completed/failed jobs")
    print("\nPress Ctrl+C to stop the server")
    print("=" * 50)
    
    # Start the web server
    uvicorn.run(dashboard.app, host="127.0.0.1", port=8000, log_level="warning")


if __name__ == "__main__":
    main()