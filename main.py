import os
import sys

# Suppress Qt accessibility table warnings on macOS (harmless noise)
# Must be set before any Qt imports.
os.environ.setdefault("QT_LOGGING_RULES", "qt.accessibility.table=false")

from PySide6.QtCore import QEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from src.config.settings import Settings  # noqa: E402
from src.utils.constants import SOFTWARE_NAME, VERSION  # noqa: E402
from src.utils.crash_handler import (  # noqa: E402
    check_previous_crash,
    clear_crash_log,
    get_previous_crash_report,
    install_crash_handler,
)
from src.utils.helper import get_path, rounded_icon  # noqa: E402
from src.utils.theme import apply_theme  # noqa: E402
from src.views.main_window import MainWindow  # noqa: E402


class FileSlingApp(QApplication):
    """Custom QApplication that re-shows the main window on Dock icon click (macOS)."""

    def __init__(self, argv: list) -> None:
        super().__init__(argv)
        self._main_window: MainWindow | None = None

    def set_main_window(self, window: MainWindow) -> None:
        self._main_window = window

    def event(self, event: QEvent) -> bool:
        # ApplicationActivate fires on macOS when the Dock icon is clicked
        if event.type() == QEvent.Type.ApplicationActivate and self._main_window:
            self._main_window.show()
            self._main_window.raise_()
            self._main_window.activateWindow()
        return super().event(event)


def _get_version() -> str:
    """Get version from package metadata, fallback for PyInstaller bundles."""
    try:
        from importlib.metadata import version

        return version("filesling")
    except Exception:
        return VERSION


def main():
    # Install global crash handler before anything else
    install_crash_handler()

    # On macOS, ensure the app is recognized as a GUI application
    # so the menu bar shows when running from Terminal
    if sys.platform == "darwin":
        try:
            from Foundation import NSBundle

            bundle = NSBundle.mainBundle()
            info = bundle.localizedInfoDictionary() or bundle.infoDictionary()
            if info:
                info["LSUIElement"] = "0"
        except ImportError:
            pass

    app = FileSlingApp(sys.argv)
    app.setApplicationName(SOFTWARE_NAME)
    app.setApplicationVersion(_get_version())

    # ---- STYLESHEET ----
    settings = Settings()
    apply_theme(app, settings.config.theme_mode)

    # ---- CHECK PREVIOUS CRASH ----
    if check_previous_crash():
        from PySide6.QtWidgets import QMessageBox

        report = get_previous_crash_report()
        msg = QMessageBox()
        msg.setWindowTitle(f"{SOFTWARE_NAME} — Previous Crash Detected")
        msg.setText(f"{SOFTWARE_NAME} crashed during the last session.")
        msg.setInformativeText("Would you like to view the crash report?")
        view_btn = msg.addButton("View Report", QMessageBox.ButtonRole.AcceptRole)
        msg.addButton("Dismiss", QMessageBox.ButtonRole.RejectRole)
        msg.exec()

        if msg.clickedButton() == view_btn:
            from src.utils.crash_handler import show_crash_dialog

            show_crash_dialog(report)

        clear_crash_log()

    # ---- ICON (rounded) ----
    logo_path = get_path("assets/icons/filesling_logo.png")
    app.setWindowIcon(rounded_icon(str(logo_path), 15))

    # ---- MAIN WINDOW ----
    window = MainWindow()
    app.set_main_window(window)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
