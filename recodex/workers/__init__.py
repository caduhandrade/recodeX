"""Worker system for processing transcoding jobs."""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from ..config import RecodeXConfig, TranscodeProfile
from ..core import TranscodeEngine, TranscodeJob
from ..database import DatabaseManager, TranscodeRecord
from ..monitoring import FileMonitor
from ..web import run_web_server

logger = logging.getLogger(__name__)


class TranscodeWorker:
    """Individual worker for processing transcoding jobs."""
    
    def __init__(self, worker_id: int, db_manager: DatabaseManager, config: RecodeXConfig):
        self.worker_id = worker_id
        self.db_manager = db_manager
        self.config = config
        self.transcode_engine = TranscodeEngine()
        self.current_job: Optional[TranscodeJob] = None
        self.running = False
    
    async def start(self, file_monitor: FileMonitor):
        """Start the worker loop."""
        self.running = True
        logger.info(f"Worker {self.worker_id} started")
        
        while self.running:
            try:
                # Get next job from monitor
                job_data = await file_monitor.get_job()
                
                if not job_data:
                    continue
                
                await self._process_job(job_data, file_monitor)
                
            except Exception as e:
                logger.error(f"Worker {self.worker_id} error: {e}")
                await asyncio.sleep(5)  # Wait before retrying
        
        logger.info(f"Worker {self.worker_id} stopped")
    
    async def stop(self):
        """Stop the worker."""
        self.running = False
        
        # Wait for current job to finish if running
        if self.current_job and self.current_job.status == "running":
            logger.info(f"Worker {self.worker_id} waiting for current job to finish...")
            # In a real implementation, we might want to interrupt the job
            # For now, we'll let it complete naturally
    
    async def _process_job(self, job_data: dict, file_monitor: FileMonitor):
        """Process a single transcoding job."""
        input_path = job_data["input_path"]
        output_path = job_data["output_path"]
        profile = job_data["profile"]
        
        logger.info(f"Worker {self.worker_id} processing: {input_path}")
        
        # Create database record
        record = TranscodeRecord(
            input_path=str(input_path),
            output_path=str(output_path),
            profile_name=profile.name,
            status="pending",
            created_at=datetime.utcnow()
        )
        
        # Add to database
        await self.db_manager.add_record(record)
        
        try:
            # Create transcoding job
            self.current_job = TranscodeJob(input_path, output_path, profile)
            
            # Update record status
            await self.db_manager.update_record(
                record.id,
                status="running",
                started_at=datetime.utcnow()
            )
            
            # Dry run mode check
            if self.config.worker.dry_run:
                logger.info(f"DRY RUN: Would transcode {input_path} -> {output_path}")
                await asyncio.sleep(2)  # Simulate processing time
                success = True
            else:
                # Perform actual transcoding
                success = await self.transcode_engine.transcode(self.current_job)
            
            # Update database record
            if success:
                await self.db_manager.update_record(
                    record.id,
                    status="completed",
                    completed_at=datetime.utcnow(),
                    original_size=self.current_job.original_size,
                    final_size=self.current_job.final_size,
                    processing_time=self.current_job.get_duration(),
                    hardware_accel_used=profile.hardware_accel
                )
                
                # Mark as processed in file monitor
                file_monitor.mark_job_processed(job_data)
                
                logger.info(f"Worker {self.worker_id} completed: {input_path}")
                
            else:
                await self.db_manager.update_record(
                    record.id,
                    status="failed",
                    completed_at=datetime.utcnow(),
                    error_message=self.current_job.error_message,
                    processing_time=self.current_job.get_duration()
                )
                
                logger.error(f"Worker {self.worker_id} failed: {input_path}")
            
        except Exception as e:
            logger.error(f"Worker {self.worker_id} exception processing {input_path}: {e}")
            
            # Update record as failed
            await self.db_manager.update_record(
                record.id,
                status="failed",
                completed_at=datetime.utcnow(),
                error_message=str(e)
            )
        
        finally:
            self.current_job = None
    
    def get_status(self) -> dict:
        """Get current worker status."""
        return {
            "worker_id": self.worker_id,
            "running": self.running,
            "current_job": {
                "input_path": str(self.current_job.input_path) if self.current_job else None,
                "progress": self.current_job.progress if self.current_job else 0.0,
                "status": self.current_job.status if self.current_job else "idle"
            }
        }


