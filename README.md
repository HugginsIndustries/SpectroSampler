# SpectroSampler

Turn long field recordings into curated sample packs with a fast, modern desktop workflow.

SpectroSampler is delivered as a GUI desktop app. Command-line usage is limited to launching the GUI with optional startup arguments.

---

## Highlights

- **Guided Workspace** – Welcome screen with recent projects/audio, autosave controls, and persistent window layout.
- **Detection Engine** – Multiple detectors (auto mix, voice VAD, transient, non-silence energy, spectral interestingness) with per-mode thresholds, merge rules, gap/duration guards, and multi-core processing control (`CPU workers`). Voice VAD pre-filters audio with a configurable 200–4500 Hz band-pass before WebRTC scoring so speech-focused projects stay cleaner.
- **Editing Surface** – High-resolution spectrogram (0.5×–32× zoom), navigator overview, draggable sample markers, context actions (disable others, center/fill view), and lockable grid snapping (time or musical bars).
- **Playback & Review** – Integrated sample player with looping, scrub bar, next/previous navigation, and sample table shortcuts (center/fill/play/delete).
- **Export Pipeline** – Per-project format, sample rate, bit depth, channel configuration, and padding. Export selected samples without re-encoding by default (WAV/FLAC supported out of the box).
- **Session Safety** – Project files capture every setting, autosave keeps rotating backups, and overlap resolution dialog protects existing edits when re-running detection.

> Looking for GUI usage details and walkthrough screenshots? See `docs/GUI_GUIDE.md`.

---

## Requirements

- **Python 3.11 or newer**
- **FFmpeg** reachable on your PATH (used for decoding/encoding)
- SpectroSampler verifies FFmpeg at startup and shows a blocking dialog with installation guidance (Windows + Linux) if it is missing, so install/verify FFmpeg before launching.
- Optional: **Visual C++ Build Tools** if you plan to install the VAD detector (`webrtcvad`) on Windows


### Install FFmpeg

