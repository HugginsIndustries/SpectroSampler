"""Typer CLI for SamplePacker."""

from pathlib import Path
from typing import Annotated

import typer

from samplepacker.pipeline import Pipeline, ProcessingSettings
from samplepacker.utils import setup_logging

app = typer.Typer(
    name="samplepacker",
    help="SamplePacker: Turn long field recordings into usable sample packs.",
    add_completion=False,
)


@app.command()
def main(
    input_path: Annotated[
        Path,
        typer.Argument(help="Input audio file or directory (for batch processing)"),
    ],
    out: Annotated[
        Path,
        typer.Option("--out", "-o", help="Output directory"),
    ],
    # Mode and thresholds
    mode: Annotated[
        str,
        typer.Option("--mode", help="Detection mode: auto, voice, transient, nonsilence, spectral"),
    ] = "auto",
    threshold: Annotated[
        str,
        typer.Option("--threshold", help="Threshold: auto or float value"),
    ] = "auto",
    # Timing (milliseconds)
    pre_ms: Annotated[
        float,
        typer.Option("--pre-ms", help="Padding before segment (milliseconds)"),
    ] = 10000.0,
    post_ms: Annotated[
        float,
        typer.Option("--post-ms", help="Padding after segment (milliseconds)"),
    ] = 10000.0,
    merge_gap_ms: Annotated[
        float,
        typer.Option("--merge-gap-ms", help="Merge segments within this gap (milliseconds)"),
    ] = 300.0,
    min_dur_ms: Annotated[
        float,
        typer.Option("--min-dur-ms", help="Minimum segment duration (milliseconds)"),
    ] = 400.0,
    max_dur_ms: Annotated[
        float,
        typer.Option("--max-dur-ms", help="Maximum segment duration (milliseconds)"),
    ] = 60000.0,
    min_gap_ms: Annotated[
        float,
        typer.Option(
            "--min-gap-ms", help="Minimum gap between samples after padding (milliseconds)"
        ),
    ] = 0.0,
    resolve_overlaps: Annotated[
        str | None,
        typer.Option(
            "--resolve-overlaps",
            help="How to handle overlap after padding: keep-highest|merge|off",
        ),
    ] = None,
    overlap_iou: Annotated[
        float | None,
        typer.Option(
            "--overlap-iou",
            help="IoU threshold used by overlap resolver (e.g., 0.20)",
        ),
    ] = None,
    no_merge_after_padding: Annotated[
        bool,
        typer.Option(
            "--no-merge-after-padding/--merge-after-padding",
            help="Disable chain-merging after padding (dedup only by raw overlap/IoU)",
        ),
    ] = True,
    # Caps/filters
    max_samples: Annotated[
        int,
        typer.Option("--max-samples", help="Maximum number of samples to export"),
    ] = 200,
    min_snr: Annotated[
        float,
        typer.Option("--min-snr", help="Minimum SNR (optional)"),
    ] = 0.0,
    # Output format
    format: Annotated[
        str,
        typer.Option("--format", help="Output format: wav or flac"),
    ] = "wav",
    samplerate: Annotated[
        int | None,
        typer.Option("--samplerate", help="Output sample rate (Hz, preserve original if omitted)"),
    ] = None,
    bitdepth: Annotated[
        str | None,
        typer.Option("--bitdepth", help="Output bit depth: 16, 24, or 32f"),
    ] = None,
    channels: Annotated[
        str | None,
        typer.Option("--channels", help="Output channels: mono or stereo"),
    ] = None,
    # Denoise/preprocessing
    denoise: Annotated[
        str,
        typer.Option("--denoise", help="Denoise method: arnndn, afftdn, or off"),
    ] = "afftdn",
    hp: Annotated[
        float | None,
        typer.Option("--hp", help="High-pass filter frequency (Hz)"),
    ] = 120.0,
    lp: Annotated[
        float | None,
        typer.Option("--lp", help="Low-pass filter frequency (Hz)"),
    ] = 6000.0,
    nr: Annotated[
        float,
        typer.Option("--nr", help="Noise reduction strength (for afftdn)"),
    ] = 12.0,
    analysis_sr: Annotated[
        int,
        typer.Option("--analysis-sr", help="Analysis sample rate (Hz)"),
    ] = 16000,
    analysis_mid_only: Annotated[
        bool,
        typer.Option("--analysis-mid-only", help="Analyze mid channel only (MS/stereo)"),
    ] = False,
    # Spectrograms/reports
    spectrogram: Annotated[
        bool,
        typer.Option("--spectrogram/--no-spectrogram", help="Generate spectrogram PNGs"),
    ] = True,
    spectro_size: Annotated[
        str,
        typer.Option("--spectro-size", help="Spectrogram size (e.g., '4096x1024')"),
    ] = "4096x1024",
    spectro_video: Annotated[
        bool,
        typer.Option("--spectro-video/--no-spectro-video", help="Generate spectrogram video (MP4)"),
    ] = False,
    report: Annotated[
        str | None,
        typer.Option("--report", help="Generate HTML report"),
    ] = None,
    # Workflow
    batch: Annotated[
        bool,
        typer.Option("--batch", help="Process directory in batch mode"),
    ] = False,
    recurse: Annotated[
        bool,
        typer.Option("--recurse", help="Recursively process subdirectories (batch mode)"),
    ] = False,
    jobs: Annotated[
        int,
        typer.Option("--jobs", "-j", help="Number of parallel jobs (batch mode)"),
    ] = 1,
    chunk_sec: Annotated[
        float,
        typer.Option("--chunk-sec", help="Chunk size for streaming analysis (seconds)"),
    ] = 600.0,
    cache: Annotated[
        bool,
        typer.Option("--cache", help="Cache denoised and analysis files"),
    ] = False,
    resume: Annotated[
        bool,
        typer.Option("--resume", help="Skip already processed files"),
    ] = False,
    skip_existing: Annotated[
        bool,
        typer.Option("--skip-existing", help="Don't re-cut samples that already exist"),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Produce reports but no audio cuts"),
    ] = False,
    save_temp: Annotated[
        bool,
        typer.Option("--save-temp", help="Keep intermediate files"),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Verbose logging"),
    ] = False,
    # Subfolders
    create_subfolders: Annotated[
        bool,
        typer.Option("--create-subfolders", help="Create subfolders per processed file"),
    ] = True,
    subfolder_template: Annotated[
        str,
        typer.Option("--subfolder-template", help="Template for subfolder names"),
    ] = "{basename}__{mode}__pre{pre}ms_post{post}ms_thr{thr}",
) -> None:
    """SamplePacker: Turn long field recordings into usable sample packs."""
    setup_logging(verbose=verbose)

    # Validate inputs
    if not input_path.exists():
        typer.echo(f"Error: Input path does not exist: {input_path}", err=True)
        raise typer.Exit(1)

    if mode not in ("auto", "voice", "transient", "nonsilence", "spectral"):
        typer.echo(
            f"Error: Invalid mode '{mode}'. Must be one of: auto, voice, transient, nonsilence, spectral",
            err=True,
        )
        raise typer.Exit(1)

    if format not in ("wav", "flac"):
        typer.echo(f"Error: Invalid format '{format}'. Must be 'wav' or 'flac'", err=True)
        raise typer.Exit(1)

    if bitdepth and bitdepth not in ("16", "24", "32f"):
        typer.echo(f"Error: Invalid bitdepth '{bitdepth}'. Must be '16', '24', or '32f'", err=True)
        raise typer.Exit(1)

    if channels and channels not in ("mono", "stereo"):
        typer.echo(f"Error: Invalid channels '{channels}'. Must be 'mono' or 'stereo'", err=True)
        raise typer.Exit(1)

    # Parse threshold
    try:
        if threshold != "auto":
            threshold = float(threshold)
    except ValueError as err:
        typer.echo(f"Error: Invalid threshold '{threshold}'. Must be 'auto' or a float", err=True)
        raise typer.Exit(1) from err

    # Create settings
    settings = ProcessingSettings(
        mode=mode,
        threshold=threshold,
        pre_pad_ms=pre_ms,
        post_pad_ms=post_ms,
        merge_gap_ms=merge_gap_ms,
        min_dur_ms=min_dur_ms,
        max_dur_ms=max_dur_ms,
        min_gap_ms=min_gap_ms,
        resolve_overlaps=resolve_overlaps,
        overlap_iou=overlap_iou,
        no_merge_after_padding=no_merge_after_padding,
        max_samples=max_samples,
        min_snr=min_snr,
        format=format,
        sample_rate=samplerate,
        bit_depth=bitdepth,
        channels=channels,
        denoise=denoise,
        hp=hp,
        lp=lp,
        nr=nr,
        analysis_sr=analysis_sr,
        analysis_mid_only=analysis_mid_only,
        spectrogram=spectrogram,
        spectro_size=spectro_size,
        spectro_video=spectro_video,
        report=report,
        chunk_sec=chunk_sec,
        cache=cache,
        dry_run=dry_run,
        save_temp=save_temp,
        verbose=verbose,
        create_subfolders=create_subfolders,
        subfolder_template=subfolder_template,
    )

    # Create pipeline and process
    try:
        pipeline = Pipeline(settings)
        pipeline.process(input_path, out, jobs=jobs, resume=resume, skip_existing=skip_existing)
        typer.echo(f"Processing complete. Output: {out}")
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        if verbose:
            import traceback

            traceback.print_exc()
        raise typer.Exit(1) from e


def cli_main() -> None:
    """Entry point for CLI (called by setup.py or PyInstaller)."""
    app()


if __name__ == "__main__":
    cli_main()
