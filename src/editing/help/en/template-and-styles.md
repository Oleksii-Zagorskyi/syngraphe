# Template and styles

An organisation's administrator sets how its documents start and how they look, under Administration: the **document template**, the **title page layout** and the **stylesheet**.

## The document template

Administration › *Template* holds what every new document starts with — its headings and any starting text — written in Markdown, in the same allowed set as the editor. It begins with a `#` heading, holds no image, and is at most 20,000 bytes; a template that breaks a rule is refused with each construct named by its line. A new document starts from the template as it stands when the document is created, put in the platform's form for the document's language. Changing the template never touches existing documents.

*New documents get a title page* decides whether a new document starts with its title page switched on. The page says who last changed the template, and when.

## The title page

A title page is generated at export from the document's details; nobody types it as a page. *Title page layout…*, on the template page, chooses which details it shows and in which order — title, number, type, edition, approver, approval date, and the document's own title-page text — and whether they stand on the left or centred. The approval line is always there, at the position chosen for it: on an export of the canonical version it names who approved the edition and when; on any other export it says the text is not approved. *Reset to the default form* returns to the platform's layout. The layout serves every document whose title page is switched on.

Whether a document has a title page, and the text of its own on it, are changed by the person editing the document, in the edit tab, as changes of the draft the reviewer sees: *Editing* tells how.

## The stylesheet

Administration › *Styles* holds the organisation's stylesheet: CSS that every document of the organisation is read and exported with — the reading view, comparisons, notices, PDF and Word files. The editor keeps the platform's look. While the stylesheet is empty, the platform's default look is used; a document's **Info** tab says which.

The stylesheet may set type, colour, background, borders, spacing and alignment on the platform's own elements and classes, and the page's size and margins with `@page`. A font is one of those installed, which the page lists, or a generic one — serif, sans-serif, monospace. Anything that would fetch from elsewhere — `@import`, `url()`, a font from the web — is refused, as are `content`, `display`, `visibility`, `position` and `opacity`, and a stylesheet over 100,000 bytes. *Apply* checks the whole text and lists each refusal with its line; nothing is applied until every line passes. Whatever the stylesheet says, the marks of a change and the approval line stay as the platform draws them. Every change to the stylesheet is recorded with its whole text.

Word files carry the stylesheet through Word's own styles — headings, paragraphs, quotations, callouts, marked roles, actions and terms, the title page. What a Word file cannot carry is listed on the page under *Not carried into Word files*.

## Trying a stylesheet first

*Export a sample PDF* and *Export a sample Word file* make an invented sample — every construct the editor accepts, a title page in the organisation's layout, an attachment list — with the stylesheet as it stands in the box, before it is applied. One sample is made at a time for the organisation, and each is kept for a day.
