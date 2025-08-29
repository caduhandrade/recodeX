# RecodeX

A Python-based media transcoding service that provides an alternative to Unmanic, focusing on simplicity and efficiency.

## Features

- **Automated Media Transcoding**: Monitor watch folders and automatically transcode media files
- **Hardware Acceleration**: Support for NVENC, VA-API, Intel QSV, and AMF
- **Single-Pass Encoding**: Efficient video + audio + subtitles processing in one pass
- **Configurable Profiles**: Multiple encoding profiles for different quality/size targets
- **Smart Decision Making**: Only re-encode when necessary based on configurable rules
- **Statistics Dashboard**: Web interface showing processing statistics and space savings
- **Job Queue Management**: Concurrent workers with safe job processing
- **CLI Interface**: Command-line tools for management and monitoring

## Installation

```bash
pip install -e .
```

## Quick Start

1. **Configuration**: Edite o arquivo de configuração criado automaticamente em `C:/Users/<seu-usuario>/\.config/recodex/config.yaml` (Windows) ou `~/.config/recodex/config.yaml` (Linux/Mac). Altere o campo `path` em `watch_folders` para o diretório que deseja monitorar. Exemplo:

```yaml
watch_folders:
	- path: C:/Users/seu-usuario/Vídeos
		profile: high_quality
		recursive: true
		extensions: [".mp4", ".mkv", ".avi"]
		output_path: C:/Users/seu-usuario/Vídeos/convertidos
		delete_original: false
```

2. **Start Service**: `recodex start`
3. **Web Dashboard**: Open http://localhost:8000 to view statistics
4. **CLI Management**: Use `recodex --help` for available commands

## Supported Codecs

- **Video**: H.264 (AVC), H.265 (HEVC), AV1
- **Audio**: AAC, Opus, AC3 (copy or re-encode)
- **Subtitles**: Soft subtitles (copy) with optional embedding
- **Containers**: MP4, MKV

## Hardware Acceleration

RecodeX automatically detects and uses available hardware acceleration:

- **NVIDIA**: NVENC (H.264, H.265)
- **Intel**: Intel Quick Sync Video (QSV)
- **AMD**: AMF (Advanced Media Framework)
- **Linux**: VA-API (Video Acceleration API)

## Configuration

Configuration is managed through YAML files and environment variables. See the documentation for detailed configuration options.

## License

MIT License - see LICENSE file for details.
