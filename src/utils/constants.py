# App
SOFTWARE_NAME = "Shuttle"
CONFIG_JSON = "config.json"

# Connection types
CONN_TYPE_SSH = "ssh"
CONN_TYPE_ADB = "adb"
CONN_TYPE_KEY = "connection_type"

# Defaults
DEFAULT_SSH_PORT = 22
DEFAULT_SSH_KEY_PATH = "~/.ssh/id_rsa"
DEFAULT_REMOTE_BASE_DIR = "/mnt/external"
DEFAULT_ADB_BASE_DIR = "/sdcard"

# Placeholders
PLACEHOLDER_HOST = "192.168.1.100"
PLACEHOLDER_USERNAME = "user"
PLACEHOLDER_SSH_KEY = "~/.ssh/id_rsa"
PLACEHOLDER_BASE_DIR = "/mnt/external or /sdcard"
PLACEHOLDER_NO_DEVICES = "No devices — plug in via USB"

# Dialog titles
DIALOG_MOVE_FAILED = "Move Failed"
DIALOG_DELETION_FAILED = "Deletion Failed"
DIALOG_RENAME_FAILED = "Rename Failed"
DIALOG_CREATION_FAILED = "Creation Failed"
DIALOG_CONNECTION_LOST = "Connection Lost"
DIALOG_CONNECTION_FAILED = "Connection Failed"
DIALOG_CONNECTION_ERROR = "Connection Error"
DIALOG_FILES_ALREADY_EXIST = "Files Already Exist"
DIALOG_FILE_ALREADY_EXISTS = "File Already Exists"
DIALOG_FOLDER_EXISTS = "Folder Exists"
DIALOG_SETUP_REQUIRED = "Setup Required"
DIALOG_SETUP_FAILED = "Setup Failed"

# Duplicate detection actions
DUP_ACTION_OVERWRITE = "overwrite"
DUP_ACTION_SKIP = "skip"
DUP_ACTION_CANCEL = "cancel"

# Transfer queue status labels
STATUS_QUEUED = "⏳ Queued"
STATUS_UPLOADING = "⬆️ Uploading"
STATUS_DOWNLOADING = "⬇️ Downloading"
STATUS_FAILED = "❌ Failed"
