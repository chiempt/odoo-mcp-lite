from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    mcp_lite_allow_registration = fields.Boolean(
        "Allow new AI apps to register", config_parameter="mcp_lite.allow_registration",
        help="Needed the first time claude.ai or ChatGPT connects. You can switch it off afterwards.")
    mcp_lite_blocked_models = fields.Char(
        "Hidden models", config_parameter="mcp_lite.blocked_models",
        help="Comma separated. AI assistants cannot read these. Use * as suffix, e.g. hr.*")
    mcp_lite_public_url = fields.Char(
        "Public URL", config_parameter="mcp_lite.public_url",
        help="The https address people use to open the ERP, e.g. https://erp.example.com. Leave empty to use web.base.url.")
    mcp_lite_kill_switch = fields.Boolean(
        "Pause all AI access", config_parameter="mcp_lite.kill_switch",
        help="Emergency stop. Every AI assistant gets an error until you switch this off. Connections stay in place.")
    mcp_lite_rate_limit = fields.Integer(
        "Calls per minute and user", config_parameter="mcp_lite.rate_limit", default=60,
        help="Tool calls above this in one minute are refused. 0 switches the limit off.")
    mcp_lite_endpoint = fields.Char("Connector URL", compute="_compute_mcp_lite_endpoint")

    @api.depends("mcp_lite_public_url")
    def _compute_mcp_lite_endpoint(self):
        for settings in self:
            base = (settings.mcp_lite_public_url or self.env["ir.config_parameter"].sudo().get_param("web.base.url") or "").rstrip("/")
            settings.mcp_lite_endpoint = base + "/mcp"
