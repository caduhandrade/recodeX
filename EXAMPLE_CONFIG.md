# RecodeX Configuration Example

This example shows how to configure RecodeX for a typical media server setup.

## Configuration File Example (`~/.config/recodex/config.yaml`):

```yaml
# Watch folders configuration
watch_folders:
  - path: /media/input/movies
    profile: high_quality
    recursive: true
    extensions: [".mp4", ".mkv", ".avi", ".mov"]
    output_path: /media/output/movies
    delete_original: false

  - path: /media/input/tv_shows
    profile: balanced
    recursive: true
    extensions: [".mp4", ".mkv", ".avi"]
    output_path: /media/output/tv_shows
    delete_original: false

# Encoding profiles
profiles:
  high_quality:
    name: "High Quality"
    video_codec: h265
    video_crf: 20
    audio_codec: copy
    container: mkv
    hardware_accel: true
    preset: slow

  balanced:
    name: "Balanced"
    video_codec: h264
    video_crf: 23
    audio_codec: aac
    audio_bitrate: 128k
    container: mp4
    hardware_accel: true
    preset: medium

  small_file:
    name: "Small File"
    video_codec: h265
    video_crf: 28
    audio_codec: aac
    audio_bitrate: 96k
    container: mp4
    hardware_accel: true
    preset: slower

# Database configuration
database:
  url: sqlite:///recodex.db
  echo: false

# Web interface
web:
  host: 0.0.0.0
  port: 8080
  reload: false

# Worker settings
worker:
  max_workers: 3
  temp_dir: /tmp/recodex
  dry_run: false

# Logging
log_level: INFO
log_file: /var/log/recodex.log
```

## Usage Examples:

```bash
# Initialize default configuration
recodex config init

# Edit configuration
recodex config edit

# View current status
recodex status

# Start the service
recodex start

# Manually transcode a file
recodex transcode /path/to/input.mp4 high_quality --output /path/to/output.mkv

# View statistics
recodex stats

# Access web dashboard
# Open http://localhost:8080 in your browser
```

## Typical Workflow:

1. **Setup**: Configure watch folders and encoding profiles
2. **Start Service**: Run `recodex start` to begin monitoring
3. **Monitor**: Use web dashboard or CLI to track progress
4. **Analyze**: Review statistics and space savings

## Hardware Acceleration:

RecodeX automatically detects and uses available hardware acceleration:

- **NVIDIA GPUs**: NVENC encoding for H.264/H.265
- **Intel CPUs**: Quick Sync Video (QSV)
- **AMD GPUs**: AMF (Advanced Media Framework)
- **Linux**: VA-API for various hardware

## Space Savings Example:

Typical space savings with different profiles:

- **High Quality (H.265)**: 30-50% smaller than original H.264
- **Balanced (H.264)**: 10-30% smaller with optimized settings
- **Small File (H.265)**: 50-70% smaller for streaming/storage
