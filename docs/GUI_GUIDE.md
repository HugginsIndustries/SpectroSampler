# SamplePacker GUI Guide

## Getting Started

### Launching the Application

Launch the GUI application:

```bash
samplepacker-gui
```

Or:

```bash
python -m samplepacker.gui
```

### Opening Audio Files

1. **File Menu**: File → Open Audio File
2. **Drag and Drop**: Drag audio files onto the window
3. **Supported Formats**: WAV, FLAC, MP3, M4A, AAC

## Interface Overview

### Main Window Layout

- **Left Panel**: Settings panel with all processing parameters
- **Center**: Timeline ruler (top), spectrogram view (middle), navigator scrollbar (bottom)
- **Bottom**: Sample table showing all detected samples

### Resizable Panels

All UI elements are resizable by clicking and dragging the edges, similar to modern DAWs like Bitwig.

## Spectrogram Navigation

### Zoom

- **Mouse Wheel**: Zoom in/out (with Ctrl for fine control)
- **Zoom Controls**: Use View menu or keyboard shortcuts
- **Zoom Levels**: 0.5x (overview) to 32x (maximum detail)
- **Zoom Center**: Zoom centers on mouse cursor position

### Pan

- **Navigator**: Click and drag in navigator scrollbar to navigate
- **Arrow Keys**: Use arrow keys to pan left/right
- **Timeline**: Click on timeline ruler to jump to time position

### Timeline Ruler

- **Time Markers**: Shows time markers (seconds, minutes, hours)
- **Click to Jump**: Click on timeline ruler to jump to time position
- **Adaptive Scale**: Time markers adapt to zoom level

### Navigator Scrollbar

- **Overview**: Shows miniature spectrogram of entire file
- **View Indicator**: Light grey rectangle shows current visible range
- **Navigate**: Click/drag in navigator to navigate
- **Resize View**: Drag edges of view indicator to resize visible range

## Sample Editing

### Selecting Samples

- **Click**: Click on sample marker in spectrogram
- **Table**: Click on row in sample table
- **Multiple Selection**: Use Ctrl/Cmd to select multiple samples

### Moving Samples

- **Drag**: Click and drag sample marker to move
- **Snap**: Enable grid snapping to snap to grid positions
- **Keyboard**: Use arrow keys to nudge selected samples

### Resizing Samples

- **Edges**: Click and drag left/right edges of sample marker
- **Snap**: Enable grid snapping to snap edges to grid positions
- **Minimum**: Minimum sample duration is enforced

### Creating Samples

- **Click and Drag**: Click and drag on empty spectrogram area
- **Snap**: Enable grid snapping to snap to grid positions
- **Visual Feedback**: Shows preview while dragging

### Deleting Samples

- **Delete Key**: Select sample and press Delete key
- **Context Menu**: Right-click sample for context menu
- **Table**: Uncheck sample in table to exclude from export

## Grid Snapping

### Free Time Mode

- **Snap Interval**: Set snap interval (e.g., 0.1s, 0.5s, 1s)
- **Grid Lines**: Visual grid lines at snap intervals
- **Adaptive**: Grid spacing adapts to zoom level

### Musical Bar Grid Mode

- **BPM**: Set tempo (60-200 BPM)
- **Subdivision**: Choose subdivision (whole, half, quarter, eighth, sixteenth, thirty-second)
- **Time Signature**: Set time signature (4/4, 3/4, 6/8, etc.)
- **Beat Numbers**: Shows beat numbers on grid

### Toggle Snap

- **Checkbox**: Check/uncheck "Snap to grid" in settings
- **Keyboard**: Press `G` key to toggle snap
- **Visual Feedback**: Highlights nearest grid line when near snap point

## Frequency Filtering

### High-Pass Filter

- **Slider**: Adjust high-pass filter frequency (Hz)
- **Real-time**: Spectrogram updates automatically
- **Range**: 0-20kHz

### Low-Pass Filter

