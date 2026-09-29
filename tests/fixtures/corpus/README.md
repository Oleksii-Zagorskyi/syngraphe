# The corpus

Two invented policy documents, one Ukrainian and one English, each built by three authors over three base commits and two hundred single edits, with an annotated tag every ten edits. Every sentence is assembled from the slot lists in `lexicon.py`; nothing comes from a real document.

| File | Holds |
|---|---|
| `corpus.py` | the generator: the edits, drawn from a fixed seed, and the record of who wrote every sentence |
| `gitplumb.py` | the bare repository written through git plumbing, with fixed identities and dates, so the corpus depends on no library under test |
| `lexicon.py` | the invented prose, per language |
| `document-ukr.md`, `document-eng.md` | each document at its last commit |
| `results/truth-ukr.json`, `results/truth-eng.json` | the record: every sentence's author, the commit that created it and what later happened to it; every commit; the expected author of every line at the last commit |

The generator is deterministic: the same seed yields the same commits, byte for byte. The tests build the repository with it into a temporary directory; the generator refuses a directory that already exists. To regenerate the committed files, from this directory:

```bash
repo="$(mktemp -d)/corpus-ukr.git"
python corpus.py --lang ukr --repo "$repo" --truth results/truth-ukr.json
git -C "$repo" show main:document.md > document-ukr.md
```

and the same with `eng`. Never edit the generated files by hand.
