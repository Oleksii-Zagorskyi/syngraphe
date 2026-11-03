"""Taking and releasing a hold (ADR-0006).

A hold is opened under the document's writer lock and, inside it, with the document's row locked by
`select_for_update()` — the lock under which its group links change — and the right to edit is
decided there, so a link removed while the taker waited is seen. The draft starts as the head's
text: the frontmatter kept apart, the body what every editor, the validator and the normalizer see,
the head's `entities.yaml` and the text of each appendix it lists beside them.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING, Any

from django.db import connection, transaction
from django.utils import timezone

from access.rights import Right, rights_on
from audit.record import record
from documents import bundle, gitstore
from documents.locks import document_lock
from documents.models import Document, DocumentState
from editing.models import Draft, Hold, OpenEditor, ReleaseKind
from identity.models import Membership
from tenancy.models import Tenant
from tenancy.schemas import current_tenant

if TYPE_CHECKING:
    from identity.models import User

BODY = "document.md"
FRONTMATTER = "frontmatter"
# The roles, actions and terms the draft declares, as the commit will write them (DL-0073).
ENTITIES = "entities.yaml"
# How long a request waits for a document's writer lock before it answers that the document is
# busy; a commit or a backup holds it for seconds at most.
LOCK_WAIT_SECONDS = 10.0


class HeldByOther(Exception):
    """Someone else holds the document."""


class NotEditable(Exception):
    """The person may not edit the document, or it is not open to editing, as the locks see it."""


class Frozen(Exception):
    """The document is frozen and the person does not hold *accept* (ADR-0016); `reason` is the
    freeze's own, possibly empty."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class DraftPreserved(Exception):
    """The person has a draft kept from a released hold of theirs (DL-0225): the tab offers it
    back before a new hold is taken. `moved` when someone committed since it was started, so it
    can only be read, or discarded (DL-0318, DL-0381)."""

    def __init__(self, moved: bool) -> None:
        super().__init__(moved)
        self.moved = moved


class NothingKept(Exception):
    """A take-back found no kept draft: it was discarded, or taken back, meanwhile."""


# The releases that keep a draft for its holder (ADR-0006): someone else ended the hold. A finish
# or a discard is the holder's own end, and a draft such a hold still has is one a stopped finish
# left behind, which its commit already holds.
KEEPING = (ReleaseKind.INACTIVITY, ReleaseKind.FORCED, ReleaseKind.BLOCKED)


def split(document_md: str) -> tuple[dict[str, Any], str]:
    """`document.md` as the draft keeps it: its frontmatter as data, and its body."""
    frontmatter, body = bundle.parse(document_md)
    return asdict(frontmatter), body


def join(frontmatter: dict[str, Any], body: str) -> str:
    """`document.md` again, byte for byte as the platform writes it."""
    return bundle.render(bundle.Frontmatter(**frontmatter), body)


def open_hold(document: Document) -> Hold | None:
    return Hold.objects.filter(document=document, released_at__isnull=True).first()


def preserved_draft(document: Document, user: Any) -> Draft | None:
    """The draft kept for `user` from their latest released hold on `document`, or `None`: a
    release by an administrator, by inactivity or by a block keeps it (ADR-0006); a finish and a
    discard delete it, and taking it back moves it to the new hold."""
    user_id = getattr(user, "pk", None)
    if user_id is None:
        return None
    latest = (
        Hold.objects.filter(document=document, user_id=user_id, released_at__isnull=False)
        .order_by("-released_at")
        .first()
    )
    if latest is None or latest.release_kind not in KEEPING:
        return None
    return Draft.objects.filter(hold=latest).first()


def tenant_number() -> int:
    number = current_tenant(connection)
    if number is None:
        raise RuntimeError("a hold is taken inside a tenant's schema")
    return number


def take(document: Document, user: User, *, take_back: bool = False) -> Hold:
    """The user's hold on `document` with its draft — the open one when they already hold it;
    `HeldByOther` when someone else does; `NotEditable` when, under the locks, they may not edit
    it or it is not active; `Frozen` while a freeze is open and they do not hold *accept*.
    `documents.locks.LockTimeout` when the lock stays busy.

    While the user has a preserved draft, a new hold is taken only by `take_back`, and only while
    nobody has committed since the draft was started — the head read under the lock (DL-0318):
    the draft row moves to the new hold, its text and base kept, and the editors the ended hold
    left open on it are closed. Otherwise `DraftPreserved`, with `moved` saying whether the head
    has moved on; `NothingKept` for a take-back that finds no kept draft."""
    number = tenant_number()
    with transaction.atomic():
        # The organisation's row and the taker's membership first, as the blocks take them before
        # any document's lock: a block being written is waited for, and then seen — no hold
        # outlives a block (DL-0256). Shared, so takes never wait on one another.
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM tenancy_tenant WHERE number = %s FOR SHARE", [number])
        list(
            Membership.objects.select_for_update(no_key=True, of=("self",)).filter(
                user=user, tenant__number=number
            )
        )
        return _take_locked(document, user, number, take_back)


def _take_locked(document: Document, user: User, number: int, take_back: bool) -> Hold:
    with (
        document_lock(number, document.number, timeout=LOCK_WAIT_SECONDS),
        transaction.atomic(),
    ):
        locked = Document.objects.select_for_update().get(pk=document.pk)
        return hold_locked(locked, user, number, take_back=take_back)


