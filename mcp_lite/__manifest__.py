{
    "name": "MCP Lite - Free Read-only AI Connector for Claude, ChatGPT and Cursor",
    "version": "19.0.1.1.0",
    "category": "Productivity",
    "summary": "Open source MCP server for your ERP: built-in OAuth, read-only tools, rate limit and kill switch. No extra server.",
    "description": """
MCP Lite turns your database into a remote MCP server at /mcp. Paste the URL
into claude.ai, ChatGPT (developer mode), Claude Code or Cursor, sign in with
your normal user and click Allow. OAuth 2.1 with dynamic client registration and
PKCE is built in, so there is no proxy and no extra process.

Read-only by design: the assistant can find models, read fields, search, count
and total records, as the signed-in user. Access rights and record rules apply.
Passwords, tokens and keys are never returned. There is a per-user rate limit
and an emergency switch. For approved changes, access policies and audit
reports see the paid AI Connector on apps.odoo.com.
""",
    "author": "3B",
    "maintainer": "3B",
    "website": "https://github.com/chiempt/odoo-mcp-lite",
    "support": "support@bro3b.dev",
    "license": "LGPL-3",
    "depends": ["base_setup", "mail"],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/config.xml",
        "views/mcp_views.xml",
        "views/res_config_settings_views.xml",
        "views/templates.xml",
    ],
    "images": [],
    "installable": True,
    "application": True,
    "auto_install": False,
    "pre_init_hook": "_pre_init_check",
    "uninstall_hook": "_uninstall_hook",
}
