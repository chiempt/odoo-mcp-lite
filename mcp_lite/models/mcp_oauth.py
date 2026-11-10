import base64
import hashlib
import secrets
from datetime import timedelta

from odoo import api, fields, models

ACCESS_TTL = timedelta(hours=1)
REFRESH_TTL = timedelta(days=30)
CODE_TTL = timedelta(minutes=10)


def _hash(value):
    return hashlib.sha256((value or "").encode()).hexdigest()


def _new_secret(prefix):
    return prefix + secrets.token_urlsafe(32)


class McpClient(models.Model):
    _name = "mcp_lite.client"
    _description = "MCP Lite: registered client"
    _order = "create_date desc"

    name = fields.Char(required=True, default="AI client")
    client_id = fields.Char(required=True, index=True, readonly=True, copy=False)
    secret_hash = fields.Char(readonly=True, copy=False, groups="base.group_system")
    redirect_uris = fields.Text(readonly=True, help="One redirect URI per line.")
    token_ids = fields.One2many("mcp_lite.token", "client_id")
    active_token_count = fields.Integer(compute="_compute_active_token_count")

    if hasattr(models, "Constraint"):  # Odoo 19+
        _client_id_uniq = models.Constraint("unique(client_id)", "Client ID must be unique.")
    else:
        _sql_constraints = [("client_id_uniq", "unique(client_id)", "Client ID must be unique.")]

    def _compute_active_token_count(self):
        now = fields.Datetime.now()
        for client in self:
            client.active_token_count = len(client.token_ids.filtered(lambda t: t.refresh_expires_at and t.refresh_expires_at > now))

    @api.model
    def _mcp_register(self, client_name, redirect_uris, confidential=False):
        values = {
            "name": (client_name or "AI client")[:128],
            "client_id": _new_secret("mcpc_"),
            "redirect_uris": "\n".join(redirect_uris),
        }
        secret = None
        if confidential:
            secret = _new_secret("mcps_")
            values["secret_hash"] = _hash(secret)
        return self.sudo().create(values), secret

    def _redirect_uri_list(self):
        self.ensure_one()
        return [uri.strip() for uri in (self.redirect_uris or "").splitlines() if uri.strip()]

    def _check_secret(self, secret):
        self.ensure_one()
        stored = self.sudo().secret_hash
        if not stored:
            return True  # public client (PKCE only)
        return bool(secret) and secrets.compare_digest(stored, _hash(secret))

    def action_revoke(self):
        self.sudo().token_ids.unlink()


class McpAuthCode(models.Model):
    _name = "mcp_lite.code"
    _description = "MCP Lite: authorization code"

    code_hash = fields.Char(required=True, index=True)
    client_id = fields.Many2one("mcp_lite.client", required=True, ondelete="cascade")
    user_id = fields.Many2one("res.users", required=True, ondelete="cascade")
    redirect_uri = fields.Char(required=True)
    code_challenge = fields.Char(required=True)
    resource = fields.Char()
    expires_at = fields.Datetime(required=True)

    @api.model
    def _issue(self, client, user, redirect_uri, code_challenge, resource):
        code = _new_secret("mcpa_")
        self.sudo().create({
            "code_hash": _hash(code),
            "client_id": client.id,
            "user_id": user.id,
            "redirect_uri": redirect_uri,
            "code_challenge": code_challenge,
            "resource": resource or False,
            "expires_at": fields.Datetime.now() + CODE_TTL,
        })
        return code

    @api.model
    def _consume(self, code, client, redirect_uri, code_verifier):
        """Return the user for a valid code, or None. A code works once."""
        record = self.sudo().search([("code_hash", "=", _hash(code))], limit=1)
        if not record:
            return None
        valid = (
            record.client_id == client
            and record.redirect_uri == redirect_uri
            and record.expires_at > fields.Datetime.now()
            and code_verifier
            and secrets.compare_digest(record.code_challenge, _pkce_s256(code_verifier))
        )
        user = record.user_id
        record.unlink()
        return user if valid else None

    @api.autovacuum
    def _gc_expired(self):
        self.sudo().search([("expires_at", "<", fields.Datetime.now())]).unlink()


def _pkce_s256(verifier):
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


