"""The rights vocabulary and its inclusions (ADR-0007, ADR-0016, DL-0234)."""

from __future__ import annotations

import pytest

from access.rights import ACTS, LADDER, PARTS, Right, implied

pytestmark = pytest.mark.fast

VIEWS = {Right.VIEW_CANONICAL, Right.VIEW_ACCEPTED, Right.VIEW_PENDING}


def test_sixteen_rights() -> None:
    assert len(Right) == 16
    assert set(LADDER) | set(ACTS) | set(PARTS) | {
        Right.VIEW_PREVIOUS_CANONICAL,
        Right.VIEW_ALL_HISTORY,
    } == set(Right)


def test_accept_implies_edit_and_the_views() -> None:
    assert implied({Right.ACCEPT}) == {Right.ACCEPT, Right.EDIT, *VIEWS}


def test_freeze_and_reserve_imply_edit() -> None:
    for act in (Right.FREEZE, Right.RESERVE_FOR_EDITING):
        result = implied({act})
        assert result == {act, Right.EDIT, *VIEWS}
        assert Right.CREATE_AND_EDIT not in result


def test_make_canonical_implies_view_accepted_only() -> None:
    result = implied({Right.MAKE_CANONICAL})

    assert result == {Right.MAKE_CANONICAL, Right.VIEW_ACCEPTED, Right.VIEW_CANONICAL}
    assert Right.VIEW_PENDING not in result
    assert Right.EDIT not in result


def test_part_rights_need_edit() -> None:
    assert implied({Right.UPLOAD_ATTACHMENT}) == frozenset()
    assert Right.UPLOAD_ATTACHMENT in implied({Right.UPLOAD_ATTACHMENT, Right.EDIT})
    assert Right.UPLOAD_ATTACHMENT in implied({Right.UPLOAD_ATTACHMENT, Right.ACCEPT})


def test_the_ladder_includes_every_step_below() -> None:
    assert implied({Right.CREATE_AND_EDIT}) == set(LADDER)
    assert implied({Right.VIEW_PENDING}) == VIEWS
    assert implied({Right.VIEW_CANONICAL}) == {Right.VIEW_CANONICAL}


def test_history_rights_stand_alone() -> None:
    assert implied({Right.VIEW_ALL_HISTORY}) == {Right.VIEW_ALL_HISTORY}
    assert implied({Right.VIEW_PREVIOUS_CANONICAL}) == {Right.VIEW_PREVIOUS_CANONICAL}
