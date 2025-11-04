# SamplePacker

Turn long field recordings into usable sample packs (CLI first, GUI second).

## Features

- **Multiple detection modes**: Voice VAD, transient flux, non-silence energy, spectral interestingness
- **Batch processing**: Process single files or entire directories
- **High-quality output**: Preserve original quality by default (no re-encoding), with optional format conversion
- **Comprehensive reports**: Spectrograms (PNG/MP4), timestamps CSV, markers (Audacity/REAPER), HTML reports
- **Performance**: Streaming analysis for long files, caching, parallel batch processing
- **Cross-platform**: Works on Windows and Linux

## Requirements

- **Python 3.11+**
- **FFmpeg** (must be installed and available in PATH)

### Installing FFmpeg

- **Windows**: Download from [ffmpeg.org](https://ffmpeg.org/download.html) or use `choco install ffmpeg`
- **Linux**: `sudo apt-get install ffmpeg` (Debian/Ubuntu) or `sudo yum install ffmpeg` (RHEL/CentOS)

## Installation

### From Source

```bash
git clone <repository-url>
cd SamplePacker
pip install -e .
```

**Windows Users**: The core dependencies should install fine. If you want to use the Voice VAD detector, you'll need `webrtcvad`:

```bash
# Option 1: If you have Visual C++ Build Tools installed:
pip install webrtcvad

# Option 2: Install pre-built wheel (if available):
pip install webrtcvad --only-binary :all:

# Option 3: Install with the optional VAD dependency (if you have build tools):
pip install -e ".[vad]"
```

**Note**: If you don't need the VAD detector, you can use other modes (transient, nonsilence, spectral) without `webrtcvad`.

### Development

```bash
pip install -e ".[dev]"
```

On Windows, you can also install without `make` using direct commands:
```powershell
# Install
pip install -e ".[dev]"

# Run tests
python -m pytest -q

# Format code
python -m black samplepacker tests scripts

# Lint
python -m ruff check samplepacker tests scripts
```

## Quick Start

### Single File

```bash
samplepacker input.wav --out output_dir
```

### Batch Processing

```bash
samplepacker input_directory --out output_dir --batch --recurse
```

### Example with Custom Settings

```bash
samplepacker recording.wav --out samples \
  --mode auto \
  --pre-ms 10000 \
  --post-ms 10000 \
  --max-samples 200 \
  --format wav \
  --spectrogram
```

## CLI Options

### Detection Mode

- `--mode [auto|voice|transient|nonsilence|spectral]` (default: `auto`)
  - `auto`: Run multiple detectors and merge results
  - `voice`: Voice Activity Detection (WebRTC VAD)
  - `transient`: Transient detection (spectral flux)
  - `nonsilence`: Non-silence energy detection
  - `spectral`: Spectral interestingness detection

### Timing (milliseconds)

- `--pre-ms 10000`: Padding before segment
- `--post-ms 10000`: Padding after segment
- `--merge-gap-ms 300`: Merge segments within this gap
- `--min-dur-ms 400`: Minimum segment duration
- `--max-dur-ms 60000`: Maximum segment duration
- `--min-gap-ms 0`: Minimum gap between samples after padding

### Output Format

- `--format [wav|flac]`: Output format (default: preserve original)
- `--samplerate <hz>`: Resample output (omit to preserve original)
- `--bitdepth [16|24|32f]`: Bit depth conversion
- `--channels [mono|stereo]`: Channel conversion

### Denoising

- `--denoise [arnndn|afftdn|off]`: Denoise method (default: `afftdn`)
- `--hp 120`: High-pass filter (Hz)
- `--lp 6000`: Low-pass filter (Hz)
- `--nr 12`: Noise reduction strength (afftdn)

### Spectrograms & Reports

- `--spectrogram`: Generate spectrogram PNGs
- `--spectro-size "4096x1024"`: Spectrogram image size
- `--spectro-video`: Generate spectrogram video (MP4)
- `--report html`: Generate HTML report

### Workflow

- `--jobs N`: Parallel jobs for batch processing
- `--cache`: Cache denoised and analysis files
- `--resume`: Skip already processed files
- `--skip-existing`: Don't re-cut samples that already exist
- `--dry-run`: Produce reports but no audio cuts
- `--verbose`: Verbose logging

## Output Structure

```
output_dir/
  <basename>/
    samples/
      <basename>_sample_000_1.0s-2.0s_detector-voice.wav
      ...
    spectrograms/
      <basename>_spectrogram.png
      <basename>_spectrogram_marked.png
    markers/
      audacity_labels.txt
      reaper_regions.csv
    data/
      timestamps.csv
      summary.json
      run.log
```

## Development

### Running Tests

**Linux/Mac:**
```bash
make test
# or
pytest -q
```

**Windows:**
```powershell
python -m pytest -q
```

### Code Formatting

**Linux/Mac:**
```bash
make format
```

**Windows:**
```powershell
python -m black samplepacker tests scripts
```

### Linting

**Linux/Mac:**
```bash
make lint
```

**Windows:**
```powershell
python -m ruff check samplepacker tests scripts
python -m mypy samplepacker --ignore-missing-imports
```

### Building PyInstaller Executable

**Linux/Mac:**
```bash
make freeze
```

**Windows:**
```powershell
pyinstaller --onefile --name samplepacker --add-data "samplepacker/presets;presets" samplepacker/cli.py
```

Note: The `Makefile` is for Unix-like systems. On Windows, use PowerShell/cmd directly or install `make` via Chocolatey/WSL.

## License

MIT

## Contributing

Contributions welcome! Please open an issue or submit a pull request.

