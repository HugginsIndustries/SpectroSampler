# SpectroSampler GUI Guide

This guide is the hands-on companion to the README. It follows the full GUI workflow—from the welcome screen to export—and calls out tips surfaced by recent updates.

_Note: this guide is currently WIP, some details may not be accurate or up-to-date._

---

## 1. Launch & Welcome Screen

Start SpectroSampler with `spectrosampler-gui` (or `python -m spectrosampler.gui.main`). The welcome screen provides:

- **Create New Project** – Start from an empty session.
- **Open Project...** – Browse for an existing `.ssproj`.
- **Recent Projects / Audio Files** – Double-click to reopen; buttons clear the history.
- At startup SpectroSampler checks that FFmpeg is available on your PATH. If it is missing, a blocking dialog explains how to install/enable FFmpeg on Windows and Linux before the GUI continues.

Autosave is enabled by default. If SpectroSampler detects an autosave newer than your last manual save, it will offer to restore it when a project loads.

![Welcome screen showing recent projects](/docs/images/welcome-screen.png "Welcome screen")

---

## 2. Main Window Tour

### 2.1 Layout at a Glance

| Area | Purpose |
| --- | --- |
| **Detection Settings (left panel)** | Detector choice, thresholds, timing limits, CPU worker count, denoise/filters, overlap defaults, detection trigger button. |
| **Sample Player (top center)** | Metadata readout, play/pause/stop, next/previous navigation, loop toggle, scrub slider. |
| **Spectrogram Canvas (center)** | Zoom/pan view, draw or adjust sample regions, right-click for context actions, drag handles to resize. |
| **Navigator Overview (below spectrogram)** | Miniature spectrogram with a draggable viewport rectangle for quick jumps. |
| **Sample Table (bottom)** | Per-sample enable checkbox, start/end/duration editing, detector info, quick actions (Center, Fill, Play, Delete). |

All splitters are draggable. Collapse the player or info table from the View menu if you prefer a taller spectrogram.

> Screenshot placeholder: `docs/images/main-window-overview.png`

### 2.2 Menus & Key Commands

- **File** – Project lifecycle (new/open/save), audio import, recent files.
- **Edit** – Undo/redo, re-run detection, auto sample ordering, bulk delete/disable, Duration Edits (expand/contract, stretch from start/end).
- **View** – Zoom controls, toggle info table/player visibility, show disabled samples, refresh-rate limiter, grid settings, and theme selection (System/Dark/Light).
- **Export** – Pre/post padding, format (WAV/FLAC), sample rate, bit depth, channels.
- **Settings** – Autosave toggle/interval, clear recent projects/audio.
- **Help** – Verbose logging option and about dialog.

