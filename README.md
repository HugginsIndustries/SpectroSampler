# SpectroSampler

Turn long field recordings into curated sample packs with a fast, modern desktop workflow.

SpectroSampler is delivered as a GUI desktop app. Command-line usage is limited to launching the GUI with optional startup arguments.

---

## Highlights

- **Guided Workspace** – Welcome screen with recent projects/audio, autosave controls, and persistent window layout.
- **Detection Engine** – Multiple detectors (auto mix, voice VAD, transient, non-silence energy, spectral interestingness) with per-mode thresholds, merge rules, gap/duration guards, and multi-core processing control (`CPU workers`). Voice VAD pre-filters audio with a configurable 200–4500 Hz band-pass before WebRTC scoring so speech-focused projects stay cleaner.
- **Editing Surface** – High-resolution spectrogram (0.5×–32× zoom) backed by a synchronized waveform preview, navigator overview, draggable sample markers, context actions (play, enable/disable toggle, rename/delete selections, center/fill view), and lockable grid snapping (time or musical bars).
- **Playback & Review** – Integrated sample player with looping, auto-play-next toggle, scrub bar, next/previous navigation, live playback indicator on the spectrogram, and sample table shortcuts (center/fill/play/delete).
- **Export Workflow** – Advanced export dialog with Global/Samples tabs, live waveform & spectrogram previews (respecting padding and bandpass filters), dynamic filename preview showing all output filenames per sample, per-batch metadata (Artist/Album/Year), per-sample title customization (always editable, applies when Custom checkbox is enabled), per-sample overrides (padding, normalization, bandpass, notes), multi-format output (WAV/FLAC/MP3), filename templating, persistent settings, resumable batch exports with pause/resume controls, and a sample player widget on the Samples tab that plays the current sample with all export settings applied and synchronized playback indicators on the previews.
- **Session Safety** – Project files capture every setting (including overlap resolution defaults and editor layout), autosave keeps rotating backups, the overlap dialog protects existing edits when re-running detection, and a Help → Diagnostics panel surfaces FFmpeg and audio device information for quick troubleshooting.

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
- **Left panel** – Toolbar with mode selection buttons (Select, Edit, Create).
- **Top center** – Sample player: scrubbable transport, loop toggle, navigation controls, and live metadata.
- **Waveform preview** – Time-aligned amplitude view sitting above the spectrogram with draggable splitter to resize or collapse (View → Show Waveform).
- **Spectrogram canvas** – Zoom/pan, drag handles to edit sample bounds, create regions by dragging. Context menu adds disable/enable actions.
- **Navigator overview** – Mini spectrogram for fast navigation, drag edges to resize view.
- **Info table** – Grid of every detected sample with enable toggle, optional Name field (feeds export filenames), center/fill shortcuts, detector name, start/end/duration editing, and per-row delete.

### Persistence & Safety
- Autosave is on by default (Settings → Auto-save). Interval is configurable; autosaves live in the system temp directory.
- Closing with unsaved edits prompts to save/discard.
- Detection, export, and overlap-resolution defaults persist between sessions and reload when you reopen a project or restart the app, so your thresholds and conflict handling follow you automatically.
- Splitter layouts (settings vs. editor, player/waveform/spectrogram stack, info table) restore exactly as saved, so collapsed panels stay collapsed when a project reopens.
- Recent projects/audio lists are available in the File menu and welcome screen; you can clear them via Settings → Clear Recent Projects/Audio.

### Running Detection
1. Load an audio file (`Ctrl+Shift+O` or drag/drop).
2. Open the **Detect Samples** dialog (`Ctrl+D` or Edit → Detect Samples).
3. Pick a detector and tune thresholds/timing.
4. Optionally configure denoise/filtering, sample spread mode, or maximum sample count (1–10,000, default 256).
   - The dialog blocks impossible combinations (for example, a minimum duration longer than the maximum) and shows a red hint explaining what to fix before detection can run.
5. Click **Detect Samples** in the dialog. A loading overlay tracks progress.
6. If new detections overlap existing samples, the Overlap Resolution dialog lets you choose to discard overlaps, discard duplicates, or keep all (with "remember my choice").

