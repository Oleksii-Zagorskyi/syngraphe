"""Loading a prepared folder as a document (DL-0341, DL-0348): created as any other document, its
text, its attachments and the entities its text marks committed as one version, and that
version accepted — each act by a named
member through the services the interface calls.

Every check runs before anything is written; a failure after the document exists names the step
and leaves a document the interface and `reconcile` continue from. Nothing is ever deleted.
"""

from __future__ import annotations

import dataclasses
import hashlib
import os
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from django.db import connection, transaction

from access.models import AccessGroup, DocumentGroup, GroupMember
from access.rights import Right, rights_on
from documents import bundle, entities, gitstore
from documents.identity import identity_for
from documents.locks import document_lock
from documents.models import (
    ROOT_FOLDER,
    Document,
    DocumentState,
    DocumentTemplate,
    DocumentType,
    Folder,
    PartIndex,
)
from documents.services import CreationStopped, create_document
from documents.template import TemplateRefused, starting_body
from editing import holds
from editing.markdown import load_spec
from editing.markdown.parser import parser
from editing.markdown.validator import validate
from editing.models import Hold
from editing.normalizer import (
    RULESET,
    Lists,
    NormalizerDefect,
    TooLarge,
    joined,
    normalize,
    trailer,
)
from editing.normalizer.headings import strip_own_numbers
from editing.normalizer.spellings import OutsideWhitelist
from identity.models import Language, Membership, MembershipState, User
from tenancy.models import Tenant
from tenancy.schemas import current_tenant

DESCRIPTION = "document.yaml"
BODY = "document.md"
KEYS = {"title", "language", "attachments"}
ITEM_KEYS = {"file", "title"}
SUMMARY = "Loaded from a prepared folder"
# The rights DL-0341's acts need, as DL-0348 narrowed them: creating the document, accepting it.
NEEDED = (Right.CREATE_AND_EDIT, Right.ACCEPT)
DESCRIPTION_LIMIT = 64 * 1024
FILE_NAME_MAX = int(PartIndex._meta.get_field("file_name").max_length or 255)


class Refused(Exception):
    """The folder, its text or the loader's rights refused, every reason at once; nothing
    written."""

    def __init__(self, folder: Path, reasons: list[str]) -> None:
        super().__init__(f"{folder.name}: " + "; ".join(reasons))
        self.reasons = reasons


class AlreadyLoaded(Exception):
    """A document of the folder's title is already reachable through the group: a re-run skips
    it rather than loading it twice."""

    def __init__(self, number: int) -> None:
        super().__init__(f"document {number} already loaded — skipped")
        self.number = number


class Stopped(Exception):
    """A step after the document was created failed; the document stands."""

    def __init__(self, number: int, step: int, error: Exception) -> None:
        super().__init__(
            f"document {number}: step {step} failed ({error}); "
            f"continue with `reconcile --tenant {current_tenant(connection)} "
            f"--document {number}` and the interface"
        )
        self.number = number
        self.step = step


@dataclass(frozen=True)
class Prepared:
    title: str
    language: Language
    body: str
    normalised: str
    files: list[tuple[str, str, bytes]]  # file name, title, bytes
    # What the load changes and says so, never refusing for it: lines joined (DL-0441).
    notices: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Loaded:
    """The loaded document, and the notices its load gave."""

    document: Document
    notices: list[str]


def _nfc(name: str) -> str:
    return unicodedata.normalize("NFC", name)


def _read(path: Path, limit: int) -> bytes:
    """At most `limit` + 1 bytes of `path`, never through a link: what is checked is what is
    committed."""
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as file:
        return file.read(limit + 1)


def _entries(folder: Path, reasons: list[str]) -> dict[str, Path]:
    """The folder's plain files by their NFC names; a link, a subfolder or two names equal once
    normalised are refused. Names beginning with a dot, such as `.DS_Store`, are ignored."""
    present: dict[str, Path] = {}
    with os.scandir(folder) as found:
        for entry in sorted(found, key=lambda e: e.name):
            if entry.name.startswith("."):
                continue
            name = _nfc(entry.name)
            if entry.is_symlink():
                reasons.append(f"{name} is a link; only plain files are loaded")
            elif not entry.is_file(follow_symlinks=False):
                reasons.append(f"{name} is not a plain file")
            elif name in present:
                reasons.append(f"{name} appears twice once its spelling is normalised")
            else:
                present[name] = Path(entry.path)
    return present


