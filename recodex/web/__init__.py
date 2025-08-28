"""Web dashboard for RecodeX."""

import asyncio
import json
from pathlib import Path
from typing import Dict, Optional

from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import uvicorn

from ..config import RecodeXConfig
from ..workers import RecodeXService

# Web models
class TranscodeRequest(BaseModel):
    input_path: str
    profile: str
    output_path: Optional[str] = None


class WebDashboard:
    """FastAPI web dashboard for RecodeX."""
    
    def __init__(self, config: RecodeXConfig, service: RecodeXService):
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
        
        @self.app.get("/api/status")
        async def get_status():
            """Get service status."""
            return self.service.get_status()
        
        @self.app.get("/api/statistics")
        async def get_statistics():
            """Get processing statistics."""
            return await self.service.get_statistics()
        
        @self.app.get("/api/config")
        async def get_config():
            """Get current configuration."""
            return {
                "watch_folders": [
                    {
                        "path": str(folder.path),
                        "profile": folder.profile,
                        "recursive": folder.recursive,
                        "extensions": folder.extensions
                    }
                    for folder in self.config.watch_folders
                ],
                "profiles": {
                    name: {
                        "name": profile.name,
                        "video_codec": profile.video_codec,
                        "audio_codec": profile.audio_codec,
                        "container": profile.container,
                        "hardware_accel": profile.hardware_accel
                    }
                    for name, profile in self.config.profiles.items()
                }
            }
        
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
            if self.service.worker_manager:
                return self.service.worker_manager.get_active_jobs()
            return []


