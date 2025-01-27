from collections.abc import Iterable
import os
import pytest
from pathlib import Path
from reform.bind import Bind, BindNode, MkdirNode, merge_bindings


@pytest.fixture
def listdir(monkeypatch: pytest.MonkeyPatch):
    def custom_listdir() -> Iterable[str]:
        yield from ("bin", "etc", "usr")

    monkeypatch.setattr(os, "listdir", custom_listdir)


def test_bind_none():
    assert merge_bindings({}) == MkdirNode()


def test_bind_root(monkeypatch):
    assert merge_bindings({"/": Bind()}) == BindNode(Path("/"))


def test_bind_single_dir(monkeypatch):
    assert merge_bindings({"/bin": Bind()}) == MkdirNode(
        children={"bin": BindNode(Path("/bin"))}
    )


def test_bind_node_with_target():
    assert merge_bindings({"/": Bind(Path.cwd())}) == BindNode(Path.cwd())


def test_bind_node_exclude_with_target(monkeypatch):
    monkeypatch.setattr(os, "listdir", lambda _: ("bin", "etc", "usr"))

    assert merge_bindings({"/": Bind(Path.cwd(), exclude="bin")}) == MkdirNode(
        children={
            "etc": BindNode(Path.cwd() / "etc"),
            "usr": BindNode(Path.cwd() / "usr"),
        }
    )


@pytest.mark.usefixtures("listdir")
def test_bind_manual_exclude(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(os, "listdir", lambda _: ("bin", "etc", "usr"))

    setup = {"/": Bind(), "/bin": Bind(empty=True)}

    assert merge_bindings(setup) == MkdirNode(
        children={
            "bin": MkdirNode(),
            "etc": BindNode(Path("/etc")),
            "usr": BindNode(Path("/usr")),
        }
    )


def test_bind_exclude(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(os, "listdir", lambda _: ("bin", "etc", "usr"))

    assert merge_bindings({"/": Bind(exclude="etc")}) == MkdirNode(
        children={"bin": BindNode(Path("/bin")), "usr": BindNode(Path("/usr"))}
    )


def test_bind_exclude_subdir(monkeypatch):
    monkeypatch.setattr(os, "listdir", lambda _: ("bin", "etc", "usr"))

    setup = {
        "/": Bind(),
        "/usr": Bind(exclude="usr"),
    }

    assert merge_bindings(setup) == MkdirNode(
        children={
            "bin": BindNode(Path("/bin")),
            "etc": BindNode(Path("/etc")),
            "usr": MkdirNode(
                children={
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
    ) == MkdirNode(
        children={
            "bin": BindNode(Path("/bin")),
            "usr": BindNode(Path("/usr")),
            "foo": MkdirNode(),
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
    ) == MkdirNode(
        children={
            "bin": BindNode(Path("/bin")),
            "usr": BindNode(Path("/usr")),
            "foo": MkdirNode(
                children={"bar": MkdirNode(children={"quz": MkdirNode()})}
            ),
        }
    )