def _read_folder(
    folder: Path, reasons: list[str], body_limit: int
) -> tuple[dict[str, Any], str, dict[str, Path]]:
    description: dict[str, Any] = {}
    body = ""
    present = _entries(folder, reasons)
    if DESCRIPTION not in present:
        reasons.append(f"{DESCRIPTION} is missing")
    else:
        try:
            raw = _read(present[DESCRIPTION], DESCRIPTION_LIMIT)
            if len(raw) > DESCRIPTION_LIMIT:
                raise ValueError("too large")
            loaded = yaml.load(raw.decode("utf-8"), Loader=bundle.UniqueKeyLoader)
        except (yaml.YAMLError, UnicodeDecodeError, ValueError, OSError) as error:
            reasons.append(f"{DESCRIPTION} is not readable YAML ({error.__class__.__name__})")
            loaded = {}
        if not isinstance(loaded, dict):
            reasons.append(f"{DESCRIPTION} is not a mapping")
            loaded = {}
        description = loaded
    if BODY not in present:
        reasons.append(f"{BODY} is missing")
    else:
        try:
            raw = _read(present[BODY], body_limit)
            if len(raw) > body_limit:
                reasons.append(f"{BODY} is over {body_limit} bytes")
            else:
                body = raw.decode("utf-8")
        except UnicodeDecodeError:
            reasons.append(f"{BODY} is not UTF-8")
        except OSError as error:
            reasons.append(f"{BODY} cannot be read ({error.__class__.__name__})")
    return description, body, present


def _check_description(
    description: dict[str, Any], present: dict[str, Path], reasons: list[str]
) -> tuple[str, Language | None, list[tuple[str, str]]]:
    unknown = sorted(map(str, set(description) - KEYS))
    if unknown:
        reasons.append(f"{DESCRIPTION} has unknown keys: {', '.join(map(str, unknown))}")
    title = description.get("title")
    if not isinstance(title, str) or not bundle.valid_title(title):
        reasons.append("the title is missing or not one printable line")
        title = ""
    code = description.get("language")
    language = Language.objects.filter(code=code).first() if isinstance(code, str) else None
    if language is None:
        reasons.append(f"the language {code!r} is not one of the platform's")
    items = description.get("attachments", [])
    named: list[tuple[str, str]] = []
    if not isinstance(items, list):
        reasons.append("attachments is not a list")
        items = []
    for position, item in enumerate(items, 1):
        if not isinstance(item, dict) or set(item) != ITEM_KEYS:
            reasons.append(f"attachment {position} needs exactly file and title")
            continue
        file_name, item_title = item["file"], item["title"]
        if not isinstance(file_name, str) or not file_name:
            reasons.append(f"attachment {position}: file is not a name")
            continue
        file_name = _nfc(file_name)
        if "/" in file_name or "\\" in file_name or file_name.startswith("."):
            reasons.append(f"attachment {position}: {file_name!r} is not a file beside the text")
            continue
        if not bundle.valid_title(file_name):
            reasons.append(f"attachment {position}: the file name is not one printable line")
            continue
        if bundle.DIRECTION.search(file_name):
            reasons.append(
                f"attachment {position}: the file name holds a mark that changes the order it is "
                "shown in"
            )
            continue
        if len(file_name) > FILE_NAME_MAX:
            reasons.append(
                f"attachment {position}: the file name is over {FILE_NAME_MAX} characters"
            )
        if not isinstance(item_title, str) or not bundle.valid_title(item_title):
            reasons.append(f"attachment {position}: the title is not one printable line")
            item_title = ""
        if file_name in {name for name, _ in named}:
            reasons.append(f"{file_name} is named twice")
            continue
        if file_name in (DESCRIPTION, BODY):
            reasons.append(f"{file_name} cannot be an attachment")
            continue
        if file_name not in present:
            reasons.append(f"{file_name} is named and absent")
        named.append((file_name, item_title))
    for name in sorted(set(present) - {DESCRIPTION, BODY} - {n for n, _ in named}):
        reasons.append(f"{name} is present and not named")
    return title, language, named