- **Slider**: Adjust low-pass filter frequency (Hz)
- **Real-time**: Spectrogram updates automatically
- **Range**: 0-20kHz

### Frequency Range Display

- **Visual Indicator**: Shows active frequency range on spectrogram axis
- **Filtered Spectrogram**: Only selected frequency range is displayed
- **Cache**: Filtered spectrograms are cached for performance

## Processing Workflow

### Step 1: Open Audio File

1. File → Open Audio File
2. Select audio file
3. File metadata is loaded and displayed

### Step 2: Adjust Settings

1. **Detection Mode**: Choose detection mode (auto, voice, transient, etc.)
2. **Timing Parameters**: Adjust pre-padding, post-padding, merge gap, etc.
3. **Audio Processing**: Configure denoise, filters, noise reduction
4. **Grid Settings**: Configure grid snapping (optional)

### Step 3: Process Preview

1. Click "Update Preview" button
2. Processing runs in background
3. Progress is shown in status bar
4. Detected samples appear on spectrogram

### Step 4: Edit Samples

1. **Select**: Click on sample markers
2. **Move**: Drag markers to adjust positions
3. **Resize**: Drag edges to adjust durations
4. **Create**: Click and drag to create new samples
5. **Delete**: Select and press Delete key

### Step 5: Export Samples

1. **Select**: Check samples to export in sample table
2. **Export**: File → Export Samples
3. **Choose Directory**: Select output directory
4. **Export**: Samples are exported to selected directory

## Keyboard Shortcuts

- **Open**: `Ctrl+O` (File → Open)
- **Save/Export**: `Ctrl+S` (File → Export)
- **Zoom In**: `Ctrl++` or `Ctrl+=`
- **Zoom Out**: `Ctrl+-`
- **Fit to Window**: `Ctrl+0`
- **Play**: `Space` (double-click sample)
- **Delete**: `Delete` key
- **Snap Toggle**: `G` key
- **Pan Left**: `Left Arrow`
- **Pan Right**: `Right Arrow`
- **Quit**: `Ctrl+Q`

## Tips for Long Recordings

### Performance

- **Tiled Rendering**: Spectrogram is rendered in tiles for long files
- **Lazy Loading**: Tiles are loaded on-demand as you zoom/pan
- **Caching**: Generated tiles are cached for performance
- **Overview**: Use overview in navigator for quick navigation

### Navigation

- **Navigator**: Use navigator scrollbar for quick navigation
- **Timeline**: Click on timeline ruler to jump to positions
- **Zoom Levels**: Use lower zoom levels for overview, higher for detail
- **Keyboard**: Use keyboard shortcuts for faster navigation

### Sample Editing

- **Grid Snapping**: Enable grid snapping for precise editing
- **Multiple Selection**: Use Ctrl/Cmd to select multiple samples
- **Batch Operations**: Use sample table for batch selection
- **Visual Feedback**: Watch for snap indicators when near grid points

## Troubleshooting

### Audio File Won't Load

- Check file format is supported (WAV, FLAC, MP3, M4A, AAC)
- Verify FFmpeg is installed and in PATH
- Check file is not corrupted

### Preview Processing Fails

- Check FFmpeg is installed and in PATH
- Verify audio file is valid
- Check settings are valid
- Look at error message in status bar

### Spectrogram Not Displaying

- Ensure audio file is loaded
- Check frequency range settings
- Verify processing completed successfully
- Try updating preview again

### Samples Not Appearing

- Check detection mode settings
- Adjust threshold if needed
- Verify timing parameters are reasonable
- Check max samples limit

## Advanced Features

### Settings Persistence

- Window state (size, position, splitter positions) is saved
- Last used directory is remembered
- Grid preferences are saved
- Theme preferences are saved

### Batch Processing

- Use CLI for batch processing (deprecated but still available)
- GUI is optimized for single file processing with preview

### Export Options

- Export only selected samples
- Preserve original quality (no re-encoding)
- Optional format conversion
- Custom filename templates

