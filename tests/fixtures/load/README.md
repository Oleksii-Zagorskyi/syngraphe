# Folders for the loader

Invented documents in the form `load_document` reads (ST-0074, DL-0341): one subfolder per document, holding `document.yaml`, `document.md` and each attachment `document.yaml` names. **Every title, sentence, table row and attachment here is a synthetic example**; nothing is taken from a real document.

| Folder | Holds |
|---|---|
| `procedure-ukr/` | the body of `../documents/two-sections-ukr/document.md` without its frontmatter, and one attachment, `scheme.txt`, the file `../documents/with-parts-ukr/` lays as `attachments/1` |
| `register-ukr/` | a Ukrainian body with a table and a paragraph of two sentences on one line — the normalizer splits them — and two attachments, `form.csv` and `order.txt` |

`document.yaml` holds `title`, `language` and `attachments` — each entry a `file` beside it and its `title` — and nothing else. `document.md` holds the body alone: the frontmatter is the platform's to write.