def _check_body(body: str, reasons: list[str]) -> None:
    if body.startswith("---"):
        reasons.append(f"{BODY} begins with a frontmatter; the frontmatter is the platform's")
        return
    for refusal in validate(body):
        reasons.append(f"line {refusal.line}: {refusal.code}")
    for token in parser().parse(body):
        for child in token.children or []:
            if child.type == "image":
                source = str(child.attrs.get("src", ""))
                reasons.append(
                    f"line {(token.map or [0])[0] + 1}: the image reference {source!r}; "
                    "the loader takes no images; add them in the editor after loading"
                )


def _check_rights(loader: User, group: AccessGroup, tenant: Tenant, reasons: list[str]) -> None:
    membership = Membership.objects.filter(
        tenant=tenant, user=loader, state=MembershipState.ACTIVE
    ).first()
    if membership is None or loader.self_blocked or loader.is_tombstoned:
        reasons.append(f"{loader.email} is not an active member of the organisation")
        return
    if not GroupMember.objects.filter(group=group, membership=membership).exists():
        reasons.append(f"{loader.email} is not a member of the group {group.name}")
    held = group.implied_rights()
    for right in NEEDED:
        if right not in held:
            reasons.append(f"the group {group.name} does not hold {right.value}")


def check(folder: Path, loader: User, group: AccessGroup) -> Prepared:
    """Everything the load needs, proven before anything is written; `Refused` with every
    reason otherwise."""
    number = current_tenant(connection)
    if number is None:
        raise RuntimeError("a folder is loaded inside a tenant's schema")
    tenant = Tenant.objects.get(number=number)
    reasons: list[str] = []
    if not folder.is_dir():
        raise Refused(folder, ["not a folder"])
    description, body, present = _read_folder(folder, reasons, load_spec().max_bytes)
    # A heading's own number is the outline's to give, never stored (DL-0441).
    body = strip_own_numbers(body) if body else body
    title, language, named = _check_description(description, present, reasons)
    if body:
        _check_body(body, reasons)
    _check_rights(loader, group, tenant, reasons)
    files: list[tuple[str, str, bytes]] = []
    for file_name, item_title in named:
        path = present.get(file_name)
        if path is None:
            continue
        try:
            data = _read(path, tenant.attachment_max_bytes)
        except OSError as error:
            reasons.append(f"{file_name} cannot be read ({error.__class__.__name__})")
            continue
        if len(data) > tenant.attachment_max_bytes:
            reasons.append(f"{file_name} is over the limit of {tenant.attachment_max_bytes} bytes")
            continue
        files.append((file_name, item_title, data))
    normalised = ""
    if not reasons and language is not None:
        previous = _template_body(title, language)
        try:
            normalised = normalize(previous.encode("utf-8"), body, Lists.of(language)).decode()
        except TooLarge:
            reasons.append(f"{BODY} is too large once normalised")
        except (NormalizerDefect, OutsideWhitelist) as error:
            reasons.append(f"{BODY} could not be normalised ({error.__class__.__name__})")
        else:
            try:
                bundle.parse(bundle.render(_frontmatter(title, language, files), normalised))
            except ValueError as error:
                reasons.append(f"the stored text would not read back ({error})")
            if normalised == previous and not files:
                reasons.append(
                    "the text is the template's and there are no attachments; nothing to load"
                )
            if len(_declared(normalised).encode("utf-8")) > entities.MAX_BYTES:
                reasons.append(
                    f"{holds.ENTITIES} would be over the limit of {entities.MAX_BYTES} bytes: "
                    "the text marks more roles, actions and terms than the platform accepts"
                )
    if reasons:
        raise Refused(folder, reasons)
    assert language is not None
    try:
        found = joined(body, Lists.of(language))
    except (NormalizerDefect, OutsideWhitelist):
        # The notices say what the load changes, and never stop it.
        found = []
    notices = [f"line {line} is joined with the next" for line in found]
    return Prepared(title, language, body, normalised, files, notices)


def _declared(normalised: str) -> str:
    """The `entities.yaml` the loaded version holds: every role, action and term the text marks,
    declared from its words, as a commit from the editor declares it (DL-0440)."""
    return entities.declared_with("[]\n", normalised)


def _template_body(title: str, language: Language) -> str:
    """The body a new document's first commit will hold, read back as the commit will be."""
    template = DocumentTemplate.objects.get()
    frontmatter = bundle.Frontmatter(
        title=title, language=language.code, title_page=template.title_page
    )
    body = starting_body(template.outline, language, strict=False)
    return bundle.parse(bundle.render(frontmatter, body))[1]


