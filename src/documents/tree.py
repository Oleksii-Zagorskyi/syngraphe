"""The folder tree: its order, a folder's path and the key that sorts paths (DL-0206, DL-0207).

Siblings sort alphabetically as Ukrainian is read, then by number; the root comes first and is
named after the organisation (DL-0194). A path is known by its names, so it sorts component by
component, never as one string.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from django.db.models.functions import Collate

from documents.models import ROOT_FOLDER, Folder

PATH_SEPARATOR = " / "


@dataclass
class Node:
    folder: Folder
    depth: int
    children: list[Node] = field(default_factory=list)


class Tree:
    """Every folder of the organisation, read in one query, or those of `numbers` and their
    ancestors."""

    def __init__(self, organisation: str, numbers: Iterable[int] | None = None) -> None:
        self.organisation = organisation
        everything = list(Folder.objects.order_by(Collate("name", "uk-x-icu"), "number"))
        self.by_pk: dict[Any, Folder] = {f.pk: f for f in everything}
        kept = {f.pk for f in everything} if numbers is None else self._with_ancestors(numbers)
        self.children: dict[Any, list[Folder]] = {}
        for folder in everything:
            if folder.pk in kept and folder.parent_id is not None:
                self.children.setdefault(folder.parent_id, []).append(folder)
        self.root = next(f for f in everything if f.number == ROOT_FOLDER)
        self.rank: dict[Any, int] = {self.root.pk: 0}
        for siblings in self.children.values():
            for i, folder in enumerate(siblings):
                self.rank[folder.pk] = i

    def _with_ancestors(self, numbers: Iterable[int]) -> set[Any]:
        by_number = {f.number: f for f in self.by_pk.values()}
        kept: set[Any] = set()
        for number in numbers:
            folder = by_number.get(number)
            while folder is not None and folder.pk not in kept:
                kept.add(folder.pk)
                folder = self.by_pk.get(folder.parent_id)
        return kept

    def nodes(self) -> list[Node]:
        """The tree from the root, each node's children in order. Built without recursion:
        folders nest without limit."""
        root = Node(self.root, 0)
        pending = [root]
        while pending:
            node = pending.pop()
            node.children = [
                Node(child, node.depth + 1) for child in self.children.get(node.folder.pk, [])
            ]
            pending.extend(node.children)
        return [root]

    def flat(self) -> list[Node]:
        """`nodes()` read depth first, root first, siblings in order: what a choice of folders
        lists."""
        listed: list[Node] = []
        pending = list(reversed(self.nodes()))
        while pending:
            node = pending.pop()
            listed.append(node)
            pending.extend(reversed(node.children))
        return listed

    def ancestry(self, folder: Folder) -> list[Folder]:
        """The folders from the first level below the root down to `folder`; empty for the
        root."""
        chain: list[Folder] = []
        current: Folder | None = self.by_pk.get(folder.pk, folder)
        while current is not None and current.parent_id is not None:
            chain.append(current)
            current = self.by_pk.get(current.parent_id)
        return list(reversed(chain))

    def path_of(self, folder: Folder) -> str:
        """The names below the root joined with ` / `; the root's path is the organisation's
        name."""
        chain = self.ancestry(folder)
        return PATH_SEPARATOR.join(f.name for f in chain) if chain else self.organisation

    def path_key(self, folder: Folder) -> tuple[int, ...]:
        """The sibling ranks from the root down to `folder`, so paths sort alphabetically
        component by component, the root's first."""
        return tuple(self.rank.get(f.pk, 0) for f in self.ancestry(folder))
