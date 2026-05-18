import sys

from PySide6.QtWidgets import QApplication

from src.components.main_window import MainWindow
from src.components.splash_screen import SplashScreen
from src.config.settings import Settings
from src.utils.constants import VERSION
from src.utils.helper import get_path, rounded_icon
from src.utils.theme import apply_theme


def _get_version() -> str:
    """Get version from package metadata, fallback for PyInstaller bundles."""
    try:
        from importlib.metadata import version

        return version("shuttle")
    except Exception:
        return VERSION


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Shuttle")
    app.setApplicationVersion(_get_version())

    # ---- STYLESHEET ----
    settings = Settings()
    apply_theme(app, settings.config.theme_mode)

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
