# TODO

## **Notes**

_Unreleased: no backward compatibility guarantees. Optimize functionality first._

Items marked [Docs Impact] will require updates to `README.md` and/or `docs/GUI_GUIDE.md`.

**Priority levels:**
- [P0] Critical/near-term items for correctness, stability, or unblocking core workflows.
- [P1] High-priority improvements that materially enhance UX/functionality; schedule next iterations.
- [P2] Nice-to-have or longer-term enhancements; plan after P0/P1.

_Summary: P0: 0 items, P1: 19 items, P2: 12 items_

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

### Audio Playback
- [ ] [P1] Improve seamless looping for short samples
  - Improve QMediaPlayer usage and buffering; consider crossfade option and/or pre-buffering.
  - Acceptance: On a 250 ms loop, audible gap < 10 ms; optional crossfade toggle.

### Error Handling & Validation
- No items currently planned

### Code Quality & Robustness
- [ ] [P1] Fix undo/redo sync issues
  - Fix undo/redo system that occasionally gets out of sync when performing certain actions.
  - Review all actions and ensure they properly push undo states at the correct times.
  - Identify and fix race conditions, missing undo state pushes, or incorrect state restoration that cause sync issues.
  - Add validation to ensure undo/redo stacks remain consistent with actual segment state.
  - Acceptance: Undo/redo remains in sync across all actions; no state inconsistencies occur; undo/redo actions correctly restore previous states regardless of action sequence.
### Processing Pipeline
- [ ] [P2] Configure audio cache lifecycle (from `spectrosampler/pipeline.py:Pipeline.__init__`)
  - Acceptance:
    - Cache directory location is configurable, created on demand, and pruned of stale entries without user intervention.
    - Documentation outlines defaults and environment overrides for the cache path.

## **Features**

### UI Improvements
- [ ] [P1] Add spectrogram scale options (linear/log/exp) and color maps
  - Real-time switchable scaling; selectable color schemes.
  - Acceptance: Scale and color map controls with immediate visual update. [Docs Impact]
- [ ] [P2] Implement custom splitter handles for editor stack
  - Keep independent divider handles for player, waveform, and spectrogram when collapsing views.
  - Ensure collapsing the waveform by drag leaves a handle visible without resizing the player.
  - Acceptance: Dragging the waveform divider to zero height keeps a visible handle, preserves player height, and persists across sessions.
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