class WorkerManager:
    """Manager for coordinating multiple transcoding workers."""
    
    def __init__(self, config: RecodeXConfig, db_manager: DatabaseManager):
        self.config = config
        self.db_manager = db_manager
        self.workers: Dict[int, TranscodeWorker] = {}
        self.worker_tasks: Dict[int, asyncio.Task] = {}
        self.file_monitor: Optional[FileMonitor] = None
        self.running = False
    
    async def start(self, file_monitor: FileMonitor):
        """Start the worker manager and all workers."""
        if self.running:
            return
        
        self.file_monitor = file_monitor
        
        logger.info(f"Starting {self.config.worker.max_workers} workers...")
        
        # Create and start workers
        for worker_id in range(self.config.worker.max_workers):
            worker = TranscodeWorker(worker_id, self.db_manager, self.config)
            self.workers[worker_id] = worker
            
            # Start worker task
            task = asyncio.create_task(worker.start(file_monitor))
            self.worker_tasks[worker_id] = task
        
        self.running = True
        logger.info("Worker manager started")
    
    async def stop(self):
        """Stop the worker manager and all workers."""
        if not self.running:
            return
        
        logger.info("Stopping worker manager...")
        
        # Stop all workers
        for worker in self.workers.values():
            await worker.stop()
        
        # Cancel worker tasks
        for task in self.worker_tasks.values():
            task.cancel()
        
        # Wait for tasks to complete
        await asyncio.gather(*self.worker_tasks.values(), return_exceptions=True)
        
        self.workers.clear()
        self.worker_tasks.clear()
        self.running = False
        
        logger.info("Worker manager stopped")
    
    def get_status(self) -> dict:
        """Get status of all workers."""
        return {
            "running": self.running,
            "worker_count": len(self.workers),
            "workers": [worker.get_status() for worker in self.workers.values()],
            "queue_size": self.file_monitor.get_queue_size() if self.file_monitor else 0
        }
    
    async def add_manual_job(self, input_path: Path, profile_name: str, output_path: Optional[Path] = None) -> dict:
        """Add a manual job to the processing queue."""
        if not self.file_monitor:
            raise RuntimeError("Worker manager not started")
        
        return await self.file_monitor.add_manual_job(input_path, profile_name, output_path)
    
    def get_active_jobs(self) -> list:
        """Get list of currently active jobs."""
        active_jobs = []
        
        for worker in self.workers.values():
            if worker.current_job:
                active_jobs.append({
                    "worker_id": worker.worker_id,
                    "input_path": str(worker.current_job.input_path),
                    "output_path": str(worker.current_job.output_path),
                    "profile": worker.current_job.profile.name,
                    "progress": worker.current_job.progress,
                    "status": worker.current_job.status
                })
        
        return active_jobs


class RecodeXService:
    """Main service coordinator for RecodeX."""
    
    def __init__(self, config: RecodeXConfig, config_path: Optional[Path] = None):
        self.config = config
        self.config_path = config_path
        self.db_manager = DatabaseManager(config.database.url)
        self.file_monitor: Optional[FileMonitor] = None
        self.worker_manager: Optional[WorkerManager] = None
        self.web_server_task: Optional[asyncio.Task] = None
        self.running = False
    
    async def start(self):
        """Start the RecodeX service."""
        if self.running:
            return
        
        logger.info("Starting RecodeX service...")
        
        # Initialize database
        await self.db_manager.initialize()
        
        # Create file monitor
        self.file_monitor = FileMonitor(self.config.watch_folders, self.config.profiles)
        await self.file_monitor.start()
        
        # Create and start worker manager
        self.worker_manager = WorkerManager(self.config, self.db_manager)
        await self.worker_manager.start(self.file_monitor)
        
        # Start web server
        self.web_server_task = asyncio.create_task(run_web_server(self.config, self))
        
        self.running = True
        logger.info("RecodeX service started")
    
    async def stop(self):
        """Stop the RecodeX service."""
        if not self.running:
            return
        
        logger.info("Stopping RecodeX service...")
        
        # Stop web server
        if self.web_server_task:
            self.web_server_task.cancel()
            try:
                await self.web_server_task
            except asyncio.CancelledError:
                pass
        
        # Stop worker manager
        if self.worker_manager:
            await self.worker_manager.stop()
        
        # Stop file monitor
        if self.file_monitor:
            await self.file_monitor.stop()
        
        # Close database
        await self.db_manager.close()
        
        self.running = False
        logger.info("RecodeX service stopped")
    
    def get_status(self) -> dict:
        """Get comprehensive service status."""
        status = {
            "service_running": self.running,
            "file_monitor": {
                "running": self.file_monitor.running if self.file_monitor else False,
                "watch_folders": len(self.config.watch_folders),
                "queue_size": self.file_monitor.get_queue_size() if self.file_monitor else 0
            },
            "workers": self.worker_manager.get_status() if self.worker_manager else None
        }
        
        return status
    
    async def add_manual_job(self, input_path: Path, profile_name: str, output_path: Optional[Path] = None) -> dict:
        """Add a manual transcoding job."""
        if not self.worker_manager:
            raise RuntimeError("Service not started")
        
        return await self.worker_manager.add_manual_job(input_path, profile_name, output_path)
    
    async def get_statistics(self) -> dict:
        """Get processing statistics."""
        stats = await self.db_manager.get_statistics()
        
        return {
            "total_processed": await stats.get_total_processed(),
            "total_space_saved": await stats.get_total_space_saved(),
            "total_original_size": await stats.get_total_original_size(),
            "average_compression_ratio": await stats.get_average_compression_ratio(),
            "average_processing_time": await stats.get_average_processing_time(),
            "top_space_savers": await stats.get_top_space_savers(),
            "recent_records": await stats.get_recent_records(),
            "statistics_by_profile": await stats.get_statistics_by_profile(),
            "statistics_by_codec": await stats.get_statistics_by_codec(),
            "queue_status": await stats.get_queue_status()
        }