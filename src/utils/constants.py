# =============================================================================
# App Identity
# =============================================================================
import os
import sys
from pathlib import Path

SOFTWARE_NAME = "FileSling"
CONFIG_JSON = "config.json"
VERSION = "3.6.1"
GITHUB_REPO_URL = "https://github.com/imlocle/filesling"

# App data directory (config, logs, history, queue)
# Windows: %APPDATA%\FileSling  (e.g., C:\Users\user\AppData\Roaming\FileSling)
# macOS/Linux: ~/.FileSling
if sys.platform == "win32":
    APP_DATA_DIR = Path(os.environ.get("APPDATA", Path.home())) / SOFTWARE_NAME
else:
    APP_DATA_DIR = Path.home() / f".{SOFTWARE_NAME}"

# =============================================================================
# Connection Types
# =============================================================================
CONN_TYPE_SSH = "ssh"
CONN_TYPE_ADB = "adb"
CONN_TYPE_IOS = "ios"
CONN_TYPE_KEY = "connection_type"

# =============================================================================
# Connection Defaults
# =============================================================================
DEFAULT_SSH_PORT = 22
DEFAULT_SSH_KEY_PATH = "~/.ssh/id_rsa"
DEFAULT_REMOTE_BASE_DIR = "/"
DEFAULT_ADB_BASE_DIR = "/"

# =============================================================================
# Timeouts (seconds)
# =============================================================================
TIMEOUT_SSH_CONNECT = 10
TIMEOUT_SSH_RETRY_DELAY = 3
TIMEOUT_ADB_COMMAND = 10
TIMEOUT_ADB_TRANSFER = 600  # 10 min for large file push/pull
TIMEOUT_ADB_PAIRING = 15
TIMEOUT_KEYCHAIN = 5
TIMEOUT_NOTIFICATION = 5
TIMEOUT_FFMPEG_INSTALL = 120

# =============================================================================
# Retry & Limits
# =============================================================================
MAX_CONNECTION_RETRIES = 3
MAX_DOWNLOAD_RETRIES = 3
MAX_UPLOAD_RETRIES = 3
MAX_PARALLEL_DOWNLOADS = 3
MAX_DRAG_BYTES = 10 * 1024 * 1024  # 10 MB — files larger than this skip drag-to-Finder
IOS_CHUNK_SIZE = 1024 * 1024  # 1 MB — iOS file streaming chunk size

# =============================================================================
# Health Check
# =============================================================================
HEALTH_CHECK_INTERVAL_MS = 15000  # 15 seconds

# =============================================================================
# History & Logging
# =============================================================================
MAX_ACTIVITY_HISTORY = 500
MAX_ERROR_LOG_ENTRIES = 500
ACTIVITY_HISTORY_FILE = "activity_history.json"
TRANSFER_QUEUE_FILE = "transfer_queue.json"
ERROR_LOG_FILE = "errors.json"
CRASH_LOG_FILE = "crash.log"
LOGS_DIR_NAME = "logs"

# =============================================================================
# UI Timing
# =============================================================================
TRANSFER_REFRESH_INTERVAL_MS = 500
QUIT_CHECK_INTERVAL_MS = 1000

# =============================================================================
# Placeholders (UI text)
# =============================================================================
PLACEHOLDER_HOST = "192.168.1.100"
PLACEHOLDER_USERNAME = "user"
PLACEHOLDER_SSH_KEY = "~/.ssh/id_rsa"
PLACEHOLDER_BASE_DIR = "/"
PLACEHOLDER_NO_DEVICES = "No devices — plug in via USB"

# =============================================================================
# Dialog Titles
# =============================================================================
DIALOG_MOVE_FAILED = "Move Failed"
DIALOG_DELETION_FAILED = "Deletion Failed"
DIALOG_CREATION_FAILED = "Creation Failed"
DIALOG_CONNECTION_LOST = "Connection Lost"
DIALOG_CONNECTION_FAILED = "Connection Failed"
DIALOG_CONNECTION_ERROR = "Connection Error"
DIALOG_FILES_ALREADY_EXIST = "Files Already Exist"
DIALOG_FILE_ALREADY_EXISTS = "File Already Exists"
DIALOG_FOLDER_EXISTS = "Folder Exists"
DIALOG_SETUP_REQUIRED = "Setup Required"
DIALOG_SETUP_FAILED = "Setup Failed"

# =============================================================================
# Duplicate Detection Actions
# =============================================================================
DUP_ACTION_OVERWRITE = "overwrite"
DUP_ACTION_SKIP = "skip"
DUP_ACTION_CANCEL = "cancel"

# =============================================================================
# Transfer Queue Status Labels
# =============================================================================
STATUS_QUEUED = "⏳ Queued"
STATUS_UPLOADING = "⬆️ Uploading"
STATUS_DOWNLOADING = "⬇️ Downloading"
STATUS_FAILED = "❌ Failed"
STATUS_CONVERTING = "🔄 Converting"
STATUS_DONE = "✅ Done"

# =============================================================================
# Metadata / NFO Tag Definitions
# =============================================================================