def _parts(files: list[tuple[str, str, bytes]]) -> list[dict[str, Any]]:
    return [
        {
            "number": number,
            "title": item_title,
            "file_name": file_name,
            "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data),
        }
        for number, (file_name, item_title, data) in enumerate(files, 1)
    ]


def _frontmatter(
    title: str, language: Language, files: list[tuple[str, str, bytes]]
) -> bundle.Frontmatter:
    return bundle.Frontmatter(title=title, language=language.code, attachments=_parts(files))


def load(folder: Path, loader: User, group: AccessGroup) -> Loaded:
    """The folder as a document whose one content version is accepted as `0.1`, with the notices
    its check gave."""
    from editing.services import ask_authorship, derive_committed
    from review.services import accept, settle_head

    prepared = check(folder, loader, group)
    loaded = (
        Document.objects.filter(
            title=prepared.title,
            state=DocumentState.ACTIVE,
            pk__in=DocumentGroup.objects.filter(group=group).values("document_id"),
        )
        .order_by("number")
        .first()
    )
    if loaded is not None:
        raise AlreadyLoaded(loaded.number)
    tenant_number = current_tenant(connection)
    assert tenant_number is not None
    # (1) Created, as the interface creates, and linked so the loader's rights reach it.
    try:
        document = create_document(
            loader,
            prepared.title,
            prepared.language.code,
            DocumentType.objects.get(code="document"),
            Folder.objects.get(number=ROOT_FOLDER),
        )
    except TemplateRefused as error:
        # Nothing written: refused before the row, as the interface's creation is.
        reason = f"the organisation's document template does not pass ({error})"
        raise Refused(folder, [reason]) from error
    except CreationStopped as error:
        raise Stopped(error.number, 1, error) from error
    try:
        DocumentGroup.link(document, group, by=loader)
    except Exception as error:
        raise Stopped(document.number, 2, error) from error
    # (3) The text, the attachments and the entities as one version, under the writer lock.
    try:
        with document_lock(tenant_number, document.number, timeout=holds.LOCK_WAIT_SECONDS):
            settle_head(document)
            repo = gitstore.open_repository(tenant_number, document.number)
            with transaction.atomic():
                locked = Document.objects.select_for_update().get(pk=document.pk)
                rights = rights_on(loader, locked)
                if locked.state != DocumentState.ACTIVE or Right.EDIT not in rights:
                    raise PermissionError(f"{loader.email} may not edit the new document")
                # One editor at a time: someone who took the new document since it was linked
                # keeps it, and the load stops here for the interface to continue.
                if Hold.objects.filter(document=locked, released_at__isnull=True).exists():
                    raise PermissionError("someone holds the new document")
                kind = gitstore.Kind.REVIEWER_EDIT if Right.ACCEPT in rights else gitstore.Kind.EDIT
                head = gitstore.head(repo)
                assert head is not None
                frontmatter, head_body = bundle.parse(
                    gitstore.read(repo, BODY, head).decode("utf-8")
                )
                lists = Lists.of(prepared.language)
                normalised = normalize(head_body.encode("utf-8"), prepared.body, lists).decode()
                if normalised != prepared.normalised:
                    raise ValueError("the template changed since the folder was checked")
                stored = dataclasses.replace(frontmatter, attachments=_parts(prepared.files))
                files = {BODY: bundle.render(stored, normalised).encode("utf-8")}
                for number, (_, _, data) in enumerate(prepared.files, 1):
                    files[f"attachments/{number}"] = data
                declared = _declared(normalised).encode("utf-8")
                if len(declared) > entities.MAX_BYTES:
                    raise ValueError(f"{holds.ENTITIES} is over the limit")
                if declared != holds.entities_at(repo, head).encode("utf-8"):
                    files[holds.ENTITIES] = declared
            sha = gitstore.commit(
                repo,
                files,
                identity_for(loader),
                SUMMARY,
                kind,
                trailers={"Normalizer": trailer(RULESET, lists).removeprefix("Normalizer: ")},
            )
            derive_committed(document, repo, sha, loader)
        ask_authorship(tenant_number, document, sha)
    except Exception as error:
        raise Stopped(document.number, 3, error) from error
    # (4) Accepted, as a reviewer accepts in the interface.
    try:
        # The version committed here, and nothing a member committed between the two locks.
        accept(document, loader, confirmed=sha)
    except Exception as error:
        raise Stopped(document.number, 4, error) from error
    return Loaded(document, prepared.notices)