class McpToken(models.Model):
    _name = "mcp_lite.token"
    _description = "MCP Lite: connection"
    _order = "last_used_at desc, id desc"

    client_id = fields.Many2one("mcp_lite.client", required=True, ondelete="cascade", readonly=True)
    user_id = fields.Many2one("res.users", required=True, ondelete="cascade", readonly=True, index=True)
    access_hash = fields.Char(index=True, readonly=True, groups="base.group_system")
    refresh_hash = fields.Char(index=True, readonly=True, groups="base.group_system")
    access_expires_at = fields.Datetime(readonly=True)
    refresh_expires_at = fields.Datetime(readonly=True)
    last_used_at = fields.Datetime(readonly=True)

    @api.model
    def _issue(self, client, user, previous=None):
        access = _new_secret("mcpt_")
        refresh = _new_secret("mcpr_")
        now = fields.Datetime.now()
        values = {
            "client_id": client.id,
            "user_id": user.id,
            "access_hash": _hash(access),
            "refresh_hash": _hash(refresh),
            "access_expires_at": now + ACCESS_TTL,
            "refresh_expires_at": now + REFRESH_TTL,
        }
        if previous:
            previous.sudo().write(values)
        else:
            self.sudo().create(values)
        return {
            "access_token": access,
            "token_type": "Bearer",
            "expires_in": int(ACCESS_TTL.total_seconds()),
            "refresh_token": refresh,
            "scope": "odoo",
        }

    @api.model
    def _find_by_refresh(self, refresh_token, client):
        token = self.sudo().search([("refresh_hash", "=", _hash(refresh_token)), ("client_id", "=", client.id)], limit=1)
        if token and token.refresh_expires_at > fields.Datetime.now() and token.user_id.active:
            return token
        return None

    @api.model
    def _user_for_access(self, access_token):
        token = self.sudo().search([("access_hash", "=", _hash(access_token))], limit=1)
        if not token or token.access_expires_at <= fields.Datetime.now() or not token.user_id.active:
            return None, None
        token.last_used_at = fields.Datetime.now()
        return token.user_id, token.client_id

    @api.model
    def _revoke(self, secret):
        digest = _hash(secret)
        self.sudo().search(["|", ("access_hash", "=", digest), ("refresh_hash", "=", digest)]).unlink()

    def action_revoke(self):
        self.sudo().unlink()

    @api.autovacuum
    def _gc_expired(self):
        self.sudo().search([("refresh_expires_at", "<", fields.Datetime.now())]).unlink()


class McpLog(models.Model):
    """Short call history. It feeds the rate limit and the 'Recent activity' list.

    Lite keeps 7 days, stores no call arguments and no returned data. The paid
    edition keeps a longer, searchable audit log with arguments and a usage report."""
    _name = "mcp_lite.log"
    _description = "MCP Lite: recent activity"
    _order = "id desc"

    user_id = fields.Many2one("res.users", readonly=True, ondelete="set null", index=True)
    client_name = fields.Char(readonly=True)
    tool = fields.Char(readonly=True, index=True)
    model = fields.Char(readonly=True, index=True)
    state = fields.Selection([("ok", "OK"), ("error", "Error"), ("denied", "Denied"), ("limited", "Rate limited")], readonly=True)
    message = fields.Char(readonly=True)

    @api.model
    def _record(self, user, client_name, tool, arguments, state, message):
        model = arguments.get("model") if isinstance(arguments, dict) else None
        self.sudo().create({
            "user_id": user.id if user else False,
            "client_name": client_name,
            "tool": tool,
            "model": model if isinstance(model, str) else False,
            "state": state,
            "message": (message or "")[:200] if state != "ok" else False,
        })

    @api.model
    def _rate_limited(self, user):
        """An error message when the user is over the per-minute limit, else False."""
        raw = self.env["ir.config_parameter"].sudo().get_param("mcp_lite.rate_limit", "60")
        limit = int(raw) if str(raw).lstrip("-").isdigit() else 60
        if limit <= 0:
            return False
        since = fields.Datetime.now() - timedelta(minutes=1)
        used = self.sudo().search_count([
            ("user_id", "=", user.id), ("create_date", ">=", since), ("state", "!=", "limited")])
        if used >= limit:
            return (f"Rate limit reached ({limit} tool calls per minute for this user). "
                    "Wait a minute, then continue with fewer calls.")
        return False

    @api.autovacuum
    def _gc_old(self):
        self.sudo().search([("create_date", "<", fields.Datetime.now() - timedelta(days=7))]).unlink()
