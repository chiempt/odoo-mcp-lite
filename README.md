# MCP Lite: a free, read-only MCP server for your ERP

Connect **Claude, ChatGPT, Claude Code or Cursor** to your Odoo database (Community or Enterprise, 17 / 18 / 19)
with **one URL**. Sign-in uses OAuth 2.1 built into the module, so there is no proxy, no Node or Python process to run, and nothing to host.

* The assistant works **as the signed-in user**: Odoo access rights, record rules and multi-company rules apply.
* **Read-only**: find models, read fields, search, count and total records. It cannot create, change or delete anything.
* Passwords, tokens, API keys and binary fields are never returned, and cannot be used to filter or group either.
* Per-user **rate limit** and a **Pause all AI access** switch.
* LGPL-3.0, no external dependencies.

> Not affiliated with or endorsed by Odoo S.A. "Odoo" is a trademark of Odoo S.A.

## What it looks like

Ask Claude: *"How much did we invoice per month this year, and which five customers owe us the most?"*
It calls `list_models`, `get_fields`, `aggregate_records` and `search_records`, then answers from your live data.

## Install (5 minutes)

1. Copy the `mcp_lite` folder into your addons path (or clone this repo and add it to `addons_path`), restart Odoo,
   update the app list, install **MCP Lite**.
2. The address of your ERP must be a public **https** URL for claude.ai and ChatGPT
   (Claude Code and Cursor also work on `http://localhost`).
   * Set `web.base.url` (Settings > Technical > System Parameters), or fill in **Public URL** in MCP Lite > Configuration > Settings.
   * Behind nginx, Caddy or Traefik, start Odoo with `proxy_mode = True` and let the proxy send
     `X-Forwarded-Proto` and `X-Forwarded-Host`.
   * With several databases on one server, set `dbfilter` so the domain opens exactly one database.
3. Administrators can connect straight away. Add other people to the group **MCP Lite: can connect AI assistants**.
4. Copy the **Connector URL** from MCP Lite > Configuration > Settings (it is `https://your-erp/mcp`).

## Connect your assistant

| Client | How |
|---|---|
| **claude.ai** (web, desktop, mobile) | Settings > Connectors > Add custom connector, paste the URL, Connect, sign in to Odoo, click **Allow** |
| **ChatGPT** | Settings > Connectors > Advanced > Developer mode, add a custom connector with the URL and OAuth, sign in, **Allow** |
| **Claude Code** | `claude mcp add --transport http erp https://your-erp/mcp`, then `/mcp` to sign in |
| **Cursor / others** | Streamable HTTP with OAuth, or an Odoo API key (Preferences > Account Security) as `Authorization: Bearer <key>` |

(Client menus change often; if a label differs, look for "custom connector" or "remote MCP server".)

## Tools

| Tool | What it does |
|---|---|
| `whoami` | Your user, company, language, timezone |
| `list_models` | Find models by name or label (only those you may read) |
| `get_fields` | Fields of a model: type, label, relation, selection values |
| `search_records` | Search and read records, with domain, fields, order, paging (max 200 per call) |
| `count_records` | Count records for a domain |
| `aggregate_records` | Group and total like a pivot table (sum, avg, min, max, count) |

## Safety

Short version; the full model and the honest list of limits is in [SECURITY.md](SECURITY.md).

* Runs with the user's rights. No `sudo()` on business data.
* Hidden: system parameters, API keys, access rules, scheduled actions, 2FA devices, the module's own tokens. Add more models in Settings.
* Hidden fields cannot leak through filters, sorting, grouping, dotted paths or `any` sub-domains (covered by tests).
* **What you let the assistant read is sent to the AI provider.** Connect only users who may share that data, and hide sensitive models (`hr.*`, payroll, bank).
* Prompt injection: text inside a record can steer an assistant. Read-only plus the user's own rights limits the damage to disclosure, not changes.

## Limits

* Read-only on purpose. No approvals, no field policies per group, no audit log with arguments, no reports, no ready-made prompts, no setup self-check.
* The recent-activity list keeps 7 days and stores no arguments or results.
* Tested on Odoo 17, 18 and 19 with the official Docker images (see below). Not tested with Odoo.sh, Odoo Online (no custom modules there) or multi-worker setups behind a load balancer.
* Single database per domain.

## Free vs paid

| | **MCP Lite** (this repo, free) | **AI Connector** (paid, [apps.odoo.com](https://apps.odoo.com/apps/modules/19.0/ant_mcp_connector?utm_source=github&utm_medium=readme-table&utm_campaign=mcp-lite)) |
|---|---|---|
| OAuth 2.1 (DCR + PKCE), one URL | yes | yes |
| Read tools: search, count, aggregate, fields | yes | yes |
| Sensitive fields hidden everywhere | yes | yes |
| Per-user rate limit, pause switch | yes | yes |
| Hide models (global list) | yes | yes |
| Odoo API key as Bearer | yes | yes |
| Write tools (create, update, post, delete, run action) | **no** | yes |
| **Changes need a person's approval** (diff, approver group) | no | yes |
| **Access policies** per model, user group, hidden fields | no | yes |
| Audit log (90 days, with arguments) and **usage report** | 7-day list, no arguments | yes |
| **Ready-made prompts** (sales, accounting, stock, CRM) | no | yes |
| **Check my setup** (https, proxy, dbfilter, discovery) | no | yes |
| Support | GitHub issues, best effort | email |

If you only want to let an assistant look at your data, the free edition is enough and we mean that.
The paid one is for teams that let the assistant change data and need approvals, rules and a trail.
**The two cannot be installed in the same database** (both answer on `/mcp`); the installer refuses.
To move up, uninstall MCP Lite, install AI Connector, and connect again.

Paid edition: https://apps.odoo.com/apps/modules/19.0/ant_mcp_connector?utm_source=github&utm_medium=readme&utm_campaign=mcp-lite

## Tests

```bash
./scripts/test.sh 19    # also 18 and 17; needs Docker; starts a throwaway PostgreSQL and the official odoo image
```

CI runs the same script for 17, 18 and 19. The suite covers OAuth (PKCE, single-use codes, refresh rotation, revoke), the
tools, access rights, leak attempts through hidden fields, rate limit and the pause switch.

## License

[LGPL-3.0](LICENSE). Why LGPL and not AGPL: it is the licence Odoo itself uses, so companies can install it next to their own code
without legal review, which is the point of a free edition. Contributions are accepted under the same licence.
The paid AI Connector is separate, proprietary code.

Contributing: [CONTRIBUTING.md](CONTRIBUTING.md). Security: [SECURITY.md](SECURITY.md).
