"""
Video conversion settings dialog.

Lets users configure codec, quality, speed preset, and audio settings
for remote ffmpeg video conversions.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

# Default settings — H.264, fast preset, CRF 22 (good quality, reasonable size),
# copy audio (fastest, keeps original quality). This works for everything:
# Jellyfin/Plex streaming, web playback, mobile devices, NAS storage.
DEFAULT_SETTINGS = {
    "codec": "h264",
    "preset": "fast",
    "crf": 22,
    "audio_codec": "copy",
    "audio_bitrate": "128k",
    "container": "mp4",
}


@dataclass
class ConvertSettings:
    """Video conversion settings."""

    codec: str = "h264"
    preset: str = "fast"
    crf: int = 22
    audio_codec: str = "copy"
    audio_bitrate: str = "128k"
    container: str = "mp4"

    @property
    def ffmpeg_video_codec(self) -> str:
        """Return the ffmpeg codec name."""
        return {
            "h264": "libx264",
            "h265": "libx265",
            "vp9": "libvpx-vp9",
        }.get(self.codec, "libx264")

    @property
    def ffmpeg_audio_args(self) -> str:
        """Return the ffmpeg audio arguments."""
        if self.audio_codec == "none":
            return "-an"
        elif self.audio_codec == "copy":
            return "-c:a copy"
        else:
            return f"-c:a {self.audio_codec} -b:a {self.audio_bitrate}"

    @property
    def output_extension(self) -> str:
        """Return the output file extension."""
        return f".{self.container}"


# Module-level current settings (persisted in memory for session)
_current_settings = ConvertSettings(**DEFAULT_SETTINGS)


def get_convert_settings() -> ConvertSettings:
    """Get the current conversion settings."""
    return _current_settings


class ConvertSettingsDialog(QDialog):
    """Dialog for configuring video conversion settings."""

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Video Conversion Settings")
        self.setMinimumSize(450, 550)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # --- Codec ---
        codec_label = QLabel("Video Codec")
        codec_label.setToolTip(
            "The compression format used to encode the video.\n\n"
            "• H.264 — Plays everywhere (TVs, phones, browsers, Plex/Jellyfin).\n"
            "  Best choice if you're unsure.\n\n"
            "• H.265 — Same quality at ~40% smaller file size, but slower to encode.\n"
            "  Some older devices can't play it.\n\n"
            "• VP9 — Open-source alternative. Good for web hosting (YouTube uses it).\n"
            "  Not great for TV/media server playback."
        )
        layout.addWidget(codec_label)
        self._codec_combo = QComboBox()
        self._codec_combo.addItem("H.264 (best compatibility)", "h264")
        self._codec_combo.addItem("H.265 / HEVC (smaller files)", "h265")
        self._codec_combo.addItem("VP9 (open, good for web)", "vp9")
        self._codec_combo.setToolTip(codec_label.toolTip())
        self._codec_combo.setCurrentIndex(
            max(0, self._codec_combo.findData(_current_settings.codec))
        )
        self._codec_combo.currentIndexChanged.connect(self._on_codec_changed)
        layout.addWidget(self._codec_combo)

        # --- Preset ---
        preset_label = QLabel("Encoding Speed")
        preset_label.setToolTip(
            "Controls the tradeoff between encoding speed and compression efficiency.\n\n"
            "Faster presets = bigger file, less CPU time.\n"
            "Slower presets = smaller file, more CPU time.\n\n"
            "The video QUALITY stays the same (controlled by CRF below).\n"
            "This only affects how long encoding takes and how efficiently\n"
            "the file is compressed.\n\n"
            "• Fast — Good default. ~2x realtime on modern hardware.\n"
            "• Medium — ~30% smaller file than Fast, takes 2-3x longer.\n"
            "• Slow — Diminishing returns. Only worth it for archival."
        )
        layout.addWidget(preset_label)
        self._preset_combo = QComboBox()
        self._preset_combo.addItem("Ultrafast (quick, larger file)", "ultrafast")
        self._preset_combo.addItem("Fast (good balance)", "fast")
        self._preset_combo.addItem("Medium (smaller file, slower)", "medium")
        self._preset_combo.addItem("Slow (high compression)", "slow")
        self._preset_combo.addItem("Very Slow (max compression)", "veryslow")
        self._preset_combo.setToolTip(preset_label.toolTip())
        self._preset_combo.setCurrentIndex(
            max(0, self._preset_combo.findData(_current_settings.preset))
        )
        layout.addWidget(self._preset_combo)

        # --- CRF (quality) ---
        crf_label = QLabel("Quality (CRF)")
        crf_label.setToolTip(
            "Constant Rate Factor — controls visual quality.\n\n"
            "Lower number = better quality, bigger file.\n"
            "Higher number = worse quality, smaller file.\n\n"
            "• 18 — Visually lossless. Can't tell from original.\n"
            "• 22 — Excellent quality. Recommended default.\n"
            "• 26 — Good quality. Noticeable on close inspection.\n"
            "• 30+ — Visible compression artifacts.\n\n"
            "For H.265, the same CRF gives better quality than H.264\n"
            "(so CRF 28 in H.265 ≈ CRF 22 in H.264)."
        )
        layout.addWidget(crf_label)
        crf_row = QHBoxLayout()
        crf_row.setSpacing(8)
        self._crf_slider = QSlider(Qt.Orientation.Horizontal)
        self._crf_slider.setRange(0, 51)
        self._crf_slider.setValue(_current_settings.crf)
        self._crf_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._crf_slider.setTickInterval(5)
        self._crf_slider.setToolTip(crf_label.toolTip())
        self._crf_label = QLabel(self._crf_text(_current_settings.crf))
        self._crf_slider.valueChanged.connect(
            lambda v: self._crf_label.setText(self._crf_text(v))
        )
        crf_row.addWidget(self._crf_slider)
        crf_row.addWidget(self._crf_label)
        layout.addLayout(crf_row)

        # --- Audio ---
        audio_label = QLabel("Audio")
        audio_label.setToolTip(
            "How to handle the audio track.\n\n"
            "• Copy — Keeps the original audio untouched (fastest).\n"
            "  Use this unless you have a reason to re-encode.\n\n"
            "• AAC — Re-encodes audio to AAC format.\n"
            "  Useful if the original uses an uncommon codec (DTS, FLAC)\n"
            "  that your player doesn't support.\n\n"
            "• No audio — Strips the audio track entirely."
        )
        layout.addWidget(audio_label)
        self._audio_combo = QComboBox()
        self._audio_combo.addItem("Copy (keep original, fastest)", "copy")
        self._audio_combo.addItem("AAC (re-encode for compatibility)", "aac")
        self._audio_combo.addItem("No audio (remove)", "none")
        self._audio_combo.setToolTip(audio_label.toolTip())
        self._audio_combo.setCurrentIndex(
            max(0, self._audio_combo.findData(_current_settings.audio_codec))
        )
        layout.addWidget(self._audio_combo)

        # Audio bitrate
        self._bitrate_label = QLabel("Audio Bitrate")
        self._bitrate_label.setToolTip(
            "The bitrate for re-encoded audio (AAC).\n\n"
            "• 128k — Standard quality. Fine for most content.\n"
            "• 192k — High quality. Good for music-heavy content.\n"
            "• 256k+ — Overkill for most video, but sounds great."
        )
        layout.addWidget(self._bitrate_label)
        self._bitrate_combo = QComboBox()
        for br in ["96k", "128k", "192k", "256k", "320k"]:
            self._bitrate_combo.addItem(br, br)
        self._bitrate_combo.setToolTip(self._bitrate_label.toolTip())
        self._bitrate_combo.setCurrentIndex(
            max(0, self._bitrate_combo.findData(_current_settings.audio_bitrate))
        )
        layout.addWidget(self._bitrate_combo)
        self._audio_combo.currentIndexChanged.connect(self._on_audio_changed)
        self._on_audio_changed()

        # --- Container ---
        container_label = QLabel("Output Container")
        container_label.setToolTip(
            "The file format that wraps the video and audio streams.\n\n"
            "• MP4 — Universal. Plays on everything.\n"
            "• MKV — Supports more codecs and subtitle formats.\n"
            "  Great for media servers, but some TVs can't play it directly.\n"
            "• WebM — For VP9 codec. Used on the web."
        )
        layout.addWidget(container_label)
        self._container_combo = QComboBox()
        self._container_combo.addItem(".mp4 (universal)", "mp4")
        self._container_combo.addItem(".mkv (flexible, media servers)", "mkv")
        self._container_combo.addItem(".webm (VP9, web)", "webm")
        self._container_combo.setToolTip(container_label.toolTip())
        self._container_combo.setCurrentIndex(
            max(0, self._container_combo.findData(_current_settings.container))
        )
        layout.addWidget(self._container_combo)

        # --- Buttons ---
        layout.addStretch()

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        defaults_btn = QPushButton("Restore Defaults")
        defaults_btn.setToolTip(
            "Reset all settings to recommended defaults:\n"
            "H.264, Fast preset, CRF 22, Copy audio, MP4 container."
        )
        defaults_btn.clicked.connect(self._restore_defaults)
        btn_row.addWidget(defaults_btn)

        btn_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        save_btn = QPushButton("Save")
        save_btn.setObjectName("primary_btn")
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(save_btn)

        layout.addLayout(btn_row)

    def _crf_text(self, value: int) -> str:
        if value <= 18:
            quality = "High"
        elif value <= 23:
            quality = "Good"
        elif value <= 28:
            quality = "Medium"
        else:
            quality = "Low"
        return f"{value} ({quality})"

    def _on_codec_changed(self) -> None:
        codec = self._codec_combo.currentData()
        if codec == "vp9":
            idx = self._container_combo.findData("webm")
            if idx >= 0:
                self._container_combo.setCurrentIndex(idx)

    def _on_audio_changed(self) -> None:
        is_reencode = self._audio_combo.currentData() == "aac"
        self._bitrate_label.setVisible(is_reencode)
        self._bitrate_combo.setVisible(is_reencode)

    def _restore_defaults(self) -> None:
        """Reset all fields to default values."""
        self._codec_combo.setCurrentIndex(
            self._codec_combo.findData(DEFAULT_SETTINGS["codec"])
        )
        self._preset_combo.setCurrentIndex(
            self._preset_combo.findData(DEFAULT_SETTINGS["preset"])
        )
        self._crf_slider.setValue(DEFAULT_SETTINGS["crf"])
        self._audio_combo.setCurrentIndex(
            self._audio_combo.findData(DEFAULT_SETTINGS["audio_codec"])
        )
        self._bitrate_combo.setCurrentIndex(
            self._bitrate_combo.findData(DEFAULT_SETTINGS["audio_bitrate"])
        )
        self._container_combo.setCurrentIndex(
            self._container_combo.findData(DEFAULT_SETTINGS["container"])
        )

    def _save(self) -> None:
        global _current_settings
        _current_settings = ConvertSettings(
            codec=self._codec_combo.currentData(),
            preset=self._preset_combo.currentData(),
            crf=self._crf_slider.value(),
            audio_codec=self._audio_combo.currentData(),
            audio_bitrate=self._bitrate_combo.currentData(),
            container=self._container_combo.currentData(),
        )
        self.accept()
