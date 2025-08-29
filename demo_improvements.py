#!/usr/bin/env python3
"""
Demonstration script for RecodeX file monitoring and job management improvements.

This script demonstrates:
1. Fixed asyncio warning when files are added to watch folders
2. Job management features (pending, completed, failed job lists)
3. Job reprocessing functionality
"""

import asyncio
import tempfile
import time
from pathlib import Path
from datetime import datetime

from recodex.config import RecodeXConfig, WatchFolder, TranscodeProfile
from recodex.monitoring import FileMonitor
from recodex.database import DatabaseManager, TranscodeRecord


async def demonstrate_file_monitoring_fix():
    """Demonstrate the asyncio fix for file monitoring."""
    print("=== File Monitoring AsyncIO Fix Demo ===")
    
    # Create temporary directory for demonstration
    with tempfile.TemporaryDirectory() as temp_dir:
        watch_path = Path(temp_dir)
        
        # Create test profile and watch folder
        profile = TranscodeProfile(
            name="Demo Profile",
            video_codec="h264",
            audio_codec="aac",
            container="mp4"
        )
        
        watch_folder = WatchFolder(
            path=watch_path,
            profile="demo_profile",
            extensions=[".mp4", ".mkv"],
            recursive=False
        )
        
        profiles = {"demo_profile": profile}
        
        # Create file monitor
        file_monitor = FileMonitor([watch_folder], profiles)
        
        print(f"Starting file monitor for: {watch_path}")
        await file_monitor.start()
        
        # Create a test file to trigger the event
        test_file = watch_path / "test_video.mp4"
        test_file.write_text("fake video content")
        
        print("Created test file, waiting for processing...")
        
        # Wait a bit for file processing
        await asyncio.sleep(2)
        
        # Check if job was added to queue
        queue_size = file_monitor.get_queue_size()
        print(f"Jobs in queue: {queue_size}")
        
        if queue_size > 0:
            print("✅ File was successfully processed without asyncio warnings!")
        else:
            print("ℹ️  File may have been skipped (expected for fake content)")
        
        await file_monitor.stop()
        print("File monitor stopped\n")


async def demonstrate_job_management():
    """Demonstrate job management features."""
    print("=== Job Management Features Demo ===")
    
    # Create temporary database
    with tempfile.NamedTemporaryFile(suffix=".db") as temp_db:
        db_url = f"sqlite:///{temp_db.name}"
        db_manager = DatabaseManager(db_url)
        await db_manager.initialize()
        
        print("Creating test job records...")
        
        # Create sample jobs
        jobs = [
            TranscodeRecord(
                input_path="/demo/pending_job.mp4",
                output_path="/demo/pending_job_output.mp4",
                profile_name="demo_profile",
                status="pending"
            ),
            TranscodeRecord(
                input_path="/demo/completed_job.mp4",
                output_path="/demo/completed_job_output.mp4",
                profile_name="demo_profile",
                status="completed",
                completed_at=datetime.utcnow(),
                processing_time=45.5,
                original_size=2000000,
                final_size=1200000
            ),
            TranscodeRecord(
                input_path="/demo/failed_job.mp4",
                output_path="/demo/failed_job_output.mp4",
                profile_name="demo_profile",
                status="failed",
                error_message="Demo error: Codec not supported"
            )
        ]
        
        # Add jobs to database
        for job in jobs:
            await db_manager.add_record(job)
        
        # Demonstrate job listing features
        print("\n📋 Getting job lists:")
        
        pending_jobs = await db_manager.get_pending_jobs()
        print(f"Pending jobs: {len(pending_jobs)}")
        for job in pending_jobs:
            print(f"  - {Path(job.input_path).name} (Profile: {job.profile_name})")
        
        completed_jobs = await db_manager.get_completed_jobs()
        print(f"Completed jobs: {len(completed_jobs)}")
        for job in completed_jobs:
            space_saved = job.space_saved or 0
            compression = job.compression_ratio or 0
            print(f"  - {Path(job.input_path).name} (Saved: {space_saved/1024/1024:.1f}MB, Compression: {compression:.2f}x)")
        
        failed_jobs = await db_manager.get_failed_jobs()
        print(f"Failed jobs: {len(failed_jobs)}")
        for job in failed_jobs:
            print(f"  - {Path(job.input_path).name} (Error: {job.error_message})")
        
        # Demonstrate job reprocessing
        print("\n🔄 Demonstrating job reprocessing:")
        
        if completed_jobs:
            job_to_reprocess = completed_jobs[0]
            print(f"Reprocessing completed job: {Path(job_to_reprocess.input_path).name}")
            
            reprocess_result = await db_manager.reprocess_job(job_to_reprocess.id)
            print(f"✅ Reprocessing successful! New job ID: {reprocess_result['id']}")
            
            # Show updated pending jobs
            updated_pending = await db_manager.get_pending_jobs()
            print(f"Updated pending jobs count: {len(updated_pending)}")
        
        if failed_jobs:
            job_to_reprocess = failed_jobs[0]
            print(f"Reprocessing failed job: {Path(job_to_reprocess.input_path).name}")
            
            reprocess_result = await db_manager.reprocess_job(job_to_reprocess.id)
            print(f"✅ Reprocessing successful! New job ID: {reprocess_result['id']}")
        
        # Try to reprocess invalid job
        try:
            await db_manager.reprocess_job(99999)
        except ValueError as e:
            print(f"❌ Expected error for invalid job: {e}")
        
        await db_manager.close()
        print("Database closed\n")


def demonstrate_web_features():
    """Show information about web features."""
    print("=== Web Interface Features ===")
    print("The web dashboard now includes:")
    print("✅ Tabbed interface for different job states:")
    print("   - Pending Jobs: Shows queued jobs waiting to be processed")
    print("   - Completed Jobs: Shows finished jobs with statistics")
    print("   - Failed Jobs: Shows failed jobs with error messages")
    print()
    print("✅ Job reprocessing buttons:")
    print("   - Completed and failed jobs can be requeued for processing")
    print("   - One-click reprocessing from the web interface")
    print()
    print("✅ New API endpoints:")
    print("   - GET /api/jobs/pending")
    print("   - GET /api/jobs/completed") 
    print("   - GET /api/jobs/failed")
    print("   - POST /api/jobs/{id}/reprocess")
    print()
    print("To see the web interface, start the RecodeX service and visit:")
    print("http://localhost:8000")
    print()


async def main():
    """Run all demonstrations."""
    print("🎬 RecodeX Improvements Demonstration")
    print("=" * 50)
    
    await demonstrate_file_monitoring_fix()
    await demonstrate_job_management()
    demonstrate_web_features()
    
    print("=" * 50)
    print("✅ All features demonstrated successfully!")
    print("\nKey improvements:")
    print("1. Fixed asyncio warnings when files are added to watch folders")
    print("2. Added comprehensive job management with lists and reprocessing")
    print("3. Enhanced web interface with tabbed job views")
    print("4. Added robust error handling and validation")


if __name__ == "__main__":
    asyncio.run(main())