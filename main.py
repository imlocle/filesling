import os
import sys

# Suppress Qt accessibility table warnings on macOS (harmless noise)
# Must be set before any Qt imports.
os.environ.setdefault("QT_LOGGING_RULES", "qt.accessibility.table=false")

from PySide6.QtWidgets import QApplication  # noqa: E402

from src.config.settings import Settings  # noqa: E402
from src.utils.constants import SOFTWARE_NAME, SPLASH_DURATION_MS, VERSION  # noqa: E402
from src.utils.crash_handler import (  # noqa: E402
    check_previous_crash,
    clear_crash_log,
    get_previous_crash_report,
    install_crash_handler,
)
from src.utils.helper import get_path, rounded_icon  # noqa: E402
from src.utils.theme import apply_theme  # noqa: E402
from src.views.main_window import MainWindow  # noqa: E402
from src.views.splash_screen import SplashScreen  # noqa: E402


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

    app = QApplication(sys.argv)
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

    # ---- SPLASH ----
    logo_path = get_path("assets/icons/filesling_logo.png")
    splash = SplashScreen(str(logo_path), duration=SPLASH_DURATION_MS)
    splash.show()

    # ---- ICON (rounded) ----
    app.setWindowIcon(rounded_icon(str(logo_path), 15))

    # ---- MAIN WINDOW ----
    window = MainWindow()

    def start_main():
        splash.close()
        window.show()

    splash.show_and_wait(start_main, window)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
