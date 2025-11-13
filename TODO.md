# TODO

## **Notes**

_Unreleased: no backward compatibility guarantees. Optimize functionality first._

Items marked [Docs Impact] will require updates to `README.md` and/or `docs/GUI_GUIDE.md`.

**Priority levels:**
- [P0] Critical/near-term items for correctness, stability, or unblocking core workflows.
- [P1] High-priority improvements that materially enhance UX/functionality; schedule next iterations.
- [P2] Nice-to-have or longer-term enhancements; plan after P0/P1.

_Summary: P0: 0 items, P1: 26 items, P2: 15 items_

**Maintainers guide (editing this TODO):**
- Use imperative phrasing for items ("Add", "Improve", "Expose", "Implement").
- For items that affect UX, add 1–3 concise acceptance bullets each (what the user sees/does).
- Keep user-facing acceptance criteria concise and testable.
- Keep formatting consistent: section → subsection(s) → item → acceptance bullets.
- Use backticks for code identifiers (files like `utils.py`, functions like `check_ffmpeg()`, classes like `FFmpegError`).
- Assign an appropriate priority tag ([P0]/[P1]/[P2]).
- Do not delete empty sections; write "No items currently planned" instead.
- Update the summary counts when adding/removing items.

## **Fixes**

### Detection & Sample Processing
- [ ] [P1] Improve VAD accuracy and reduce false positives
  - Fix Voice Activity Detection to reduce false positives (too many non-voice samples detected) and improve reliability (better detection of actual voice samples).
  - Review and adjust aggressiveness settings, frame merging logic, post-processing filters, and segment validation criteria.
  - Consider additional filtering mechanisms (e.g., energy-based validation, spectral characteristics, duration heuristics) to distinguish voice from non-voice audio.
  - Acceptance: VAD detects fewer false positives (non-voice samples); VAD reliably detects actual voice samples; measurable precision/recall improvement on voice/non-voice test clips.
- [ ] [P1] Improve detection defaults for better accuracy
  - Review current defaults (e.g., VoiceVAD aggressiveness=3), thresholds, and padding.
  - Consider adaptive thresholds based on audio characteristics.
  - Acceptance:
    - Documented default set per detector.
    - Measurable precision/recall improvement on a small reference clip set.
- [ ] [P1] Finish WebRTC VAD detection pipeline (from `spectrosampler/detectors/vad.py:VoiceVADDetector.detect`)
  - Implement optional bandpass preprocessing that respects `low_freq`/`high_freq` using `spectrosampler/dsp.bandpass_filter` or an FFmpeg fallback when configured.
  - Convert float audio buffers into 16-bit PCM frames derived from `frame_duration_ms`, ensuring byte alignment for WebRTC VAD.
  - Merge consecutive voiced frames into `Segment` instances and discard runs shorter than `min_duration_ms`.
  - Acceptance:
    - Optional bandpass filtering and frame merging honor `min_duration_ms` and aggressiveness while remaining thread-safe.
    - Unit tests cover voiced/unvoiced fixtures and assert consistent segment counts when `webrtcvad` is available.

### Audio Playback
- [ ] [P1] Improve seamless looping for short samples
  - Improve QMediaPlayer usage and buffering; consider crossfade option and/or pre-buffering.
  - Acceptance: On a 250 ms loop, audible gap < 10 ms; optional crossfade toggle.
- [ ] [P2] Auto-play next sample
  - Player toggle to automatically advance to the next sample (default off).
  - Acceptance: When enabled, playback advances on end-of-media.

### Error Handling & Validation
- [ ] [P1] Improve FFmpeg subprocess failure handling
  - Keep `FFmpegError` but provide actionable remediation in UI; validate args before run.
  - Acceptance: Export/cut failures surface a dialog with failing command summary and suggestions.
- [ ] [P1] Make analysis duration mismatch warning actionable
  - Provide likely causes and a retry with alternate resampling.
  - Acceptance: Warning dialog includes “Try alternate resample” that re-runs analysis.

