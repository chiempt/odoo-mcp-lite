"""MCP over Streamable HTTP at /mcp, plus a small OAuth 2.1 authorization
server (dynamic client registration + PKCE) so claude.ai, ChatGPT and other
remote MCP clients can connect by pasting one URL. No external process."""
import base64
import json
import logging
import time
from urllib.parse import urlencode, urlparse

from odoo import http
from odoo.http import request

from ..models.mcp_tools import McpToolError, tool_error_message

_logger = logging.getLogger(__name__)

PROTOCOL_VERSIONS = ["2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05"]
SERVER_NAME = "MCP Lite"
SERVER_VERSION = "1.0.0"
GROUP = "mcp_lite.group_mcp_user"
INSTRUCTIONS = (
    "You are connected read-only to an ERP database as the signed-in user; you see only what that user may see. "
    "Workflow: list_models to find a model, get_fields to learn its columns, then search_records, "
    "count_records or aggregate_records. Domains are Odoo domains as JSON lists, e.g. "
    "[[\"state\",\"in\",[\"sale\",\"done\"]],[\"date_order\",\">=\",\"2026-01-01\"]]. "
    "Amounts are in the company currency unless a currency field says otherwise. "
    "This connector cannot create, change or delete anything: if the user asks for a change, tell them to do it in the ERP."
)


def _json_response(payload, status=200, headers=None):
    body = json.dumps(payload, default=str, ensure_ascii=False)
    all_headers = [("Content-Type", "application/json"), ("Cache-Control", "no-store")]
    all_headers += list((headers or {}).items())
    return request.make_response(body, headers=all_headers, status=status)


def _base_url():
    icp = request.env["ir.config_parameter"].sudo()
    url = icp.get_param("mcp_lite.public_url") or icp.get_param("web.base.url") or request.httprequest.host_url
    return url.rstrip("/")


def _valid_redirect_uri(uri):
    try:
        parsed = urlparse(uri)
    except ValueError:
        return False
    if parsed.fragment:
        return False
    if parsed.scheme == "https" and parsed.netloc:
        return True
    if parsed.scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1", "::1"):
        return True
    # native apps use private URI schemes (cursor://, vscode://, com.example.app:/)
    return parsed.scheme in ("cursor", "vscode", "claude") or (bool(parsed.scheme) and "." in parsed.scheme)


def _in_group(user):
    return user.has_group(GROUP)


