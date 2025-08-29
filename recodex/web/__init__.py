"""Web dashboard for RecodeX."""

import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, Optional, TYPE_CHECKING, List

from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import uvicorn

from ..config import RecodeXConfig, TranscodeProfile, WatchFolder

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ..workers import RecodeXService

# Web models
class TranscodeRequest(BaseModel):
    input_path: str
    profile: str
    output_path: Optional[str] = None

class ProfileRequest(BaseModel):
    name: str
    video_codec: str = "h264"
    video_bitrate: Optional[str] = None
    video_crf: Optional[int] = 23
    audio_codec: str = "copy"
    audio_bitrate: Optional[str] = None
    audio_normalize: bool = False
    subtitles: str = "copy"
    container: str = "mp4"
    hardware_accel: bool = True
    preset: str = "medium"

class WatchFolderRequest(BaseModel):
    path: str
    profile: str
    recursive: bool = True
    extensions: List[str] = [".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".m4v", ".webm"]
    output_path: Optional[str] = None
    delete_original: bool = False


class WebDashboard:
    """FastAPI web dashboard for RecodeX."""
    
    def __init__(self, config: RecodeXConfig, service: "RecodeXService"):
        self.config = config
        self.service = service
        self.app = FastAPI(title="RecodeX Dashboard", version="0.1.0")
        
        # Setup templates (we'll create basic HTML templates)
        self.templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
        
        # Setup routes
        self._setup_routes()
    
    def _setup_routes(self):
        """Setup FastAPI routes."""
        
        @self.app.get("/", response_class=HTMLResponse)
        async def dashboard(request: Request):
            """Main dashboard page."""
            return self.templates.TemplateResponse("dashboard.html", {
                "request": request,
                "title": "RecodeX Dashboard"
            })
        
        @self.app.get("/config", response_class=HTMLResponse)
        async def config_page(request: Request):
            """Configuration page."""
            return self.templates.TemplateResponse("config.html", {
                "request": request,
                "title": "RecodeX Configuration"
            })
        
        @self.app.get("/api/status")
        async def get_status():
            """Get service status."""
            try:
                return self.service.get_status()
            except Exception as e:
                logger.error(f"Error getting status: {e}")
                return {
                    "service_running": False,
                    "ffmpeg_running": False,
                    "active_jobs_count": 0,
                    "file_monitor": {
                        "running": False,
                        "watch_folders": 0,
                        "queue_size": 0
                    },
                    "workers": None,
                    "error": str(e)
                }
        
        @self.app.get("/api/statistics")
        async def get_statistics():
            """Get processing statistics."""
            try:
                return await self.service.get_statistics()
            except Exception as e:
                logger.error(f"Error getting statistics: {e}")
                return {
                    "total_processed": 0,
                    "total_space_saved": 0,
                    "total_original_size": 0,
                    "error": str(e)
                }
        
        @self.app.get("/api/config")
        async def get_config():
            """Get current configuration."""
            return {
                "watch_folders": [
                    {
                        "path": str(folder.path),
                        "profile": folder.profile,
                        "recursive": folder.recursive,
                        "extensions": folder.extensions,
                        "output_path": str(folder.output_path) if folder.output_path else None,
                        "delete_original": folder.delete_original
                    }
                    for folder in self.config.watch_folders
                ],
                "profiles": {
                    name: {
                        "name": profile.name,
                        "video_codec": profile.video_codec,
                        "video_bitrate": profile.video_bitrate,
                        "video_crf": profile.video_crf,
                        "audio_codec": profile.audio_codec,
                        "audio_bitrate": profile.audio_bitrate,
                        "audio_normalize": profile.audio_normalize,
                        "subtitles": profile.subtitles,
                        "container": profile.container,
                        "hardware_accel": profile.hardware_accel,
                        "preset": profile.preset
                    }
                    for name, profile in self.config.profiles.items()
                }
            }
        
        @self.app.post("/api/config/profiles")
        async def create_profile(request: ProfileRequest):
            """Create or update a transcoding profile."""
            try:
                # Create profile instance
                profile = TranscodeProfile(
                    name=request.name,
                    video_codec=request.video_codec,
                    video_bitrate=request.video_bitrate,
                    video_crf=request.video_crf,
                    audio_codec=request.audio_codec,
                    audio_bitrate=request.audio_bitrate,
                    audio_normalize=request.audio_normalize,
                    subtitles=request.subtitles,
                    container=request.container,
                    hardware_accel=request.hardware_accel,
                    preset=request.preset
                )
                
                # Update configuration
                profile_key = request.name.lower().replace(" ", "_")
                self.config.profiles[profile_key] = profile
                
                # Save configuration
                config_path = self.service.config_path
                if config_path:
                    self.config.to_yaml(config_path)
                
                return {"status": "success", "message": f"Profile '{request.name}' saved successfully"}
                
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))
        
        @self.app.delete("/api/config/profiles/{profile_name}")
        async def delete_profile(profile_name: str):
            """Delete a transcoding profile."""
            try:
                if profile_name not in self.config.profiles:
                    raise HTTPException(status_code=404, detail="Profile not found")
                
                del self.config.profiles[profile_name]
                
                # Save configuration
                config_path = self.service.config_path
                if config_path:
                    self.config.to_yaml(config_path)
                
                return {"status": "success", "message": f"Profile '{profile_name}' deleted successfully"}
                
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))
        
        @self.app.post("/api/config/watch-folders")
        async def create_watch_folder(request: WatchFolderRequest):
            """Create or update a watch folder."""
            try:
                from pathlib import Path
                
                # Create watch folder instance
                watch_folder = WatchFolder(
                    path=Path(request.path),
                    profile=request.profile,
                    recursive=request.recursive,
                    extensions=request.extensions,
                    output_path=Path(request.output_path) if request.output_path else None,
                    delete_original=request.delete_original
                )
                
                # Check if folder already exists (by path)
                existing_index = None
                for i, folder in enumerate(self.config.watch_folders):
                    if str(folder.path) == request.path:
                        existing_index = i
                        break
                
                if existing_index is not None:
                    self.config.watch_folders[existing_index] = watch_folder
                else:
                    self.config.watch_folders.append(watch_folder)
                
                # Save configuration
                config_path = self.service.config_path
                if config_path:
                    self.config.to_yaml(config_path)
                
                return {"status": "success", "message": f"Watch folder '{request.path}' saved successfully"}
                
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))
        
        @self.app.delete("/api/config/watch-folders/{folder_index}")
        async def delete_watch_folder(folder_index: int):
            """Delete a watch folder by index."""
            try:
                if folder_index < 0 or folder_index >= len(self.config.watch_folders):
                    raise HTTPException(status_code=404, detail="Watch folder not found")
                
                folder_path = str(self.config.watch_folders[folder_index].path)
                del self.config.watch_folders[folder_index]
                
                # Save configuration
                config_path = self.service.config_path
                if config_path:
                    self.config.to_yaml(config_path)
                
                return {"status": "success", "message": f"Watch folder '{folder_path}' deleted successfully"}
                
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))
        
        @self.app.get("/api/hardware-acceleration")
        async def get_hardware_acceleration():
            """Get available hardware acceleration options."""
            from ..core import HardwareAcceleration
            return HardwareAcceleration.get_available_accelerations()
        
        @self.app.post("/api/transcode")
        async def add_transcode_job(request: TranscodeRequest, background_tasks: BackgroundTasks):
            """Add a manual transcoding job."""
            try:
                input_path = Path(request.input_path)
                output_path = Path(request.output_path) if request.output_path else None
                
                job = await self.service.add_manual_job(
                    input_path, request.profile, output_path
                )
                
                return {"status": "success", "job": {
                    "input_path": str(job["input_path"]),
                    "output_path": str(job["output_path"]),
                    "profile": job["profile"].name
                }}
                
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))
        
        @self.app.get("/api/jobs/active")
        async def get_active_jobs():
            """Get currently active jobs."""
            try:
                if self.service.worker_manager:
                    return self.service.worker_manager.get_active_jobs()
                return []
            except Exception as e:
                logger.error(f"Error getting active jobs: {e}")
                return []


