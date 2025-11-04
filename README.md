# SamplePacker

Turn long field recordings into usable sample packs with a modern GUI interface.

**Note**: The GUI is now the primary interface. The CLI is deprecated but still available for batch processing.

## Features

- **Modern GUI**: Dark theme with system integration, DAW-style timeline interface
- **Interactive spectrogram**: Zoom, pan, and navigate through hour-long recordings
- **Preview system**: See detected samples before exporting
- **Sample editing**: Select, move, resize, and create samples visually on the spectrogram
- **Grid snapping**: Free time or musical bar grid with tempo settings
- **Frequency filtering**: High/low cut filters with real-time spectrogram updates
- **Multiple detection modes**: Voice VAD, transient flux, non-silence energy, spectral interestingness
- **High-quality output**: Preserve original quality by default (no re-encoding), with optional format conversion
- **Navigator scrollbar**: Bitwig-style overview with spectrogram preview
- **Cross-platform**: Works on Windows and Linux

## GUI Features

- **Timeline ruler**: Time markers at the top showing seconds, minutes, hours
- **Spectrogram view**: Interactive spectrogram with zoom (0.5x to 32x) and pan
- **Navigator scrollbar**: Bottom overview showing entire file with current view indicator
- **Sample markers**: Visual markers on spectrogram with drag-and-drop editing
- **Grid system**: Free time or musical bar grid with configurable snapping
- **Frequency filtering**: High/low cut filters update spectrogram display in real-time
- **Settings panel**: All processing parameters in scrollable panel
- **Sample table**: List of detected samples with checkboxes for export selection
- **Resizable panels**: Click and drag edges to resize UI elements (DAW-style)

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

### GUI Application

Launch the GUI application:

```bash
samplepacker-gui
```

Or:

```bash
python -m samplepacker.gui
```

1. **Open Audio File**: File → Open Audio File (or drag and drop)
2. **Adjust Settings**: Configure detection mode, timing parameters, and filters in the settings panel
3. **Update Preview**: Click "Update Preview" to process the audio and detect samples
4. **Edit Samples**: Click and drag markers on the spectrogram to adjust samples
5. **Export**: File → Export Samples to export selected samples

### Keyboard Shortcuts

- **Zoom In/Out**: `Ctrl++` / `Ctrl+-` or mouse wheel
- **Pan**: Arrow keys or drag in navigator
- **Play**: `Space` (double-click sample)
- **Delete**: `Delete` key
- **Snap Toggle**: `G` key

### Legacy CLI (Deprecated)

The CLI is still available but deprecated:

```bash
samplepacker input.wav --out output_dir
```

## GUI Usage

### Opening Files

- **File Menu**: File → Open Audio File
- **Drag and Drop**: Drag audio files onto the window
- **Supported Formats**: WAV, FLAC, MP3, M4A, AAC

### Navigation

- **Zoom**: Mouse wheel (with Ctrl for fine control) or zoom controls
- **Pan**: Click and drag in navigator scrollbar or use arrow keys
- **Timeline**: Click on timeline ruler to jump to time position
- **Navigator**: Click/drag in navigator to navigate, drag edges to resize view

### Sample Editing

- **Select**: Click on sample marker in spectrogram
- **Move**: Click and drag sample marker
- **Resize**: Click and drag left/right edges of sample marker
- **Create**: Click and drag on empty spectrogram area
- **Delete**: Select sample and press Delete key

### Grid Snapping

- **Free Time Mode**: Set snap interval (e.g., 0.1s, 1s)
- **Musical Bar Mode**: Set BPM and subdivision (quarter, eighth, etc.)
- **Toggle Snap**: Check/uncheck "Snap to grid" or press `G` key

### Frequency Filtering

- **High-pass Filter**: Set minimum frequency (Hz)
- **Low-pass Filter**: Set maximum frequency (Hz)
- **Real-time Update**: Spectrogram updates automatically when filters change

## Legacy CLI Options (Deprecated)

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

