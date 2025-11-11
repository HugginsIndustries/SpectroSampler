# TODO

## **Notes**

_Unreleased: no backward compatibility guarantees. Optimize functionality first._

Items marked [Docs Impact] will require updates to `README.md` and/or `docs/GUI_GUIDE.md`.

**Priority levels:**
- [P0] Critical/near-term items for correctness, stability, or unblocking core workflows.
- [P1] High-priority improvements that materially enhance UX/functionality; schedule next iterations.
- [P2] Nice-to-have or longer-term enhancements; plan after P0/P1.

_Summary: P0: 0 items, P1: 32 items, P2: 20 items_

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
- [ ] [P1] Improve audio loading failure messages
  - Validate file existence/format/corruption early; replace generic exceptions with specific messages.
  - Acceptance: File open failure dialogs name the cause and suggest next steps.
- [ ] [P1] Improve FFmpeg subprocess failure handling
  - Keep `FFmpegError` but provide actionable remediation in UI; validate args before run.
  - Acceptance: Export/cut failures surface a dialog with failing command summary and suggestions.
- [ ] [P1] Make analysis duration mismatch warning actionable
  - Provide likely causes and a retry with alternate resampling.
  - Acceptance: Warning dialog includes “Try alternate resample” that re-runs analysis.

### Code Quality & Robustness
- [ ] [P1] Verify marker export formats (from `spectrosampler/export.py`)
  - Acceptance:
    - Audacity label, REAPER region CSV, and timestamps CSV outputs match published schemas and reflect optional padding flags.
    - Regression tests open the generated files and assert headers/rows align with expectations.
- [ ] [P1] Add input validation for settings ranges
  - Validate durations, paddings, thresholds, etc.; disable invalid UI inputs or surface validation messages.
  - Acceptance: Impossible values cannot be entered or are rejected with clear guidance.

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
- [ ] [P1] Add optional sample name field for export filenames
  - Add a Name field; append to current filename template when set.
  - Acceptance: `field_sample_0000_bird_14.2s-14.4s_detector-manual.wav` when Name="bird"; otherwise current format.
- [ ] [P2] Add bulk rename/edit for samples
  - Multi-select + batch operations, including find/replace in names.
  - Acceptance: Apply a pattern or find/replace to selected rows.
- [ ] [P2] Add export to multiple formats in one run
  - WAV/FLAC/MP3 simultaneous export.
  - Acceptance: Single operation writes multiple formats per selected sample.

### UI Improvements
- [ ] [P1] Add spectrogram scale options (linear/log/exp) and color maps
  - Real-time switchable scaling; selectable color schemes.
  - Acceptance: Scale and color map controls with immediate visual update. [Docs Impact]
- [ ] [P1] Add playback indicator in main spectrogram
  - Moving line (or icon) for the currently playing sample when in view.
  - Acceptance: Indicator accurately tracks playback position.
- [ ] [P2] Add waveform view toggle
  - Switch between spectrogram and waveform for precise edits.
  - Acceptance: Toggle control with synced selection and zoom.
- [ ] [P1] Add filtering/search in sample table
  - Filter by name, detector, time range, or duration.
  - Acceptance: Text+facet filters reduce visible rows accordingly.
- [ ] [P1] Add multi-select in sample table
  - Ctrl/Shift selection enabling bulk operations.
  - Acceptance: Bulk delete/export/rename across selected rows.
- [ ] [P2] Restore editor splitter layout on load (from `spectrosampler/gui/main_window.py:_restore_window_geometry`)
  - Acceptance:
    - Saving and reopening a project restores the inner editor splitter sizes exactly as previously stored.
    - Automated GUI test or manual checklist verifies collapse/expand state survives restart.
- [ ] [P2] Add zoom to fit selection
  - Shortcut/button to fit selected samples in view.
  - Acceptance: View window adjusts to encompass selected segments.
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
- [ ] [P1] Add edit menu actions for removing overlaps and duplicates
  - Add `Remove All Overlaps` and `Remove All Duplicates` under the `Edit` menu.
  - Acceptance:
    - `Remove All Overlaps` keeps the earliest-starting sample in each overlap group and removes the rest.
    - `Remove All Duplicates` removes samples whose start/end times are within 5 ms of another sample, keeping one per set.
    - Actions disable when no overlaps or duplicates are detected.

### Project Management
- No items currently planned

### Settings & Configuration
- [ ] [P1] Add presets for detection/export (GUI integration)
  - Load/Save presets as YAML in `spectrosampler/presets`; quick selector in UI.
  - Acceptance: Preset dropdown and “Save as preset…” dialog. [Docs Impact]
- [ ] [P1] Persist detection and export settings (QSettings + project round-trip)
  - Restore on app restart and when loading projects.
  - Acceptance: Last-used values restored; project load applies saved values. [Docs Impact]
- [ ] [P2] Add customizable keyboard shortcuts
  - Remapping UI with persistence.
  - Acceptance: Changes survive restart; conflicts are prevented.
- [ ] [P1] Persist overlap handling defaults in project settings
  - Ensure the settings panel writes dialog visibility and default behavior into `ProcessingSettings` so projects carry the preference.
  - Acceptance:
    - Saving and reopening a project restores overlap dialog visibility and default behavior.
    - Overlap resolution uses the restored values without re-prompting when the dialog is disabled.

### Workflow Improvements

#### Export Workflow
- [ ] [P1] Add export progress with cancel and final summary
  - Progress bar, ETA, safe cancel; end-of-run dialog summarizing per-sample status.
  - Acceptance: Summary lists success/failures; cancel cleans temporary files. [Docs Impact]
- [ ] [P1] Expand HTML report contents (from `spectrosampler/report.py:create_html_report`)
  - Acceptance:
    - Report includes processing settings summary, detector statistics, and deep links to generated assets.
    - Smoke test renders the HTML and validates required sections exist.
- [ ] [P2] Add sample preview before export
  - Lightweight preview/edit dialog for boundaries and info.
  - Acceptance: Adjustments applied prior to writing files.
- [ ] [P1] Add optional peak normalization on export
  - When enabled, normalize each sample to a target peak (e.g., -0.1 dBFS) without clipping.
  - Acceptance: Export setting toggle; resulting files peak at target ±0.1 dB; no clipping; source audio unchanged. [Docs Impact]
- [ ] [P2] Add batch export with pause/resume
  - Track per-sample status and allow resume.
  - Acceptance: Resuming completes remaining items after restart.

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

- [ ] [P2] Add diagnostics panel
  - Show FFmpeg version, audio device info, and environment details.
  - Acceptance: Accessible from Help; assists in support cases. [Docs Impact]

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
- [ ] [P1] Add edge case tests
  - Very short/long files, unsupported/corrupt files, boundary conditions.
  - Acceptance: Clear error messages and no crashes.
- [ ] [P1] Add error handling tests
  - FFmpeg missing/failures, invalid settings.
  - Acceptance: Expected dialogs and logs, no uncaught exceptions.