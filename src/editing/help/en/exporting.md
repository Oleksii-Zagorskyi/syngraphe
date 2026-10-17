# Exporting

**Export** on a document's page makes a file of one stated version, which you then download. Only what you may read can be exported.

- **What.** The **document**, its **attachments**, or both. When the version has attachments, the document's export ends with the **attachment list**: each attachment's title, file name and hash. Ticking *Attachments* also adds the files themselves.
- **Format.** **PDF** and **DOCX** carry the numbers of the headings and clauses and page numbers at the foot; no page carries a header — the file's name says which document, version and view it holds, as does the title page where the document has one. The PDF also carries the outline in the viewer's sidebar. **Markdown** is the text as the source view shows it, its headings numbered, without the document's frontmatter, and never carries marked changes.
- **View.** Which version to export, among those you may read: the **canonical version**, the **accepted edits**, the **pending edits**, or **my edits** while you hold the document. The version's number is named beside each.
- **Changes.** A view with an earlier version before it in the chain, named beside it, can be exported **marked against** that version, with its insertions and deletions shown as the pending view shows them, or as **clean text**. A change to formatting alone is printed once, marked.
- **My edits** exports your draft's text with the attachments as they were last sent for review. A change to an attachment that is still in your draft is not in the file.
- **A title page**, when the document has one switched on, opens the file. On the canonical version it names who approved the edition and when. On any other version it says the text is not approved.

**Delivery.** One file, or one zip when attachments are included or a Markdown export's text holds images. The file is named after the document's title, the version's number and the view, in the platform's language: in English, for example, `Title_—_1.0_—_canonical_version.pdf`, with `-marked` added when changes are marked. The export is made in the background: the page shows *The file is being made…* until it is ready, then offers the download. The file is kept for a day; after that, export again. You can have one export of a document waiting at a time.

**When an export fails**, the page says why. If the version can no longer be exported by you, or a version you chose has no attachments, choose again. If your draft was sent for review or discarded after you asked, export another version. If the file was not made in time, export again. If it could not be made, try again; if it fails again, tell the platform's operator.

## Images

PDF and DOCX carry the document's images where its text holds them, a photograph standing as it was taken; a marked export shows a changed image before and after. A Markdown export whose text holds images is one zip: the `.md` file beside an `images` folder holding them.