### Reviewing & Editing
- **Tool Modes**: Use the toolbar buttons (left panel) to switch between three interaction modes:
  - **Select** (default): Click or drag a selection box to select samples. Compatible with `Ctrl`-click to toggle and `Shift`-click to extend selection.
  - **Edit**: Drag samples to move them, or drag their edges to resize. Only one mode is active at a time.
  - **Create**: Click and drag on empty space to create new sample regions.
- Select samples in the spectrogram or info table (they stay in sync).
- Use `Ctrl`-click to toggle additional samples and `Shift`-click to extend the selection in both views for bulk zooming, editing, and export operations.
- Enable the sample player's Auto-play Next toggle to queue the next enabled sample automatically when playback ends; Loop still takes precedence when you need to rehearse a single segment.
- Right-click a segment or multi-selection to toggle enablement, rename samples in bulk, disable everything else, or delete the selection; chosen names appear beneath the sample ID and flow into export filenames.
- Frame one or more samples instantly with **View → Zoom to Selection** (`Ctrl+Shift+F`) to inspect edits without manual panning.
- Use **Duration Edits** (Edit menu) to expand/contract or stretch from start/end.
- Re-order or re-rank samples automatically (Edit → Auto Sample Order / Re-order Samples), and use **Enable All Samples** / **Disable All Samples** for quick project-wide toggles.
- Remove overlapping or duplicate samples (Edit → Remove All Overlaps / Remove All Duplicates) or merge overlapping samples into single samples (Edit → Merge All Overlaps) to clean up detection results.
- Toggle display of disabled samples and the waveform preview (View menu).
- Switch between System, Dark, and Light themes (View → Theme); the choice persists between sessions via your local preferences.
- Lock snap to grid or adjust BPM/subdivision (View → Grid Settings).
- Limit UI refresh rate if working on large projects (View → Limit UI Refresh Rate → Refresh Rate).

