# MCP Lite v0.2.0

Still read-only. Still one Odoo module, LGPL-3, no dependencies.

## New
- `period_report`: total a measure per day / week / month / quarter / year, with optional date range and a second split field. Revenue per month is now one call.
- `search_by_name`: find customers, products, employees the way the search box does, returns ids.
- `suggest_questions`: example questions for the apps installed here that the user may read (a plain tool, not an MCP prompt).
- README: 5-minute setup for Claude Desktop and Claude Code (browser and API-key flows), a real call replay (`docs/demo`), a plain Lite vs paid table.
- `scripts/demo.sh` and `scripts/render_gif.py` rebuild the replay from a local container.
- Launch post drafts in `docs/launch/`.

## Security
- New tools reuse the same checks: date field, split field, measure, filter and order are verified against the visibility rules (hidden fields, dotted paths, blocked models). Tests cover refusals.
- `search_by_name` honours the blocked-model list and access rights.

## Tested
11 tests pass on the official Docker images for Odoo 17, 18 and 19, and the same suite passes on the `odoo:20` nightly (2026-11-02 build). On 20 the test script converts the access file with `scripts/port20.py`; the module code itself now runs on 17 to 20 (`mcp_lite/compat.py` handles the renamed config-parameter API). Not tested end to end against live claude.ai or ChatGPT, Odoo.sh, or multi-worker deployments.

## Upgrade
Replace the `mcp_lite` folder and update the module. No data migration.