### Code Quality & Robustness
- [ ] [P1] Fix undo/redo sync issues
  - Fix undo/redo system that occasionally gets out of sync when performing certain actions.
  - Review all actions and ensure they properly push undo states at the correct times.
  - Identify and fix race conditions, missing undo state pushes, or incorrect state restoration that cause sync issues.
  - Add validation to ensure undo/redo stacks remain consistent with actual segment state.
  - Acceptance: Undo/redo remains in sync across all actions; no state inconsistencies occur; undo/redo actions correctly restore previous states regardless of action sequence.
- [ ] [P1] Remove broken Ctrl++ and Ctrl+- zoom shortcuts and View menu options
  - Remove "Zoom In" and "Zoom Out" menu items from View menu and their associated keyboard shortcuts (Ctrl++ and Ctrl+-) as they don't work and are unnecessary.
  - Remove `_on_zoom_in()` and `_on_zoom_out()` handler methods and related action definitions.
  - Update README.md to remove these shortcuts from the Keyboard Shortcuts table.
  - Ensure changes do not break existing functional zooming methods (scroll wheel and navigator highlight).
  - Acceptance: Zoom In/Out menu items and shortcuts removed; README updated; scroll wheel zoom and navigator highlight zoom remain functional; no broken functionality remains. [Docs Impact]

### Processing Pipeline
- [ ] [P1] Build resilient batch processing runner (from `spectrosampler/pipeline.py:Pipeline.process`)
  - Acceptance:
    - Directory processing handles large trees with resume/skip flags, per-file progress, and `jobs>1` parallel execution.
    - Unit tests or integration smoke tests cover single-file and directory workflows, ensuring deterministic output order.
- [ ] [P2] Configure audio cache lifecycle (from `spectrosampler/pipeline.py:Pipeline.__init__`)
  - Acceptance:
    - Cache directory location is configurable, created on demand, and pruned of stale entries without user intervention.
    - Documentation outlines defaults and environment overrides for the cache path.

## **Features**

### Sample Export & Naming
- [ ] [P2] Add bulk rename/edit for samples
  - Multi-select + batch operations, including find/replace in names.
  - Acceptance: Apply a pattern or find/replace to selected rows.
- [ ] [P2] Add export to multiple formats in one run
  - WAV/FLAC/MP3 simultaneous export.
  - Acceptance: Single operation writes multiple formats per selected sample.

### UI Improvements
- [ ] [P1] Add waveform view above spectrogram
  - Add waveform view above spectrogram (below player) with a divider between. Waveform syncs with the current spectrogram view (time range and zoom).
  - Allow hiding via dragging divider and/or View menu option "Show Waveform" (default on).
  - Default height should be the same as the navigator bar below the spectrogram (minimum 60 pixels).
  - Acceptance: Waveform view visible above spectrogram with divider; syncs with spectrogram view changes; can be hidden via divider drag or View menu toggle; default height matches navigator; state persists across sessions. [Docs Impact]
- [ ] [P1] Add spectrogram scale options (linear/log/exp) and color maps
  - Real-time switchable scaling; selectable color schemes.
  - Acceptance: Scale and color map controls with immediate visual update. [Docs Impact]
- [ ] [P2] Add waveform view toggle
  - Switch between spectrogram and waveform for precise edits.
  - Acceptance: Toggle control with synced selection and zoom.
- [ ] [P1] Add filtering/search in sample table
  - Filter by name, detector, time range, or duration.
  - Acceptance: Text+facet filters reduce visible rows accordingly.
- [ ] [P2] Add statistics panel
  - Totals, averages, detector distribution.
  - Acceptance: Panel reflects current table selection and updates live. [Docs Impact]
- [ ] [P2] Add metadata tags for samples
  - Tags/categories on samples (e.g., "bird", "water", "urban"); filter by tags.
  - Acceptance: Tags editable in table; export embeds tags where format supports it; tag filter works. [Docs Impact]
- [ ] [P2] Add timeline markers/bookmarks
  - Place named/color-coded markers on the timeline for reference and quick navigation.
  - Acceptance: Markers visible on ruler, listed in a panel/menu, clickable to jump; persist in project files. [Docs Impact]