### Exporting
- Press `Ctrl+E` (File → Export Samples…) to open the export dialog. The **Global** tab covers formats (select multiple), sample rate/bit depth/channels, pre/post padding, peak normalization, bandpass filters (low/high cut fields are always editable with 20Hz/20000Hz defaults, but only apply when the option is enabled), metadata defaults (Artist/Album/Year), filename template, and destination folder. The **Samples** tab includes a sample player widget at the bottom with play/pause/stop controls, loop toggle, and Auto-Play toggle. The player automatically loads the current sample with all global export settings and per-sample overrides applied, and displays synchronized playback indicators (orange vertical lines) on the waveform and spectrogram previews. The Auto-Play toggle (different from the main player's auto-play-next) automatically starts playback when navigating samples with Next/Previous buttons. Loop and Auto-Play settings persist when navigating between samples.
- Use the **Samples** tab to step through enabled samples with live waveform/spectrogram previews. The top-right corner shows a filename preview listing all output filenames for the current sample (one per selected format, newline-delimited) that updates automatically when formats, template, padding, metadata, or sample overrides change. The **Title** section (above the Per-sample Overrides) provides a text field that is always editable; enable the **Custom** checkbox to apply your custom title (otherwise it defaults to the sample name from the info table, or "sample" if empty). The **Per-sample Overrides** section lets you override padding, normalization, bandpass (fields are always editable, but only apply when Override is checked), and notes on a per-sample basis. Overrides win over the global defaults.
- Click **Export Sample(s)** to launch the batch. The progress dialog reports ETA, supports pause/resume, and allows safe cancel. Cancelled runs store the unfinished sample IDs so the next launch can resume immediately.
- Enable "Save as default export settings" to persist the current Global settings for new projects. Per-project overrides and resume progress live inside the project file and reload automatically.
- Exported filenames follow the template (default `{id}_{title}_{start}_{duration}`) and sanitize illegal characters automatically. `{id}` is a zero-padded sample index (`0001`…`9999`), and `{title}` comes from the optional sample name in the info table (falling back to `sample` when empty), or from the custom title if the Custom checkbox is enabled in the Samples tab. One file per selected format is written per sample with embedded metadata.
- Templates (and the Notes field) accept rich tokens pulled from metadata and the sample table: `{id}`, `{title}`, `{artist}`, `{album}`, `{year}`, `{format}`, `{detector}`, `{start}`, `{end}`, `{duration}`, `{pre_pad_ms}`, `{post_pad_ms}`, `{basename}`, `{sample_id}`, `{total}` and any custom attributes as `{attr_<name>}`. Use them to build descriptive filenames or notes like `"{id}_{title}_{detector}"` or `"Start={start}s | Detector={detector}"`.
- If FFmpeg encounters an error during export, SpectroSampler surfaces a detailed dialog with the exact command plus actionable suggestions (verify source paths, check diagnostics, confirm folder permissions) so you can correct the issue and retry immediately.

---

## Quick Start Checklist

1. Launch SpectroSampler and open an audio file.
2. Open the **Detect Samples** dialog (`Ctrl+D` or Edit → Detect Samples), review settings, then click **Detect Samples**.
3. Audition results with the sample player; loop tricky regions when needed.
4. Fine-tune boundaries directly on the spectrogram or by editing numbers in the info table.
5. Save a project file to capture the session (`Ctrl+S`).
6. Open the **Export Samples** dialog (`Ctrl+E`), review Global/Sample settings, then run the batch.

---

## Developer API Overview

Prefer Python automation over the GUI? The processing engine is fully reusable:

- `spectrosampler.pipeline` provides a `Pipeline` class plus `process_file()` helper that mirrors the GUI workflow.
- `ProcessingSettings` (from `spectrosampler.pipeline_settings`) collects all detection, padding, and export knobs.
- Detector implementations, the shared `Segment` data model, audio I/O helpers, and export/report writers are all importable without launching Qt.

See `docs/DEVELOPER_API.md` for a module map, minimal script, and extension patterns.

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
| Navigation | Fit to Window | `Ctrl+0` |
|  | Zoom to Selection | `Ctrl+Shift+F` |
|  | Pan | Arrow keys or drag in navigator |
|  | Play Sample | `Space` (double-click sample) |
| Grid | Toggle Snap | `G` |
| App | Quit (platform default) | `Ctrl+Q` |

---

## Project Files (`.ssproj`)

Project saves capture:

- Audio file reference (re-locate if moved)
- Detection settings, timing guards, filter values
- Sample metadata (start/end/duration, detector name, enabled flag, per-sample Name)
- Export configuration (formats, sample rate/bit depth/channels, padding, normalization, bandpass filters, filename template, metadata defaults, destination folder, per-sample overrides, export resume state)
- Grid settings, overlap dialog defaults, and UI layout (splitter sizes, panels hidden/shown)
- Waveform preview visibility and height
- Recent playback state (current view, zoom)
- Preferred theme mode is stored per user (System/Dark/Light)

Files are JSON; you can inspect or version-control them. Autosaves keep the last three revisions in the temp directory.

---

## Troubleshooting

- **FFmpeg not found** – Ensure it is on PATH (`ffmpeg -version`).
- **Audio file won’t open** – The error dialog spells out the cause (missing file, unsupported codec, permissions, or FFmpeg availability) and suggested fixes; follow the guidance or convert the file to WAV/FLAC.
- **Analysis duration mismatch warning** – Use the dialog’s **Try alternate resample** button to rerun detection with the high-precision SOXR resampler. If the warning persists, convert the source file to WAV/FLAC and retry.
- **Need system details for support?** – Open Help → Diagnostics to copy FFmpeg, audio device, and environment details into bug reports.
- **`webrtcvad` build errors (Windows)** – Install Visual Studio Build Tools or skip VAD.
- **GUI feels sluggish on big files** – Lower refresh rate (View → Limit UI Refresh Rate) or disable disabled-sample display.
- **Overlap resolution keeps popping up** – Set a default choice, tick “Remember my choice” (it saves inside the project), or adjust detection thresholds to reduce duplicates.
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