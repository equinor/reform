from __future__ import annotations

import os
from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
import sys
from typing_extensions import Any, override

from . import libc


@dataclass
class Bind:
    host_path: str | Path | None = None
    allow_writes: bool = False
    empty: bool = False
    parents: bool = False
    exclude: str | Iterable[str] | None = None


class PathNode(ABC):
    def __init__(self, *, children: dict[str, PathNode] | None = None) -> None:
        self.children: dict[str, PathNode] = children or {}

    @override
    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, self.__class__):
            return False
        return self.children == other.children

    @override
    def __repr__(self) -> str:
        children = ", ".join(f"{repr(k)}: {repr(v)}" for k, v in self.children.items())
        return f"{self.__class__.__name__}({children})"

    @abstractmethod
    def validate(self, current_dir: Path) -> None:
        pass

    @abstractmethod
    def pre_mount(self, chroot_dir: Path, current_dir: Path) -> None:
        pass

    @abstractmethod
    def mount(self, chroot_dir: Path, current_dir: Path) -> None:
        pass

    @abstractmethod
    def post_mount(self, chroot_dir: Path, current_dir: Path) -> None:
        pass

    def validate_all(self, current_dir: Path | None = None) -> None:
        if current_dir is None:
            current_dir = Path()

        self.validate(current_dir)
        for name, child in self.children.items():
            child.validate_all(current_dir / name)

    def pre_mount_all(self, chroot_dir: Path, current_dir: Path | None = None) -> None:
        if current_dir is None:
            current_dir = Path()

        self.pre_mount(chroot_dir, current_dir)
        for name, child in self.children.items():
            child.pre_mount_all(chroot_dir, current_dir / name)

    def mount_all(self, chroot_dir: Path, current_dir: Path | None = None) -> None:
        if current_dir is None:
            current_dir = Path()

        for name, child in self.children.items():
            child.mount_all(chroot_dir, current_dir / name)
        self.mount(chroot_dir, current_dir)

    def post_mount_all(self, chroot_dir: Path, current_dir: Path | None = None) -> None:
        if current_dir is None:
            current_dir = Path()

        self.post_mount(chroot_dir, current_dir)
        for name, child in self.children.items():
            child.post_mount_all(chroot_dir, current_dir / name)


class MkdirNode(PathNode):
    @override
    def validate(self, current_dir: Path) -> None:
        pass

    @override
    def pre_mount(self, chroot_dir: Path, current_dir: Path) -> None:
        if current_dir == Path(""):
            return

    @override
    def mount(self, chroot_dir: Path, current_dir: Path) -> None:
        pass

    @override
    def post_mount(self, chroot_dir: Path, current_dir: Path) -> None:
        pass


class BindNode(PathNode):
    def __init__(
        self,
        source: Path,
        *,
        children: dict[str, PathNode] | None = None,
        allow_writes: bool = False,
    ):
        super().__init__(children=children)
        self.source: Path = source
        self.allow_writes: bool = allow_writes

    @override
    def __eq__(self, other: Any) -> bool:
        return super().__eq__(other) and str(self.source) == str(other.source)

    @override
    def __repr__(self) -> str:
        children = ", ".join(f"{repr(k)}: {repr(v)}" for k, v in self.children.items())
        return f"{self.__class__.__name__}[{self.source}]({children})"

    @override
    def validate(self, current_dir: Path) -> None:
        if not self.source.exists():
            raise ValueError(f"{self.source} can't be bound because it doesn't exist")

    @override
    def pre_mount(self, chroot_dir: Path, current_dir: Path) -> None:
        source = chroot_dir / current_dir

        source.mkdir()

    @override
    def mount(self, chroot_dir: Path, current_dir: Path) -> None:
        source = self.source
        target = chroot_dir / current_dir

        mount_flags = libc.MS_BIND | libc.MS_REC | libc.MS_PRIVATE
        if not self.allow_writes:
            mount_flags |= libc.MS_RDONLY

        if source.is_symlink() or source.is_file():
            return
        target.mkdir(parents=True, exist_ok=True)
        if (
            libc.mount(
                source,
                target,
                b"none",
                mount_flags,
            )
            != 0
        ):
            sys.exit(f"Could not mount {source} to {target}: {libc.get_error()}")

    @override
    def post_mount(self, chroot_dir: Path, current_dir: Path) -> None:
        pass


def merge_bindings(mapping: Mapping[str, Bind]) -> PathNode:
    # The user requested a completely empty chroot
    if not mapping:
        return MkdirNode()

    # Handle the edge case of just a single mapping that is the root binding
    if len(mapping) == 1 and (r := mapping.get("/")) is not None and r.exclude is None:
        return BindNode(Path(r.host_path or Path("/")), allow_writes=r.allow_writes)

    root: PathNode = MkdirNode()

    for path, params in mapping.items():
        parts = Path(path).parts
        prev_node: PathNode = root
        current_dir = Path("/")
        for index, part in enumerate(parts):
            node: PathNode | None = prev_node.children.get(part)
            children: dict[str, PathNode] = {}
            current_dir /= part

            # Non-leaf part of the path
            if index + 1 < len(parts):
                if isinstance(node, BindNode):
                    # Split up a BindNode into sub-BindNodes
                    children = {
                        name: BindNode(node.source / name)
                        for name in os.listdir(node.source)
                    }

                    node = MkdirNode(children=children)
                elif node is None:
                    node = MkdirNode()

            # Leaf part
            else:
                if params.exclude is not None:
                    target = (
                        Path(params.host_path)
                        if params.host_path
                        else Path("/") / current_dir
                    )
                    if isinstance(node, BindNode):
                        target = node.source
                    children.update(
                        {
                            name: BindNode(target / name)
                            for name in os.listdir(target)
                            if name not in (params.exclude or [])
                        }
                    )
                if node is not None:
                    children.update(node.children)

                if params.empty:
                    node = MkdirNode()
                elif children:
                    node = MkdirNode(children=children)
                else:
                    node = BindNode(Path(params.host_path or Path("/") / current_dir))

            assert node is not None
            prev_node.children[part] = node
            prev_node = node

    return root.children["/"]
