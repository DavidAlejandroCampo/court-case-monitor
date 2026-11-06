"""Detect whether an Excel workbook is open before writing to it.

Excel keeps its own copy in memory and creates a hidden "~$name.xlsx" file. If a
script writes to the file on disk, the next save from Excel erases that work
without any warning, so this project refuses to write while the lock exists.
"""
from __future__ import annotations

from pathlib import Path


def lock_path(workbook: Path) -> Path:
    workbook = Path(workbook)
    return workbook.with_name(f"~${workbook.name}")


def lock_owner(workbook: Path) -> str | None:
    """Return the user recorded in the lock file, or None if there is no lock.

    The first byte of the file holds the length of the user name.
    """
    path = lock_path(workbook)
    if not path.exists():
        return None
    data = path.read_bytes()
    if not data:
        return ""
    return data[1 : 1 + data[0]].decode("latin-1", "replace").strip()


def is_locked(workbook: Path) -> bool:
    return lock_path(workbook).exists()