class McpController(http.Controller):

    # ------------------------------------------------------------------ discovery
    def _protected_resource(self):
        base = _base_url()
        return _json_response({
            "resource": base + "/mcp",
            "authorization_servers": [base],
            "bearer_methods_supported": ["header"],
            "resource_name": SERVER_NAME,
        })

    @http.route(["/.well-known/oauth-protected-resource", "/.well-known/oauth-protected-resource/mcp"],
                type="http", auth="none", methods=["GET", "OPTIONS"], csrf=False, cors="*", save_session=False)
    def protected_resource(self, **kw):
        return self._protected_resource()

    @http.route(["/.well-known/oauth-authorization-server", "/.well-known/oauth-authorization-server/mcp",
                 "/.well-known/openid-configuration", "/.well-known/openid-configuration/mcp"],
                type="http", auth="none", methods=["GET", "OPTIONS"], csrf=False, cors="*", save_session=False)
    def authorization_server(self, **kw):
        base = _base_url()
        return _json_response({
            "issuer": base,
            "authorization_endpoint": base + "/mcp/oauth/authorize",
            "token_endpoint": base + "/mcp/oauth/token",
            "registration_endpoint": base + "/mcp/oauth/register",
            "revocation_endpoint": base + "/mcp/oauth/revoke",
            "authorization_response_iss_parameter_supported": True,
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": ["none", "client_secret_post", "client_secret_basic"],
            "scopes_supported": ["odoo"],
        })

    # ------------------------------------------------------------------ registration (RFC 7591)
    @http.route("/mcp/oauth/register", type="http", auth="none", methods=["POST", "OPTIONS"],
                csrf=False, cors="*", save_session=False, readonly=False)
    def register(self, **kw):
        if request.env["ir.config_parameter"].sudo().get_param("mcp_lite.allow_registration", "True") != "True":
            return _json_response({"error": "access_denied",
                                   "error_description": "New AI apps are switched off in MCP Lite settings."}, 403)
        try:
            data = json.loads(request.httprequest.get_data() or b"{}")
        except ValueError:
            return _json_response({"error": "invalid_client_metadata", "error_description": "Body must be JSON."}, 400)
        uris = data.get("redirect_uris") or []
        if not isinstance(uris, list) or not uris or not all(isinstance(u, str) and _valid_redirect_uri(u) for u in uris):
            return _json_response({"error": "invalid_redirect_uri",
                                   "error_description": "redirect_uris must be https URLs (or http on localhost)."}, 400)
        method = data.get("token_endpoint_auth_method") or "none"
        if method not in ("none", "client_secret_post", "client_secret_basic"):
            method = "none"
        client, secret = request.env["mcp_lite.client"]._mcp_register(
            data.get("client_name"), uris, confidential=method != "none")
        payload = {
            "client_id": client.client_id,
            "client_id_issued_at": int(time.time()),
            "client_name": client.name,
            "redirect_uris": uris,
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": method,
        }
        if secret:
            payload.update(client_secret=secret, client_secret_expires_at=0)
        return _json_response(payload, 201)

    # ------------------------------------------------------------------ authorize
    def _authorize_error(self, message):
        return request.render("mcp_lite.mcp_lite_consent_error", {"message": message, "disable_footer": True})

    def _check_authorize(self, params):
        client = request.env["mcp_lite.client"].sudo().search([("client_id", "=", params.get("client_id") or "")], limit=1)
        if not client:
            return None, "This AI app is not registered with this database. Remove the connector in your AI app and add it again."
        if params.get("redirect_uri") not in client._redirect_uri_list():
            return None, "The return address of this AI app does not match its registration."
        return client, None

    @http.route("/mcp/oauth/authorize", type="http", auth="user", methods=["GET"], website=False)
    def authorize(self, **params):
        client, error = self._check_authorize(params)
        if error:
            return self._authorize_error(error)
        redirect_uri = params["redirect_uri"]
        if params.get("response_type") != "code" or not params.get("code_challenge") \
                or params.get("code_challenge_method", "plain") != "S256":
            return request.redirect(redirect_uri + ("&" if "?" in redirect_uri else "?") + urlencode({
                "error": "invalid_request",
                "error_description": "response_type=code with a S256 code_challenge is required",
                **({"state": params["state"]} if params.get("state") else {}),
            }), local=False)
        user = request.env.user
        if not _in_group(user):
            return self._authorize_error(
                "Your user is not allowed to connect AI assistants. Ask an administrator to add you to "
                "'MCP Lite: can connect AI assistants'.")
        response = request.render("mcp_lite.mcp_lite_consent", {
            "client": client,
            "user": user,
            "params": {k: params.get(k) or "" for k in ("client_id", "redirect_uri", "state", "code_challenge", "resource", "scope")},
            "disable_footer": True,
        })
        # the consent page must never be framed (clickjacking)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = "frame-ancestors 'none'"
        return response

    @http.route("/mcp/oauth/approve", type="http", auth="user", methods=["POST"], website=False)
    def approve(self, **params):
        client, error = self._check_authorize(params)
        if error:
            return self._authorize_error(error)
        redirect_uri = params["redirect_uri"]
        query = {}
        if params.get("decision") == "allow" and _in_group(request.env.user) and params.get("code_challenge"):
            query["code"] = request.env["mcp_lite.code"]._issue(
                client, request.env.user, redirect_uri, params["code_challenge"], params.get("resource"))
        else:
            query.update(error="access_denied", error_description="The user declined the connection.")
        if params.get("state"):
            query["state"] = params["state"]
        query["iss"] = _base_url()
        return request.redirect(redirect_uri + ("&" if "?" in redirect_uri else "?") + urlencode(query), local=False)

    # ------------------------------------------------------------------ token
    def _token_error(self, error, description, status=400):
        return _json_response({"error": error, "error_description": description}, status)

    @http.route("/mcp/oauth/token", type="http", auth="none", methods=["POST", "OPTIONS"],
                csrf=False, cors="*", save_session=False, readonly=False)
    def token(self, **params):
        client_id, client_secret = params.get("client_id"), params.get("client_secret")
        auth = request.httprequest.headers.get("Authorization", "")
        if auth.lower().startswith("basic "):
            try:
                client_id, _, client_secret = base64.b64decode(auth[6:]).decode().partition(":")
            except ValueError:
                return self._token_error("invalid_client", "Malformed Basic credentials.", 401)
        client = request.env["mcp_lite.client"].sudo().search([("client_id", "=", client_id or "")], limit=1)
        if not client or not client._check_secret(client_secret):
            return self._token_error("invalid_client", "Unknown client or wrong secret.", 401)
        grant = params.get("grant_type")
        tokens = request.env["mcp_lite.token"]
        if grant == "authorization_code":
            user = request.env["mcp_lite.code"]._consume(
                params.get("code") or "", client, params.get("redirect_uri") or "", params.get("code_verifier") or "")
            if not user or not user.active or not _in_group(user):
                return self._token_error("invalid_grant", "The code is invalid, expired or already used.")
            return _json_response(tokens._issue(client, user))
        if grant == "refresh_token":
            token = tokens._find_by_refresh(params.get("refresh_token") or "", client)
            if not token or not _in_group(token.user_id):
                return self._token_error("invalid_grant", "The refresh token is invalid or expired.")
            return _json_response(tokens._issue(client, token.user_id, previous=token))
        return self._token_error("unsupported_grant_type", "Use authorization_code or refresh_token.")

    @http.route("/mcp/oauth/revoke", type="http", auth="none", methods=["POST", "OPTIONS"],
                csrf=False, cors="*", save_session=False, readonly=False)
    def revoke(self, **params):
        """RFC 7009: always 200, whether or not the token existed."""
        request.env["mcp_lite.token"]._revoke(params.get("token") or "")
        return _json_response({})

    # ------------------------------------------------------------------ MCP endpoint
    def _unauthorized(self, description="Sign in required"):
        meta = _base_url() + "/.well-known/oauth-protected-resource"
        return _json_response(
            {"jsonrpc": "2.0", "id": None, "error": {"code": -32001, "message": description}}, 401,
            {"WWW-Authenticate": f'Bearer resource_metadata="{meta}", error="invalid_token", error_description="{description}"'})

    def _authenticate(self):
        header = request.httprequest.headers.get("Authorization", "")
        if not header.lower().startswith("bearer "):
            return None, None
        secret = header[7:].strip()
        user, client = request.env["mcp_lite.token"]._user_for_access(secret)
        if user:
            return user, client.name
        # Odoo API key (Preferences > Account Security), handy for Claude Code, Cursor, n8n...
        uid = request.env["res.users.apikeys"].sudo()._check_credentials(scope="rpc", key=secret)
        if uid:
            return request.env["res.users"].sudo().browse(uid), "API key"
        return None, None

    @http.route("/mcp", type="http", auth="none", methods=["GET", "POST", "DELETE", "OPTIONS"],
                csrf=False, cors="*", save_session=False, readonly=False)
    def mcp(self, **kw):
        method = request.httprequest.method
        user, client_name = self._authenticate()
        if not user:
            return self._unauthorized()
        if not _in_group(user):
            return self._unauthorized("This user is not allowed to connect AI assistants")
        if request.env["ir.config_parameter"].sudo().get_param("mcp_lite.kill_switch") == "True":
            return _json_response({"jsonrpc": "2.0", "id": None, "error": {
                "code": -32000, "message": "AI access to this database is paused by an administrator."}}, 503)
        if method == "DELETE":
            return request.make_response("", status=204)
        if method == "GET":  # no server-initiated stream
            return request.make_response("", headers=[("Allow", "POST, DELETE")], status=405)
        try:
            message = json.loads(request.httprequest.get_data() or b"")
        except ValueError:
            return _json_response({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}, 400)

        request.update_env(user=user.id)
        request.update_context(**request.env["res.users"].context_get())
        if isinstance(message, list):
            replies = [r for r in (self._handle(m, user, client_name) for m in message) if r is not None]
            return _json_response(replies) if replies else request.make_response("", status=202)
        reply = self._handle(message, user, client_name)
        if reply is None:
            return request.make_response("", status=202)
        return _json_response(reply)

    def _handle(self, message, user, client_name):
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or "method" not in message:
            return {"jsonrpc": "2.0", "id": message.get("id") if isinstance(message, dict) else None,
                    "error": {"code": -32600, "message": "Invalid Request"}}
        msg_id = message.get("id")
        if msg_id is None:  # notification
            return None
        method, params = message["method"], message.get("params") or {}
        try:
            result = self._dispatch(method, params, user, client_name)
        except _RpcError as err:
            return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": err.code, "message": err.message}}
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

    def _dispatch(self, method, params, user, client_name):
        server = request.env["mcp_lite.server"]
        if method == "initialize":
            asked = params.get("protocolVersion")
            return {
                "protocolVersion": asked if asked in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0],
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                "instructions": INSTRUCTIONS + f" Database: {request.env.cr.dbname}. User: {user.name}. "
                                               f"Company: {request.env.company.name} ({request.env.company.currency_id.name}).",
            }
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": server._tool_specs()}
        if method == "tools/call":
            return self._call_tool(server, params.get("name"), params.get("arguments") or {}, user, client_name)
        if method == "resources/list":
            return {"resources": []}
        raise _RpcError(-32601, f"Method not found: {method}")

    def _call_tool(self, server, name, arguments, user, client_name):
        limited = request.env["mcp_lite.log"]._rate_limited(user)
        if limited:
            request.env["mcp_lite.log"]._record(user, client_name, name, arguments, "limited", limited)
            return {"content": [{"type": "text", "text": limited}], "isError": True}
        state, text = "ok", ""
        try:
            with request.env.cr.savepoint():
                result = server._call_tool(name, arguments)
            text = json.dumps(result, default=str, ensure_ascii=False)
        except Exception as exc:  # noqa: BLE001 - every failure goes back to the AI as a tool error
            state = "denied" if "not allowed" in str(exc) or "blocked" in str(exc) or "not available" in str(exc) else "error"
            text = tool_error_message(exc)
            if not isinstance(exc, McpToolError):
                _logger.info("MCP Lite tool %s failed: %s", name, text)
        request.env["mcp_lite.log"]._record(user, client_name, name, arguments, state, text)
        if state != "ok":
            return {"content": [{"type": "text", "text": text}], "isError": True}
        return {"content": [{"type": "text", "text": text}]}


class _RpcError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code, self.message = code, message
