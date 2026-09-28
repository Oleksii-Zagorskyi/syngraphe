"""Load the language lists from the repository's fixtures, one file per language (ADR-0012).

A missing row is inserted, an identical one left alone, and a row whose lists differ from its
file is reported and kept; `--overwrite` rewrites it from the file.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from audit.record import record
from identity.models import Language
from syngraphe.provenance import ActorKind

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "languages"
CODE = re.compile(r"^[a-z]{2,8}$")
LISTS = ("never_final", "may_be_final")


def _load(path: Path) -> dict[str, str]:
    """The file's row, checked: the code is the file's name, the items are what the splitter
    compares — lowercase, stripped, without the trailing stop, no repeats."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        code, label = data["code"], data["label"]
        lists = {name: data[name] for name in LISTS}
    except (ValueError, KeyError, TypeError) as error:
        raise CommandError(f"{path.name}: not a language fixture ({error})") from error
    if code != path.stem or not CODE.match(code):
        raise CommandError(
            f"{path.name}: its code must be {path.stem!r}, a lowercase language code"
        )
    if not isinstance(label, str) or not label:
        raise CommandError(f"{path.name}: the label must be a non-empty string")
    for name, items in lists.items():
        if not isinstance(items, list) or not all(isinstance(i, str) and i for i in items):
            raise CommandError(f"{path.name}: {name} must be a list of non-empty strings")
        bad = [i for i in items if i != i.strip().lower() or i.endswith(".")]
        if bad:
            raise CommandError(f"{path.name}: {name} holds {bad!r}; lowercase, no trailing stop")
        if len(set(items)) != len(items):
            raise CommandError(f"{path.name}: {name} repeats an item")
    return {"label": label, **{name: "\n".join(items) for name, items in lists.items()}}


class Command(BaseCommand):
    help = "Seed the LANGUAGE rows from identity/fixtures/languages/*.json."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="rewrite a row whose lists differ from its file",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        for path in sorted(FIXTURES.glob("*.json")):
            wanted = _load(path)
            code = path.stem
            row = Language.objects.filter(code=code).first()
            if row is None:
                Language.objects.create(code=code, actor_kind=ActorKind.SYSTEM, **wanted)
                self.stdout.write(f"{code}: seeded")
                continue
            current = {key: getattr(row, key) for key in wanted}
            differing = sorted(key for key in wanted if current[key] != wanted[key])
            if not differing:
                self.stdout.write(f"{code}: unchanged")
            elif options["overwrite"]:
                for key, value in wanted.items():
                    setattr(row, key, value)
                row.updated_by = None
                row.save(update_fields=[*wanted, "updated_by", "updated_at"])
                record(
                    actor=None,
                    action="language.reseeded",
                    obj=row,
                    before={"code": code, **{k: current[k] for k in differing}},
                    after={"code": code, **{k: wanted[k] for k in differing}},
                )
                self.stdout.write(f"{code}: overwritten ({', '.join(differing)})")
            else:
                self.stdout.write(
                    f"{code}: differs from its file ({', '.join(differing)}); kept, "
                    "--overwrite rewrites it"
                )