### Overlaps & Duplicates
- [ ] [P2] Duplicate sample detection warning
  - Warn on high overlap or similarity threshold.
  - Acceptance: Warning badge in table and quick-fix to remove duplicates.

### Project Management
- No items currently planned

### Settings & Configuration
- [ ] [P1] Add presets for detection/export (GUI integration)
  - Load/Save presets as YAML in `spectrosampler/presets`; quick selector in UI.
  - Acceptance: Preset dropdown and “Save as preset…” dialog. [Docs Impact]
- [ ] [P2] Add customizable keyboard shortcuts
  - Remapping UI with persistence.
  - Acceptance: Changes survive restart; conflicts are prevented.

### Workflow Improvements

#### Export Workflow
- [ ] [P1] Add full export dialog with advanced options
  - Create comprehensive export dialog with tabbed interface: "Global" tab for modifying all global batch settings (format, sample rate, bit depth, channels, bandpass filtering utilizing existing `bandpass_filter`, pre-padding, post-padding, normalization, file name format, export folder, etc.) and "Samples" tab with one-by-one sample review UI.
  - Samples tab shows mini spectrogram and waveform preview for current sample (including pre/post-padding that updates when those settings change), forward/back navigation buttons, and sample indicator showing current position (e.g., "4/72").
  - Allow per-sample overrides for settings that support it (bandpass filtering, padding, normalization, etc.); per-sample settings override global settings when configured.
  - "Cancel" and "Export Sample(s)" buttons visible at bottom regardless of active tab.
  - Move all options from current "Export" menu into new export dialog (pre-padding, post-padding, format, sample rate, bit depth, channels, peak normalization).
  - Include export progress tracking with progress bar, ETA, safe cancel, and end-of-run dialog summarizing per-sample status (success/failures).
  - Support batch export with pause/resume functionality: track per-sample status and allow resuming to complete remaining items after restart.
  - Persist all export settings (batch defaults and per-sample overrides) across sessions.
  - Acceptance: Export dialog has Global and Samples tabs; Samples tab shows current sample preview with forward/back navigation and position indicator (e.g., "4/72"); all settings available as global batch defaults; per-sample settings can override global when configured; Cancel and Export buttons always visible; progress tracking with cancel and summary dialog; pause/resume functionality works; all Export menu options moved to dialog; settings persist across sessions. [Docs Impact]
- [ ] [P1] Expand HTML report contents (from `spectrosampler/report.py:create_html_report`)
  - Acceptance:
    - Report includes processing settings summary, detector statistics, and deep links to generated assets.
    - Smoke test renders the HTML and validates required sections exist.

#### File Management
- [ ] [P1] Polish drag & drop flow
  - Properly load dropped audio file(s).
  - When a project/file is already loaded, show a confirmation dialog with options:
    - "Create New Project" – if there are unsaved changes, prompt to Save/Discard/Cancel; then close current project and load the dropped file(s).
    - "Append Audio File(s)" – keep existing audio and append dropped file(s) to the end of the current timeline with no gap (for split recordings); support multiple dropped files appended in alphanumerical order.
    - "Cancel" – abort the operation.
  - Support drag & drop of multiple audio files simultaneously; process and append in alphanumerical order.
  - Acceptance: The three-choice dialog appears; append preserves timing alignment.

#### Editing Workflow
- [ ] [P1] Add tool modes for spectrogram interaction (Select/Edit/Create)
  - Implement three distinct tool modes similar to modern DAW software: "Select" (allows drag selection of samples compatible with CTRL/SHIFT selection and existing click + CTRL/SHIFT click selection), "Edit" (allows current editing behavior: dragging samples/edges), and "Create" (allows current click drag adding of samples).
  - When each mode is active, all other modes are disabled, allowing the user to select exactly what action they want to do.
  - Add tool mode selector toolbar above detection settings panel (with divider, same default height as player) with visual indication of active mode.
  - Ensure feature integrates with all existing functionality (undo/redo, ESC cancellation, context menus, keyboard shortcuts, etc.).
  - Acceptance: Tool mode selector toolbar visible above detection settings with divider; Select mode enables drag selection box; Edit mode enables sample drag/resize; Create mode enables sample creation; only one mode active at a time; all existing features work correctly in each mode. [Docs Impact]
