from __future__ import annotations

import os
import shutil
from pathlib import Path

from send2trash import send2trash


def delete_path(path: str, force: bool = False) -> bool:
    """Delete a file or directory.

    When ``force`` is False, move the target to the system trash/recycle bin.
    When ``force`` is True, remove it permanently.
    """
    abs_path = os.path.abspath(path)
    if not os.path.exists(abs_path):
        return False

    if force:
        if os.path.isdir(abs_path) and not os.path.islink(abs_path):
            shutil.rmtree(abs_path)
        else:
            Path(abs_path).unlink()
    else:
        send2trash(abs_path)

    return True
