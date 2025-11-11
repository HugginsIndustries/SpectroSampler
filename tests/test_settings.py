"""Tests for GUI settings persistence helpers."""

from spectrosampler.gui.settings import SettingsManager


def test_detection_max_samples_persistent_and_clamped(tmp_path, monkeypatch):
    """Max samples should persist between manager instances and stay within 1-10,000."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    manager = SettingsManager()
    manager.set_detection_max_samples(10_000)
    assert manager.get_detection_max_samples() == 10_000

    # Values outside the allowed range should clamp.
    manager.set_detection_max_samples(0)
    assert manager.get_detection_max_samples() == 1

    manager.set_detection_max_samples(15_000)
    assert manager.get_detection_max_samples() == 10_000

    manager.set_detection_max_samples(5_432)

    # A fresh manager should read the persisted value.
    other_manager = SettingsManager()
    assert other_manager.get_detection_max_samples() == 5_432