- [ ] [P1] Add temporary grid snap on Ctrl+drag for sample clips and edges
  - Hold Ctrl while dragging sample clips or resizing clip edges to temporarily snap to grid, even when grid snapping is disabled globally.
  - Snapping applies during drag/resize operations and releases when Ctrl is released or mouse button is released.
  - Acceptance: Holding Ctrl while dragging/resizing snaps to grid positions; releasing Ctrl returns to free movement; works regardless of global grid snap setting. [Docs Impact]
- [ ] [P2] Implement advanced undo/redo
  - Extend undo/redo beyond samples/segments to all project changes, including settings changes (exclude global user settings that apply to all projects, e.g., auto-save).
  - Add Edit menu submenus for Undo and Redo that list the last 10 states with human-readable change descriptions.
  - Add "Undo All" and "Redo All" options for full stack control.
  - Ensure compatibility with existing samples/segments undo stack and UI indicators.
  - Acceptance: Edit menu lists last 10 states with human-readable labels; Undo All/Redo All available; segments/settings changes are reversible without breaking current indicators.

### Documentation & Help
- [ ] [P1] Add in-app Keyboard Shortcuts dialog (F1)
  - Searchable dialog reflecting current shortcuts; link from Help menu.
  - Acceptance: F1 opens dialog; content matches README. [Docs Impact]
- [ ] [P1] Add tooltips and inline help for settings
  - Concise explanations and links to docs.
  - Acceptance: All controls have helpful tooltips. [Docs Impact]
- [ ] [P2] Improve user guide
  - Screenshots and step-by-step tutorials.
  - Acceptance: Updated `README.md` and `docs/GUI_GUIDE.md`. [Docs Impact]

### Utilities

- No items currently planned

## **Performance & Optimization**

### Memory & Processing
- [ ] [P1] Expose spectrogram tile cache size and stats
  - `SpectrogramTiler` already has LRU (default 64). Add setting and a status readout.
  - Acceptance: Setting to change cache size; UI shows current tile count and memory estimate. [Docs Impact]
- [ ] [P2] Optimize spectrogram generation for very large files
  - Consider chunked/streaming processing and progressive loading (lower-res first).
  - Acceptance: Files > 1h remain responsive during navigation.
- [ ] [P1] Add background detection progress and cancellation
  - Keep UI responsive and allow cancel.
  - Acceptance: Progress indicator and responsive cancel during detection.
- [ ] [P2] Add multi-threading for detection where safe
  - Parallelize detector execution across cores when thread-safe.
  - Acceptance: Noticeable speedup on multi-core systems without UI jank.

### UI Responsiveness
- [ ] [P1] Navigator rendering quality & performance
  - Reduce pixelation at high zoom with adaptive resolution while keeping smooth interaction.
  - Acceptance: No visible pixelation at high zoom; target 60 FPS on typical files.
- [ ] [P1] Debounce/throttle bursty UI updates
  - Smooth slider drags and rapid changes; batch redraws.
  - Acceptance: No noticeable lag when adjusting settings rapidly.

## **Testing & Quality Assurance**

### Test Coverage
- [ ] [P1] Add GUI integration tests for core workflows
  - File load → detect → edit → export happy path.
  - Acceptance: Stable tests passing in CI.
- [ ] [P1] Add pipeline integration regression test (from `tests/test_cli_integration.py:test_cli_integration`)
  - Acceptance:
    - Test harness runs the pipeline entry point against synthetic audio, producing actual samples/markers in a temporary directory.
    - Assertions validate exported filenames, manifest counts, and metadata contents.
- [ ] [P2] Add performance benchmarks
  - Track detection, processing, and UI operations over time.
  - Acceptance: Baselines defined; regressions flagged.