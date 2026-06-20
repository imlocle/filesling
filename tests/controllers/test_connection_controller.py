"""
Unit tests for ConnectionController.

Tests connection lifecycle, health monitoring, and auto-reconnect logic.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget

from src.controllers.connection_controller import ConnectionController


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def qapp():
    """Ensure a QApplication exists for QObject-based tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def mock_view(qapp):
    """Create a mock MainWindow (real QWidget for QObject parenting)."""
    widget = QWidget()
    widget.remote_explorer = MagicMock()
    widget.remote_explorer.sftp = MagicMock()
    widget.remote_explorer._detail_panel = MagicMock()
    widget.remote_explorer._loader_thread = None
    widget.connect_btn = MagicMock()
    widget.connection_status_label = MagicMock()
    widget.connection_status_label.objectName.return_value = "connection_connected"
    widget.controller = MagicMock()
    widget.controller.manual_transfer.is_busy.return_value = False
    widget.controller.download_ctrl.is_active = False
    widget.connection_attempts = 0
    widget.handle_connection_failure = MagicMock()
    return widget


@pytest.fixture
def mock_settings():
    """Create a mock Settings."""
    settings = MagicMock()
    settings.host = "192.168.1.100"
    settings.username = "pi"
    settings.ssh_key_path = "/Users/test/.ssh/id_rsa"
    settings.ssh_port = 22
    settings.remote_base_dir = "/mnt/external"
    settings.config.current_server_id = "test-server"
    settings.get_server.return_value = {
        "connection_type": "ssh",
        "name": "Test Pi",
    }
    settings.get_default_bookmark.return_value = None
    return settings


@pytest.fixture
def mock_connection_manager():
    """Create a mock ConnectionManagerService."""
    cm = MagicMock()
    cm.is_connected.return_value = True
    cm.check_alive.return_value = True
    cm.measure_latency.return_value = 45.0
    cm.sftp_client = MagicMock()
    cm.sftp_metadata = MagicMock()
    cm.sftp_background = MagicMock()
    return cm


@pytest.fixture
def controller(mock_view, mock_settings, mock_connection_manager):
    """Create a ConnectionController with mocked dependencies."""
    ctrl = ConnectionController(
        view=mock_view,
        settings=mock_settings,
        connection_manager=mock_connection_manager,
        parent=None,
    )
    return ctrl


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


class TestHealthCheck:
    def test_health_check_updates_latency(self, controller, mock_connection_manager):
        """Health check should measure and store latency."""
        mock_connection_manager.measure_latency.return_value = 32.5
        controller.check_health()
        assert controller.last_latency == 32.5

    def test_health_check_skips_when_not_connected(self, controller, mock_connection_manager):
        """Health check should skip if not connected."""
        mock_connection_manager.is_connected.return_value = False
        controller.check_health()
        mock_connection_manager.measure_latency.assert_not_called()

    def test_health_check_skips_during_transfer(self, controller, mock_view):
        """Health check should skip if a transfer is in progress."""
        mock_view.controller.manual_transfer.is_busy.return_value = True
        controller.check_health()
        # measure_latency shouldn't be called during active transfers
        controller.connection_manager.measure_latency.assert_not_called()

    def test_health_check_skips_during_download(self, controller, mock_view):
        """Health check should skip if a download is in progress."""
        mock_view.controller.download_ctrl.is_active = True
        controller.check_health()
        controller.connection_manager.measure_latency.assert_not_called()

    def test_health_check_skips_during_directory_load(self, controller, mock_view):
        """Health check should skip if DirectoryLoader is running."""
        loader = MagicMock()
        loader.isRunning.return_value = True
        mock_view.remote_explorer._loader_thread = loader
        controller.check_health()
        controller.connection_manager.measure_latency.assert_not_called()

    def test_health_check_triggers_reconnect_on_failure(
        self, controller, mock_connection_manager, mock_view
    ):
        """Health check should attempt reconnect when connection is dead."""
        mock_connection_manager.check_alive.return_value = False
        mock_connection_manager.reconnect.return_value = True

        controller.check_health()

        mock_connection_manager.reconnect.assert_called_once()

    def test_health_check_emits_disconnected_on_reconnect_failure(
        self, controller, mock_connection_manager
    ):
        """Should emit disconnected signal if reconnect fails."""
        mock_connection_manager.check_alive.return_value = False
        mock_connection_manager.reconnect.return_value = False

        with patch.object(controller, "disconnected") as mock_signal:
            controller.check_health()
            mock_signal.emit.assert_called_once()

    def test_health_check_skips_adb_connections(self, controller, mock_view):
        """Health check should skip ADB connections (stateless USB)."""
        from src.clients.adb_client import ADBClient

        # Patch get_adb_path so we can instantiate ADBClient
        with patch("src.clients.adb_client.get_adb_path", return_value="/usr/bin/adb"):
            adb_client = ADBClient(device_id="test")
            mock_view.remote_explorer.sftp = adb_client
            controller.check_health()
            controller.connection_manager.measure_latency.assert_not_called()


# ---------------------------------------------------------------------------
# Connection status
# ---------------------------------------------------------------------------


