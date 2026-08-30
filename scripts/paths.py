from __future__ import annotations

import os
from pathlib import Path


def data_dir() -> Path:
    return Path(os.getenv("BACKUPPER_DATA_DIR", ".")).resolve()
