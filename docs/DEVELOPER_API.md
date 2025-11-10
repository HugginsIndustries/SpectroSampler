# SpectroSampler Developer API

SpectroSampler ships as a desktop-first experience, but the core engine is reusable
from Python. This guide maps the modules that make up the processing pipeline and
shows how to stitch them together in automation scripts or notebooks.

---

## Module Overview

| Module | Responsibility | Highlights |
| --- | --- | --- |
| `spectrosampler.pipeline` | High-level orchestration for denoise → detect → export. | `process_file()` helper and `Pipeline` class for batch work. |
| `spectrosampler.pipeline_settings` | Container for tunable knobs used by the pipeline and GUI. | `ProcessingSettings` collects detection, padding, and export options. |
| `spectrosampler.detectors` | Detector implementations and shared data model. | `BaseDetector`, concrete detectors, and the `Segment` struct. |
| `spectrosampler.audio_io` | FFmpeg-backed helpers for metadata, resampling, denoise, and cutting. | `check_ffmpeg()`, `denoise_audio()`, `extract_sample()`, spectrogram utilities. |
| `spectrosampler.export` | File naming and export flows. | `build_sample_filename()`, `export_sample()`, marker/CSV writers. |
| `spectrosampler.report` | HTML and annotated spectrogram report helpers. | `create_html_report()` and `create_annotated_spectrogram()`. |

Every module is importable without launching the GUI. The public surface is regular
Python—you can unit test or extend components just like any other library code.

---

## Minimal Pipeline Script

```python
from pathlib import Path

from spectrosampler.pipeline import Pipeline
from spectrosampler.pipeline_settings import ProcessingSettings

settings = ProcessingSettings(
    mode="auto",
    detection_pre_pad_ms=40.0,
    detection_post_pad_ms=120.0,
    export_pre_pad_ms=50.0,
    export_post_pad_ms=150.0,
    max_samples=128,
    format="wav",
    spectrogram=True,
    report="html",
)

pipeline = Pipeline(settings)
pipeline.process(
    input_path=Path("field_recording.wav"),
    output_dir=Path("build/samples"),
)
```

The script mirrors the GUI defaults:

- `ProcessingSettings` accepts keyword args for every dial exposed in the app.
- `Pipeline.process()` takes either a single file or a directory tree; it will
  denoise, resample, run the configured detectors, deduplicate/merge, write samples,
  and emit reports into the supplied output directory.
- FFmpeg must be on PATH (`spectrosampler.audio_io.check_ffmpeg()` validates this
  when the pipeline is constructed).

---

## Working with Segments

Detectors emit `Segment` instances (defined in `spectrosampler.detectors.base`):

```python
from spectrosampler.detectors import Segment

segment = Segment(start=12.345, end=13.210, detector="voice", score=0.87, attrs={})
duration_seconds = segment.duration()
```

Each segment stores:

- `start`/`end` in seconds (floats).
- `detector` label (string).
- `score` (detector-specific confidence).
- `attrs` (dict) for extra metadata such as `primary_detector` or raw bounds.

Segments flow through merge, spread, export, and reporting helpers without GUI code.
You can mutate or filter them before exporting.

---

## Extending Detection

Create a custom detector by subclassing `BaseDetector`:

```python
from spectrosampler.detectors import BaseDetector, Segment


class MyDetector(BaseDetector):
    name = "my-detector"

    def detect(self, audio, sample_rate):
        # audio is a 1-D NumPy array, sample_rate is an int
        peaks = find_stuff(audio, sample_rate)
        return [
            Segment(start=peak.start, end=peak.end, detector=self.name, score=peak.score)
            for peak in peaks
        ]
```

Then inject it into your pipeline:

```python
pipeline = Pipeline(settings)
custom_segments = MyDetector().detect(audio_array, sample_rate)
# Merge with built-in detectors
```

`process_file()` assembles the built-in detectors automatically, but you can copy
the approach if you need finer control (e.g., add detectors, adjust scoring, or
swap in alternate preprocessing).

---

## Utility Building Blocks

- **FFmpeg helpers** (in `audio_io`) wrap common operations—denoising, resampling,
  sample extraction, and spectrogram rendering—while raising `FFmpegError` with
  the raw command output when failures occur.
- **Export helpers** (in `export`) produce sanitized filenames and write timestamp
  manifests compatible with Audacity and REAPER.
- **Reports** (in `report`) can convert a processed run into HTML, annotated PNGs,
  or JSON summaries when you want to integrate with dashboards or ops tooling.

Combine these to build bespoke workflows: reuse the cache (`AudioCache`), generate
spectrograms for QA, or call `export_sample()` directly for ad hoc cuts.

---

## Next Steps

- For GUI workflows, continue with `docs/GUI_GUIDE.md`.
- To contribute new detectors or pipeline behaviours, browse the corresponding
  modules under `spectrosampler/` and follow the existing patterns for logging,
  error handling, and configuration.

