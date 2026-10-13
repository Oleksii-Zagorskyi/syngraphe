# Mail

The platform sends each notification as an email from a **sending address**: the organisation's own, set by its administrators in Administration › *Sending address*, or else the platform's, set by a platform administrator in Administration › *Mail and outbox*. Without either, no email is sent and notifications stay in the platform.

**The settings.** The address the email leaves from and an optional *sender's name*; the **server** and **port** of the mail server that carries it; the **connection** — *STARTTLS* (usually port 587), *TLS* (usually 465) or *unencrypted*; and a **user name** and **password** when the server asks you to sign in. The password is never shown again: leave its field empty to keep it, and type it again whenever you change the server, the port, the connection or the user name. Signing in over an unencrypted connection is allowed only to a server on the same machine. *Apply settings* puts them in use; *Remove* stops sending from this address.

**Send a test email** sends a message from the address to itself and reports each step — **connection**, **sign-in** and **sending** — so a failure says where it happened. One test runs at a time.

**The outbox**, below the settings, lists the newest 200 emails with each one's recipient, state and attempts: *queued*, *sent*, or *failed*. A refused email is tried again five minutes later; after the third refusal it is *failed* and the administrators are told in the platform. The reason beside a row says what went wrong — the server's own answer, a server that could not be reached, a certificate or encryption the server would not accept. An email about a document its recipient may no longer open is not sent. With no sending address left, or a password the mail key cannot open, an email waits — its attempts untouched — until the address or the password is set again.

**For an organisation's own address**, email is delivered reliably only when the domain's DNS records — SPF and DKIM — allow the server to send for it; whoever runs the domain sets them.