| Platform | Install | Verify |
| --- | --- | --- |
| Windows | `choco install ffmpeg` or download from [ffmpeg.org](https://ffmpeg.org/download.html) and add `ffmpeg\bin` to PATH | `ffmpeg -version` |
| macOS | `brew install ffmpeg` | `ffmpeg -version` |
| Debian/Ubuntu | `sudo apt-get install ffmpeg` | `ffmpeg -version` |
| Fedora/CentOS | `sudo dnf install ffmpeg` or `sudo yum install ffmpeg` | `ffmpeg -version` |

---

## Installation

### From Source

```bash
git clone https://github.com/HugginsIndustries/SpectroSampler.git
cd SpectroSampler
pip install -e .
```

Install optional extras as needed:

- `pip install -e ".[vad]"` – adds Voice VAD detector (`webrtcvad`, requires build tools on Windows)
- `pip install -e ".[dev]"` – formatter, linters, tests

On Windows, confirm “Add Python to PATH” during installation. If `pip install webrtcvad` fails, install **Visual Studio Build Tools (Desktop development with C++)** or use a prebuilt wheel (`pip install webrtcvad --only-binary :all:`).

---

## Launching the App

Run the GUI with either command:

```bash
spectrosampler-gui
# or
python -m spectrosampler.gui.main
```

First launch presents the welcome screen where you can start a new project, open existing `.ssproj` files, or jump to recent audio.

### Command-line options

```text
spectrosampler-gui                    Launch the GUI
spectrosampler-gui --project <path>   Open a specific project file
spectrosampler-gui --audio <path>     Open a specific audio file
spectrosampler-gui --verbose          Enable verbose (DEBUG) console logging
spectrosampler-gui --help             Show help and exit
spectrosampler-gui --version          Show version and exit
```

---

## Guided Tour

### Workspace Layout
- **Left panel** – Detection settings (mode, thresholds, timing rules, denoise/high/low-pass filters, auto-sample order, CPU workers).
- **Top center** – Sample player: scrubbable transport, loop toggle, navigation controls, and live metadata.
- **Spectrogram canvas** – Zoom/pan, drag handles to edit sample bounds, create regions by dragging. Context menu adds disable/enable actions.
- **Navigator overview** – Mini spectrogram for fast navigation, drag edges to resize view.
- **Info table** – Grid of every detected sample with enable toggle, center/fill shortcuts, detector name, start/end/duration editing, and per-row delete.

### Persistence & Safety
- Autosave is on by default (Settings → Auto-save). Interval is configurable; autosaves live in the system temp directory.
- Closing with unsaved edits prompts to save/discard.
- Recent projects/audio lists are available in the File menu and welcome screen; you can clear them via Settings → Clear Recent Projects/Audio.

### Running Detection
1. Load an audio file (`Ctrl+Shift+O` or drag/drop).
2. Pick a detector and tune thresholds/timing.
3. Optionally configure denoise/filtering, sample spread mode, or maximum sample count.
4. Click **Detect Samples** (`Ctrl+D`). A loading overlay tracks progress.
5. If new detections overlap existing samples, the Overlap Resolution dialog lets you choose to discard overlaps, discard duplicates, or keep all (with “remember my choice”).

### Reviewing & Editing
- Select samples in the spectrogram or info table (they stay in sync).
- Use **Duration Edits** (Edit menu) to expand/contract or stretch from start/end.
- Re-order or re-rank samples automatically (Edit → Auto Sample Order / Re-order Samples).
- Toggle display of disabled samples (View menu).
- Switch between System, Dark, and Light themes (View → Theme); the choice persists between sessions via your local preferences.
- Lock snap to grid or adjust BPM/subdivision (View → Grid Settings).
- Limit UI refresh rate if working on large projects (View → Limit UI Refresh Rate → Refresh Rate).

### Exporting
- Choose format, sample rate, bit depth, and channels from the Export menu (set sample rate to `0` or pick “None (original)” for bit depth/channels to inherit source values).
- Configure pre/post padding to add silence to each export.
- Only enabled & checked samples in the info table are exported. Default format preserves original audio (no re-encode if parameters match).
- Exported filenames are sanitized automatically, so reserved characters and Windows device names never block writing files on Windows, macOS, or Linux.

---

## Quick Start Checklist

1. Launch SpectroSampler and open an audio file.
2. Review detection settings, then press **Detect Samples**.
3. Audition results with the sample player; loop tricky regions when needed.
4. Fine-tune boundaries directly on the spectrogram or by editing numbers in the info table.
5. Save a project file to capture the session (`Ctrl+S`).
6. Choose export parameters and run **Export Samples** (`Ctrl+E`).

---

## Keyboard Shortcuts

| Category | Action | Shortcut |
| --- | --- | --- |
| Project | New Project | `Ctrl+N` |
|  | Open Project | `Ctrl+O` |
|  | Open Audio File | `Ctrl+Shift+O` |
|  | Save Project | `Ctrl+S` |
|  | Save Project As | `Ctrl+Shift+S` |
|  | Export Samples | `Ctrl+E` |
| Editing | Detect Samples | `Ctrl+D` |
|  | Undo / Redo | `Ctrl+Z` / `Ctrl+Shift+Z` |
|  | Delete Sample | `Delete` |
| Navigation | Zoom In / Out | `Ctrl++` / `Ctrl+-` |
|  | Fit to Window | `Ctrl+0` |
|  | Pan | Arrow keys or drag in navigator |
|  | Play Sample | `Space` (double-click sample) |
| Grid | Toggle Snap | `G` |
| App | Quit (platform default) | `Ctrl+Q` |

---

## Project Files (`.ssproj`)

Project saves capture:

- Audio file reference (re-locate if moved)
- Detection settings, timing guards, filter values
- Sample metadata (start/end/duration, detector name, enabled flag)
- Export configuration (format, rate, padding, channels, bit depth)
- Grid settings and UI layout (splitter sizes, panels hidden/shown)
- Recent playback state (current view, zoom)
- Preferred theme mode is stored per user (System/Dark/Light)

Files are JSON; you can inspect or version-control them. Autosaves keep the last three revisions in the temp directory.

---

## Troubleshooting

- **FFmpeg not found** – Ensure it is on PATH (`ffmpeg -version`).
- **`webrtcvad` build errors (Windows)** – Install Visual Studio Build Tools or skip VAD.
- **GUI feels sluggish on big files** – Lower refresh rate (View → Limit UI Refresh Rate) or disable disabled-sample display.
- **Overlap resolution keeps popping up** – Set a default choice and tick “Remember my choice,” or adjust detection thresholds to reduce duplicates.
- **Audio missing when reopening project** – The `.ssproj` stores the file path only; relink if the audio moved.

---

## Development Notes

```bash
# Install dev tooling
pip install -e ".[dev]"

# Run tests
pytest -q

# Format & lint
black spectrosampler tests scripts
ruff check spectrosampler tests scripts
mypy spectrosampler --ignore-missing-imports
```

Make targets (`make format`, `make lint`, `make test`, `make freeze`) are available on macOS/Linux. On Windows, run the equivalent Python commands directly.

### Building Standalone Executables

PyInstaller spec lives in `spectrosampler.spec`. The build script in the repo mirrors:

```powershell
pyinstaller --onefile --name spectrosampler-gui --add-data "spectrosampler/presets;presets" spectrosampler/gui/main.py
```

Artifacts land in `dist/`; intermediary build products go to `build/`.

---

## Contributing & License

Contributions are welcome! File an issue or open a pull request for bug fixes, feature proposals, or documentation improvements.

SpectroSampler is released under the **MIT License**.