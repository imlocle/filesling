"""macOS menu bar status item (system tray icon) for FileSling."""

from PySide6.QtGui import QAction, QIcon, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon, QWidget

from src.utils.constants import SOFTWARE_NAME
from src.utils.helper import get_path


class MenuBarService:
    """Manages the macOS menu bar icon and its dropdown menu."""

    def __init__(self, parent: QWidget) -> None:
        self._parent = parent
        self._tray: QSystemTrayIcon | None = None
        self._menu: QMenu | None = None
        self._status_action: QAction | None = None
        self._setup()

    def _setup(self) -> None:
        """Create the system tray icon and menu."""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return

        # Load template icon (monochrome, macOS auto-tints for light/dark)
        icon_path = get_path("assets/icons/menubar_iconTemplate.png")
        icon = QIcon(QPixmap(str(icon_path)))
        icon.setIsMask(True)  # Tell macOS this is a template image

        self._tray = QSystemTrayIcon(icon, self._parent)

        # Build dropdown menu
        self._menu = QMenu()

        self._status_action = self._menu.addAction("No active transfers")
        self._status_action.setEnabled(False)

        self._menu.addSeparator()

        show_action = self._menu.addAction(f"Show {SOFTWARE_NAME}")
        show_action.triggered.connect(self._show_window)

        self._menu.addSeparator()

        quit_action = self._menu.addAction(f"Quit {SOFTWARE_NAME}")
        quit_action.triggered.connect(self._quit)

        self._tray.setContextMenu(self._menu)
        self._tray.activated.connect(self._on_activated)
        self._tray.show()

    def update_status(self, message: str) -> None:
        """Update the status line in the dropdown menu."""
        if self._status_action:
            self._status_action.setText(message)

    def set_transfer_count(self, count: int) -> None:
        """Update status based on active transfer count."""
        if count == 0:
            self.update_status("No active transfers")
        elif count == 1:
            self.update_status("1 transfer in progress")
        else:
            self.update_status(f"{count} transfers in progress")

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        """Handle click on the tray icon — show/raise the main window."""
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._show_window()

    def _show_window(self) -> None:
        """Show and raise the main window."""
        self._parent.show()
        self._parent.raise_()
        self._parent.activateWindow()

    def _quit(self) -> None:
        """Quit the application via the main window's force quit flow."""
        if hasattr(self._parent, "_force_quit"):
            self._parent._force_quit()
        else:
            from PySide6.QtWidgets import QApplication

            QApplication.quit()

    def cleanup(self) -> None:
        """Remove the tray icon."""
        if self._tray:
            self._tray.hide()
            self._tray = None
