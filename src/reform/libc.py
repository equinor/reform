from __future__ import annotations

import ctypes
import os
from pathlib import Path
from typing import Literal, cast


_libc = ctypes.CDLL(None, use_errno=True)

# $ man 2 unshare
# int unshare(int flags);
_libc.unshare.restype = ctypes.c_int
_libc.unshare.argtypes = (ctypes.c_int,)


def unshare(flags: int, /) -> int:
    return cast(int, _libc.unshare(flags))


# $ man 2 mount
# int mount(const char *source, const char *target,
#           const char *filesystemtype, unsigned long mountflags,
#           const void *_Nullable data);
_libc.mount.restype = ctypes.c_int
_libc.mount.argtypes = (
    ctypes.c_char_p,
    ctypes.c_char_p,
    ctypes.c_char_p,
    ctypes.c_ulong,
    ctypes.c_void_p,
)


def mount(
    source: Path, target: Path, filesystemtype: Literal[b"none"], mountflags: int
) -> int:
    return cast(
        int, _libc.mount(bytes(source), bytes(target), filesystemtype, mountflags, None)
    )


def get_error() -> str:
    return os.strerror(ctypes.get_errno())


# From /usr/include/linux/sched.h
CLONE_NEWNS = 0x00020000
CLONE_NEWUSER = 0x10000000


# From /usr/include/linux/mount.h
MS_RDONLY = 1
MS_BIND = 4096
MS_REC = 16384
MS_PRIVATE = 1 << 18
