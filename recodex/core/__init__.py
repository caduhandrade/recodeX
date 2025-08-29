"""Core transcoding functionality for RecodeX."""

import asyncio
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import ffmpeg
import psutil

from ..config import TranscodeProfile

logger = logging.getLogger(__name__)


class HardwareAcceleration:
    """Hardware acceleration detection and configuration."""
    
    @staticmethod
    def detect_nvidia() -> bool:
        """Detect NVIDIA GPU with NVENC support."""
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0 and result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
    
    @staticmethod
    def detect_intel_qsv() -> bool:
        """Detect Intel Quick Sync Video support."""
        try:
            # Check for Intel GPU
            result = subprocess.run(
                ["lspci", "-nn"],
                capture_output=True,
                text=True,
                timeout=5
            )
            return "Intel" in result.stdout and "VGA" in result.stdout
        except (subprocess.TimeoutExpired, FileNotFoundError):
            # Try alternative method on non-Linux systems
            return Path("/dev/dri").exists()
    
    @staticmethod
    def detect_amd_amf() -> bool:
        """Detect AMD AMF support."""
        try:
            result = subprocess.run(
                ["lspci", "-nn"],
                capture_output=True,
                text=True,
                timeout=5
            )
            return "AMD" in result.stdout and ("VGA" in result.stdout or "Display" in result.stdout)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
    
    @staticmethod
    def detect_vaapi() -> bool:
        """Detect VA-API support."""
        return Path("/dev/dri").exists()
    
    @classmethod
    def get_available_accelerations(cls) -> Dict[str, bool]:
        """Get all available hardware accelerations."""
        return {
            "nvenc": cls.detect_nvidia(),
            "qsv": cls.detect_intel_qsv(),
            "amf": cls.detect_amd_amf(),
            "vaapi": cls.detect_vaapi(),
        }


class MediaInfo:
    """Media file information and analysis."""
    
    def __init__(self, file_path: Path):
        self.file_path = file_path
        self._info: Optional[Dict] = None
    
    async def get_info(self) -> Dict:
        """Get media file information using ffprobe."""
        if self._info is None:
            try:
                self._info = ffmpeg.probe(str(self.file_path))
            except ffmpeg.Error as e:
                logger.error(f"Failed to probe {self.file_path}: {e}")
                raise
        return self._info
    
    async def get_video_codec(self) -> Optional[str]:
        """Get video codec name."""
        info = await self.get_info()
        for stream in info.get("streams", []):
            if stream.get("codec_type") == "video":
                return stream.get("codec_name")
        return None
    
    async def get_audio_codec(self) -> Optional[str]:
        """Get audio codec name."""
        info = await self.get_info()
        for stream in info.get("streams", []):
            if stream.get("codec_type") == "audio":
                return stream.get("codec_name")
        return None
    
    async def get_duration(self) -> Optional[float]:
        """Get media duration in seconds."""
        info = await self.get_info()
        format_info = info.get("format", {})
        duration = format_info.get("duration")
        return float(duration) if duration else None
    
    async def get_file_size(self) -> int:
        """Get file size in bytes."""
        return self.file_path.stat().st_size
    
    async def get_bitrate(self) -> Optional[int]:
        """Get overall bitrate in bits/second."""
        info = await self.get_info()
        format_info = info.get("format", {})
        bitrate = format_info.get("bit_rate")
        return int(bitrate) if bitrate else None
    
    async def get_resolution(self) -> Optional[Tuple[int, int]]:
        """Get video resolution (width, height)."""
        info = await self.get_info()
        for stream in info.get("streams", []):
            if stream.get("codec_type") == "video":
                width = stream.get("width")
                height = stream.get("height")
                if width and height:
                    return (int(width), int(height))
        return None
    
    async def needs_transcoding(self, profile: TranscodeProfile) -> bool:
        """Determine if file needs transcoding based on profile."""
        try:
            video_codec = await self.get_video_codec()
            audio_codec = await self.get_audio_codec()
            bitrate = await self.get_bitrate()
            
            # Check video codec
            if video_codec and video_codec.lower() not in [profile.video_codec.lower(), "h264", "h265", "av1"]:
                return True
            
            # Check if target codec is different
            target_codec = profile.video_codec.lower()
            if video_codec and video_codec.lower() != target_codec:
                # Only transcode if going to more efficient codec or forced
                if target_codec in ["h265", "hevc", "av1"] and video_codec.lower() in ["h264", "avc"]:
                    return True
                if target_codec == "av1" and video_codec.lower() in ["h264", "h265", "hevc"]:
                    return True
            
            # Check bitrate if specified in profile
            if profile.video_bitrate and bitrate:
                target_bitrate = self._parse_bitrate(profile.video_bitrate)
                if bitrate > target_bitrate * 1.2:  # 20% tolerance
                    return True
            
            # Check audio codec
            if profile.audio_codec != "copy" and audio_codec:
                if audio_codec.lower() != profile.audio_codec.lower():
                    return True
            
            return False
            
        except Exception as e:
            logger.warning(f"Error checking if transcoding needed for {self.file_path}: {e}")
            return False
    
    @staticmethod
    def _parse_bitrate(bitrate_str: str) -> int:
        """Parse bitrate string to bits/second."""
        bitrate_str = bitrate_str.lower()
        if bitrate_str.endswith('k'):
            return int(float(bitrate_str[:-1]) * 1000)
        elif bitrate_str.endswith('m'):
            return int(float(bitrate_str[:-1]) * 1000000)
        else:
            return int(bitrate_str)


