# Launch post drafts (copy-paste, NOT posted)

Rules followed per channel. Post each once, from a personal account, by hand. Do not cross-post the same text, do not ask for upvotes or stars, answer every comment honestly, and say plainly that you built it and that a paid edition exists.

Before posting: confirm the repo README GIF and the "Tested" line are still true, and that you can answer questions for the next 24 hours.

---

## 1. Show HN

Rules: title starts with "Show HN:", no marketing words or caps, link goes to the repo (not a landing page), the author comments first with context, never ask for votes. Post on a weekday morning US Pacific.

**Title:** Show HN: MCP Lite, a free read-only MCP server for Odoo, as one module

**URL:** https://github.com/chiempt/odoo-mcp-lite

**First comment:**

I build modules for Odoo and kept getting asked how to let Claude or ChatGPT look at company data without exporting spreadsheets or running a separate proxy. MCP Lite is the small answer: one Odoo module that serves a remote MCP endpoint at /mcp, with OAuth 2.1 (dynamic client registration + PKCE) built in, so you paste one URL into claude.ai, ChatGPT, Claude Code or Cursor and sign in as your normal Odoo user.

What it does: eight read-only tools (list models, fields, search, count, aggregate, report by period, find by name, suggest questions). It runs as the signed-in user, so Odoo access rights and record rules decide what is visible. There is no code path that writes.

The part I spent most time on is leak prevention. Filtering, sorting or grouping on a hidden field leaks it one yes/no at a time (for example a domain on user_ids.password). Every hop of a dotted path, every "any" sub-domain and every sort key is checked against the same visibility rules. The test suite has attack cases for these and runs on Odoo 17, 18 and 19 in Docker.

Honest limits: nothing here is tested against claude.ai or ChatGPT itself from a public host by CI (the protocol and OAuth flow are covered by the test suite, which drives the endpoints directly); it is not tested on Odoo.sh or behind multi-worker load balancers; what the assistant reads is sent to the AI provider, so connect only people who may share that data.

Licence is LGPL-3. I also sell a paid edition (writes with approval, per-group policies, audit log) on the Odoo app store; the free one is complete for read-only use and the README has a plain comparison table. Happy to take criticism of the security model, SECURITY.md lists what I know is weak.

---

## 2. Reddit r/Odoo

Rules to check first (r/Odoo): read the sidebar, self-promotion needs to be disclosed and low-volume; do not post if you have not participated in the sub. Use the "Showcase"/relevant flair if one exists. Disclose authorship in the first line.

**Title:** I made a free, open-source module that lets Claude/ChatGPT read your Odoo data (read-only, one URL, no proxy)

**Body:**

Disclosure: I made this, and I also sell a paid module in the same area.

MCP Lite is a free Odoo module (LGPL-3, 17/18/19) that exposes your database as a remote MCP server. Install it, copy the connector URL from Settings, add it as a custom connector in Claude (or ChatGPT developer mode, Claude Code, Cursor), sign in with your Odoo user and click Allow.

- Read-only: search, count, group/total, report by month, find records by name. No create/write/delete code at all.
- Runs as the user, so access rights and record rules apply.
- Passwords, tokens, API keys, binary fields are never returned or usable in filters.
- Per-user rate limit and a "pause all AI access" switch.

Needs a public https URL for the web clients (Claude Code and Cursor work on localhost). It has not been tested on Odoo.sh or behind several workers.

Repo: https://github.com/chiempt/odoo-mcp-lite

If you try it and something breaks, please open an issue; I would rather hear it than get a star.

---

## 3. Odoo community forum (odoo.com/forum)

Rules: use the "Odoo Apps"/relevant category, search first for existing threads, keep it factual, one post. Avoid links to the paid listing in the first post; mention the paid edition only in answers if asked.

**Title:** Open-source read-only MCP server module for Odoo 17-19 (use Claude/ChatGPT on your data)

**Body:**

Hello,

I published a small LGPL-3 module, mcp_lite, that turns an Odoo database into a remote MCP endpoint (/mcp) so an AI assistant can read data as the logged-in user. OAuth 2.1 with PKCE is inside the module, no external process.

Scope on purpose: read only (find models, fields, search, count, aggregate, report by period). Odoo ACLs and record rules apply. Sensitive fields are hidden, and cannot be used in domains, ordering or grouping (including dotted paths and "any" sub-domains), which is where simple implementations leak.

Install: copy mcp_lite to your addons path, install, open Settings, copy the connector URL. Details and a 5-minute guide for Claude Desktop / Claude Code are in the README.

Source and tests (Odoo 17/18/19 in Docker): https://github.com/chiempt/odoo-mcp-lite

Feedback on the security model is the most useful thing to me. Known gaps are listed in SECURITY.md.