class TestConnectionStatus:
    def test_set_status_updates_label(self, controller, mock_view):
        """_set_status should update the label text and objectName."""
        controller._set_status("● Connecting...", "connection_warning")
        mock_view.connection_status_label.setText.assert_called_with("● Connecting...")
        mock_view.connection_status_label.setObjectName.assert_called_with("connection_warning")

    def test_latency_color_green(self, controller, mock_view):
        """Latency under 100ms should show green."""
        controller._update_status_with_latency(45.0)
        mock_view.connection_status_label.setText.assert_called_with("45ms")
        mock_view.connection_status_label.setObjectName.assert_called_with("connection_connected")

    def test_latency_color_yellow(self, controller, mock_view):
        """Latency 100-300ms should show warning color."""
        controller._update_status_with_latency(180.0)
        mock_view.connection_status_label.setText.assert_called_with("180ms")
        mock_view.connection_status_label.setObjectName.assert_called_with("connection_warning")

    def test_latency_color_red(self, controller, mock_view):
        """Latency over 300ms should show slow/red color."""
        controller._update_status_with_latency(450.0)
        mock_view.connection_status_label.setText.assert_called_with("450ms")
        mock_view.connection_status_label.setObjectName.assert_called_with("connection_slow")

    def test_connect_btn_green_when_connected(self, controller, mock_view):
        """Power button should turn green when status is connected."""
        mock_view.connection_status_label.objectName.return_value = "connection_connected"
        controller._update_connect_btn()
        mock_view.connect_btn.setStyleSheet.assert_called()
        call_arg = mock_view.connect_btn.setStyleSheet.call_args[0][0]
        assert "#30d158" in call_arg  # green color


# ---------------------------------------------------------------------------
# SSH connection callbacks
# ---------------------------------------------------------------------------


class TestSSHCallbacks:
    def test_on_ssh_connected_sets_sftp(self, controller, mock_view, mock_connection_manager):
        """Successful SSH connection should set SFTP on the explorer."""
        controller._on_ssh_connected()

        mock_view.remote_explorer.set_sftp.assert_called_once_with(
            mock_connection_manager.sftp_client
        )
        mock_view.remote_explorer._detail_panel.set_sftp.assert_called_once_with(
            mock_connection_manager.sftp_metadata
        )
        mock_view.remote_explorer.set_sftp_background.assert_called_once_with(
            mock_connection_manager.sftp_background
        )

    def test_on_ssh_connected_emits_signal(self, controller):
        """Successful connection should emit the connected signal."""
        with patch.object(controller, "connected") as mock_signal:
            controller._on_ssh_connected()
            mock_signal.emit.assert_called_once()

    def test_on_ssh_connected_enables_button(self, controller, mock_view):
        """Successful connection should re-enable the connect button."""
        controller._on_ssh_connected()
        mock_view.connect_btn.setEnabled.assert_called_with(True)

    def test_on_ssh_failed_auth_error(self, controller, mock_view):
        """Auth failure should show critical dialog."""
        with patch("src.controllers.connection_controller.QMessageBox") as MockMB:
            MockMB.StandardButton.Ok = QMessageBox.StandardButton.Ok
            controller._on_ssh_failed("AuthenticationError", "Auth failed", "bad key")
            MockMB.critical.assert_called_once()
        mock_view.handle_connection_failure.assert_called_once()

    def test_on_ssh_failed_connection_error(self, controller, mock_view):
        """Connection failure should show warning dialog."""
        with patch("src.controllers.connection_controller.QMessageBox") as MockMB:
            MockMB.StandardButton.Ok = QMessageBox.StandardButton.Ok
            controller._on_ssh_failed("SSHConnectionError", "Timeout", "3 retries")
            MockMB.warning.assert_called_once()
        mock_view.handle_connection_failure.assert_called_once()


# ---------------------------------------------------------------------------
# Shutdown
# ---------------------------------------------------------------------------


class TestShutdown:
    def test_shutdown_stops_timer(self, controller):
        """Shutdown should stop the health timer."""
        with patch.object(controller._health_timer, "stop") as mock_stop:
            controller.shutdown()
            mock_stop.assert_called_once()

    def test_shutdown_disconnects(self, controller, mock_connection_manager):
        """Shutdown should disconnect the connection manager."""
        controller.shutdown()
        mock_connection_manager.disconnect.assert_called_once()

    def test_shutdown_stops_connect_thread(self, controller):
        """Shutdown should stop the connection thread if running."""
        thread = MagicMock()
        thread.isRunning.return_value = True
        controller._connect_thread = thread

        controller.shutdown()

        thread.quit.assert_called_once()
        thread.wait.assert_called_once_with(2000)


# ---------------------------------------------------------------------------
# Initial path logic
# ---------------------------------------------------------------------------


class TestInitialPath:
    def test_uses_default_bookmark_if_set(self, controller, mock_settings):
        """Should use default bookmark as initial path."""
        mock_settings.get_default_bookmark.return_value = "/mnt/external/Movies"
        result = controller._get_initial_path("/mnt/external")
        assert result == "/mnt/external/Movies"

    def test_falls_back_to_root_path(self, controller, mock_settings):
        """Should use root_path if no default bookmark."""
        mock_settings.get_default_bookmark.return_value = None
        result = controller._get_initial_path("/mnt/external")
        assert result == "/mnt/external"