def create_templates_directory():
    """Create basic HTML templates for the web dashboard."""
    templates_dir = Path(__file__).parent / "templates"
    templates_dir.mkdir(exist_ok=True)
    
    # Only create dashboard.html if it doesn't already exist
    dashboard_file = templates_dir / "dashboard.html"
    if not dashboard_file.exists():
        # Read enhanced dashboard template
        enhanced_template_path = Path("/tmp/enhanced_dashboard.html")
        if enhanced_template_path.exists():
            dashboard_html = enhanced_template_path.read_text()
        else:
            # Fallback to basic template if enhanced one doesn't exist
            dashboard_html = '''<!DOCTYPE html>
<html><head><title>{{ title }}</title></head>
<body><h1>RecodeX Dashboard</h1><p>Enhanced configuration interface will be available soon.</p></body>
</html>'''
        
        dashboard_file.write_text(dashboard_html)


async def run_web_server(config: RecodeXConfig, service: "RecodeXService"):
    """Run the web server."""
    # Create templates
    create_templates_directory()
    
    # Create dashboard
    dashboard = WebDashboard(config, service)
    
    # Configure uvicorn
    server_config = uvicorn.Config(
        dashboard.app,
        host=config.web.host,
        port=config.web.port,
        reload=config.web.reload,
        log_level="info"
    )
    
    server = uvicorn.Server(server_config)
    
    # Run server
    await server.serve()