class TranscodeJob:
    """A transcoding job with progress tracking."""
    
    def __init__(self, input_path: Path, output_path: Path, profile: TranscodeProfile):
        self.input_path = input_path
        self.output_path = output_path
        self.profile = profile
        self.progress = 0.0
        self.status = "pending"
        self.error_message: Optional[str] = None
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        self.original_size: Optional[int] = None
        self.final_size: Optional[int] = None
    
    def get_duration(self) -> Optional[float]:
        """Get job duration in seconds."""
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return None
    
    def get_compression_ratio(self) -> Optional[float]:
        """Get compression ratio (original_size / final_size)."""
        if self.original_size and self.final_size and self.final_size > 0:
            return self.original_size / self.final_size
        return None
    
    def get_space_saved(self) -> Optional[int]:
        """Get space saved in bytes."""
        if self.original_size and self.final_size:
            return max(0, self.original_size - self.final_size)
        return None


class TranscodeEngine:
    """Main transcoding engine."""
    
    def __init__(self):
        self.hardware_accel = HardwareAcceleration.get_available_accelerations()
        logger.info(f"Available hardware acceleration: {self.hardware_accel}")
    
    async def transcode(self, job: TranscodeJob) -> bool:
        """Execute a transcoding job."""
        try:
            job.status = "running"
            job.start_time = asyncio.get_event_loop().time()
            job.original_size = job.input_path.stat().st_size
            
            logger.info(f"Starting transcode: {job.input_path} -> {job.output_path}")
            
            # Create temporary output file
            temp_output = job.output_path.with_suffix(f".tmp{job.output_path.suffix}")
            
            # Build ffmpeg command
            input_stream = ffmpeg.input(str(job.input_path))
            
            # Video encoding options
            video_options = self._get_video_options(job.profile)
            audio_options = self._get_audio_options(job.profile)
            
            # Build output stream
            output_args = {**video_options, **audio_options}
            
            # Add subtitle options
            if job.profile.subtitles == "copy":
                output_args["c:s"] = "copy"
            elif job.profile.subtitles == "none":
                output_args["sn"] = None  # No subtitles
            
            output_stream = ffmpeg.output(input_stream, str(temp_output), **output_args)
            
            # Add overwrite option
            output_stream = ffmpeg.overwrite_output(output_stream)
            
            # Execute ffmpeg
            process = await self._run_ffmpeg(output_stream, job)
            
            if process.returncode == 0:
                # Move temp file to final location
                temp_output.replace(job.output_path)
                job.final_size = job.output_path.stat().st_size
                job.status = "completed"
                job.end_time = asyncio.get_event_loop().time()
                
                logger.info(f"Transcode completed: {job.input_path} -> {job.output_path}")
                return True
            else:
                job.status = "failed"
                job.error_message = f"FFmpeg failed with return code {process.returncode}"
                logger.error(job.error_message)
                
                # Clean up temp file
                if temp_output.exists():
                    temp_output.unlink()
                
                return False
                
        except Exception as e:
            job.status = "failed"
            job.error_message = str(e)
            job.end_time = asyncio.get_event_loop().time()
            logger.error(f"Transcode failed: {job.input_path}: {e}")
            return False
    
    def _get_video_options(self, profile: TranscodeProfile) -> Dict[str, str]:
        """Get video encoding options for profile."""
        options = {}
        
        # Video codec
        codec = profile.video_codec.lower()
        hardware_used = False
        
        if profile.hardware_accel and self.hardware_accel.get("nvenc"):
            # NVIDIA NVENC
            if codec in ["h264", "avc"]:
                options["c:v"] = "h264_nvenc"
                hardware_used = True
            elif codec in ["h265", "hevc"]:
                options["c:v"] = "hevc_nvenc"
                hardware_used = True
            else:
                options["c:v"] = "libx264"  # Fallback
        elif profile.hardware_accel and self.hardware_accel.get("qsv"):
            # Intel Quick Sync
            if codec in ["h264", "avc"]:
                options["c:v"] = "h264_qsv"
                hardware_used = True
            elif codec in ["h265", "hevc"]:
                options["c:v"] = "hevc_qsv"
                hardware_used = True
            else:
                options["c:v"] = "libx264"
        elif profile.hardware_accel and self.hardware_accel.get("vaapi"):
            # VA-API - add initialization filters
            if codec in ["h264", "avc"]:
                options["c:v"] = "h264_vaapi"
                options["vaapi_device"] = "/dev/dri/renderD128"
                options["vf"] = "format=nv12,hwupload"
                hardware_used = True
            elif codec in ["h265", "hevc"]:
                options["c:v"] = "hevc_vaapi"
                options["vaapi_device"] = "/dev/dri/renderD128"
                options["vf"] = "format=nv12,hwupload"
                hardware_used = True
            else:
                options["c:v"] = "libx264"
        else:
            # Software encoding
            if codec in ["h264", "avc"]:
                options["c:v"] = "libx264"
            elif codec in ["h265", "hevc"]:
                options["c:v"] = "libx265"
            elif codec == "av1":
                options["c:v"] = "libaom-av1"
            else:
                options["c:v"] = "libx264"
        
        # Log hardware acceleration usage
        if hardware_used:
            logger.info(f"Using hardware acceleration: {options['c:v']}")
        
        # Quality settings
        if profile.video_crf is not None:
            if hardware_used and any(hw in options["c:v"] for hw in ["_vaapi"]):
                # VA-API uses different quality parameter
                options["qp"] = str(profile.video_crf)
            elif hardware_used and any(hw in options["c:v"] for hw in ["_nvenc"]):
                # NVENC uses cq for constant quality
                options["cq"] = str(profile.video_crf)
            else:
                options["crf"] = str(profile.video_crf)
        
        if profile.video_bitrate:
            options["b:v"] = profile.video_bitrate
        
        # Preset (hardware encoders may not support all presets)
        if profile.preset and not any(hw in options.get("c:v", "") for hw in ["_nvenc", "_qsv", "_vaapi", "_amf"]):
            options["preset"] = profile.preset
        elif profile.preset and "_nvenc" in options.get("c:v", ""):
            # NVENC presets are different
            nvenc_presets = {
                "ultrafast": "p1", "superfast": "p2", "veryfast": "p3",
                "faster": "p4", "fast": "p5", "medium": "p6",
                "slow": "p7", "slower": "p7", "veryslow": "p7"
            }
            options["preset"] = nvenc_presets.get(profile.preset, "p6")
        
        return options
    
    def _get_audio_options(self, profile: TranscodeProfile) -> Dict[str, str]:
        """Get audio encoding options for profile."""
        options = {}
        
        if profile.audio_codec == "copy":
            options["c:a"] = "copy"
        else:
            options["c:a"] = profile.audio_codec
            
            if profile.audio_bitrate:
                options["b:a"] = profile.audio_bitrate
            
            if profile.audio_normalize:
                # Add audio normalization filter
                options["af"] = "loudnorm"
        
        return options
    
    async def _run_ffmpeg(self, output_stream, job: TranscodeJob) -> subprocess.CompletedProcess:
        """Run ffmpeg process with progress tracking."""
        import re
        
        # Get ffmpeg command and add progress option
        cmd = ffmpeg.compile(output_stream)
        # Add progress reporting to stderr
        cmd = cmd + ['-progress', 'pipe:2']
        
        logger.debug(f"FFmpeg command: {' '.join(cmd)}")
        
        # Get duration from input file for progress calculation
        duration = None
        try:
            probe = ffmpeg.probe(str(job.input_path))
            format_info = probe.get('format', {})
            duration_str = format_info.get('duration')
            if duration_str:
                duration = float(duration_str)
        except Exception as e:
            logger.warning(f"Could not get duration for progress tracking: {e}")
        
        # Run process
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        # Read stderr line by line for progress tracking
        stderr_lines = []
        stdout_data = b''
        
        # Read stdout (shouldn't have much)
        async def read_stdout():
            nonlocal stdout_data
            if process.stdout:
                stdout_data = await process.stdout.read()
        
        # Read stderr for progress
        async def read_stderr():
            if not process.stderr:
                return
            
            while True:
                line = await process.stderr.readline()
                if not line:
                    break
                
                line_str = line.decode('utf-8', errors='replace').strip()
                stderr_lines.append(line_str)
                
                # Parse progress information
                if duration and 'time=' in line_str:
                    # Look for time=HH:MM:SS.mmm format
                    time_match = re.search(r'time=(\d+):(\d+):(\d+\.\d+)', line_str)
                    if time_match:
                        hours = int(time_match.group(1))
                        minutes = int(time_match.group(2))
                        seconds = float(time_match.group(3))
                        current_time = hours * 3600 + minutes * 60 + seconds
                        
                        # Calculate progress percentage
                        progress = min(100.0, (current_time / duration) * 100)
                        job.progress = progress
                        
                        logger.debug(f"FFmpeg progress: {progress:.1f}% ({current_time:.1f}s / {duration:.1f}s)")
        
        # Start reading both streams
        await asyncio.gather(read_stdout(), read_stderr())
        
        # Wait for process to complete
        returncode = await process.wait()
        
        # Join stderr lines
        stderr_data = '\n'.join(stderr_lines).encode('utf-8')
        
        # Create a completed process object
        completed_process = subprocess.CompletedProcess(
            cmd, returncode, stdout_data, stderr_data
        )
        
        if completed_process.returncode != 0:
            logger.error(f"FFmpeg stderr: {stderr_data.decode()}")
        else:
            # Set progress to 100% on successful completion
            job.progress = 100.0
        
        return completed_process