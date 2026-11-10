# Contributing

Thanks for helping. Keep this module small, read-only and safe.

## Scope

In scope: bug fixes, Odoo 17/18/19 compatibility, better error messages for the AI client, MCP protocol conformance,
docs, tests, hardening of read tools.

Out of scope for this repository: tools that change data, per-group policies, approvals, audit reports.
These live in the paid edition. Please do not send pull requests for them; we would have to decline.
A security fix is always welcome, whatever it touches.

## Development

```bash
./scripts/test.sh 19      # runs the test suite in docker against odoo:19 (also 18, 17)
```

* One module: `mcp_lite/`. Tests: `mcp_lite/tests/test_mcp.py` (HttpCase, talks to `/mcp` like a real client).
* Every change that touches a tool needs a test, and a leak test if it touches field or domain handling.
* Code must work on 17, 18 and 19. The only per-version difference today is `<list>` vs `<tree>` in views
  (the test script converts for 17). Keep it that way.
* Style: PEP 8, no new dependencies, no `sudo()` on business data.

## Pull requests

Describe the problem, show the test that fails before and passes after. By contributing you agree your work is
licensed under LGPL-3.0, the same as the project. Please sign off your commits (`git commit -s`).