def hold_locked(locked: Document, user: User, number: int, *, take_back: bool = False) -> Hold:
    """`take`'s body, for a caller that holds the document's writer lock and, in its transaction,
    the document's row — an act that opens the hold only once it is sure to write in it."""
    from editions.models import open_freeze

    rights = rights_on(user, locked)
    if locked.state != DocumentState.ACTIVE or Right.EDIT not in rights:
        raise NotEditable(locked.number)
    frozen = open_freeze(locked)
    if frozen is not None and Right.ACCEPT not in rights:
        raise Frozen(frozen.reason)
    existing = open_hold(locked)
    if existing is not None:
        if existing.user_id != user.pk:
            raise HeldByOther(locked.number)
        return existing
    repo = gitstore.open_repository(number, locked.number)
    base = gitstore.head(repo)
    if base is None:
        raise RuntimeError(f"document {locked.number} has no commit to edit")
    kept = preserved_draft(locked, user)
    if take_back and kept is None:
        raise NothingKept(locked.number)
    if kept is not None and (not take_back or kept.base_commit != base):
        raise DraftPreserved(moved=kept.base_commit != base)
    now = timezone.now()
    hold = Hold.objects.create(document=locked, user=user, acquired_at=now, last_activity_at=now)
    if kept is not None:
        kept.hold = hold
        kept.save(update_fields=["hold", "updated_at"])
        OpenEditor.objects.filter(draft=kept, closed_at__isnull=True).update(closed_at=now)
        return hold
    frontmatter, body = split(gitstore.read(repo, BODY, base).decode("utf-8"))
    content = {BODY: body, FRONTMATTER: frontmatter, ENTITIES: entities_at(repo, base)}
    # Each listed appendix's text beside the body, as the editors and the commit read it;
    # one whose file is missing is the reconciler's to report, and reads as the base has it.
    for entry in frontmatter["appendices"]:
        path = f"appendices/{int(entry['number'])}.md"
        try:
            content[path] = gitstore.read(repo, path, base).decode("utf-8")
        except KeyError:
            continue
    Draft.objects.create(hold=hold, base_commit=base, content=content)
    return hold


def entities_at(repo: Any, commit: str) -> str:
    """`entities.yaml` at `commit`, as the draft holds it; an empty list where the tree has none."""
    try:
        return gitstore.read(repo, ENTITIES, commit).decode("utf-8")
    except KeyError:
        return "[]\n"


def draft_state(hold: Hold) -> dict[str, Any]:
    """The state of `hold`'s draft, as a release or a discard records what it leaves behind
    (DL-0225, DL-0256): the commit it started from, when it last changed, and how many editors
    are still open on it — `None` for each where the hold has no draft."""
    draft = Draft.objects.filter(hold=hold).first()
    if draft is None:
        return {"draft_base": None, "draft_updated_at": None, "open_editors": None}
    return {
        "draft_base": draft.base_commit,
        "draft_updated_at": draft.updated_at.isoformat(),
        "open_editors": OpenEditor.objects.filter(draft=draft, closed_at__isnull=True).count(),
    }


def release(
    hold: Hold,
    kind: ReleaseKind,
    *,
    actor: User | None = None,
    released_by: User | None = None,
    reason: str = "",
    finish_completed: bool = False,
) -> bool:
    """End `hold`, keeping its draft (ADR-0003) — unless it holds no edits, which a release of a
    keeping kind, or *released*, deletes: an empty hold keeps nothing (DL-0514). Whether this
    call ended it. The caller holds the
    document's writer lock and, inside a transaction, its row lock, as `take` does, so a release
    never falls between the steps of a commit. `released_by` is who forced or blocked it, when
    someone did; `actor` is who acted, for the audit trail, `None` for the platform or an
    operator's command. Audited with the document's number, never a title. A release of a kind
    that keeps the draft first completes a finish that stopped after its commit (DL-0414): the
    hold then ends `finished`, which the caller reads on the hold."""
    locked = Hold.objects.select_for_update().get(pk=hold.pk)
    if locked.released_at is not None:
        return False
    if kind in KEEPING:
        from editing.services import finish_stopped

        # A draft its holder's own commit already holds is no work at risk: the stopped finish
        # is completed instead, and the hold released `finished` (DL-0414).
        if finish_stopped(locked, actor=actor, reason=reason):
            return True
    locked.released_at = timezone.now()
    locked.release_kind = kind
    locked.released_by = released_by
    locked.release_reason = reason
    locked.save(update_fields=["released_at", "release_kind", "released_by", "release_reason"])
    document = Document.objects.get(pk=locked.document_id)
    draft = None
    if kind in (*KEEPING, ReleaseKind.RELEASED):
        # Locked before it is read: a capture writing the first edit commits first and is seen,
        # and one arriving after waits, then finds the hold ended.
        draft = Draft.objects.select_for_update().filter(hold=locked).first()
    # Read before any deletion, so the audit says what there was.
    state = draft_state(locked)
    if draft is not None:
        from editing.services import has_edits

        # A draft with nothing in it is no work to keep, and nothing is offered back for it —
        # whatever the kind, the draft decides (DL-0514).
        if not has_edits(locked):
            draft.files.all().delete()
            draft.delete()
            state["kept"] = False
    record(
        actor=actor,
        action="document.hold_released",
        obj=document,
        before=None,
        after={
            "number": document.number,
            "release_kind": kind.value,
            "reason": reason,
            "holder": str(locked.user_id),
            **state,
            **({"finish_completed": True} if finish_completed else {}),
        },
        tenant=Tenant.objects.get(number=tenant_number()),
    )
    return True


def draft_entities(draft: Any, repo: Any, commit: str) -> str:
    """The draft's `entities.yaml`; a draft kept from before it carried one reads it as `commit`
    holds it — the head, wherever the draft is shown or committed, so the lists, the picker and
    the commit read one file."""
    if ENTITIES in draft.content:
        return str(draft.content[ENTITIES])
    return entities_at(repo, commit)
