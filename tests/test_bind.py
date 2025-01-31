from collections.abc import Iterable
import os
import pytest
from pathlib import Path
from reform.bind import Bind, BindNode, DirNode, LinkNode, merge_bindings


@pytest.fixture(autouse=True)
def islink(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "is_symlink", lambda self: False)


@pytest.fixture
def listdir(monkeypatch: pytest.MonkeyPatch):
    def custom_listdir() -> Iterable[str]:
        yield from ("bin", "etc", "usr")

    monkeypatch.setattr(os, "listdir", custom_listdir)


def test_bind_none():
    assert merge_bindings({}) == DirNode({})


def test_bind_root(monkeypatch):
    assert merge_bindings({"/": Bind()}) == BindNode(Path("/"))


def test_bind_single_dir(monkeypatch):
    assert merge_bindings({"/bin": Bind()}) == DirNode(
        children={"bin": BindNode(Path("/bin"))}
    )


def test_bind_node_with_target():
    assert merge_bindings({"/": Bind(Path.cwd())}) == BindNode(Path.cwd())


def test_bind_node_exclude_with_target(monkeypatch):
    monkeypatch.setattr(os, "listdir", lambda _: ("bin", "etc", "usr"))
    monkeypatch.setattr(Path, "is_dir", lambda self: True)

    assert merge_bindings({"/": Bind(Path.cwd(), exclude="bin")}) == DirNode(
        {
            "etc": BindNode(Path.cwd() / "etc"),
            "usr": BindNode(Path.cwd() / "usr"),
        }
    )


@pytest.mark.usefixtures("listdir")
def test_bind_manual_exclude(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(os, "listdir", lambda _: ("bin", "etc", "usr"))

    setup = {"/": Bind(), "/bin": Bind(empty=True)}

    assert merge_bindings(setup) == DirNode(
        {
            "bin": DirNode({}),
            "etc": BindNode(Path("/etc")),
            "usr": BindNode(Path("/usr")),
        }
    )


def test_bind_exclude(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(os, "listdir", lambda _: ("bin", "etc", "usr"))

    assert merge_bindings({"/": Bind(exclude="etc")}) == DirNode(
        {"bin": BindNode(Path("/bin")), "usr": BindNode(Path("/usr"))}
    )


def test_bind_exclude_subdir(monkeypatch):
    monkeypatch.setattr(os, "listdir", lambda _: ("bin", "etc", "usr"))

    setup = {
        "/": Bind(),
        "/usr": Bind(exclude="usr"),
    }

    assert merge_bindings(setup) == DirNode(
        {
            "bin": BindNode(Path("/bin")),
            "etc": BindNode(Path("/etc")),
            "usr": DirNode(
                {
                    "bin": BindNode(Path("/usr/bin")),
                    "etc": BindNode(Path("/usr/etc")),
                }
            ),
        }
    )


def test_bind_subdir_empty(monkeypatch):
    def listdir(_):
        yield from ("bin", "usr")

    monkeypatch.setattr(os, "listdir", listdir)
    assert merge_bindings(
        {
            "/": Bind(),
            "/foo": Bind(empty=True),
        }
    ) == DirNode(
        {
            "bin": BindNode(Path("/bin")),
            "usr": BindNode(Path("/usr")),
            "foo": DirNode({}),
        }
    )


def test_bind_subsubdir_empty(monkeypatch):
    def listdir(_):
        yield from ("bin", "usr")

    monkeypatch.setattr(os, "listdir", listdir)
    assert merge_bindings(
        {
            "/": Bind(),
            "/foo/bar/quz": Bind(empty=True),
        }
    ) == DirNode(
        {
            "bin": BindNode(Path("/bin")),
            "usr": BindNode(Path("/usr")),
            "foo": DirNode({"bar": DirNode({"quz": DirNode({})})}),
        }
    )


def test_bind_with_symlink(monkeypatch):
    def listdir(_):
        yield from ("bin", "usr", "lib")

    def is_symlink(self):
        return self == Path("/lib")

    def readlink(self):
        return Path("fake/link")

    monkeypatch.setattr(os, "listdir", listdir)
    monkeypatch.setattr(Path, "is_symlink", is_symlink)
    monkeypatch.setattr(Path, "readlink", readlink)
    assert merge_bindings(
        {
            "/": Bind(exclude="prog"),
        }
    ) == DirNode(
        {
            "bin": BindNode(Path("/bin")),
            "usr": BindNode(Path("/usr")),
            "lib": LinkNode(Path("fake/link")),
        }
    )