Keyboard shortcuts mirror these actions; see [Appendix A](#appendix-a-keyboard-shortcuts).

---

### 2.3 Theme Modes

Use **View → Theme** to switch between:

- **System** – Follow the operating system theme (auto-detects on launch).
- **Dark** – Force the dark palette.
- **Light** – Force the light palette.

Your choice is saved in user settings and stored with the current project, so reopening SpectroSampler (or sharing the project) restores the preferred look automatically.

---

## 3. Preparing Detection

### 3.1 Loading Audio

1. Drag-and-drop a file or use **File → Open Audio File** (`Ctrl+Shift+O`).
2. Supported formats: WAV, FLAC, MP3, M4A, AAC (FFmpeg handles decoding).
3. The status bar confirms sample rate, channels, and duration.

### 3.2 Choosing a Detector

The **Detection Mode** combo offers:

- `auto` – Hybrid scoring that chooses a detector automatically.
- `voice` – WebRTC VAD (requires optional dependency) with a configurable 200–4500 Hz Butterworth band-pass applied before scoring (tune the High-pass/Low-pass sliders under **Audio Processing**; set them to 0 Hz and half the sample rate to disable).
- `transient` – Spectral flux-based hit detection.
- `nonsilence` – Energy-based detection for general material.
- `spectral` – Highlights “interesting” regions in the spectrogram.

Adjust the **Threshold** slider to refine sensitivity. Lower values detect more segments; higher values are stricter.

### 3.3 Timing & Overlap Controls

- **Detection pre/post padding** – Add context around detected regions before they appear in the table.
- **Merge gap / min gap** – Automatically merge detections or insist on spacing between them.
- **Min/Max duration** – Clamp sample length.
- **Max samples** – Cap the total number of detections (1–10,000) so exported filenames stay aligned with the 4-digit sample index.
- **Sample spread** – Keep detections evenly spaced (strict or closest).
- **Overlap Resolution** – Decide how to handle duplicates/overlaps when re-running detection; pick defaults and optionally remember them.

### 3.4 Audio Processing & Resources

- **Denoise (off / afftdn / arnndn)** – Light clean-up before detection.
- **High-pass / Low-pass** – Restrict processing to a frequency band; the spectrogram updates live.
- **Noise reduction** – Apply additional attenuation in dB.
- **CPU workers** – Tweak how many cores detection uses (default is the system count minus one).

When the settings look good, click **Detect Samples** or press `Ctrl+D`. A full-screen overlay shows progress while detection runs on a worker thread.

> Screenshot placeholder: `docs/images/detection-overlay.png`

---

## 4. Navigating & Auditioning

### 4.1 Spectrogram Navigation

- **Zoom** by dragging the navigator rectangle edges, or using scroll wheel.
- **Pan** by dragging the navigator rectangle, or using Alt + scroll wheel.
- **Timeline jumps** by clicking the navigator bar below the spectrogram.

![Animated overview of zooming and panning](/docs/gifs/spectrogram-nav.gif "Spectrogram navigation demo")

### 4.2 Using the Sample Player

- Select a sample to populate the player with ID, start/end, duration, and detector name.
- Transport buttons provide play/pause/stop/next/previous control; `Space` plays the focused sample.
- Toggle **Loop** to rehearse a region.
- Scrub within the sample using the slider; releasing emits a seek event while playback continues.

### 4.3 Sync with the Sample Table

Selecting a sample from the table highlights it in the spectrogram and vice versa. Table columns provide:

- **Enable** – Include/exclude from export.
- **Start / End / Duration** – Editable numeric cells (double-click to edit, press Enter to commit).
- **Detector** – Source detector label.
- **Actions** – Center, Fill (zoom the sample to the viewport width), Play, Delete.

Use the context menu or toolbar buttons on the spectrogram to disable the current sample or disable everything except the current one.

> Screenshot placeholder: `docs/images/sample-table.png`

---

## 5. Editing Samples

### 5.1 Basics

- Drag inside a region to move it across the timeline.
- Drag handles to adjust boundaries. Hold `Shift` to temporarily ignore snapping.
- Draw a new sample by clicking an empty area and dragging.
- Delete with the `Delete` key or the table’s Delete action.

### 5.2 Precision Tools

- **Duration Edits (Edit menu)** –
  - *Expand/Contract* adjusts both edges.
  - *Extend/Shorten (From Start)* moves the end boundary only.
  - *Extend/Shorten (From End)* moves the start boundary only.
- **Lock duration on start edit** – Maintains length while you reposition start time (toggle in Edit menu).
- **Auto Sample Order** – Re-rank samples by priority after manual edits.

### 5.3 Grid Snapping

Open **View → Grid Settings** to control:

- Mode: Free time vs. Musical bars.
- Snap interval (time) or BPM/subdivision/time signature (musical).
- Visibility of grid lines and snap strength.

Toggle snapping quickly with the `G` key or the checkbox under detection settings.

> Screenshot placeholder: `docs/images/grid-settings-dialog.png`

---

## 6. Exporting Your Pack

Open the **Export** menu to configure session-wide parameters:

- **Pre/Post padding...** – Add silence before/after every exported sample.
- **Format** – WAV or FLAC.
- **Sample Rate** – Enter 0 to keep the original.
- **Bit Depth** – 16-bit, 24-bit, 32-bit float, or “None (original).”
- **Channels** – Mono, stereo, or “None (original)” to keep source layout.

When ready, choose **File → Export Samples** (`Ctrl+E`). Only enabled (checked) columns are included. Exported filenames include the detector name, index, and source file id, and they are sanitized automatically so reserved characters or Windows device names never derail the export on any platform.

> Screenshot placeholder: `docs/images/export-menu.png`

---

## 7. Managing Sessions Safely

- **Autosave** – Enabled by default; configure via Settings → Auto-save → Auto-save Interval.
- **Manual Save** – `Ctrl+S` writes the current `.ssproj`. `Ctrl+Shift+S` prompts for a new filename.
- **Unsaved Changes Prompt** – Closing the window or quitting the app with modifications opens a Save/Discard/Cancel dialog.
- **Recent Lists** – Clear stale entries from Settings → Clear Recent Projects/Audio.

Project files are plain JSON and include audio paths, detection/export settings, grid config, and window layout. If the referenced audio is missing, SpectroSampler prompts to relink it when opening the project.

---

## 8. Performance Tips

- **Limit UI Refresh Rate** – View → Limit UI Refresh Rate, then choose a lower Hz value to reduce GPU/CPU load on dense projects.
- **Hide Panels** – Temporarily hide the sample table or player from the View menu to focus resources on the spectrogram.
- **Batch Clean-ups** – Use Edit → Disable All Samples or Delete All Samples before rerunning detection on a different configuration.
- **Navigator** – Stay zoomed in for editing while relying on the navigator for coarse movement.

Large projects benefit from leaving the info table collapsed while you fine-tune detections, then re-expanding for export prep.

---

## 9. Troubleshooting

| Symptom | Try This |
| --- | --- |
| Audio file fails to load | Confirm the file plays in another app. Verify FFmpeg is installed and on PATH. |
| Detection returns nothing | Lower the threshold, reduce minimum duration, or switch detectors. Ensure `Max samples` isn’t set too low. |
| Overlap dialog shows every run | Set a preferred default and tick “Remember my choice,” then re-run detection. |
| Playback is silent | Check workstation audio output, confirm the sample’s Enable checkbox is on, and ensure the sample isn’t muted in your OS mixer. |
| GUI stutters on long files | Lower the refresh rate, collapse panels, or reduce zoom. Close other heavy applications. |

Run `spectrosampler-gui --verbose` to capture additional diagnostics in the console when filing bug reports.

---

## Appendix A – Keyboard Shortcuts

| Area | Action | Shortcut |
| --- | --- | --- |
| File | New Project | `Ctrl+N` |
|  | Open Project | `Ctrl+O` |
|  | Open Audio File | `Ctrl+Shift+O` |
|  | Save Project | `Ctrl+S` |
|  | Save Project As | `Ctrl+Shift+S` |
|  | Export Samples | `Ctrl+E` |
| Edit | Detect Samples | `Ctrl+D` |
|  | Undo / Redo | `Ctrl+Z` / `Ctrl+Shift+Z` |
|  | Delete Sample | `Delete` |
| View | Zoom In / Out / Fit | `Ctrl++`, `Ctrl+-`, `Ctrl+0` |
|  | Toggle Snap | `G` |
|  | Toggle Disabled Samples | `View → Show Disabled Samples` (no default shortcut) |
| Navigation | Pan | Arrow keys or drag navigator |
|  | Play Selected Sample | `Space` or double-click |
|  | Seek Within Sample | Drag the player slider |
| App | Quit | `Ctrl+Q` |

---

## Appendix B – Developer API Overview

- The processing engine is importable without the GUI. Start with `spectrosampler.pipeline.Pipeline` and a `ProcessingSettings` instance to replicate the end-to-end workflow.
- Detector classes, the shared `Segment` data model, and helpers in `spectrosampler.audio_io`, `spectrosampler.export`, and `spectrosampler.report` can be reused in notebooks, batch scripts, or custom tooling.
- See `docs/DEVELOPER_API.md` for a complete module map, minimal script, and guidance on extending detectors.

---

## Appendix C – Reference

- **README** – High-level feature overview and installation instructions.
- **`spectrosampler/gui/main_window.py`** – Source for menus, shortcuts, and interaction logic.
- **`spectrosampler/gui/detection_settings.py`** – Detection configuration widgets.
- **`spectrosampler/gui/sample_player.py`** – Player behavior and signals.
- **`spectrosampler/gui/autosave.py`** – Autosave implementation details.

If you notice behavior mismatches or missing documentation, open an issue or submit a pull request—contributions are welcome!

