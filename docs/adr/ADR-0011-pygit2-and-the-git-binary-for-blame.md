---
tags:
  - adr
aliases:
  - ADR-0011 pygit2 for the repository, the git binary for blame
status: accepted
date: 2026-09-27
supersedes: []
superseded_by:
  - DL-0425 (in part — the undo walks each line forward with the move rule, not by reverse blame)
  - DL-0547 (in part — no git revert among the operations pygit2 performs)
---

# ADR-0011: pygit2 for the repository, the git binary for blame

**Date:** 2026-09-27
**Status:** Accepted
**Deciders:** Oleksii
**Supersedes:** None

## Context

Django performs every git operation itself, through a library, on bare repositories it owns (ADR-0002); the operation set is init, commit, read, diff, blame, revert and tag, with no branches and no merges (ADR-0003). Nothing is ever checked out: a read is a read of a blob at a commit, and a revert has to produce a tree without a working directory. Authorship is derived from blame by a worker after each commit and cached per commit (`technical-design.md § Runtime`), and it must follow a paragraph moved within a section, exclude a named commit when a future migration re-splits lines, and let a reviewer undo one author's edits since the last acceptance, with the sentences a later version changed listed for editing by hand rather than chosen (ST-0037, DL-0243).

Four claims settled the choice (`verification-plan.md` V-05 to V-08 and V-11), measured on Python 3.12 on Debian 12 with 2 CPUs against a generated forty-page history of 203 commits by three authors, in Ukrainian and in English.

## Decision

**Use pygit2 for the repository and the `git` binary for blame, and let the platform recognise moved sentences itself.** pygit2 — the libgit2 binding, no git binary needed — performs init, commit, read at a commit, diff, revert and tag on the bare repositories, revert as a three-way merge into an in-memory index written out as a tree. Blame is run by invoking `git blame` and reading its porcelain output, because excluding a named commit (`--ignore-rev`), the reverse walk per-author undo needs (`--reverse`) and bounding a blame to the commits since the cached one (`^cached new`) exist only in the binary. A moved sentence is recognised by the authorship worker as a line removed and re-added verbatim within one commit, not by git's `-M`.

## Rationale

**The two parts each do what the other cannot.** libgit2 has none of the three blame options above; the binary cannot be a library. libgit2 performs the write path — commit, revert, tag — as library calls with no working tree and no process, which is how the application wants to own its repositories. The binary carries the blame options that libgit2 never grew, and blame is a read run by a worker, where a subprocess costs nothing that matters: 0.23 s over a forty-page history, 8 ms bounded. Using the binary for blame does not make git a service or a second authorisation surface (ADR-0002): it runs inside the worker, on repositories only the application reaches.

**It passed every claim it was asked to.**
- Every operation on a bare repository, revert included, through pygit2 alone; the same through GitPython, with a workaround for Debian's git.
- Cold blame far under the 5 s budget on every route — 0.55 s pygit2, 0.23 s the binary, 0.26 s GitPython — and pygit2 and the binary agreeing on all 1,624 lines.
- Excluding a named commit left every one of 1,302 sentence and heading lines attributed exactly as before, through the binary; libgit2 has no equivalent.
- Repack and prune removed only debris; every tagged version read back byte-identical through pygit2 and GitPython.
- Per-author undo for one author — 440 sentences, 22 built on by others — classified exactly as the generator's record, in 3.1 s, from a reverse blame that only the binary offers.

**Move detection is decided in the platform rather than left to git** because git scores a moved block by its ASCII letters and digits, so a paragraph of Ukrainian text is never followed however the threshold is set, and libgit2 does not implement move detection at all. The failure is systematic, not marginal: the platform's documents are Ukrainian, and a rule that depends on how many digits a sentence happens to contain would attribute the same edit differently from one paragraph to the next. The exact-line rule is cheaper than git's heuristic and follows from the normal form, which the platform already enforces.

**The choice is cheap to revise in one direction.** Should libgit2 gain ignore-revs or a reverse walk, blame moves into the library and the binary leaves the image; the porcelain parser is the only code that changes.

