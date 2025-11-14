"""Export manager orchestrating batch exports with progress and pause/resume control."""

from __future__ import annotations

import threading
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QThread, Signal

from spectrosampler.detectors.base import Segment
from spectrosampler.export import export_sample
from spectrosampler.gui.export_models import (
    DEFAULT_FILENAME_TEMPLATE,
    ExportBatchSettings,
    ExportSampleOverride,
    apply_template,
    build_template_context,
    compute_sample_id,
    derive_sample_title,
    render_filename_from_template,
)
from spectrosampler.utils import sanitize_filename


@dataclass(slots=True)
class ExportSampleResult:
    """Outcome of exporting a single sample."""

    sample_id: str
    index: int
    formats: list[str] = field(default_factory=list)
    output_paths: list[Path] = field(default_factory=list)
    success: bool = True
    message: str | None = None


@dataclass(slots=True)
class ExportSummary:
    """Aggregate summary returned by the manager."""

    total_samples: int
    completed: list[ExportSampleResult] = field(default_factory=list)
    failed: list[ExportSampleResult] = field(default_factory=list)
    cancelled: bool = False
    resume_state: dict[str, str] = field(default_factory=dict)
    remaining_sample_ids: list[str] = field(default_factory=list)

    @property
    def successful_count(self) -> int:
        return len(self.completed)


@dataclass(slots=True)
class _ExportTask:
    """Internal representation of a single export task."""

    sample_id: str
    index: int
    segment: Segment
    override: ExportSampleOverride | None


