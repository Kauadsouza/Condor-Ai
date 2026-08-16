"""Trava de instancia unica portavel entre Windows, Linux e macOS."""

from __future__ import annotations

import os
from pathlib import Path
from typing import IO

from condor.paths import state_path

_LOCKS: list[IO[str]] = []


def acquire(name: str) -> bool:
    path = state_path("runtime", f"{name}.lock")
    stream = path.open("a+", encoding="utf-8")
    try:
        if os.name == "nt":
            import msvcrt
            stream.seek(0)
            if path.stat().st_size == 0:
                stream.write("0")
                stream.flush()
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (OSError, BlockingIOError):
        stream.close()
        return False
    stream.seek(0)
    stream.truncate()
    stream.write(str(os.getpid()))
    stream.flush()
    _LOCKS.append(stream)
    return True