# Common tags shown by default in the Edit Metadata dialog
# Format: (field_key, display_label)
METADATA_COMMON_TAGS = [
    ("title", "Title"),
    ("sort_name", "Sort Title"),
    ("artist", "Artist"),
    ("director", "Director"),
    ("album", "Album / Series"),
    ("show", "Show Name"),
    ("season_number", "Season"),
    ("episode_sort", "Episode #"),
    ("date", "Date / Year"),
    ("genre", "Genre"),
    ("description", "Description"),
]

# Advanced tags (hidden by default, expandable)
METADATA_ADVANCED_TAGS = [
    ("track", "Track Number"),
    ("disc", "Disc Number"),
    ("composer", "Composer"),
    ("performer", "Performer"),
    ("publisher", "Publisher / Studio"),
    ("copyright", "Copyright"),
    ("language", "Language"),
    ("network", "Network"),
    ("synopsis", "Synopsis"),
    ("grouping", "Grouping"),
    ("lyrics", "Lyrics"),
    ("rating", "Rating"),
    ("comment", "Comment"),
    ("sort_artist", "Sort Artist"),
    ("sort_album", "Sort Album"),
    ("compilation", "Compilation"),
    ("encoded_by", "Encoded By"),
    ("url", "URL"),
]

# Placeholder text and tooltip for each metadata field
# Format: field_key → (placeholder_text, tooltip)
METADATA_FIELD_HINTS = {
    "title": ("e.g., The Challenge", "Display name in Jellyfin."),
    "sort_name": ("e.g., 01", "Controls sort order. Set to '01' to sort first."),
    "artist": ("e.g., Tony Horton", "Creator, performer, or main actor."),
    "director": ("e.g., Christopher Nolan", "Director of the video."),
    "album": ("e.g., P90X3", "Collection or series group."),
    "show": ("e.g., P90X3", "TV show or series name."),
    "season_number": ("e.g., 1", "Season or disc number."),
    "episode_sort": ("e.g., 5", "Episode number for ordering."),
    "date": ("e.g., 2014", "Year or full date (YYYY-MM-DD)."),
    "genre": ("e.g., Fitness;Workout", "Use semicolons for multiple."),
    "description": ("e.g., Full body strength workout", "Short summary or plot."),
    "track": ("e.g., 3", "Track number within an album/disc."),
    "disc": ("e.g., 2", "Disc number in a multi-disc set."),
    "composer": ("e.g., Hans Zimmer", "Music composer."),
    "performer": ("e.g., Tony Horton", "Main performer or actor."),
    "publisher": ("e.g., Beachbody", "Publisher, studio, or distributor."),
    "copyright": ("e.g., © 2014 Beachbody", "Copyright notice."),
    "language": ("e.g., eng, jpn", "Primary language (ISO 639 code)."),
    "network": ("e.g., Netflix, HBO", "Network or streaming platform."),
    "synopsis": ("e.g., A detailed plot summary...", "Full plot synopsis."),
    "grouping": ("e.g., Phase 1", "Content grouping or phase."),
    "lyrics": ("e.g., Song lyrics...", "Lyrics or transcript."),
    "rating": ("e.g., TV-PG, PG-13", "Content rating."),
    "comment": ("e.g., Ripped from DVD", "Freeform notes."),
    "sort_artist": ("e.g., Horton, Tony", "Sort order for artist."),
    "sort_album": ("e.g., P90X3 Season 1", "Sort order for album."),
    "compilation": ("e.g., 1", "Set to 1 if part of a compilation."),
    "encoded_by": ("e.g., HandBrake 1.6", "Encoding software."),
    "url": ("e.g., https://...", "Related URL."),
}

# Mapping from our field keys to Jellyfin NFO XML element names
METADATA_KEY_TO_NFO = {
    "title": "title",
    "sort_name": "sorttitle",
    "artist": "artist",
    "director": "director",
    "album": "set",
    "show": "showtitle",
    "season_number": "season",
    "episode_sort": "episode",
    "date": "year",
    "genre": "genre",
    "description": "plot",
    "track": "track",
    "disc": "disc",
    "composer": "composer",
    "performer": "actor",
    "publisher": "studio",
    "copyright": "copyright",
    "language": "language",
    "network": "network",
    "synopsis": "outline",
    "rating": "mpaa",
    "comment": "comment",
    "sort_artist": "sortartist",
    "sort_album": "sortset",
    "url": "website",
}

# NFO element names that map back to our field keys (reverse lookup)
METADATA_NFO_TO_KEY = {
    "sorttitle": "sort_name",
    "showtitle": "show",
    "season": "season_number",
    "episode": "episode_sort",
    "year": "date",
    "set": "album",
    "plot": "description",
    "studio": "publisher",
}

# NFO XML elements to skip when reading (non-editable metadata)
METADATA_NFO_SKIP_KEYS = {"actor", "thumb", "fanart", "uniqueid", "fileinfo"}

# People fields that generate <actor> entries in NFO output
METADATA_PEOPLE_ROLES = {
    "director": "Director",
    "artist": "Artist",
    "performer": "Actor",
    "composer": "Composer",
}
