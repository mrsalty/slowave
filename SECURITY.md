# Security Policy

## Reporting a Vulnerability

Please **do not** open a public GitHub issue for security-sensitive reports.

Security-sensitive examples include:

- memory data exposure or leakage between scopes
- unsafe file permissions on the database or config files
- path traversal in file handling
- prompt or context injection via stored memory
- accidental logging of private memory content
- unsafe default storage behavior

### How to report

Open a **minimal public issue** stating only that you found a security-sensitive problem and request a private contact channel. A maintainer will respond with a way to share details privately.

Alternatively, use [GitHub's private vulnerability reporting](https://github.com/mrsalty/slowave/security/advisories/new) if you prefer a fully private channel from the start.

## Scope

Slowave stores all memory locally in a plain SQLite file (`~/.slowave/slowave.db`). The file is unencrypted. If you store sensitive information, protect it using OS-level permissions or full-disk encryption — this is by design and documented in the README.

The MCP server listens on localhost only (`127.0.0.1`) and is not intended to be exposed to a network.

## Response

This is an early-stage open source project maintained by a small team. We will acknowledge reports promptly and aim to ship fixes as quickly as the severity warrants.
