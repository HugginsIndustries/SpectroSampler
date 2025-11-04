# Windows Installation Guide

## Quick Setup

### 1. Install Python 3.11+

Download from [python.org](https://www.python.org/downloads/) and ensure Python is in your PATH.

### 2. Install FFmpeg

**Option A: Using Chocolatey (recommended)**
```powershell
choco install ffmpeg
```

**Option B: Manual Installation**
1. Download from [ffmpeg.org](https://ffmpeg.org/download.html)
2. Extract to a folder (e.g., `C:\ffmpeg`)
3. Add `C:\ffmpeg\bin` to your PATH environment variable

Verify installation:
```powershell
ffmpeg -version
```

### 3. Install SamplePacker

```powershell
# Clone the repository
git clone <repository-url>
cd SamplePacker

# Install core dependencies (no build tools needed)
pip install -e .
```

### 4. (Optional) Install VAD Support

The Voice VAD detector requires `webrtcvad`, which needs C++ compilation on Windows:

**Option A: Install Visual C++ Build Tools**
1. Download [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/)
2. Install with "Desktop development with C++" workload
3. Then run: `pip install webrtcvad`

**Option B: Use Pre-built Wheel** (if available)
```powershell
pip install webrtcvad --only-binary :all:
```

**Option C: Skip VAD** (use other detectors)
You can use `--mode transient`, `--mode nonsilence`, or `--mode spectral` without VAD.

## Running Tests (Windows)

Since Windows doesn't have `make` by default, use direct commands:

```powershell
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
python -m pytest -q

# Format code
python -m black samplepacker tests scripts

# Lint
python -m ruff check samplepacker tests scripts
```

## Troubleshooting

### Error: "make is not recognized"
Use PowerShell commands directly instead of `make`. See above.

### Error: "Microsoft Visual C++ 14.0 or greater is required"
This is only needed for `webrtcvad`. Either:
- Install Visual C++ Build Tools (see above)
- Skip VAD detector and use other modes
- Use pre-built wheel if available

### Error: "ffmpeg not found"
Ensure FFmpeg is installed and in your PATH. Verify with:
```powershell
ffmpeg -version
```

## Building Executable (PyInstaller)

```powershell
# Install PyInstaller
pip install pyinstaller

# Build
pyinstaller --onefile --name samplepacker --add-data "samplepacker/presets;presets" samplepacker/cli.py

# Executable will be in dist\samplepacker.exe
```

