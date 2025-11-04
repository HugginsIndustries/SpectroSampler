"""Main entry point for SamplePacker GUI."""

import logging
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from samplepacker.gui.main_window import MainWindow
from samplepacker.utils import setup_logging

logger = logging.getLogger(__name__)


def main() -> None:
    """Main entry point for GUI application."""
    # Setup logging
    setup_logging(verbose=True)

    # Create application
    app = QApplication(sys.argv)
    app.setApplicationName("SamplePacker")
    app.setApplicationVersion("0.1.0")
    app.setOrganizationName("SamplePacker")

    # Create main window
    window = MainWindow()
    window.setWindowTitle("SamplePacker")
    window.resize(1400, 900)
    window.show()

    # Run application
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

