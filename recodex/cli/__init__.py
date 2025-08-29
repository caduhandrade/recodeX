"""Command Line Interface for RecodeX."""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.panel import Panel
from rich.text import Text

from ..config import RecodeXConfig, load_config, get_config_path
from ..workers import RecodeXService

console = Console()


def setup_logging(log_level: str, log_file: Optional[Path] = None):
    """Setup logging configuration."""
    level = getattr(logging, log_level.upper(), logging.INFO)
    
    # Configure root logger
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            *([] if log_file is None else [logging.FileHandler(log_file)])
        ]
    )
    
    # Reduce noise from third-party libraries
    logging.getLogger("watchdog").setLevel(logging.WARNING)
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)


@click.group()
@click.option('--config', '-c', type=click.Path(path_type=Path), help='Configuration file path')
@click.option('--log-level', default='INFO', help='Logging level')
@click.option('--log-file', type=click.Path(path_type=Path), help='Log file path')
@click.pass_context
def cli(ctx, config: Optional[Path], log_level: str, log_file: Optional[Path]):
    """RecodeX - Media Transcoding Service."""
    # Load configuration
    if config is None:
        config = get_config_path()
    
    ctx.ensure_object(dict)
    ctx.obj['config_path'] = config
    ctx.obj['config'] = load_config(config)
    
    # Setup logging
    if log_file is None and ctx.obj['config'].log_file:
        log_file = ctx.obj['config'].log_file
    
    if log_level == 'INFO' and ctx.obj['config'].log_level:
        log_level = ctx.obj['config'].log_level
    
    setup_logging(log_level, log_file)


@cli.command()
@click.pass_context
def start(ctx):
    """Start the RecodeX service."""
    config: RecodeXConfig = ctx.obj['config']
    
    console.print("[bold green]Starting RecodeX Service...[/bold green]")
    
    # Validate configuration
    if not config.watch_folders:
        console.print("[bold red]Error:[/bold red] No watch folders configured.")
        console.print("Run 'recodex config edit' to configure watch folders.")
        sys.exit(1)
    
    if not config.profiles:
        console.print("[bold red]Error:[/bold red] No profiles configured.")
        console.print("Run 'recodex config edit' to configure profiles.")
        sys.exit(1)
    
    # Create and start service
    service = RecodeXService(config)
    
    async def run_service():
        try:
            await service.start()
            
            console.print("[bold green]RecodeX service started successfully![/bold green]")
            console.print(f"Web interface: http://{config.web.host}:{config.web.port}")
            console.print("Press Ctrl+C to stop the service.")
            
            # Keep running until interrupted
            while True:
                await asyncio.sleep(1)
                
        except KeyboardInterrupt:
            console.print("\n[yellow]Shutting down...[/yellow]")
        except Exception as e:
            console.print(f"[bold red]Error:[/bold red] {e}")
        finally:
            await service.stop()
            console.print("[green]Service stopped.[/green]")
    
    # Run the service
    try:
        asyncio.run(run_service())
    except KeyboardInterrupt:
        pass


@cli.command()
@click.pass_context
def status(ctx):
    """Show service status."""
    config: RecodeXConfig = ctx.obj['config']
    
    # For now, just show configuration status
    console.print("[bold]RecodeX Configuration Status[/bold]")
    
    # Watch folders
    if config.watch_folders:
        table = Table(title="Watch Folders")
        table.add_column("Path", style="cyan")
        table.add_column("Profile", style="magenta")
        table.add_column("Recursive", style="green")
        table.add_column("Extensions")
        
        for folder in config.watch_folders:
            table.add_row(
                str(folder.path),
                folder.profile,
                "Yes" if folder.recursive else "No",
                ", ".join(folder.extensions)
            )
        
        console.print(table)
    else:
        console.print("[yellow]No watch folders configured[/yellow]")
    
    # Profiles
    if config.profiles:
        table = Table(title="Transcode Profiles")
        table.add_column("Name", style="cyan")
        table.add_column("Video Codec", style="magenta")
        table.add_column("Audio Codec", style="green")
        table.add_column("Container")
        table.add_column("HW Accel", style="yellow")
        
        for name, profile in config.profiles.items():
            table.add_row(
                name,
                profile.video_codec,
                profile.audio_codec,
                profile.container,
                "Yes" if profile.hardware_accel else "No"
            )
        
        console.print(table)
    else:
        console.print("[yellow]No profiles configured[/yellow]")


@cli.group()
def config():
    """Configuration management commands."""
    pass


@config.command('show')
@click.pass_context
def config_show(ctx):
    """Show current configuration."""
    config: RecodeXConfig = ctx.obj['config']
    config_path: Path = ctx.obj['config_path']
    
    console.print(f"[bold]Configuration File:[/bold] {config_path}")
    console.print(f"[bold]Exists:[/bold] {config_path.exists()}")
    
    if config_path.exists():
        with open(config_path, 'r') as f:
            content = f.read()
        
        console.print("\n[bold]Configuration Content:[/bold]")
        console.print(Panel(content, title="config.yaml", border_style="blue"))
    else:
        console.print("[yellow]Configuration file does not exist. Using defaults.[/yellow]")


