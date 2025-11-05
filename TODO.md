# TODO

Note: Do not worry about backward compatibility for now. The program is unreleased, so anything can be changed. The goal is to improve the functionality as much as possible.

## Fixes

### Detection & Sample Processing
- [ ] Change detection algorithms/settings defaults to improve detection accuracy
  - Review current defaults for VoiceVAD aggressiveness (currently hardcoded to 3), threshold values, and padding settings
  - Consider adaptive thresholds based on audio characteristics
  - Add validation to ensure detector settings are within valid ranges

### Audio Playback
- [ ] Make looping samples more seamless (currently very choppy with short samples)
  - Investigate QMediaPlayer loop functionality and buffering for seamless playback
  - Consider using sounddevice for lower-latency playback with better looping support
  - Add crossfade option for loop transitions
  - May need to pre-load and buffer short samples differently

### Error Handling & Validation
- [ ] Check FFmpeg availability at application startup and show user-friendly error if missing
  - Currently `check_ffmpeg()` exists but may not be called early enough
  - Display helpful installation instructions in error dialog
- [ ] Improve error handling for audio file loading failures
  - Add validation for file existence, format support, and corruption before processing
  - Show user-friendly error messages instead of silent failures or generic exceptions
- [ ] Handle FFmpeg subprocess failures more gracefully
  - Currently raises generic `FFmpegError` - add more specific error types and recovery suggestions
  - Validate FFmpeg command arguments before execution
- [ ] Fix analysis duration mismatch warning to be more actionable
  - Currently logs warning but doesn't suggest fixes or prevent potential issues
  - Consider retry logic or alternative resampling methods

### Code Quality & Robustness
- [ ] Replace bare `except Exception:` clauses with specific exception types
  - Found in `pipeline.py` (detector initialization) and `audio_io.py` - should catch specific exceptions
  - Add proper error logging for debugging
- [ ] Complete TODO items in code comments
  - `dsp.py`: Implement geometric mean calculation and highpass/lowpass filtering
  - `utils.py`: Complete sanitize_filename TODO (handle non-ASCII gracefully) and format_duration (hours/minutes formatting)
  - `export.py`: Markers export functions have TODOs but appear implemented - verify and remove comments
  - `pipeline.py`: Batch processing and parallelization TODOs
- [ ] Add input validation for settings ranges
  - Validate min/max durations, padding values, thresholds, etc. to prevent invalid configurations
  - Show warnings when settings may cause issues (e.g., very large max_samples)

## Features

### Sample Export & Naming
- [ ] Add ability to set names for exported samples
  - Add a "Name" row to the sample info section
  - Allow user to input a custom name for each sample that is added to the existing file naming
  - Example: for "field.wav" input file - `field_sample_0000_14.2s-14.4s_detector-manual.wav` becomes `field_sample_0000_bird_14.2s-14.4s_detector-manual.wav` when name is set to "bird"
  - When no name is set, use current file name format
- [ ] Add bulk rename/edit functionality for samples
  - Allow selecting multiple samples and applying name patterns or batch edits
  - Support find/replace in sample names
- [ ] Export samples to multiple formats simultaneously
  - Allow exporting same samples to WAV, FLAC, MP3, etc. in one operation
  - Useful for creating sample packs with different format options

### UI Improvements
- [ ] Add logarithmic & exponential spectrogram options
  - Currently only linear scaling available - add options for better frequency visualization
  - Allow user to switch between scales in real-time
- [ ] Add playback indicator to main spectrogram
  - When a sample is playing and in current spectrogram view window, render a line that moves across the sample as it plays
  - Alternatively add a simple speaker icon to indicate the currently playing sample
  - Do both if possible
- [ ] Add waveform view option alongside spectrogram
  - Option to toggle between spectrogram and waveform visualization
  - Useful for precise editing and timing
- [ ] Add color customization for spectrogram
  - Allow users to choose color schemes (e.g., grayscale, color, inverted)
  - Useful for different use cases and accessibility
- [ ] Implement sample filtering/search in table
  - Add search box to filter samples by name, detector type, time range, or duration
  - Useful for large sample counts
- [ ] Add multi-select functionality in sample table
  - Allow Ctrl+Click and Shift+Click selection of multiple samples
  - Enable bulk operations (delete, export, rename, etc.)
- [ ] Add zoom to fit selection
  - Keyboard shortcut or button to zoom spectrogram to fit selected sample(s)
  - Quick navigation to selected samples
- [ ] Add statistics panel
  - Show total samples, total duration, average sample length, etc.
  - Display detection statistics (detector distribution, score ranges)
- [ ] Add duplicate sample detection warning
  - Warn when samples overlap significantly or are very similar
  - Option to automatically remove duplicates

### Project Management
- [ ] Implement project files (saves current "project" audio file, samples, settings, etc. to be able to exit program and resume creating sample pack)
  - Useful for very long audio files
  - Save format: JSON or custom format with audio path reference, all sample segments, settings, UI state
  - Include version information for project file compatibility
- [ ] Implement welcome screen with options to create new project or open project
  - Show recent projects list
  - Quick start templates
