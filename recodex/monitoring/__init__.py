"""File monitoring system for RecodeX."""

import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Optional, Set
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileMovedEvent

from ..config import WatchFolder, TranscodeProfile
from ..core import MediaInfo

logger = logging.getLogger(__name__)


class MediaFileHandler(FileSystemEventHandler):
    """File system event handler for media files."""
    
    def __init__(self, watch_folder: WatchFolder, job_queue: asyncio.Queue, profiles: Dict[str, TranscodeProfile]):
        super().__init__()
        self.watch_folder = watch_folder
        self.job_queue = job_queue
        self.profiles = profiles
        self.processed_files: Set[Path] = set()
        self.processing_files: Set[Path] = set()
    
    def on_created(self, event):
        """Handle file creation events."""
        if not event.is_directory:
            file_path = Path(event.src_path)
            asyncio.create_task(self._process_new_file(file_path))
    
    def on_moved(self, event):
        """Handle file move events."""
        if not event.is_directory:
            file_path = Path(event.dest_path)
            asyncio.create_task(self._process_new_file(file_path))
    
    async def _process_new_file(self, file_path: Path):
        """Process a newly detected file."""
        try:
            # Check if file extension is supported
            if not self._is_media_file(file_path):
                return
            
            # Avoid duplicate processing
            if file_path in self.processed_files or file_path in self.processing_files:
                return
            
            # Wait for file to be completely written
            await self._wait_for_file_ready(file_path)
            
            # Check if file already exists in output location
            if await self._is_already_processed(file_path):
                logger.info(f"File already processed, skipping: {file_path}")
                self.processed_files.add(file_path)
                return
            
            # Add to processing set
            self.processing_files.add(file_path)
            
            # Get profile
            profile = self.profiles.get(self.watch_folder.profile)
            if not profile:
                logger.error(f"Profile '{self.watch_folder.profile}' not found for {file_path}")
                return
            
            # Check if transcoding is needed
            media_info = MediaInfo(file_path)
            if not await media_info.needs_transcoding(profile):
                logger.info(f"File doesn't need transcoding, skipping: {file_path}")
                self.processed_files.add(file_path)
                self.processing_files.remove(file_path)
                return
            
            # Generate output path
            output_path = self._get_output_path(file_path, profile)
            
            # Create job and add to queue
            job = {
                "input_path": file_path,
                "output_path": output_path,
                "profile": profile,
                "watch_folder": self.watch_folder
            }
            
            await self.job_queue.put(job)
            logger.info(f"Added job to queue: {file_path} -> {output_path}")
            
        except Exception as e:
            logger.error(f"Error processing file {file_path}: {e}")
            if file_path in self.processing_files:
                self.processing_files.remove(file_path)
    
    def _is_media_file(self, file_path: Path) -> bool:
        """Check if file is a supported media file."""
        return file_path.suffix.lower() in self.watch_folder.extensions
    
    async def _wait_for_file_ready(self, file_path: Path, timeout: int = 30):
        """Wait for file to be completely written."""
        previous_size = 0
        stable_count = 0
        
        for _ in range(timeout):
            try:
                if not file_path.exists():
                    await asyncio.sleep(1)
                    continue
                
                current_size = file_path.stat().st_size
                
                if current_size == previous_size and current_size > 0:
                    stable_count += 1
                    if stable_count >= 3:  # File size stable for 3 seconds
                        return
                else:
                    stable_count = 0
                    previous_size = current_size
                
                await asyncio.sleep(1)
                
            except (OSError, IOError):
                await asyncio.sleep(1)
                continue
        
        logger.warning(f"File may not be ready after {timeout} seconds: {file_path}")
    
    async def _is_already_processed(self, file_path: Path) -> bool:
        """Check if file has already been processed."""
        # Check if output file already exists
        for profile_name, profile in self.profiles.items():
            output_path = self._get_output_path(file_path, profile)
            if output_path.exists():
                return True
        
        # TODO: Check database for processing history
        return False
    
    def _get_output_path(self, input_path: Path, profile: TranscodeProfile) -> Path:
        """Generate output path for processed file."""
        # Determine output directory
        if self.watch_folder.output_path:
            output_dir = self.watch_folder.output_path
        else:
            output_dir = input_path.parent
        
        # Generate filename with profile suffix
        stem = input_path.stem
        if not stem.endswith(f"_{profile.name}"):
            stem = f"{stem}_{profile.name}"
        
        # Use profile container format
        extension = f".{profile.container}"
        
        output_path = output_dir / f"{stem}{extension}"
        
        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        return output_path
    
    def mark_processed(self, file_path: Path):
        """Mark file as processed."""
        if file_path in self.processing_files:
            self.processing_files.remove(file_path)
        self.processed_files.add(file_path)


