# Repository documentation instructions

Maintain professional, accurate documentation from the actual source code,
configuration, tests, workflows, and existing docs. Do not invent features,
commands, integrations, metrics, screenshots, architecture, or supported
versions.

Keep `README.md` concise and put detailed material in relevant files under
`docs/`. Use GitHub Markdown, tables, callouts, and readable Mermaid diagrams
only when they clarify real behavior. For every command, state where it runs,
prerequisites, safe defaults, and useful validation. Clearly mark privileged or
destructive actions. Before finishing, inspect the repository, compare docs
with source/configuration, verify commands and links, and record evidence gaps
or manual validation needs. Never expose credentials, tokens, customer data,
or internal-only endpoints.

## Example data is always invented

This repository is public. Every name, address, path, identifier, hostname and
folder name in it must be made up.

Never copy example data out of a conversation, a terminal session, a screenshot,
or the user's own files into code, tests, comments or documentation, however
convenient the illustration. Real colleagues' names, a work address, an account
name, mailbox folder names and internal tracker references have each reached
this repository that way, and removing them meant rewriting published history.

Reach for obvious placeholders instead: `YOUR_WINDOWS_USER`, `example.com`,
`Lee, Sam`, `PROJ-4821`, `mailbox_-_Inbox`. This does not contradict the rule
against inventing features: describe only behaviour the code actually has, but
illustrate it with data that belongs to nobody.

Before finishing, search the tree for anything identifying — personal and
company names, addresses, account names, hostnames, addresses on the network,
tracker keys — and confirm it is absent from commits as well as from files.
