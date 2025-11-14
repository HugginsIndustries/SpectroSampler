"""Tests for export templating helpers."""

from __future__ import annotations

from spectrosampler.detectors.base import Segment
from spectrosampler.gui.export_models import (
    DEFAULT_FILENAME_TEMPLATE,
    apply_template,
    build_template_context,
    derive_sample_title,
    render_filename_from_template,
)


def test_render_filename_supports_new_tokens() -> None:
    """Filename templates should resolve new tokens like id/title/start/duration."""

    segment = Segment(
        start=0.5,
        end=1.25,
        detector="vad",
        score=0.92,
        attrs={"name": "Lead Vox"},
    )
    rendered = render_filename_from_template(
        template="{id}_{title}_{start}_{duration}",
        base_name="session",
        sample_id="seg-002",
        index=2,
        total=20,
        segment=segment,
        fmt="wav",
        normalized=False,
        pre_pad_ms=25.0,
        post_pad_ms=10.0,
    )
    # Index=2 should map to id "0003" (1-based, zero padded) and values formatted to 3 decimals.
    assert rendered == "0003_Lead Vox_0.500_0.750"


def test_template_context_exposes_metadata_and_sample_fields() -> None:
    """Token context should include metadata and sample-table values for notes/templates."""

    segment = Segment(
        start=1.0,
        end=1.5,
        detector="flux",
        score=0.5,
        attrs={"enabled": False, "take": 7},
    )
    title = derive_sample_title(0, segment, fallback="sample")
    context = build_template_context(
        base_name="source",
        sample_id="seg-000",
        index=0,
        total=1,
        segment=segment,
        fmt="flac",
        normalize=True,
        pre_pad_ms=100.0,
        post_pad_ms=50.0,
        title=title,
        artist="SpectroSampler",
        album="Field Notes",
        year=2025,
        sample_rate_hz=48000,
        bit_depth="24",
        channels="stereo",
    )

    assert context["id"] == "0001"
    assert context["title"] == "sample"
    assert context["detector"] == "flux"
    # Attribute tokens should be namespaced with attr_ prefix.
    assert context["attr_take"] == 7

    rendered_notes = apply_template(
        "Title={title}; Artist={artist}; Start={start}; Detector={detector}; Enabled={enabled}",
        context,
    )
    assert (
        rendered_notes
        == "Title=sample; Artist=SpectroSampler; Start=1.000; Detector=flux; Enabled=False"
    )

    default_name = render_filename_from_template(
        template=DEFAULT_FILENAME_TEMPLATE,
        base_name="source",
        sample_id="seg-000",
        index=0,
        total=1,
        segment=segment,
        fmt="flac",
        normalized=True,
        pre_pad_ms=100.0,
        post_pad_ms=50.0,
        title=title,
        artist="SpectroSampler",
        album="Field Notes",
        year=2025,
        sample_rate_hz=48000,
        bit_depth="24",
        channels="stereo",
    )
    assert default_name.startswith("0001_sample_1.000_0.500")
