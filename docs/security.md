# Security and data handling

Xtoo is designed for one local user. It binds to `127.0.0.1`, accepts only
`localhost` and `127.0.0.1` host headers, sends a restrictive Content Security
Policy, disables public API documentation, and renders document previews as
text. Refresh requests require `X-Xtoo-Request: 1` and reject a different
origin.

These controls do not provide authentication or isolate Xtoo from another
process that can access the same localhost session. Do not expose it through a
tunnel, reverse proxy, LAN binding, or shared workstation service.

The SQLite index stores extracted text, filenames, and source paths. It is not
encrypted by Xtoo. The CLI sets a restrictive umask and the default index is
private to the Linux user, but host permissions, backups, and disk encryption
remain the organization's responsibility. Treat the index and WAL files as work
data. Xtoo reads source files and does not modify them; it does not execute
macros or embedded scripts. Script files such as `.ps1`, `.bat`, `.sh`, and
`.py` are indexed as text only. Scripts and configuration-as-code frequently
contain hostnames, connection strings, or credentials, and that text is copied
into the index; exclude those directories or narrow `folders` if the index
should not hold them.

Exported mail is treated the same way: `.msg` and `.eml` files are parsed as
data, attachments are never opened or decoded, and message text is copied into
the index. An export is a second unencrypted copy of mailbox content on disk.

Before indexing work content, confirm that local indexing, mail export, and
database storage are allowed by company policy. No Microsoft, Confluence, or AI credentials are
used by this release.
