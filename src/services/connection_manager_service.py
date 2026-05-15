from __future__ import annotations

import os
from time import sleep
from typing import Optional

from paramiko import (
    AuthenticationException,
    AutoAddPolicy,
    SFTPClient,
    SSHClient,
    SSHException,
)

from src.config.settings import Settings
from src.models.errors import (
    AuthenticationError,
    FileAccessError,
    SFTPConnectionError,
    SSHConnectionError,
)
from src.utils.logging_signal import logger


class ConnectionManagerService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.ssh_client: Optional[SSHClient] = None
        self.sftp_client: Optional[SFTPClient] = None

    def connect(self) -> bool:
        """
        Establishes SSH connection with retry logic.

        Returns:
            True if connection successful, False otherwise

        Raises:
            SSHConnectionError: If connection fails after all retries
            AuthenticationError: If SSH authentication fails
            FileAccessError: If SSH key file is not accessible
        """
        if self.ssh_client and self.sftp_client:
            return True

        # Validate SSH key exists before attempting connection
        if not os.path.exists(self.settings.ssh_key_path):
            error_msg = f"SSH key not found: {self.settings.ssh_key_path}"
            logger.error(f"Connection: {error_msg}")
            raise FileAccessError(
                "SSH key file not found",
                path=self.settings.ssh_key_path,
                details="Please check your SSH key path in settings",
            )

        # Check SSH key permissions (should be 600 or 400)
        try:
            key_stat = os.stat(self.settings.ssh_key_path)
            key_perms = oct(key_stat.st_mode)[-3:]
            if key_perms not in ["600", "400"]:
                logger.warn(
                    f"Connection: SSH key has insecure permissions: {key_perms}. "
                    f"Should be 600 or 400"
                )
        except OSError as e:
            logger.warn(f"Connection: Could not check SSH key permissions: {e}")

        retries = 0
        max_retries = 3
        last_error: Optional[Exception] = None

        while retries < max_retries:
            try:
                self.ssh_client = SSHClient()
                self.ssh_client.set_missing_host_key_policy(AutoAddPolicy())

                self.ssh_client.connect(
                    hostname=self.settings.host,
                    username=self.settings.username,
                    key_filename=self.settings.ssh_key_path,
                    timeout=10,
                )

                # Open SFTP session
                try:
                    self.sftp_client = self.ssh_client.open_sftp()
                except Exception as e:
                    # Close SSH if SFTP fails
                    if self.ssh_client:
                        self.ssh_client.close()
                        self.ssh_client = None
                    raise SFTPConnectionError(
                        "Failed to open SFTP session", details=str(e)
                    )

                logger.success(f"Connected: {self.settings.host}")
                return True

            except AuthenticationException as e:
                last_error = e
                logger.error(
                    f"Connection: Authentication Failed: {e}\n"
                    f"Please check your SSH key and server credentials"
                )
                # Don't retry authentication errors
                self.ssh_client = None
                self.sftp_client = None
                raise AuthenticationError(
                    "SSH authentication failed",
                    details=f"User: {self.settings.username}, Key: {self.settings.ssh_key_path}",
                )

            except SSHException as e:
                last_error = e
                retries += 1
                logger.error(
                    f"Connection: SSH Error: Retry {retries}/{max_retries}: {e}"
                )
                self.ssh_client = None
                self.sftp_client = None

                if retries < max_retries:
                    sleep(3)

            except TimeoutError as e:
                last_error = e
                retries += 1
                logger.error(
                    f"Connection: Timeout: Retry {retries}/{max_retries}\n"
                    f"Check if server is reachable at {self.settings.host}"
                )
                self.ssh_client = None
                self.sftp_client = None

                if retries < max_retries:
                    sleep(3)

            except Exception as e:
                last_error = e
                retries += 1
                logger.error(f"Connection: Failed: Retry {retries}/{max_retries}: {e}")
                self.ssh_client = None
                self.sftp_client = None

                if retries < max_retries:
                    sleep(3)

        # All retries exhausted
        error_msg = (
            f"Connection failed after {max_retries} attempts. "
            f"Please check:\n"
            f"1. Server is powered on and connected to network\n"
            f"2. IP address is correct: {self.settings.host}\n"
            f"3. SSH is enabled on the server\n"
            f"4. SSH key is authorized on the server"
        )
        logger.error(f"Connection: {error_msg}")

        raise SSHConnectionError(
            f"Failed to connect after {max_retries} attempts",
            details=str(last_error) if last_error else "Unknown error",
        )

    def open_sftp_session(self) -> Optional[SFTPClient]:
        """
        Create a NEW SFTP client for a worker thread.
        This avoids thread contention with the UI explorer's SFTP.

        Returns:
            New SFTP client or None if SSH not connected

        Raises:
            SFTPConnectionError: If SFTP session cannot be opened
        """
        try:
            if not self.ssh_client:
                logger.warn("Connection: Cannot open SFTP session - SSH not connected")
                return None
            return self.ssh_client.open_sftp()
        except Exception as e:
            logger.error(f"Connection: Failed to open SFTP session: {e}")
            raise SFTPConnectionError(
                "Failed to open worker SFTP session", details=str(e)
            )

    def is_connected(self) -> bool:
        return self.ssh_client is not None and self.sftp_client is not None

    def disconnect(self) -> None:
        """Close SSH + SFTP connections gracefully."""
        try:
            if self.sftp_client:
                self.sftp_client.close()
                self.sftp_client = None
        except Exception as e:
            logger.warn(f"Connection: Error closing SFTP: {e}")

        try:
            if self.ssh_client:
                self.ssh_client.close()
                self.ssh_client = None
        except Exception as e:
            logger.warn(f"Connection: Error closing SSH: {e}")

        logger.stop("Connection: Disconnected")

    def test_connection(self) -> bool:
        """
        Temporary connection just for testing.

        Returns:
            True if connection succeeds, False otherwise
        """
        test_ssh = None
        try:
            if not os.path.exists(self.settings.ssh_key_path):
                logger.error(f"Test: SSH key not found: {self.settings.ssh_key_path}")
                return False

            test_ssh = SSHClient()
            test_ssh.set_missing_host_key_policy(AutoAddPolicy())
            test_ssh.connect(
                hostname=self.settings.host,
                username=self.settings.username,
                key_filename=self.settings.ssh_key_path,
                timeout=10,
            )
            logger.success("Test: Connection successful")
            return True
        except AuthenticationException as e:
            logger.error(f"Test: Authentication failed: {e}")
            return False
        except TimeoutError:
            logger.error(
                f"Test: Connection timeout - server not reachable at {self.settings.host}"
            )
            return False
        except Exception as e:
            logger.error(f"Test: Connection failed: {e}")
            return False
        finally:
            if test_ssh:
                try:
                    test_ssh.close()
                except Exception:
                    pass
