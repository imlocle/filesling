"""Background worker for remote video conversion."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from src.utils.constants import TIMEOUT_SSH_CONNECT


class ConvertWorker(QObject):
    """Background worker for remote ffmpeg video conversion."""

    finished = Signal()
    error = Signal(str)
    progress = Signal(int)

    def __init__(
        self,
        host: str,
        username: str,
        key_path: str,
        port: int,
        remote_path: str,
        password: str = "",
        key_passphrase: str = "",
        video_codec: str = "libx264",
        preset: str = "fast",
        crf: int = 18,
        audio_args: str = "-c:a aac -b:a 128k",
        container: str = "mp4",
    ) -> None:
        super().__init__()
        self.host = host
        self.username = username
        self.key_path = key_path
        self.port = port
        self.remote_path = remote_path
        self.password = password
        self.key_passphrase = key_passphrase
        self.video_codec = video_codec
        self.preset = preset
        self.crf = crf
        self.audio_args = audio_args
        self.container = container

    def run(self) -> None:
        try:
            from paramiko import RejectPolicy, SSHClient

            from src.services.ffmpeg_service import convert_video, replace_original

            # Open a dedicated SSH connection for this conversion
            # so it doesn't block the explorer's SFTP session
            ssh = SSHClient()
            try:
                ssh.load_system_host_keys()
                ssh.set_missing_host_key_policy(RejectPolicy())
                connect_kwargs = {
                    "hostname": self.host,
                    "username": self.username,
                    "port": self.port,
                    "timeout": TIMEOUT_SSH_CONNECT,
                }
                if self.password:
                    connect_kwargs["password"] = self.password
                else:
                    connect_kwargs["key_filename"] = self.key_path
                    if self.key_passphrase:
                        connect_kwargs["passphrase"] = self.key_passphrase
                ssh.connect(**connect_kwargs)

                def progress_cb(pct: int) -> None:
                    self.progress.emit(pct)

                output_path = convert_video(
                    ssh_client=ssh,
                    remote_path=self.remote_path,
                    preset=self.preset,
                    crf=self.crf,
                    video_codec=self.video_codec,
                    audio_args=self.audio_args,
                    container=self.container,
                    progress_cb=progress_cb,
                )
                replace_original(ssh, self.remote_path, output_path)
                self.finished.emit()
            finally:
                ssh.close()
        except Exception as e:
            self.error.emit(str(e))