class FileMonitor:
    """Main file monitoring coordinator."""
    
    def __init__(self, watch_folders: List[WatchFolder], profiles: Dict[str, TranscodeProfile]):
        self.watch_folders = watch_folders
        self.profiles = profiles
        self.job_queue: asyncio.Queue = asyncio.Queue()
        self.observers: List[Observer] = []
        self.handlers: List[MediaFileHandler] = []
        self.running = False
    
    async def start(self):
        """Start monitoring all watch folders."""
        if self.running:
            return
        
        logger.info("Starting file monitoring...")
        
        for watch_folder in self.watch_folders:
            if not watch_folder.path.exists():
                logger.warning(f"Watch folder does not exist: {watch_folder.path}")
                continue
            
            # Create handler for this watch folder
            handler = MediaFileHandler(watch_folder, self.job_queue, self.profiles)
            self.handlers.append(handler)
            
            # Create observer
            observer = Observer()
            observer.schedule(
                handler,
                str(watch_folder.path),
                recursive=watch_folder.recursive
            )
            
            self.observers.append(observer)
            observer.start()
            
            logger.info(f"Monitoring: {watch_folder.path} (profile: {watch_folder.profile})")
        
        # Scan existing files
        await self._scan_existing_files()
        
        self.running = True
        logger.info("File monitoring started")
    
    async def stop(self):
        """Stop monitoring."""
        if not self.running:
            return
        
        logger.info("Stopping file monitoring...")
        
        for observer in self.observers:
            observer.stop()
            observer.join()
        
        self.observers.clear()
        self.handlers.clear()
        self.running = False
        
        logger.info("File monitoring stopped")
    
    async def _scan_existing_files(self):
        """Scan existing files in watch folders."""
        logger.info("Scanning existing files...")
        
        for watch_folder in self.watch_folders:
            if not watch_folder.path.exists():
                continue
            
            # Find handler for this watch folder
            handler = None
            for h in self.handlers:
                if h.watch_folder == watch_folder:
                    handler = h
                    break
            
            if not handler:
                continue
            
            # Scan directory
            if watch_folder.recursive:
                pattern = "**/*"
            else:
                pattern = "*"
            
            for file_path in watch_folder.path.glob(pattern):
                if file_path.is_file() and handler._is_media_file(file_path):
                    await handler._process_new_file(file_path)
        
        logger.info("Existing file scan completed")
    
    async def get_job(self) -> Optional[dict]:
        """Get next job from queue."""
        try:
            return await asyncio.wait_for(self.job_queue.get(), timeout=1.0)
        except asyncio.TimeoutError:
            return None
    
    def mark_job_processed(self, job: dict):
        """Mark job as processed."""
        input_path = job["input_path"]
        
        # Find corresponding handler and mark file as processed
        for handler in self.handlers:
            if handler.watch_folder.path in input_path.parents or handler.watch_folder.path == input_path.parent:
                handler.mark_processed(input_path)
                break
        
        # Delete original file if configured
        watch_folder = job["watch_folder"]
        if watch_folder.delete_original and input_path.exists():
            try:
                input_path.unlink()
                logger.info(f"Deleted original file: {input_path}")
            except Exception as e:
                logger.error(f"Failed to delete original file {input_path}: {e}")
    
    def get_queue_size(self) -> int:
        """Get current queue size."""
        return self.job_queue.qsize()
    
    async def add_manual_job(self, input_path: Path, profile_name: str, output_path: Optional[Path] = None):
        """Manually add a job to the queue."""
        profile = self.profiles.get(profile_name)
        if not profile:
            raise ValueError(f"Profile '{profile_name}' not found")
        
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")
        
        if not output_path:
            # Generate output path
            stem = input_path.stem
            if not stem.endswith(f"_{profile.name}"):
                stem = f"{stem}_{profile.name}"
            extension = f".{profile.container}"
            output_path = input_path.parent / f"{stem}{extension}"
        
        job = {
            "input_path": input_path,
            "output_path": output_path,
            "profile": profile,
            "watch_folder": None  # Manual job
        }
        
        await self.job_queue.put(job)
        logger.info(f"Added manual job: {input_path} -> {output_path}")
        
        return job