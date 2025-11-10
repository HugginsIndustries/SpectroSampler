"""Main entry point for SpectroSampler GUI."""

import argparse
import logging
import sys
import warnings
from pathlib import Path

from spectrosampler.audio_io import check_ffmpeg
from spectrosampler.utils import setup_logging

logger = logging.getLogger(__name__)

# Suppress third-party deprecation warning emitted by webrtcvad's pkg_resources import.
warnings.filterwarnings(
    "ignore",
    category=UserWarning,
    message="pkg_resources is deprecated as an API",
    module="webrtcvad",
)


def _print_help() -> None:
    print(
        "SpectroSampler GUI\n\n"
        "Usage:\n"
        "  spectrosampler-gui                    Launch the GUI\n"
        "  spectrosampler-gui --project <path>   Open specific project file\n"
        "  spectrosampler-gui --audio <path>     Open specific audio file\n"
        "  spectrosampler-gui --verbose          Enable verbose (DEBUG) logging\n"
        "  spectrosampler-gui --help             Show this help and exit\n"
        "  spectrosampler-gui --version          Show version and exit\n"
    )


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        Parsed arguments.
    """
    parser = argparse.ArgumentParser(description="SpectroSampler GUI", add_help=False)
    parser.add_argument("--project", type=str, help="Open specific project file")
    parser.add_argument("--audio", type=str, help="Open specific audio file")
    parser.add_argument("--help", action="store_true", help="Show help and exit")
    parser.add_argument("--version", action="store_true", help="Show version and exit")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose (DEBUG) logging")
    return parser.parse_args()


def _check_autosave_recovery() -> Path | None:
    """Check for auto-save files and prompt user for recovery.

    Returns:
        Path to auto-save file to recover, or None if no recovery needed.
    """
    from spectrosampler.gui.autosave import AutoSaveManager

    autosave_manager = AutoSaveManager()
    autosave_files = autosave_manager.get_autosave_files()

    if not autosave_files:
        return None

    # Find most recent auto-save file
    most_recent = max(autosave_files, key=lambda p: p.stat().st_mtime)

    # Show recovery dialog
    from PySide6.QtWidgets import QApplication, QMessageBox

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    msg = QMessageBox()
    msg.setWindowTitle("Recover Unsaved Work?")
    msg.setText(
        f"Unsaved work was detected from a previous session.\n\n"
        f"Most recent auto-save: {most_recent.name}\n"
        f"Would you like to recover it?"
    )
    msg.setStandardButtons(
        QMessageBox.StandardButton.Yes
        | QMessageBox.StandardButton.No
        | QMessageBox.StandardButton.Discard
    )
    msg.button(QMessageBox.StandardButton.Yes).setText("Restore")
    msg.button(QMessageBox.StandardButton.No).setText("Ignore")
    msg.button(QMessageBox.StandardButton.Discard).setText("Delete")

    result = msg.exec()

    if result == QMessageBox.StandardButton.Yes:
        return most_recent
    elif result == QMessageBox.StandardButton.Discard:
        # Delete all auto-save files
        autosave_manager.cleanup_old_autosaves(keep_count=0)
        return None
    else:
        return None


def main() -> None:
    """Main entry point for GUI application."""
    # Parse arguments
    args = _parse_args()

    # Setup logging
    setup_logging(verbose=getattr(args, "verbose", False))

    # Fast-path for CI/CLI flags before importing Qt (avoids EGL/X11 deps for --help/--version)
    if args.help:
        _print_help()
        return
    if args.version:
        print("SpectroSampler 0.1.0")
        return

    # Import Qt and window lazily to avoid loading GUI stack when not needed
    from PySide6.QtWidgets import QApplication, QFileDialog, QMainWindow, QMessageBox

    from spectrosampler.gui.main_window import MainWindow
    from spectrosampler.gui.welcome_screen import WelcomeScreen

    # Create application
    app = QApplication(sys.argv)
    app.setApplicationName("SpectroSampler")
    app.setApplicationVersion("0.1.0")
    app.setOrganizationName("SpectroSampler")

    if not check_ffmpeg():
        logger.error("FFmpeg not detected on PATH. Showing installation guidance dialog.")
        guidance_lines = [
            "SpectroSampler requires FFmpeg to process audio but it was not detected on this system.",
            "",
            "Windows: Download the FFmpeg release from https://ffmpeg.org/download.html, extract it, and add the 'bin' folder to your PATH environment variable.",
            "Linux: Install FFmpeg through your package manager (for example: 'sudo apt install ffmpeg') and ensure it is available on PATH.",
            "",
            "After installing FFmpeg, restart SpectroSampler.",
        ]
        msg_box = QMessageBox()
        msg_box.setIcon(QMessageBox.Icon.Critical)
        msg_box.setWindowTitle("FFmpeg Not Found")
        msg_box.setText("\n".join(guidance_lines))
        msg_box.setStandardButtons(QMessageBox.StandardButton.Close)
        msg_box.setDefaultButton(QMessageBox.StandardButton.Close)
        msg_box.exec()
        sys.exit(1)

    # Check for auto-save recovery (before showing welcome screen)
    recovery_path: Path | None = None
    if not args.project and not args.audio:
        recovery_path = _check_autosave_recovery()

    # If command-line arguments provided, open directly
    if args.project:
        project_path = Path(args.project)
        if project_path.exists():
            window = MainWindow()
            window.setWindowTitle("SpectroSampler")
            window.resize(1400, 900)
            window.show()
            window.load_project_file(project_path)
            sys.exit(app.exec())
        else:
            print(f"Error: Project file not found: {project_path}", file=sys.stderr)
            sys.exit(1)
    elif args.audio:
        audio_path = Path(args.audio)
        if audio_path.exists():
            window = MainWindow()
            window.setWindowTitle("SpectroSampler")
            window.resize(1400, 900)
            window.show()
            window.load_audio_file(audio_path)
            sys.exit(app.exec())
        else:
            print(f"Error: Audio file not found: {audio_path}", file=sys.stderr)
            sys.exit(1)
    elif recovery_path:
        # Recover from auto-save
        window = MainWindow()
        window.setWindowTitle("SpectroSampler*")
        window.resize(1400, 900)
        window.show()
        window.load_project_file(recovery_path)
        window._project_modified = True  # Mark as modified
        window._update_window_title()
        sys.exit(app.exec())
    else:
        # Show welcome screen
        welcome_window = QMainWindow()
        welcome_window.setWindowTitle("SpectroSampler")
        welcome_window.resize(800, 600)
        welcome_screen = WelcomeScreen()
        welcome_window.setCentralWidget(welcome_screen)
        welcome_window.show()

        # Handle welcome screen actions
        def on_new_project() -> None:
            welcome_window.close()
            window = MainWindow()
            window.setWindowTitle("SpectroSampler")
            window.resize(1400, 900)
            window.show()

        def on_open_project() -> None:
            file_path, _ = QFileDialog.getOpenFileName(
                welcome_window, "Open Project", "", "SpectroSampler Projects (*.ssproj)"
            )
            if file_path:
                welcome_window.close()
                window = MainWindow()
                window.setWindowTitle("SpectroSampler")
                window.resize(1400, 900)
                window.show()
                window.load_project_file(Path(file_path))

        def on_recent_project(path: Path) -> None:
            welcome_window.close()
            window = MainWindow()
            window.setWindowTitle("SpectroSampler")
            window.resize(1400, 900)
            window.show()
            window.load_project_file(path)

        def on_recent_audio(path: Path) -> None:
            welcome_window.close()
            window = MainWindow()
            window.setWindowTitle("SpectroSampler")
            window.resize(1400, 900)
            window.show()
            window.load_audio_file(path)

        welcome_screen.new_project_requested.connect(on_new_project)
        welcome_screen.open_project_requested.connect(on_open_project)
        welcome_screen.recent_project_clicked.connect(on_recent_project)
        welcome_screen.recent_audio_file_clicked.connect(on_recent_audio)

    # Run application
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
