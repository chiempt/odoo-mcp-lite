# Security policy

MCP Lite exposes an ERP database to AI assistants, so we treat security reports as the top priority.

## Reporting a vulnerability

Email **support@bro3b.dev** with the subject `SECURITY: MCP Lite`. Please do not open a public issue for a
vulnerability. We aim to answer within 3 working days and to ship a fix or a mitigation within 14 days for
anything that exposes data or bypasses access rights. We credit reporters who want to be credited.

Useful in a report: Odoo version, module version, the MCP request you sent, and what you could read that you should not.

## Security model

* Every tool call runs as the signed-in user (`request.update_env(user=...)`). Access rights, record rules and
  multi-company rules of Odoo apply unchanged. The module never uses `sudo()` to read business data.
* **Read-only.** There are no tools that create, write, delete or run methods. Changes are not a setting; the code is not there.
* **Hidden fields.** Field names matching `password|passwd|secret|token|api_key|totp|private_key|signature_key|oauth_access`,
  binary fields and fields restricted by `groups=` are never returned and cannot be used in a domain, a sort order,
  a group-by or a measure. Dotted paths (`partner_id.user_ids.password`) and `any` / `not any` sub-domains are checked hop by hop.
  This closes the "filter or group by a hidden field, learn it one answer at a time" leak.
* **Hidden models.** System parameters, API keys, access rules, scheduled actions, 2FA devices and the module's own tokens
  are always blocked. Administrators can add more in Settings (`hr.*`, `account.payment`...).
* **OAuth 2.1.** Dynamic client registration, authorization code with S256 PKCE only, single-use codes, rotating refresh tokens.
  Tokens are stored as SHA-256 hashes. Redirect URIs must be https (or localhost, or a private app scheme) and are matched exactly.
  The consent page cannot be framed.
* **Limits.** Per-user rate limit (default 60 calls/minute), page size caps, a cap on domain size, and a **Pause all AI access** switch.
* **Logging.** A 7-day list of calls (who, which tool, which model, outcome). Call arguments and returned data are not stored.

## Known limits (honest list)

* Prompt injection: an assistant that reads a record can be steered by text inside it. Because MCP Lite is read-only
  and runs with the user's own rights, the worst case is that data the user could read is shown to the assistant's provider.
  Connect assistants only for users who may send that data to that provider, and hide sensitive models.
* Data you let the assistant read is sent to the AI provider (Anthropic, OpenAI...). That is how MCP works.
* There is no per-field or per-group policy in the free edition beyond the hidden-models list. Use Odoo's own groups and record rules.
* The module has no external dependencies, but it does not replace a reverse proxy, TLS, `dbfilter` and normal hardening.
