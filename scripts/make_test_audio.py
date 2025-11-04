"""Script to generate synthetic test audio files."""

import argparse
from pathlib import Path

import numpy as np
import soundfile as sf


def generate_test_audio(
    output_path: Path,
    duration: float = 12.0,
    sample_rate: int = 16000,
    noise_level: float = 0.3,
    speech_count: int = 3,
    transient_count: int = 2,
) -> None:
    """Generate synthetic test audio: pink noise + speech-like tones + transients.

    Args:
        output_path: Output WAV file path.
        duration: Duration in seconds.
        sample_rate: Sample rate in Hz.
        noise_level: Background noise level (0-1).
        speech_count: Number of speech-like segments.
        transient_count: Number of transient events.
    """
    t = np.linspace(0, duration, int(sample_rate * duration))

    # Pink noise bed (rain)
    pink_noise = np.random.randn(len(t))
    pink_noise = np.cumsum(pink_noise) * 0.01
    pink_noise = pink_noise / np.std(pink_noise) * noise_level

    # Speech-like AM tones
    speech_audio = np.zeros_like(t)
    for i in range(speech_count):
        start_time = duration / (speech_count + 1) * (i + 1) - 0.5
        end_time = start_time + 1.0
        if start_time < 0:
            start_time = 0.1
        if end_time > duration:
            end_time = duration - 0.1

        mask = (t >= start_time) & (t < end_time)
        tone_freq = 500.0 + (i * 500.0)  # 500, 1000, 1500 Hz
        am_freq = 5.0 + i  # 5, 6, 7 Hz modulation
        tone = np.sin(2 * np.pi * tone_freq * t[mask])
        modulation = (np.sin(2 * np.pi * am_freq * t[mask]) + 1) / 2
        speech_audio[mask] = tone * modulation * 0.5

    # Sharp transients
    transients = np.zeros_like(t)
    for i in range(transient_count):
        transient_time = duration / (transient_count + 1) * (i + 1)
        idx = int(transient_time * sample_rate)
        click_len = int(0.01 * sample_rate)  # 10ms
        click = np.sin(2 * np.pi * 5000 * np.linspace(0, 0.01, click_len)) * np.exp(
            -np.linspace(0, 10, click_len)
        )
        if idx + click_len < len(transients):
            transients[idx : idx + click_len] = click * 0.8

    # Combine
    audio = pink_noise + speech_audio + transients
    audio = audio / np.max(np.abs(audio)) * 0.8  # Normalize

    # Write
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(output_path, audio, sample_rate)
    print(f"Generated test audio: {output_path} ({duration}s, {sample_rate} Hz)")


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Generate synthetic test audio")
    parser.add_argument("output", type=Path, help="Output WAV file path")
    parser.add_argument("--duration", type=float, default=12.0, help="Duration in seconds")
    parser.add_argument("--sample-rate", type=int, default=16000, help="Sample rate in Hz")
    parser.add_argument(
        "--noise-level", type=float, default=0.3, help="Background noise level (0-1)"
    )
    parser.add_argument(
        "--speech-count", type=int, default=3, help="Number of speech-like segments"
    )
    parser.add_argument("--transient-count", type=int, default=2, help="Number of transient events")

    args = parser.parse_args()
    generate_test_audio(
        args.output,
        duration=args.duration,
        sample_rate=args.sample_rate,
        noise_level=args.noise_level,
        speech_count=args.speech_count,
        transient_count=args.transient_count,
    )


if __name__ == "__main__":
    main()
