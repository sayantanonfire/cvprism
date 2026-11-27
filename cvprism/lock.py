"""Cross-platform single-instance lock using OS file locks (released automatically on crash)."""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path


class AlreadyRunning(RuntimeError):
    pass


@contextmanager
def single_instance(path: Path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    f = open(path, "a+")
    try:
        if os.name == "nt":
            import msvcrt

            try:
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as e:
                raise AlreadyRunning() from e
        else:
            import fcntl

            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as e:
                raise AlreadyRunning() from e
        yield
    finally:
        f.close()
