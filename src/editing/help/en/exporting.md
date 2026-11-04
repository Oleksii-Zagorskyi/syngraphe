# Exporting

**Export**, an icon beside a document's heading, opens a page of its own, which makes a file of one stated version for you to download. It starts on what you were reading: from a version's page, that version; from your draft, *My edits*; from a comparison, its newer version; from the document's latest version, the newest view you may export. The page's heading names the version that will be exported and follows the view you choose. Only what you may read can be exported.

- **What.** The **document**, its **appendices**, its **attachments**, or any of them. Appendices go **embedded** — after the body and before the attachment list, each numbered from 1 and starting a new page in PDF, their titles not printed — or **separate**, each a file of its own named by its number and title; appendices chosen without the document always go as separate files. When the version has attachments, the document's export ends with the **attachment list**: each attachment's title, file name and hash. Ticking *Attachments* also adds the files themselves.
- **Format.** **PDF** and **DOCX** carry the numbers of the headings and clauses and page numbers at the foot; no page carries a header — the file's name says which document, version and view it holds, as does the title page where the document has one. The PDF also carries the outline in the viewer's sidebar. **Markdown** is the text as the source view shows it, its headings numbered, without the document's frontmatter, and never carries marked changes.
- **View.** Which version to export, among those you may read: the **canonical version**, the **accepted edits**, the **pending edits**, or **my edits** while you hold the document. The version's number is named beside each.
- **Changes.** A view with an earlier version before it in the chain, named beside it, can be exported **marked against** that version, with its insertions and deletions shown as the pending view shows them, or as **clean text**. A change to formatting alone is printed once, marked.
- **My edits** exports your draft as it stands: its text, its appendices, its attachment list and its files, the changes still in your draft included.
- **A title page**, when the document has one switched on, opens the file. On the canonical version it names who approved the edition and when. On any other version it says the text is not approved.

**Delivery.** One file, or one zip when attachments or separate appendices are included or a Markdown export's text holds images. The file is named after the document's title, the version's number and the view, and the file, its name and its own words — the title page, the attachment list, a zip's entries — are in the document's language, whoever exports it: for a document in English, for example, `Title_—_1.0_—_canonical_version.pdf`, with `-marked` added when changes are marked. A refusal or a failure is said in your own interface language. The export is made in the background: the page shows *The file is being made…* until it is ready, then offers the download. The file is kept for a day; after that, export again. You can have one export of a document waiting at a time.

**When an export fails**, the page says why. If the version can no longer be exported by you, or a version you chose has no appendices or no attachments, choose again. If an attachment's file does not match its record, tell the platform's operator. If your draft was sent for review or discarded after you asked, export another version. If the file was not made in time, export again. If it could not be made, try again; if it fails again, tell the platform's operator.

## Images

PDF and DOCX carry the document's images where its text holds them, a photograph standing as it was taken; a marked export shows a changed image before and after. A Markdown export whose text holds images is one zip: the `.md` file beside an `images` folder holding them.

## The title page and the stylesheet

Which details a title page shows, in which order and how aligned, is the organisation's *Title page layout*; whether a document has a title page, and its own text on it, are changed while editing, as part of a draft. The organisation's stylesheet sets how PDF and Word files look, as it does the reading view. *Template and styles* tells how both are set.
