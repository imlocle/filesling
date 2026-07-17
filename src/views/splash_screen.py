from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QSplashScreen


class SplashScreen(QSplashScreen):
    def __init__(self, logo_path: str, duration: int = 2500) -> None:
        # Load original image (already has rounded corners baked in)
        original = QPixmap(logo_path)

        # Scale down to 300px for a compact splash
        scaled = original.scaled(
            300,
            300,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

        super().__init__(scaled)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.duration = duration
        self.min_duration_timer = None
        self.ready_to_close = False
        self.window_loaded = False

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setXOffset(0)
        shadow.setYOffset(5)
        shadow.setColor(QColor(0, 0, 0, 80))  # semi-transparent black
        self.setGraphicsEffect(shadow)

    def show_and_wait(self, callback: object, window: object = None) -> None:
        """
        Show splash screen and wait for both:
        1. Minimum duration to elapse
        2. Window to signal it's fully loaded

        Args:
            callback: Function to call when ready to show main window
            window: MainWindow instance to monitor for loaded signal
        """
        self.show()
        self.callback = callback

        # Set minimum duration timer
        self.min_duration_timer = QTimer()
        self.min_duration_timer.setSingleShot(True)
        self.min_duration_timer.timeout.connect(self._on_min_duration_elapsed)
        self.min_duration_timer.start(self.duration)

        # Connect to window's loaded signal if provided
        if window:
            window.fully_loaded.connect(self._on_window_loaded)

    def _on_min_duration_elapsed(self) -> None:
        """Called when minimum display duration has elapsed."""
        self.ready_to_close = True
        self._try_close()

    def _on_window_loaded(self) -> None:
        """Called when main window signals it's fully loaded."""
        self.window_loaded = True
        self._try_close()

    def _try_close(self) -> None:
        """Close splash only when both conditions are met."""
        if self.ready_to_close and self.window_loaded:
            self.callback()
