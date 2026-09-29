"""Generate the test corpus: a ~40-page invented document, three authors, 3 base commits + 200 single edits.

The generator keeps its own record of who wrote every sentence (`results/truth-<lang>.json`), so a blame result can be
checked for correctness, not only timed. On disk the document is one sentence per line with blank lines
between paragraphs — the product's normal form — so a blamed line is a sentence.

    python corpus.py --lang ukr --repo <dir>/corpus-ukr.git --truth results/truth-ukr.json
"""

import argparse
import json
import random
import time

import gitplumb
from lexicon import LEXICONS, make_sentence

AUTHORS = [1, 2, 3]
SECTIONS = 12
SUBSECTIONS = 3
PARAS_PER_SUB = 7
EDITS = 200
EDIT_KINDS = [("insert", 30), ("rewrite", 30), ("delete", 10), ("append", 15), ("move", 15)]


class Model:
    """The document as blocks; a paragraph is a list of sentence ids. Sentences carry their history."""

    def __init__(self, lex, rng):
        self.lex = lex
        self.rng = rng
        self.blocks = []  # {"type": "heading", "text": ...} | {"type": "para", "section": n, "ids": [...]}
        self.sentences = {}  # id -> {"text", "author", "created", "status", "changed_by", "changed_at", "replaced_by", "replaces"}
        self.used = set()
        self.next_id = 1

    def new_sentence(self, author, commit_no):
        while True:
            text = make_sentence(self.rng, self.lex)
            if text not in self.used:
                break
        self.used.add(text)
        sid = self.next_id
        self.next_id += 1
        self.sentences[sid] = {
            "text": text,
            "author": author,
            "created": commit_no,
            "status": "live",
            "changed_by": None,
            "changed_at": None,
            "replaced_by": None,
            "replaces": None,
        }
        return sid

    def build_sections(self, first, last, author, commit_no):
        subs = self.lex["subsections"]
        for n in range(first, last + 1):
            self.blocks.append(
                {"type": "heading", "text": f"## {n}. {self.lex['sections'][n - 1]}"}
            )
            chosen = self.rng.sample(subs, SUBSECTIONS)
            for m, title in enumerate(chosen, 1):
                self.blocks.append({"type": "heading", "text": f"### {n}.{m} {title}"})
                for _ in range(PARAS_PER_SUB):
                    k = self.rng.randint(3, 6)
                    self.blocks.append(
                        {
                            "type": "para",
                            "section": n,
                            "ids": [self.new_sentence(author, commit_no) for _ in range(k)],
                        }
                    )

    def render(self):
        out = [
            "---",
            f"title: {self.lex['title']}",
            f"language: {self.lex['language']}",
            "synthetic: true",
            "---",
            "",
            f"# {self.lex['title']}",
            "",
        ]
        for b in self.blocks:
            if b["type"] == "heading":
                out.append(b["text"])
            else:
                out.extend(self.sentences[i]["text"] for i in b["ids"])
            out.append("")
        return "\n".join(out)

    # --- edits: each returns a description, or None if it could not apply ---
    def paras(self):
        return [b for b in self.blocks if b["type"] == "para"]

    def edit_insert(self, author, commit_no):
        p = self.rng.choice(self.paras())
        pos = self.rng.randint(0, len(p["ids"]))
        sid = self.new_sentence(author, commit_no)
        p["ids"].insert(pos, sid)
        return {"sentence": sid, "section": p["section"]}

    def _pick_other_sentence(self, author):
        cands = [
            (p, i) for p in self.paras() for i in p["ids"] if self.sentences[i]["author"] != author
        ]
        return self.rng.choice(cands) if cands else (None, None)

    def edit_rewrite(self, author, commit_no):
        p, old = self._pick_other_sentence(author)
        if old is None:
            return None
        new = self.new_sentence(author, commit_no)
        self.sentences[new]["replaces"] = old
        o = self.sentences[old]
        o.update(status="rewritten", changed_by=author, changed_at=commit_no, replaced_by=new)
        p["ids"][p["ids"].index(old)] = new
        return {"old": old, "new": new, "old_author": o["author"], "section": p["section"]}

    def edit_delete(self, author, commit_no):
        p, old = self._pick_other_sentence(author)
        if old is None or len(p["ids"]) < 2:
            return None
        o = self.sentences[old]
        o.update(status="deleted", changed_by=author, changed_at=commit_no)
        p["ids"].remove(old)
        return {"old": old, "old_author": o["author"], "section": p["section"]}

    def edit_append(self, author, commit_no):
        # a new paragraph at the end of a random subsection: after the last paragraph before the next heading
        idxs = [
            i
            for i, b in enumerate(self.blocks)
            if b["type"] == "para"
            and (i + 1 == len(self.blocks) or self.blocks[i + 1]["type"] == "heading")
        ]
        i = self.rng.choice(idxs)
        k = self.rng.randint(3, 5)
        ids = [self.new_sentence(author, commit_no) for _ in range(k)]
        self.blocks.insert(
            i + 1, {"type": "para", "section": self.blocks[i]["section"], "ids": ids}
        )
        return {"sentences": ids, "section": self.blocks[i]["section"]}

    def edit_move(self, author, commit_no, want_authors=None):
        """Move a paragraph to another position inside its subsection. Authors of its sentences are unchanged."""
        runs = self._subsection_runs()
        self.rng.shuffle(runs)
        for run in runs:
            if len(run) < 2:
                continue
            cands = [
                i
                for i in run
                if len(self.blocks[i]["ids"]) >= 2
                and (
                    want_authors is None
                    or {self.sentences[s]["author"] for s in self.blocks[i]["ids"]} == want_authors
                )
            ]
            if not cands:
                continue
            src = self.rng.choice(cands)
            targets = [j for j in run if j != src]
            dst = self.rng.choice(targets)
            block = self.blocks.pop(src)
            self.blocks.insert(dst, block)
            for s in block["ids"]:
                self.sentences[s].setdefault("moved", []).append(commit_no)
            return {
                "sentences": block["ids"],
                "authors": sorted({self.sentences[s]["author"] for s in block["ids"]}),
                "from": src,
                "to": dst,
                "section": block["section"],
            }
        return None

    def _subsection_runs(self):
        runs, cur = [], []
        for i, b in enumerate(self.blocks):
            if b["type"] == "heading":
                if cur:
                    runs.append(cur)
                cur = []
            else:
                cur.append(i)
        if cur:
            runs.append(cur)
        return runs

    def line_truth(self):
        """Expected author per line of the rendered document (None for headings, frontmatter and blanks)."""
        truth = [None] * 8
        for b in self.blocks:
            if b["type"] == "heading":
                truth.append(None)
            else:
                truth.extend(self.sentences[i]["author"] for i in b["ids"])
            truth.append(None)
        return truth

    def to_json(self, commits):
        return {
            "blocks": self.blocks,
            "sentences": {str(k): v for k, v in self.sentences.items()},
            "commits": commits,
            "line_truth": self.line_truth(),
        }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", choices=LEXICONS, required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--truth", required=True)
    ap.add_argument("--sentences")
    ap.add_argument("--seed", type=int, default=20260927)
    a = ap.parse_args()

    t0 = time.perf_counter()
    lex = LEXICONS[a.lang]
    rng = random.Random(a.seed)
    m = Model(lex, rng)
    gitplumb.init_bare(a.repo)
    commits = []
    seq = 0

    # three base commits: each author writes a third of the sections
    thirds = [(1, 4), (5, 8), (9, 12)]
    for author, (first, last) in zip(AUTHORS, thirds, strict=True):
        seq += 1
        m.build_sections(first, last, author, seq)
        sha = gitplumb.commit_document(
            a.repo, m.render(), author, f"Base {seq}: sections {first}-{last}", seq
        )
        commits.append(
            {
                "n": seq,
                "sha": sha,
                "author": author,
                "kind": "base",
                "detail": {"sections": [first, last]},
            }
        )

    kinds = [k for k, w in EDIT_KINDS for _ in range(w)]
    counts = {}
    n_edits = 0
    while n_edits < EDITS:
        author = rng.choice(AUTHORS)
        kind = rng.choice(kinds)
        seq_try = seq + 1
        before = m.render()
        detail = getattr(m, f"edit_{kind}")(author, seq_try)
        if detail is None or m.render() == before:
            continue
        seq = seq_try
        n_edits += 1
        sha = gitplumb.commit_document(a.repo, m.render(), author, f"Edit {n_edits}: {kind}", seq)
        commits.append({"n": seq, "sha": sha, "author": author, "kind": kind, "detail": detail})
        counts[kind] = counts.get(kind, 0) + 1
        if n_edits % 10 == 0:
            gitplumb.tag(
                a.repo, f"1.{n_edits // 10}", sha, author, seq, f"Version 1.{n_edits // 10}"
            )

    doc = m.render()
    with open(a.truth, "w", encoding="utf-8") as f:
        json.dump(m.to_json(commits), f, ensure_ascii=False, indent=0)
    if a.sentences:
        with open(a.sentences, "w", encoding="utf-8") as f:
            f.write(
                "# SYNTHETIC test prose, generated by the corpus generator; not from any real document.\n"
            )
            for sid in sorted(m.sentences):
                f.write(m.sentences[sid]["text"] + "\n")
    words = sum(len(l.split()) for l in doc.splitlines())
    lines = doc.count("\n")
    print(
        json.dumps(
            {
                "lang": a.lang,
                "commits": len(commits),
                "edits": counts,
                "sentences": len(m.sentences),
                "words": words,
                "lines": lines,
                "pages_at_400_words": round(words / 400, 1),
                "seconds": round(time.perf_counter() - t0, 1),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