## Consequences

- The image carries `git` (Debian 12's 2.39.5 suffices; 2.40 is not required) beside pygit2. The licence of each is compatible with redistribution in an Apache-2.0 product: libgit2 and pygit2 are GPL-2.0 with a linking exception; git is an unmodified GPL-2.0 binary invoked as a process.
- The authorship worker per commit: `git blame ^cached new`, overlaid on the cached authorship, plus the move rule over that commit's diff. A re-split migration writes its commits to an ignore-revs file rather than rewriting the derived store.
- Undoing one author's edits (ST-0037, DL-0243) is a reverse-blame walk from each of the author's commits, which also yields the sentences later versions changed — 3 s over a forty-page history without a cache, within the 5 s budget.
- Authorship is per sentence line; blank lines carry none and are excluded from any identity check between blames — `--ignore-rev` re-assigns them by heuristic.
- The move rule matches lines verbatim. Two identical sentences in one document, one moved and one not, are ambiguous to it; the worker records such a case rather than guessing.
- V-06 is disproven for the library's blame and met by the platform's rule, which rests on DL-0244: the normalizer keeps a moved paragraph's stored lines on every path, so the bytes the rule compares are unchanged.
- The application owns a porcelain parser for `git blame` output and the plumbing to build a commit from a tree through pygit2 — small code, but product code, tested.

## Alternatives Rejected

| Option | Raised by | Outcome |
|---|---|---|
| pygit2 for the repository, the `git` binary for blame, the platform's own move rule | agent | chosen |
| GitPython alone | verification plan | rejected — 7/7 on the operations, but it drives the same binary as the chosen blame route and adds a second wrapper around it; its revert over Debian's git 2.39.5 needs a temporary index and `read-tree -m` because `merge-tree --merge-base` arrived in git 2.40; `--ignore-rev` needs `allow_unsafe_options=True` |
| dulwich alone | verification plan | rejected — pure Python, 6/7 on the operations, but no blame: the one operation the claims time |
| pygit2 alone | verification plan | rejected — no move detection (the copy-tracking flags are declared and not implemented), no way to exclude a named commit, no reverse walk; would have needed authorship re-derived from diffs, the V-05 fallback |
| the `git` binary alone, no library | agent | rejected — every commit, revert and tag becomes a process with exit codes for errors, where libgit2 gives typed objects and in-memory indexes; the write path is the part the application most wants as library calls |
| git's own move detection (`-M`) for moved sentences | verification plan | rejected — scores a moved block by its ASCII letters and digits; a Cyrillic paragraph never reaches the threshold, and `-M1` follows only sentences that happen to carry a digit or Latin letter |
| authorship computed from each commit's diff, blame as a repair path | verification plan (V-05 fallback) | not needed — blame is 0.23 s cold and 8 ms bounded; kept as the fallback it is |
| gitoxide (`gix`) | agent | rejected — Rust, no Python binding |
| gitdb | agent | rejected — GitPython's object store only; no commit, diff or blame API |

## Review triggers

- libgit2 gains ignore-revs, a reverse blame or move detection: blame moves into pygit2 and the binary leaves the image.
- Bounded blame plus the move rule exceeds the worker's budget on the organisation's real documents.
- A git upgrade changes blame's ignore or move heuristics so that a sentence line's attribution differs between versions.
- The move rule meets identical sentences in one document often enough to matter.

## Appendix — what was compared, and how

The comparison ran in two stages. The long list screened every candidate on the requirements that need no benchmark: a licence the product can redistribute, operation on a bare repository without a working tree, a blame the platform can call, and maintenance. The short list — the three Python libraries and the binary they wrap or replace — ran the same harness on the same corpus: the seven operations on a tiny bare repository, then blame timed five times in fresh interpreters on the forty-page history, then the move, exclusion, repack and per-author-undo tests (V-05 to V-08, V-11). Everything ran in `python:3.12-slim-bookworm` (Python 3.12.14, Debian 12.15, git 2.39.5) on the development host's 2-CPU Docker VM. Versions are those installed on 2026-09-27. Results and the harness's logs are kept with the session that ran them.

### Long list — the basic requirements

| Candidate | Version | Licence | Needs a git binary | Bare repository, no working tree | Blame | Maintained | Result |
|---|---|---|---|---|---|---|---|
| pygit2 (libgit2) | 1.20.1 (libgit2 1.9.7) | GPL-2.0 with linking exception | no | yes | yes — plain only | yes, tracks libgit2 | short list |
| dulwich | 1.2.15 | Apache-2.0 or GPL-2.0+ | no | yes | **no** | yes | short list, screened out at blame |
| GitPython | 3.1.62 | BSD-3-Clause | yes | yes, through plumbing | yes — the binary's | yes | short list |
| `git` binary via subprocess | 2.39.5 (Debian 12) | GPL-2.0 | is the binary | yes | yes — every option | yes | short list |
| gitoxide (`gix`) | current | MIT or Apache-2.0 | no | yes | partial | yes | out — no Python binding |
| gitdb | 4.0.12 | BSD-3-Clause | no | object store only | no | maintained with GitPython | out — no commit, diff or blame API |

### Short list — what the harness asked

Ukrainian / English figures where the two corpora differ; one figure where they agree.

| Question | pygit2 | dulwich | GitPython | `git` binary |
|---|---|---|---|---|
| init a bare repository | pass | pass | pass | pass |
| commit with the user id and the non-routable address | pass | pass | pass | pass |
| read a file at a named commit | pass | pass | pass | pass |
| diff two commits | pass | pass | pass | pass |
| blame a file | pass | **fail — no blame** | pass | pass |
| revert a commit without a working tree | pass — `revert_commit` → index → tree | pass — `three_way_merge` | pass — temporary index and `read-tree -m` on git < 2.40; `merge-tree --merge-base` from 2.40 | as GitPython |
| annotated tag | pass | pass | pass — needs a tagger identity in the environment | as GitPython |
| cold blame over 203 commits, median of 5 | 0.55 / 0.38 s | not run — no blame | 0.26 / 0.22 s | 0.23 / 0.19 s |
| blame after one more commit, whole history | 0.52 / 0.38 s | not run — no blame | 0.26 / 0.22 s | 0.24 / 0.19 s |
| blame bounded to the commits since the cached one | not offered in this form | not run — no blame | as the binary | **8 / 6 ms** |
| agreement with the other route, 1,624 lines | 0 differences vs the binary | not run — no blame | not compared — same binary | 0 differences vs pygit2 |
| moved paragraph, English, follows the author | no (copy-tracking flags not implemented) | not run — no blame | yes with `-M` | yes with `-M` |
| moved paragraph, Ukrainian, follows the author | no | not run — no blame | **no** on `-M`, `-M1`, `-M0`, `-C` | **no** — sentences score 0 ASCII alphanumerics; with `(п. 4.2.1)` appended, `-M1` follows |
| exclude a named commit, 1,302 text lines identical | **no** — `IGNORE_WHITESPACE` only | not run — no blame | yes, with `allow_unsafe_options=True` | yes — `--ignore-rev`, `--ignore-revs-file` |
| reverse blame for per-author undo | no | not run — no blame | same binary; not run | yes — 3.1 / 2.1 s for one author, 440 sentences, 0 disagreements with the record |
| read every tag after repack and prune | 20 of 20, byte-identical | not run — screened out | 20 of 20, byte-identical | not run — read through the libraries |
| binary in the image | not needed | not needed | required | is the binary |
| stable major version | 1.x | 1.x since 2026 | 3.x | 2.x |

## References

- `verification-plan.md` V-05, V-06, V-07, V-08, V-11
- ADR-0002 — Django owns the workflow; git is a library, never a service
- ADR-0003 — linear edit history
- ST-0037 — undoing one author's edits, as re-scoped by DL-0243
- DL-0244 — the normalizer keeps a moved paragraph's stored lines
- `technical-design.md § Who performs git operations`
