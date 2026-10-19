# Settings, access history and the audit log

What the record answers for: an organisation's own limits, who could read a document on a past day, every act on the platform, and who last edited each line of a past version.

## Settings

Administration › *Settings* holds three of the organisation's own rules, for its administrators:

- **Attachment size cap** — the largest attachment the organisation accepts, in whole megabytes, from 1 to the platform's own upload maximum, which the page names. An upload is refused at whichever of the two is smaller.
- **Inactivity timeout** — how long an editor may stay idle before being asked *Are you still working?*, from 5 to 480 minutes. A reserved document is never released for inactivity.
- **Distinct approver check** — when on, nobody who accepted any of the runs since the previous edition may make the next one canonical: a second person stands behind every text that becomes authoritative.

*Apply* sets them; a value outside its bound is refused with the bound named. A change governs the next act and the next check of an idle editor; it releases or asks nothing by itself. Every change is recorded with the settings it changed.

## Access history

Administration › *Access history* answers who could read a document at a past moment, from the record alone. Choose a document and a day — the end of that day — or one of the document's editions, which answers at the moment it was approved.

The answer lists the groups linked to the document then, each with who linked it and when, its rights with who granted each, and its members that day with who added each. A membership the organisation had blocked is listed as blocked and not counted; a person's own block of their account never shows here. A line says when the document did not exist yet, was archived — no group could read it — when the organisation was blocked, or when no canonical edition existed, so *view canonical* reached nothing. Administrators read every document and are not listed. Below, every change to access that led there, the newest 200.

*Any document* lists every change to access in the organisation up to the chosen day — links, rights, members, memberships blocked or made administrators, documents archived and restored — the newest 200. People are named by their address.

## The audit log

Administration › *Audit log*, for platform administrators on the platform's own address, lists every recorded act on the platform, newest first: when, who, whether a person, the system or an agent acted, in which organisation, the act's code, its object and what it changed. Filter by organisation or the platform itself, by the kind of actor — a person, the system or an agent — by the start of an act's code — `document.` gives every act on documents — and by a period. The page shows the newest 200 that match and says so; narrow the filters to reach older ones.

## Edit authors on a past version

*Show edit authors* — on *Pending edits* and on a past version's page alike — names who last edited each line, on hovering it. A past version's edit authors are worked out when first asked for: the page says so and shows the text without them; reload it in a moment. They are kept for a day.