def create_templates_directory():
    """Create basic HTML templates for the web dashboard."""
    templates_dir = Path(__file__).parent / "templates"
    templates_dir.mkdir(exist_ok=True)
    
    # Dashboard template
    dashboard_html = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }}</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        .header {
            background: white;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .cards {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }
        .card {
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .card h3 {
            margin-top: 0;
            color: #333;
        }
        .stat {
            display: flex;
            justify-content: space-between;
            margin: 10px 0;
        }
        .stat-value {
            font-weight: bold;
            color: #007bff;
        }
        .table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
        }
        .table th, .table td {
            padding: 8px 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }
        .table th {
            background-color: #f8f9fa;
            font-weight: 600;
        }
        .status-running { color: #28a745; }
        .status-pending { color: #ffc107; }
        .status-failed { color: #dc3545; }
        .refresh-btn {
            background: #007bff;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 4px;
            cursor: pointer;
            margin-left: 10px;
        }
        .refresh-btn:hover {
            background: #0056b3;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>RecodeX Dashboard</h1>
            <p>Media Transcoding Service</p>
            <button class="refresh-btn" onclick="refreshData()">Refresh</button>
        </div>
        
        <div class="cards">
            <div class="card">
                <h3>Service Status</h3>
                <div id="service-status">Loading...</div>
            </div>
            
            <div class="card">
                <h3>Statistics</h3>
                <div id="statistics">Loading...</div>
            </div>
            
            <div class="card">
                <h3>Active Jobs</h3>
                <div id="active-jobs">Loading...</div>
            </div>
        </div>
        
        <div class="card">
            <h3>Configuration</h3>
            <div id="configuration">Loading...</div>
        </div>
    </div>

    <script>
        async function fetchData(endpoint) {
            try {
                const response = await fetch(endpoint);
                return await response.json();
            } catch (error) {
                console.error('Error fetching data:', error);
                return null;
            }
        }
        
        function formatBytes(bytes) {
            if (bytes === 0) return '0 Bytes';
            const k = 1024;
            const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
        }
        
        function formatDuration(seconds) {
            const hours = Math.floor(seconds / 3600);
            const minutes = Math.floor((seconds % 3600) / 60);
            const secs = Math.floor(seconds % 60);
            
            if (hours > 0) {
                return `${hours}h ${minutes}m ${secs}s`;
            } else if (minutes > 0) {
                return `${minutes}m ${secs}s`;
            } else {
                return `${secs}s`;
            }
        }
        
        async function updateServiceStatus() {
            const status = await fetchData('/api/status');
            if (!status) return;
            
            const element = document.getElementById('service-status');
            element.innerHTML = `
                <div class="stat">
                    <span>Service Running:</span>
                    <span class="stat-value ${status.service_running ? 'status-running' : 'status-failed'}">
                        ${status.service_running ? 'Yes' : 'No'}
                    </span>
                </div>
                <div class="stat">
                    <span>File Monitor:</span>
                    <span class="stat-value ${status.file_monitor.running ? 'status-running' : 'status-failed'}">
                        ${status.file_monitor.running ? 'Running' : 'Stopped'}
                    </span>
                </div>
                <div class="stat">
                    <span>Watch Folders:</span>
                    <span class="stat-value">${status.file_monitor.watch_folders}</span>
                </div>
                <div class="stat">
                    <span>Queue Size:</span>
                    <span class="stat-value">${status.file_monitor.queue_size}</span>
                </div>
                <div class="stat">
                    <span>Active Workers:</span>
                    <span class="stat-value">${status.workers ? status.workers.worker_count : 0}</span>
                </div>
            `;
        }
        
        async function updateStatistics() {
            const stats = await fetchData('/api/statistics');
            if (!stats) return;
            
            const element = document.getElementById('statistics');
            element.innerHTML = `
                <div class="stat">
                    <span>Files Processed:</span>
                    <span class="stat-value">${stats.total_processed}</span>
                </div>
                <div class="stat">
                    <span>Space Saved:</span>
                    <span class="stat-value">${formatBytes(stats.total_space_saved)}</span>
                </div>
                <div class="stat">
                    <span>Original Size:</span>
                    <span class="stat-value">${formatBytes(stats.total_original_size)}</span>
                </div>
                <div class="stat">
                    <span>Avg Processing Time:</span>
                    <span class="stat-value">${formatDuration(stats.average_processing_time)}</span>
                </div>
                <div class="stat">
                    <span>Avg Compression:</span>
                    <span class="stat-value">${stats.average_compression_ratio.toFixed(2)}x</span>
                </div>
            `;
        }
        
        async function updateActiveJobs() {
            const jobs = await fetchData('/api/jobs/active');
            if (!jobs) return;
            
            const element = document.getElementById('active-jobs');
            
            if (jobs.length === 0) {
                element.innerHTML = '<p>No active jobs</p>';
                return;
            }
            
            let html = '<table class="table"><thead><tr><th>Worker</th><th>File</th><th>Profile</th><th>Status</th></tr></thead><tbody>';
            
            jobs.forEach(job => {
                const fileName = job.input_path.split('/').pop();
                html += `
                    <tr>
                        <td>${job.worker_id}</td>
                        <td title="${job.input_path}">${fileName}</td>
                        <td>${job.profile}</td>
                        <td class="status-${job.status}">${job.status}</td>
                    </tr>
                `;
            });
            
            html += '</tbody></table>';
            element.innerHTML = html;
        }
        
        async function updateConfiguration() {
            const config = await fetchData('/api/config');
            if (!config) return;
            
            const element = document.getElementById('configuration');
            
            let html = '<h4>Watch Folders</h4>';
            
            if (config.watch_folders.length === 0) {
                html += '<p>No watch folders configured</p>';
            } else {
                html += '<table class="table"><thead><tr><th>Path</th><th>Profile</th><th>Recursive</th><th>Extensions</th></tr></thead><tbody>';
                
                config.watch_folders.forEach(folder => {
                    html += `
                        <tr>
                            <td>${folder.path}</td>
                            <td>${folder.profile}</td>
                            <td>${folder.recursive ? 'Yes' : 'No'}</td>
                            <td>${folder.extensions.join(', ')}</td>
                        </tr>
                    `;
                });
                
                html += '</tbody></table>';
            }
            
            html += '<h4>Profiles</h4>';
            
            if (Object.keys(config.profiles).length === 0) {
                html += '<p>No profiles configured</p>';
            } else {
                html += '<table class="table"><thead><tr><th>Name</th><th>Video Codec</th><th>Audio Codec</th><th>Container</th><th>HW Accel</th></tr></thead><tbody>';
                
                Object.entries(config.profiles).forEach(([name, profile]) => {
                    html += `
                        <tr>
                            <td>${name}</td>
                            <td>${profile.video_codec}</td>
                            <td>${profile.audio_codec}</td>
                            <td>${profile.container}</td>
                            <td>${profile.hardware_accel ? 'Yes' : 'No'}</td>
                        </tr>
                    `;
                });
                
                html += '</tbody></table>';
            }
            
            element.innerHTML = html;
        }
        
        async function refreshData() {
            await Promise.all([
                updateServiceStatus(),
                updateStatistics(),
                updateActiveJobs(),
                updateConfiguration()
            ]);
        }
        
        // Initial load
        refreshData();
        
        // Auto-refresh every 5 seconds
        setInterval(refreshData, 5000);
    </script>
</body>
</html>'''
    
    (templates_dir / "dashboard.html").write_text(dashboard_html)


async def run_web_server(config: RecodeXConfig, service: RecodeXService):
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