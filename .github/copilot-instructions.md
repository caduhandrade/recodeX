# RecodeX Development Instructions

**ALWAYS follow these instructions first and fallback to search or bash commands only when you encounter unexpected information that does not match the info here.**

RecodeX is a Python media transcoding service that provides an alternative to Unmanic. It features a CLI interface, web dashboard, automated file monitoring, and job queue management using FFmpeg for media processing.

## Working Effectively

### Bootstrap, Build, and Test
- Install FFmpeg (required external dependency): `sudo apt-get update && sudo apt-get install -y ffmpeg`
- Install the package: `pip install -e .`
- Install dev dependencies: `pip install pytest pytest-asyncio black flake8 mypy coverage httpx`
- Run tests: `python -m pytest tests/ -v` -- takes 1-2 seconds, NEVER CANCEL. All 28 tests should pass.
- Check linting: `black --check recodex/ tests/` and `flake8 recodex/ tests/`

### Core Commands (Validated to Work)
- Initialize configuration: `recodex config init`
- Show current config: `recodex config show`
- Edit configuration: `recodex config edit`  
- Check service status: `recodex status`
- Manual transcoding: `recodex transcode <input_file> <profile> [--dry-run]`
- View statistics: `recodex stats`
- Start service: `recodex start`
- Web interface only: `recodex web`

### Configuration Location
- Configuration file: `~/.config/recodex/config.yaml`
- Always run `recodex config init` first to create default configuration
- Default profiles available: `high_quality` (H.265), `balanced` (H.264), `small_file` (H.265)

### Web Interface
- Demo server: `python start_demo_web.py` - starts on http://localhost:8000
- Features: job management tabs, statistics dashboard, reprocessing buttons
- API endpoints: `/api/jobs/pending`, `/api/jobs/completed`, `/api/jobs/failed`, `/api/jobs/{id}/reprocess`

## Validation

### Manual Testing Workflow
- ALWAYS test functionality after making changes by running through this complete scenario:
  1. `recodex config init` - initialize configuration
  2. Create test video: `ffmpeg -f lavfi -i testsrc=duration=5:size=320x240:rate=30 -f lavfi -i sine=frequency=1000:duration=5 -c:v libx264 -c:a aac -shortest /tmp/test_input.mp4`
  3. `recodex transcode /tmp/test_input.mp4 balanced --dry-run` - verify transcoding works
  4. `python start_demo_web.py` - test web interface (Ctrl+C to stop)
  5. Visit http://localhost:8000 to validate web dashboard loads correctly

### Testing Requirements
- FFmpeg must be installed for transcoding functionality
- Hardware acceleration automatically detected (NVENC, Intel QSV, AMD AMF, VA-API)
- All tests must pass: `python -m pytest tests/ -v`
- ALWAYS run `recodex status` to verify profiles are loaded correctly

### Build Validation
- Package installation works: `pip install -e .` completes successfully
- CLI accessible: `recodex --help` shows all available commands
- Configuration system works: `recodex config show` displays current settings

## Common Tasks

### Code Quality
- Run formatting before committing: `black recodex/ tests/`
- Run linting: `flake8 recodex/ tests/` (expect style warnings but should not fail)
- Current codebase has formatting issues that should be fixed when making changes

### Development Environment  
- Python 3.8+ required (tested with 3.12)
- SQLite database used by default (`sqlite:///recodex.db`)
- All dependencies install via pip (main package and dev tools)

### Package Structure
```
recodex/
├── cli/          # CLI commands and interface
├── config/       # Configuration management  
├── core/         # Transcoding engine and media processing
├── database/     # Job tracking and statistics
├── monitoring/   # File system monitoring
├── web/          # Web dashboard and API
└── workers/      # Job processing and queue management
```

### Key Files Reference
- `pyproject.toml` - package configuration and dependencies
- `start_demo_web.py` - demo web server with sample data
- `demo_improvements.py` - feature demonstration script
- `EXAMPLE_CONFIG.md` - configuration examples
- `tests/` - test suite covering all major functionality

## Troubleshooting

### Common Issues
- **FFmpeg not found**: Install with `sudo apt-get install ffmpeg`
- **Dev dependencies fail**: Install individually: `pip install pytest pytest-asyncio black flake8 mypy coverage httpx`
- **Tests fail with missing httpx**: Install with `pip install httpx`
- **Configuration not found**: Run `recodex config init` to create default config
- **Service won't start**: Check FFmpeg installation and configuration file exists

### Expected Warnings
- SQLAlchemy connection warnings in tests (non-critical)
- DeprecationWarning for datetime.utcnow() usage (non-critical)
- MovedIn20Warning for declarative_base() (non-critical)

### Hardware Acceleration
- Automatically detects available hardware encoders
- Intel QSV and VA-API commonly available in Linux environments
- NVENC requires NVIDIA GPU, AMF requires AMD GPU
- Software encoding used as fallback

Always validate changes work by running the complete manual testing workflow and ensuring all tests pass before considering work complete.