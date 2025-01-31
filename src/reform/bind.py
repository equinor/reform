from __future__ import annotations

import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from queue import Queue

from . import libc


@dataclass
class Bind:
    host_path: str | Path | None = None
    allow_writes: bool = False
    empty: bool = False
    parents: bool = False
    exclude: str | Iterable[str] | None = None


@dataclass
class Node:
    pass


@dataclass
class DirNode(Node):
    children: dict[str, Node]


@dataclass
class LinkNode(Node):
    target: Path


@dataclass
class BindNode(Node):
    source: Path
    allow_writes: bool = False


def _bfs(
    func: Callable[[Node, Path, Path], None], root: Node, chroot_dir: Path
) -> None:
    queue: Queue[tuple[Node, Path]] = Queue()
    queue.put((root, Path()))

    while not queue.empty():
        node, path = queue.get()
        func(node, path, chroot_dir)
        if isinstance(node, DirNode):
            for name, child in node.children.items():
                queue.put((child, path / name))


def _perform(node: Node, path: Path, chroot_dir: Path) -> None:
    in_chroot_path = chroot_dir / path

    if isinstance(node, DirNode):
        if in_chroot_path != chroot_dir:
            in_chroot_path.mkdir()
    elif isinstance(node, LinkNode):
        in_chroot_path.symlink_to(node.target)
    elif isinstance(node, BindNode):
        mount_flags = libc.MS_BIND | libc.MS_REC | libc.MS_PRIVATE
        if not node.allow_writes:
            mount_flags |= libc.MS_RDONLY

        in_chroot_path.mkdir()
        libc.mount(
            node.source,
            in_chroot_path,
            b"none",
            mount_flags,
        )


def mount_all(root: Node, chroot_dir: Path) -> None:
    _bfs(_perform, root, chroot_dir)


def _listdir_nodes(path: Path, exclude: Iterable[str] = ()) -> dict[str, Node]:
    nodes: dict[str, Node] = {}
    for name in os.listdir(path):
        if name in exclude:
            continue
        subpath = path / name
        if subpath.is_symlink():
            nodes[name] = LinkNode(subpath.readlink())
        elif subpath.is_dir():
            nodes[name] = BindNode(subpath)
        else:
            print(f"Warning: Could not bind {subpath}")
    return nodes


def merge_bindings(mapping: Mapping[str, Bind]) -> Node:
    # The user requested a completely empty chroot
    if not mapping:
        return DirNode({})

    # Handle the edge case of just a single mapping that is the root binding
    if len(mapping) == 1 and (r := mapping.get("/")) is not None and r.exclude is None:
        return BindNode(Path(r.host_path or Path("/")), allow_writes=r.allow_writes)

    root: DirNode = DirNode({})

    for path, params in mapping.items():
        parts = Path(path).parts
        prev_node: DirNode = root
        current_dir = Path("/")
        for index, part in enumerate(parts):
            node: Node | None = (
                prev_node.children.get(part) if isinstance(prev_node, DirNode) else None
            )
            children: dict[str, Node] = {}
            current_dir /= part

            # Non-leaf part of the path
            if index + 1 < len(parts):
                if isinstance(node, BindNode):
                    # Split up a BindNode into sub-BindNodes
                    node = DirNode(_listdir_nodes(node.source))
                elif node is None:
                    node = DirNode({})

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
                    children.update(_listdir_nodes(target, params.exclude or ()))
                if isinstance(node, DirNode):
                    children.update(node.children)

                if params.empty:
                    node = DirNode({})
                elif children:
                    node = DirNode(children)
                else:
                    node = BindNode(Path(params.host_path or Path("/") / current_dir))

            assert node is not None
            prev_node.children[part] = node
            if not isinstance(node, DirNode):
                break
            prev_node = node

    return root.children["/"]