class ExportWorker(QObject):
    """Worker that performs exports in a background thread."""

    progress = Signal(float, int, int)
    sample_started = Signal(str, int)
    sample_finished = Signal(ExportSampleResult)
    state_changed = Signal(str)
    finished = Signal(ExportSummary)
    error = Signal(str)

    def __init__(
        self,
        *,
        audio_path: Path,
        base_name: str,
        output_dir: Path,
        batch_settings: ExportBatchSettings,
        tasks: Sequence[_ExportTask],
        resume_state: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__()
        self._audio_path = audio_path
        self._base_name = base_name
        self._output_dir = output_dir
        self._batch_settings = replace(batch_settings)
        self._tasks = list(tasks)
        self._resume_state: dict[str, str] = dict(resume_state or {})

        self._cancel_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.clear()
        self._start_time: float | None = None
        self._processed_count: int = 0

    def cancel(self) -> None:
        """Request cancellation."""

        self._cancel_event.set()

    def pause(self) -> None:
        """Pause the export loop."""

        self._pause_event.set()
        self.state_changed.emit("paused")

    def resume(self) -> None:
        """Resume a paused export loop."""

        if self._pause_event.is_set():
            self._pause_event.clear()
            self.state_changed.emit("running")

    def run(self) -> None:
        """Entry point executed on the worker thread."""

        try:
            summary = self._execute()
        except Exception as exc:  # pragma: no cover - defensive
            self.error.emit(str(exc))
            return
        self.finished.emit(summary)

    def run_blocking(self) -> ExportSummary:
        """Execute exports on the current thread (synchronous code path)."""

        return self._execute()

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _execute(self) -> ExportSummary:
        total = len(self._tasks)
        completed_results: list[ExportSampleResult] = []
        failed_results: list[ExportSampleResult] = []
        processed = 0
        resume_snapshot = dict(self._resume_state)
        remaining_ids: list[str] = []

        ensure_dir = self._output_dir
        ensure_dir.mkdir(parents=True, exist_ok=True)

        self._start_time = time.monotonic()
        for task in self._tasks:
            if self._cancel_event.is_set():
                remaining_ids.append(task.sample_id)
                break

            while self._pause_event.is_set() and not self._cancel_event.is_set():
                time.sleep(0.1)

            self.sample_started.emit(task.sample_id, task.index)
            result = self._process_task(task)

            if result.success:
                completed_results.append(result)
                resume_snapshot[task.sample_id] = "completed"
            else:
                failed_results.append(result)
                resume_snapshot[task.sample_id] = "failed"
                if task.sample_id not in remaining_ids:
                    remaining_ids.append(task.sample_id)

            processed += 1
            self._processed_count = processed
            percent = processed / total if total else 1.0
            self.sample_finished.emit(result)
            self.progress.emit(percent, processed, total)

        # Append remaining tasks when cancelled mid-loop
        seen_remaining = set(remaining_ids)
        for task in self._tasks[processed:]:
            if task.sample_id in resume_snapshot and resume_snapshot[task.sample_id] == "completed":
                continue
            if task.sample_id not in seen_remaining:
                remaining_ids.append(task.sample_id)
                seen_remaining.add(task.sample_id)

        for sample_id in remaining_ids:
            resume_snapshot.setdefault(sample_id, "pending")

        summary = ExportSummary(
            total_samples=total,
            completed=completed_results,
            failed=failed_results,
            cancelled=self._cancel_event.is_set(),
            resume_state=resume_snapshot,
            remaining_sample_ids=remaining_ids,
        )
        return summary

    def _process_task(self, task: _ExportTask) -> ExportSampleResult:
        override = task.override
        formats = self._resolve_formats(override)
        result = ExportSampleResult(sample_id=task.sample_id, index=task.index, formats=formats)

        for fmt in formats:
            if self._cancel_event.is_set():
                break

            output_path = self._build_output_path(task, fmt)
            try:
                export_sample(
                    input_path=self._audio_path,
                    output_path=output_path,
                    segment=task.segment,
                    pre_pad_ms=self._resolve_pre_pad(override),
                    post_pad_ms=self._resolve_post_pad(override),
                    format=fmt,
                    sample_rate=self._resolve_sample_rate(override),
                    bit_depth=self._resolve_bit_depth(override),
                    channels=self._resolve_channels(override),
                    normalize=self._resolve_normalize(override),
                    bandpass_low_hz=self._resolve_bandpass_low(override),
                    bandpass_high_hz=self._resolve_bandpass_high(override),
                    metadata=self._build_metadata(task, override, fmt),
                )
                result.output_paths.append(output_path)
            except Exception as exc:  # pragma: no cover - defensive
                result.success = False
                result.message = str(exc)
                break

        return result

    def _build_output_path(self, task: _ExportTask, fmt: str) -> Path:
        filename = self._render_filename(task, fmt)
        return self._output_dir / f"{filename}.{fmt}"

    def _render_filename(self, task: _ExportTask, fmt: str) -> str:
        override = task.override
        if override and override.filename:
            return sanitize_filename(override.filename)

        normalize = self._resolve_normalize(override)
        pre_pad = self._resolve_pre_pad(override)
        post_pad = self._resolve_post_pad(override)
        sample_rate = self._resolve_sample_rate(override)
        bit_depth = self._resolve_bit_depth(override)
        channels = self._resolve_channels(override)
        title_value = self._resolve_title_value(task, override)
        artist = self._resolve_artist(override)
        album = self._resolve_album(override)
        year = self._resolve_year(override)
        template = self._batch_settings.filename_template or DEFAULT_FILENAME_TEMPLATE
        return render_filename_from_template(
            template=template,
            base_name=self._base_name,
            sample_id=task.sample_id,
            index=task.index,
            total=len(self._tasks),
            segment=task.segment,
            fmt=fmt,
            normalized=normalize,
            pre_pad_ms=pre_pad,
            post_pad_ms=post_pad,
            title=title_value,
            artist=artist,
            album=album,
            year=year,
            sample_rate_hz=sample_rate,
            bit_depth=bit_depth,
            channels=channels,
        )

    def _resolve_formats(self, override: ExportSampleOverride | None) -> list[str]:
        if override and override.formats:
            return list(dict.fromkeys(override.formats))
        return list(dict.fromkeys(self._batch_settings.formats or ["wav"]))

    def _resolve_pre_pad(self, override: ExportSampleOverride | None) -> float:
        if override and override.pre_pad_ms is not None:
            return float(override.pre_pad_ms)
        return float(self._batch_settings.pre_pad_ms)

    def _resolve_post_pad(self, override: ExportSampleOverride | None) -> float:
        if override and override.post_pad_ms is not None:
            return float(override.post_pad_ms)
        return float(self._batch_settings.post_pad_ms)

    def _resolve_normalize(self, override: ExportSampleOverride | None) -> bool:
        if override and override.normalize is not None:
            return bool(override.normalize)
        return bool(self._batch_settings.normalize)

    def _resolve_sample_rate(self, override: ExportSampleOverride | None) -> int | None:
        if override and override.sample_rate_hz:
            return int(override.sample_rate_hz)
        return self._batch_settings.sample_rate_hz

    def _resolve_bit_depth(self, override: ExportSampleOverride | None) -> str | None:
        if override and override.bit_depth:
            return override.bit_depth
        return self._batch_settings.bit_depth

    def _resolve_channels(self, override: ExportSampleOverride | None) -> str | None:
        if override and override.channels:
            return override.channels
        return self._batch_settings.channels

    def _resolve_bandpass_low(self, override: ExportSampleOverride | None) -> float | None:
        if override and override.bandpass_low_hz is not None:
            return float(override.bandpass_low_hz)
        return self._batch_settings.bandpass_low_hz

    def _resolve_bandpass_high(self, override: ExportSampleOverride | None) -> float | None:
        if override and override.bandpass_high_hz is not None:
            return float(override.bandpass_high_hz)
        return self._batch_settings.bandpass_high_hz

    def _resolve_title_value(self, task: _ExportTask, override: ExportSampleOverride | None) -> str:
        if override and override.title:
            return override.title
        return derive_sample_title(task.index, task.segment)

    def _resolve_artist(self, override: ExportSampleOverride | None) -> str:
        if override and override.artist:
            return override.artist
        return self._batch_settings.artist

    def _resolve_album(self, override: ExportSampleOverride | None) -> str | None:
        if override and override.album:
            return override.album
        return self._batch_settings.album

    def _resolve_year(self, override: ExportSampleOverride | None) -> int | None:
        if override and override.year:
            return override.year
        return self._batch_settings.year

    def _build_metadata(
        self, task: _ExportTask, override: ExportSampleOverride | None, fmt: str
    ) -> dict[str, Any]:
        title_value = self._resolve_title_value(task, override)
        artist = self._resolve_artist(override)
        album = self._resolve_album(override)
        year = self._resolve_year(override)
        normalize = self._resolve_normalize(override)
        pre_pad = self._resolve_pre_pad(override)
        post_pad = self._resolve_post_pad(override)
        sample_rate = self._resolve_sample_rate(override)
        bit_depth = self._resolve_bit_depth(override)
        channels = self._resolve_channels(override)

        context = build_template_context(
            base_name=self._base_name,
            sample_id=task.sample_id,
            index=task.index,
            total=len(self._tasks),
            segment=task.segment,
            fmt=fmt,
            normalize=normalize,
            pre_pad_ms=pre_pad,
            post_pad_ms=post_pad,
            title=title_value,
            artist=artist,
            album=album,
            year=year,
            sample_rate_hz=sample_rate,
            bit_depth=bit_depth,
            channels=channels,
        )

        metadata: dict[str, Any] = {
            "title": title_value,
            "artist": artist,
            "album": album,
            "year": year,
            "track": task.index + 1,
            "format": fmt.upper(),
        }
        notes_template = (
            override.notes if override and override.notes else self._batch_settings.notes
        )
        if notes_template:
            rendered_notes = apply_template(notes_template, context).strip()
            if rendered_notes:
                metadata["comment"] = rendered_notes
        # Remove None entries
        return {key: value for key, value in metadata.items() if value not in (None, "")}


class ExportManager(QObject):
    """High-level controller that manages export workers and exposes progress."""

    progress = Signal(float, int, int)
    sample_started = Signal(str, int)
    sample_finished = Signal(ExportSampleResult)
    state_changed = Signal(str)
    completed = Signal(ExportSummary)
    error = Signal(str)

    def __init__(
        self,
        *,
        audio_path: Path,
        segments: Sequence[Segment],
        batch_settings: ExportBatchSettings,
        overrides: Sequence[ExportSampleOverride] | None = None,
        resume_state: Mapping[str, str] | None = None,
        output_dir: Path,
        base_name: str | None = None,
    ) -> None:
        super().__init__()
        self._audio_path = audio_path
        self._segments = list(segments)
        self._batch_settings = replace(batch_settings)
        self._overrides = {ov.sample_id: ov for ov in (overrides or [])}
        self._output_dir = output_dir
        self._base_name = base_name or audio_path.stem
        self._resume_state = dict(resume_state or {})

        self._thread: QThread | None = None
        self._worker: ExportWorker | None = None

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def execute_blocking(
        self,
        selected_indices: Iterable[int] | None = None,
    ) -> ExportSummary:
        """Run exports synchronously on the caller thread."""

        tasks = self._prepare_tasks(selected_indices)
        worker = ExportWorker(
            audio_path=self._audio_path,
            base_name=self._base_name,
            output_dir=self._output_dir,
            batch_settings=self._batch_settings,
            tasks=tasks,
            resume_state=self._resume_state,
        )
        return worker.run_blocking()

    def start(self, selected_indices: Iterable[int] | None = None) -> None:
        """Start exports in a background thread."""

        if self._thread is not None:
            raise RuntimeError("ExportManager is already running")

        tasks = self._prepare_tasks(selected_indices)
        self._worker = ExportWorker(
            audio_path=self._audio_path,
            base_name=self._base_name,
            output_dir=self._output_dir,
            batch_settings=self._batch_settings,
            tasks=tasks,
            resume_state=self._resume_state,
        )

        self._thread = QThread(self)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self.progress)
        self._worker.sample_started.connect(self.sample_started)
        self._worker.sample_finished.connect(self.sample_finished)
        self._worker.state_changed.connect(self.state_changed)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.error.connect(self._on_worker_error)
        self._thread.start()
        self.state_changed.emit("running")

    def pause(self) -> None:
        if self._worker:
            self._worker.pause()

    def resume(self) -> None:
        if self._worker:
            self._worker.resume()

    def cancel(self) -> None:
        if self._worker:
            self._worker.cancel()

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.isRunning()

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _prepare_tasks(self, selected_indices: Iterable[int] | None) -> list[_ExportTask]:
        if selected_indices is None:
            indices = range(len(self._segments))
        else:
            indices = [idx for idx in selected_indices if 0 <= idx < len(self._segments)]

        tasks: list[_ExportTask] = []
        for idx in indices:
            segment = self._segments[idx]
            sample_id = compute_sample_id(idx, segment)
            if self._resume_state.get(sample_id) == "completed":
                continue
            override = self._overrides.get(sample_id)
            tasks.append(
                _ExportTask(sample_id=sample_id, index=idx, segment=segment, override=override)
            )
        return tasks

    def _on_worker_finished(self, summary: ExportSummary) -> None:
        self._resume_state.update(summary.resume_state)
        self.completed.emit(summary)
        self._cleanup_thread()

    def _on_worker_error(self, message: str) -> None:
        self.error.emit(message)
        self._cleanup_thread()

    def _cleanup_thread(self) -> None:
        if self._thread:
            self._thread.quit()
            self._thread.wait(3000)
        self._thread = None
        self._worker = None


class _SafeDict(dict[str, Any]):
    """Dictionary that returns its key in braces when missing (for templates)."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"
