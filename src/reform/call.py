from __future__ import annotations

from contextlib import suppress
import pickle
import shutil
import sys
import os
from pathlib import Path
from tempfile import mkdtemp
from traceback import print_exception
from typing import Any, Callable, TypeVar, cast
from typing_extensions import ParamSpec
from collections.abc import Mapping
import ctypes
from queue import Queue

from reform.bind import Bind, BindNode, MkdirNode, PathNode, merge_bindings
from reform import libc


_P = ParamSpec("_P")
_T = TypeVar("_T")


def mount_all(node: PathNode, chroot_dir: Path) -> None:
    q: Queue[tuple[Path, PathNode]] = Queue()
    q.put((Path(), node))

    reverse_order: list[tuple[Path, PathNode]] = []

    while not q.empty():
        path, node = q.get()
        if isinstance(node, BindNode):
            reverse_order.append((path, node))
        if isinstance(node, MkdirNode):
            for name, child in node.children.items():
                q.put((path / name, child))

    for path, node in reversed(reverse_order):
        node.mount(chroot_dir, path)


def call(
    mapping: Mapping[str, Bind],
    func: Callable[_P, _T],
    *args: _P.args,
    **kwargs: _P.kwargs,
) -> _T:
    tree = merge_bindings({**mapping, "/proc": Bind()})
    tree.validate_all(Path("/"))

    chroot_dir = Path(mkdtemp(prefix="deploy-chroot-"))

    fd_rd, fd_wr = os.pipe()
    rd = os.fdopen(fd_rd, "rb")
    wr = os.fdopen(fd_wr, "wb")

    # In case we are the parent, wait for child to finish and exit
    if (pid := os.fork()) != 0:
        try:
            _, status = os.waitpid(pid, os.WUNTRACED)
            if status != 0:
                raise RuntimeError(
                    f"chroot_func: subprocess exited with status {status}"
                )
            is_exc, result = cast(tuple[bool, Any], pickle.load(rd))
            if is_exc:
                raise result
            return cast(_T, result)
        finally:
            shutil.rmtree(chroot_dir)
            rd.close()

    # The following happens only inside the child process
    try:
        cwd = os.getcwd()
        uid = os.getuid()
        gid = os.getgid()

        if libc.unshare(libc.CLONE_NEWNS | libc.CLONE_NEWUSER) != 0:
            sys.exit(f"Could not unshare: {os.strerror(ctypes.get_errno())}")

        mount_all(tree, chroot_dir)

        os.chroot(chroot_dir)
        with suppress(FileNotFoundError):
            os.chdir(cwd)

        _ = Path("/proc/self/setgroups").write_text("deny")
        _ = Path("/proc/self/uid_map").write_text(f"{uid} {uid} 1")
        _ = Path("/proc/self/gid_map").write_text(f"{gid} {gid} 1")
        pickle.dump((False, func(*args, **kwargs)), wr)
    except BaseException as exc:
        print_exception(exc)
        pickle.dump((True, exc), wr)
    finally:
        wr.close()
        os._exit(0)