@config.command('init')
@click.pass_context
def config_init(ctx):
    """Initialize default configuration."""
    config_path: Path = ctx.obj['config_path']
    
    if config_path.exists():
        if not click.confirm(f"Configuration file already exists at {config_path}. Overwrite?"):
            return
    
    # Create default configuration
    default_config = RecodeXConfig().get_default_config()
    
    # Ensure config directory exists
    config_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Save configuration
    default_config.to_yaml(config_path)
    
    console.print(f"[green]Configuration initialized at {config_path}[/green]")
    console.print("Edit the configuration file to customize your settings.")


@config.command('edit')
@click.pass_context
def config_edit(ctx):
    """Edit configuration file."""
    config_path: Path = ctx.obj['config_path']
    
    if not config_path.exists():
        if click.confirm("Configuration file does not exist. Create default configuration?"):
            ctx.invoke(config_init)
        else:
            return
    
    # Try to open with default editor
    try:
        import os
        import sys
        if sys.platform.startswith('linux'):
            editor = os.environ.get('EDITOR', 'nano')
        elif sys.platform == 'darwin':
            editor = os.environ.get('EDITOR', 'open')
        else:
            editor = os.environ.get('EDITOR', 'notepad')
        os.system(f'{editor} {config_path}')
        console.print("[green]Configuration edited.[/green]")
    except Exception as e:
        console.print(f"[red]Error opening editor: {e}[/red]")
        console.print(f"Please manually edit: {config_path}")


@cli.command()
@click.argument('input_path', type=click.Path(exists=True, path_type=Path))
@click.argument('profile', type=str)
@click.option('--output', '-o', type=click.Path(path_type=Path), help='Output path')
@click.option('--dry-run', is_flag=True, help='Show what would be done without actually doing it')
@click.pass_context
def transcode(ctx, input_path: Path, profile: str, output: Optional[Path], dry_run: bool):
    """Manually transcode a single file."""
    config: RecodeXConfig = ctx.obj['config']
    
    # Check if profile exists
    if profile not in config.profiles:
        console.print(f"[red]Error: Profile '{profile}' not found.[/red]")
        console.print("Available profiles:")
        for name in config.profiles.keys():
            console.print(f"  - {name}")
        sys.exit(1)
    
    # Set dry run mode if requested
    if dry_run:
        config.worker.dry_run = True
        console.print("[yellow]DRY RUN MODE - No actual transcoding will be performed[/yellow]")
    
    async def run_transcode():
        service = RecodeXService(config)
        
        try:
            await service.start()
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console
            ) as progress:
                task = progress.add_task("Transcoding...", total=None)
                
                job = await service.add_manual_job(input_path, profile, output)
                
                console.print(f"[green]Job added:[/green] {job['input_path']} -> {job['output_path']}")
                
                # Wait for job to complete
                while True:
                    status = service.get_status()
                    active_jobs = status.get('workers', {}).get('workers', [])
                    
                    if not any(worker['current_job']['status'] == 'running' for worker in active_jobs):
                        break
                    
                    await asyncio.sleep(1)
                
                progress.remove_task(task)
                console.print("[green]Transcoding completed![/green]")
                
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
        finally:
            await service.stop()
    
    asyncio.run(run_transcode())


@cli.command()
@click.pass_context
def stats(ctx):
    """Show transcoding statistics."""
    config: RecodeXConfig = ctx.obj['config']
    
    async def show_stats():
        service = RecodeXService(config)
        
        try:
            await service.start()
            
            with Progress(
                SpinnerColumn(),
                TextColumn("Loading statistics..."),
                console=console
            ) as progress:
                task = progress.add_task("Loading...", total=None)
                
                statistics = await service.get_statistics()
                
                progress.remove_task(task)
            
            # Display statistics
            console.print("[bold]RecodeX Statistics[/bold]")
            
            # Overview
            total_processed = statistics['total_processed']
            total_space_saved = statistics['total_space_saved']
            total_original = statistics['total_original_size']
            
            overview_table = Table(title="Overview")
            overview_table.add_column("Metric", style="cyan")
            overview_table.add_column("Value", style="green")
            
            overview_table.add_row("Files Processed", str(total_processed))
            overview_table.add_row("Space Saved", f"{total_space_saved / (1024**3):.2f} GB" if total_space_saved else "0 GB")
            overview_table.add_row("Original Size", f"{total_original / (1024**3):.2f} GB" if total_original else "0 GB")
            
            if total_original > 0:
                savings_pct = (total_space_saved / total_original) * 100
                overview_table.add_row("Savings Percentage", f"{savings_pct:.1f}%")
            
            console.print(overview_table)
            
            # Top space savers
            top_savers = statistics['top_space_savers']
            if top_savers:
                top_table = Table(title="Top Space Savers")
                top_table.add_column("File", style="cyan")
                top_table.add_column("Space Saved", style="green")
                
                for record in top_savers[:10]:
                    space_saved = record.space_saved or 0
                    top_table.add_row(
                        Path(record.input_path).name,
                        f"{space_saved / (1024**2):.1f} MB"
                    )
                
                console.print(top_table)
            
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
        finally:
            await service.stop()
    
    asyncio.run(show_stats())


def main():
    """Main entry point for the CLI."""
    cli()


if __name__ == '__main__':
    main()