- [ ] Add action under "File" menu: save project & load project
  - Keyboard shortcuts: Ctrl+S to save, Ctrl+O to open
- [ ] Add auto-save functionality
  - Periodically save project state to temporary file
  - Auto-recovery on crash with option to restore
- [ ] Add recent files menu
  - Track recently opened audio files in menu
  - Persist across application restarts

### Settings & Configuration
- [ ] Change max samples range to (1-10000) to match all possible file name outputs: "sample_0000"-"sample_9999"
  - Currently limited to lower range - expand to support 4-digit zero-padding fully
- [ ] Implement settings presets for sample detection/export
  - Save/load named presets for different use cases (voice, transients, music, etc.)
  - Share presets via files (YAML/JSON format)
  - Quick preset selector in UI
- [ ] Add settings persistence
  - Remember user's preferred settings between sessions
  - Store in user config directory (platform-appropriate)
- [ ] Add customizable keyboard shortcuts
  - Allow users to remap keyboard shortcuts
  - Save custom key bindings in settings

### Workflow Improvements
- [ ] Add export progress indicator with cancel option
  - Show progress bar and estimated time remaining during export
  - Allow cancellation of long-running exports
  - Resume capability for interrupted exports
- [ ] Add sample preview before export
  - Quick preview dialog showing sample boundaries and basic info
  - Option to adjust before final export
- [ ] Add drag and drop support for multiple audio files
  - Currently supports single file - allow batch loading
  - Queue files for sequential or parallel processing
- [ ] Add batch export with resume capability
  - Export large numbers of samples with ability to pause/resume
  - Track export status per sample
- [ ] Add undo/redo keyboard shortcuts
  - Currently has undo/redo stacks but may not have keyboard shortcuts (Ctrl+Z, Ctrl+Shift+Z)
  - Show in Edit menu with current state

### Documentation & Help
- [ ] Add keyboard shortcuts help dialog
  - List all available keyboard shortcuts in a searchable dialog
  - Accessible via Help menu or F1
- [ ] Add tooltips and help text for settings
  - Explain what each setting does and its impact
  - Link to more detailed documentation
- [ ] Improve user guide documentation
  - Add screenshots and step-by-step tutorials
  - Video tutorials for common workflows
- [ ] Add API documentation
  - Generate Sphinx/other docs for developer API
  - Document detector interface and extension points

## Performance & Optimization

### Memory & Processing
- [ ] Implement lazy loading of spectrogram tiles
  - Currently may load all tiles at once - load on-demand as user navigates
  - Reduce memory usage for very long audio files
- [ ] Add cache management with size limits
  - Implement cache size limits and cleanup policies
  - Show cache size in settings and allow manual cleanup
  - Prevent cache from growing unbounded
- [ ] Optimize spectrogram generation for large files
  - Consider chunked processing or streaming for files > 1 hour
  - Progressive loading with lower resolution first
- [ ] Add background processing for detection
  - Run detection in background thread to keep UI responsive
  - Show progress and allow cancellation
- [ ] Implement multi-threading for detection
  - Parallelize detector execution where possible
  - Use all CPU cores for faster processing

### UI Responsiveness
- [ ] Optimize navigator scrollbar rendering
  - Currently mentioned as pixelated at high zoom - implement adaptive resolution
  - Cache rendered tiles to avoid regeneration
- [ ] Debounce/throttle UI updates during rapid changes
  - Prevent UI lag when adjusting sliders or rapidly changing settings
  - Batch updates where possible

## Testing & Quality Assurance

### Test Coverage
- [ ] Add integration tests for GUI workflows
  - Test file loading, detection, export end-to-end
  - Use Qt testing frameworks or automated UI testing
- [ ] Add performance benchmarks
  - Benchmark detection algorithms, file processing, and UI operations
  - Track performance regressions
- [ ] Add tests for edge cases
  - Very short/long audio files, corrupted files, unsupported formats
  - Boundary conditions (zero samples, overlapping samples, etc.)
- [ ] Add tests for error handling
  - FFmpeg failures, missing files, invalid settings
  - Verify user-friendly error messages are shown

## Low Priority

### UI Enhancements
- [ ] Generate higher resolution on the navigator scrollbar when zooming in (maybe have a high/medium/low resolution?)
  - It gets pretty pixelated past a certain zoom level
  - Make sure to implement in a way that doesn't slow down zooming and moving on the navigator
  - Consider adaptive quality based on zoom level
- [ ] Add export project as template
  - Save project settings as reusable template for similar audio files
  - Share templates with community
- [ ] Add metadata tags support
  - Add tags/categories to samples (e.g., "bird", "water", "urban")
  - Export metadata with samples (e.g., ID3 tags, WAV metadata chunks)
  - Filter and search by tags
- [ ] Add timeline markers/bookmarks
  - Allow users to place custom markers on timeline for reference
  - Name and color-code markers
- [ ] Add audio analysis tools
  - RMS level, peak detection, frequency analysis per sample
  - Visualize audio characteristics in sample info panel

