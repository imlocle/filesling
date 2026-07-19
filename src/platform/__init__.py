"""
Platform abstraction layer for FileSling.

Automatically imports the correct platform implementation based on the OS.
All platform-specific behavior is accessed through this module:

    from src.platform import notify, reveal_in_file_manager, store_credential

Available functions:
- store_credential(account, password) -> bool
- get_credential(account) -> Optional[str]
- delete_credential(account) -> bool
- has_credential(account) -> bool
- notify(title, message, subtitle=None, sound=False)
- set_dock_badge(count)
- inhibit_sleep() -> bool
- release_sleep()
- is_sleep_inhibited() -> bool
- reveal_in_file_manager(path)
"""

import sys

if sys.platform == "darwin":
    from src.platform.macos import (  # noqa: F401
        delete_credential,
        get_credential,
        has_credential,
        inhibit_sleep,
        is_sleep_inhibited,
        notify,
        release_sleep,
        reveal_in_file_manager,
        set_dock_badge,
        store_credential,
    )
elif sys.platform == "win32":
    from src.platform.windows import (  # noqa: F401
        delete_credential,
        get_credential,
        has_credential,
        inhibit_sleep,
        is_sleep_inhibited,
        notify,
        release_sleep,
        reveal_in_file_manager,
        set_dock_badge,
        store_credential,
    )
else:
    from src.platform.base import (  # noqa: F401
        delete_credential,
        get_credential,
        has_credential,
        inhibit_sleep,
        is_sleep_inhibited,
        notify,
        release_sleep,
        reveal_in_file_manager,
        set_dock_badge,
        store_credential,
    )
