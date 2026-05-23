import sys

from PySide6.QtWidgets import QApplication

from src.config.settings import Settings
from src.utils.constants import VERSION
from src.utils.crash_handler import (
    check_previous_crash,
    clear_crash_log,
    get_previous_crash_report,
    install_crash_handler,
)
from src.utils.helper import get_path, rounded_icon
from src.utils.theme import apply_theme
from src.views.main_window import MainWindow
from src.views.splash_screen import SplashScreen


def _get_version() -> str:
    """Get version from package metadata, fallback for PyInstaller bundles."""
    try:
        from importlib.metadata import version

        return version("shuttle")
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
    app.setApplicationName("Shuttle")
    app.setApplicationVersion(_get_version())

    # ---- STYLESHEET ----
    settings = Settings()
    apply_theme(app, settings.config.theme_mode)

    # ---- CHECK PREVIOUS CRASH ----
    if check_previous_crash():
        from PySide6.QtWidgets import QMessageBox

        report = get_previous_crash_report()
        msg = QMessageBox()
        msg.setWindowTitle("Shuttle — Previous Crash Detected")
        msg.setText("Shuttle crashed during the last session.")
        msg.setInformativeText("Would you like to view the crash report?")
        view_btn = msg.addButton("View Report", QMessageBox.ButtonRole.AcceptRole)
        msg.addButton("Dismiss", QMessageBox.ButtonRole.RejectRole)
        msg.exec()

        if msg.clickedButton() == view_btn:
            from src.utils.crash_handler import show_crash_dialog

            show_crash_dialog(report)

        clear_crash_log()

    # ---- SPLASH ----
    logo_path = get_path("assets/icons/shuttle_logo.png")
    splash = SplashScreen(str(logo_path), duration=2500)
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
