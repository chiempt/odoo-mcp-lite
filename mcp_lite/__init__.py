from . import controllers, models


def _pre_init_check(env):
    """Both editions answer on /mcp, so they cannot run in the same database."""
    paid = env["ir.module.module"].sudo().search([("name", "=", "ant_mcp_connector"), ("state", "=", "installed")])
    if paid:
        from odoo.exceptions import UserError
        raise UserError(
            "The paid AI Connector (ant_mcp_connector) is installed in this database. It already includes "
            "everything in MCP Lite and uses the same /mcp address, so MCP Lite cannot be installed next to it.")


def _uninstall_hook(env):
    env["ir.config_parameter"].sudo().search([("key", "=like", "mcp_lite.%")]).unlink()
