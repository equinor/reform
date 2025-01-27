from __future__ import annotations

import signal
import pytest
import os
from pathlib import Path
from reform import Bind, call


def test_chroot_python_call():
    """Test that chroot_call works even with an empty environment"""
    assert call({}, (lambda x: x + 1), 2) == 3


def test_chroot_exception():
    def raises():
        raise ValueError("Hello, world")

    with pytest.raises(ValueError, match="Hello, world"):
        call({}, raises)


def test_chroot_assert():
    def raises():
        assert False

    with pytest.raises(AssertionError, match="assert False"):
        call({}, raises)


def test_chroot_listdir(tmp_path: Path):
    def listdir() -> set[str]:
        return set(os.listdir("/"))

    name = "this-does-not-exist"
    (tmp_path / name).mkdir()
    inside = call(
        {
            f"/{name}": Bind(tmp_path),
        },
        listdir,
    )

    # /proc is added automatically
    assert inside == {"proc", name}


def test_chroot_abort_exits_correctly():
    def silent_abort():
        # Override the SIGABRT handler so that Python doesn't write traceback
        _ = signal.signal(signal.SIGABRT, signal.SIG_IGN)
        os.abort()

    with pytest.raises(RuntimeError):
        call({}, silent_abort)


def test_chroot_files_created_outside_are_visible_inside(tmp_path: Path):
    name = "this-does-not-exist"
    _ = (tmp_path / "myfile").write_text("Heisann")

    def inner() -> str:
        return (Path("/") / name / "myfile").read_text()

    result = call({f"/{name}": Bind(tmp_path)}, inner)
    assert result == "Heisann"


def test_chroot_files_created_inside_are_visible_outside(tmp_path: Path):
    name = "this-does-not-exist"

    def inner() -> None:
        _ = (Path("/") / name / "myfile").write_text("Hoppsann")

    call({f"/{name}": Bind(tmp_path)}, inner)
    assert (tmp_path / "myfile").read_text() == "Hoppsann"
