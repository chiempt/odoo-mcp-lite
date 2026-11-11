import base64
import hashlib
import json
import secrets
from urllib.parse import parse_qs, urlparse

from odoo.addons.mcp_lite.compat import set_param
from odoo.tests import HttpCase, tagged

REDIRECT = "https://claude.ai/api/mcp/auth_callback"


def _challenge(verifier):
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")


@tagged("post_install", "-at_install")
class TestMcpConnector(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.icp = cls.env["ir.config_parameter"].sudo()
        set_param(cls.icp, "mcp_lite.public_url", "")
        users = cls.env["res.users"].with_context(no_reset_password=True)
        groups_field = "group_ids" if "group_ids" in users._fields else "groups_id"
        cls.group = cls.env.ref("mcp_lite.group_mcp_user")
        cls.basic = users.create({
            "name": "MCP Basic", "login": "mcp_basic", "password": "mcp_basic_pw_123", "email": "mcp_basic@example.com",
            groups_field: [(6, 0, [cls.env.ref("base.group_user").id, cls.env.ref("base.group_partner_manager").id, cls.group.id])],
        })
        cls.outsider = users.create({
            "name": "MCP Outsider", "login": "mcp_outsider", "password": "mcp_outsider_pw_123",
            groups_field: [(6, 0, [cls.env.ref("base.group_user").id])],
        })
        cls.partner = cls.env["res.partner"].create({"name": "Azure MCP Interior", "email": "azure@mcp.example"})

    # ------------------------------------------------------------- helpers
    def _post_json(self, url, payload, token=None):
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
        if token:
            headers["Authorization"] = "Bearer " + token
        return self.url_open(url, data=json.dumps(payload), headers=headers)

    def _rpc(self, token, method, params=None, msg_id=1):
        res = self._post_json("/mcp", {"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params or {}}, token)
        self.assertEqual(res.status_code, 200, res.text)
        return res.json()

    def _tool(self, token, tool_name, **arguments):
        result = self._rpc(token, "tools/call", {"name": tool_name, "arguments": arguments})["result"]
        return result.get("isError", False), result["content"][0]["text"]

    def _register(self):
        res = self._post_json("/mcp/oauth/register", {"client_name": "Claude", "redirect_uris": [REDIRECT]})
        self.assertEqual(res.status_code, 201, res.text)
        return res.json()["client_id"]

    def _oauth_token(self, login, password):
        client_id = self._register()
        verifier = secrets.token_urlsafe(48)
        self.authenticate(login, password)
        query = {
            "response_type": "code", "client_id": client_id, "redirect_uri": REDIRECT,
            "code_challenge": _challenge(verifier), "code_challenge_method": "S256", "state": "xyz",
            "resource": self.base_url() + "/mcp",
        }
        page = self.url_open("/mcp/oauth/authorize?" + "&".join(f"{k}={v}" for k, v in query.items()))
        self.assertEqual(page.status_code, 200)
        self.assertIn("Allow", page.text)
        self.assertEqual(page.headers.get("X-Frame-Options"), "DENY")
        csrf = page.text.split('name="csrf_token" value="')[1].split('"')[0]
        form = {k: v for k, v in query.items() if k not in ("response_type", "code_challenge_method")}
        form.update(csrf_token=csrf, decision="allow")
        res = self.url_open("/mcp/oauth/approve", data=form, allow_redirects=False)
        self.assertIn(res.status_code, (302, 303))
        location = urlparse(res.headers["Location"])
        self.assertTrue(res.headers["Location"].startswith(REDIRECT))
        params = parse_qs(location.query)
        self.assertEqual(params["state"], ["xyz"])
        self.logout()
        token = self.url_open("/mcp/oauth/token", data={
            "grant_type": "authorization_code", "code": params["code"][0], "redirect_uri": REDIRECT,
            "client_id": client_id, "code_verifier": verifier,
        })
        self.assertEqual(token.status_code, 200, token.text)
        return client_id, token.json(), params["code"][0], verifier

    # ------------------------------------------------------------- discovery
    def test_discovery_and_401(self):
        meta = self.url_open("/.well-known/oauth-protected-resource").json()
        self.assertTrue(meta["resource"].endswith("/mcp"))
        server = self.url_open("/.well-known/oauth-authorization-server").json()
        self.assertEqual(server["code_challenge_methods_supported"], ["S256"])
        self.assertTrue(server["registration_endpoint"].endswith("/mcp/oauth/register"))
        res = self._post_json("/mcp", {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        self.assertEqual(res.status_code, 401)
        self.assertIn("resource_metadata=", res.headers["WWW-Authenticate"])
        bad = self._post_json("/mcp", {"jsonrpc": "2.0", "id": 1, "method": "ping"}, token="nope")
        self.assertEqual(bad.status_code, 401)

    def test_register_rejects_bad_redirect(self):
        res = self._post_json("/mcp/oauth/register", {"redirect_uris": ["http://evil.example/cb"]})
        self.assertEqual(res.status_code, 400)
        set_param(self.icp, "mcp_lite.allow_registration", "False")
        res = self._post_json("/mcp/oauth/register", {"redirect_uris": [REDIRECT]})
        self.assertEqual(res.status_code, 403)

    # ------------------------------------------------------------- full flow
    def test_oauth_flow_and_read_tools(self):
        client_id, tokens, code, verifier = self._oauth_token("mcp_basic", "mcp_basic_pw_123")
        access = tokens["access_token"]
        init = self._rpc(access, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t"}})
        self.assertEqual(init["result"]["protocolVersion"], "2025-06-18")
        notif = self._post_json("/mcp", {"jsonrpc": "2.0", "method": "notifications/initialized"}, access)
        self.assertEqual(notif.status_code, 202)
        names = {t["name"] for t in self._rpc(access, "tools/list")["result"]["tools"]}
        self.assertIn("search_records", names)
        self.assertNotIn("create_record", names)  # read-only by default

        err, text = self._tool(access, "whoami")
        self.assertFalse(err)
        self.assertEqual(json.loads(text)["login"], "mcp_basic")
        err, text = self._tool(access, "search_records", model="res.partner",
                               domain=[["email", "=", "azure@mcp.example"]], fields=["name", "email"])
        self.assertFalse(err, text)
        self.assertEqual(json.loads(text)["records"][0]["name"], "Azure MCP Interior")
        err, text = self._tool(access, "count_records", model="res.partner", domain=[["name", "ilike", "Azure MCP"]])
        self.assertEqual(json.loads(text)["count"], 1)
        err, text = self._tool(access, "aggregate_records", model="res.partner", groupby=["is_company"])
        self.assertFalse(err, text)
        err, text = self._tool(access, "get_fields", model="res.partner", query="email")
        self.assertIn("email", text)
        err, text = self._tool(access, "list_models", query="partner")
        self.assertIn("res.partner", text)

        # code is single use, wrong verifier fails
        again = self.url_open("/mcp/oauth/token", data={
            "grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT,
            "client_id": client_id, "code_verifier": verifier})
        self.assertEqual(again.status_code, 400)

        # refresh rotates
        refreshed = self.url_open("/mcp/oauth/token", data={
            "grant_type": "refresh_token", "refresh_token": tokens["refresh_token"], "client_id": client_id}).json()
        self.assertNotEqual(refreshed["access_token"], access)
        self.assertEqual(self._post_json("/mcp", {"jsonrpc": "2.0", "id": 1, "method": "ping"}, access).status_code, 401)
        self.assertEqual(self._rpc(refreshed["access_token"], "ping")["result"], {})
        old = self.url_open("/mcp/oauth/token", data={
            "grant_type": "refresh_token", "refresh_token": tokens["refresh_token"], "client_id": client_id})
        self.assertEqual(old.status_code, 400)

        # revoke
        self.url_open("/mcp/oauth/revoke", data={"token": refreshed["refresh_token"]})
        self.assertEqual(self._post_json("/mcp", {"jsonrpc": "2.0", "id": 1, "method": "ping"},
                                         refreshed["access_token"]).status_code, 401)
        logs = self.env["mcp_lite.log"].search([("user_id", "=", self.basic.id)])
        self.assertTrue(logs.filtered(lambda l: l.tool == "search_records" and l.state == "ok"))

    def test_v02_tools(self):
        _cid, tokens, _c, _v = self._oauth_token("mcp_basic", "mcp_basic_pw_123")
        access = tokens["access_token"]
        err, text = self._tool(access, "search_by_name", model="res.partner", name="Azure MCP")
        self.assertFalse(err, text)
        self.assertEqual(json.loads(text)["matches"][0]["id"], self.partner.id)
        err, text = self._tool(access, "search_by_name", model="ir.config_parameter", name="x")
        self.assertTrue(err)
        err, text = self._tool(access, "period_report", model="res.partner", date_field="create_date",
                               period="month", date_from="2000-01-01")
        self.assertFalse(err, text)
        self.assertTrue(json.loads(text)["rows"])
        err, text = self._tool(access, "period_report", model="res.partner", date_field="create_date",
                               split_by="user_id", measure="id", func="max")
        self.assertFalse(err, text)
        # hidden fields cannot be used as split, measure or date field
        for kw in ({"split_by": "user_ids.password"}, {"split_by": "signup_token"}, {"measure": "signup_token"},
                   {"date_from": "not-a-date"}, {"period": "decade"}):
            err, text = self._tool(access, "period_report", model="res.partner", date_field="create_date", **kw)
            self.assertTrue(err, kw)
        err, text = self._tool(access, "period_report", model="res.partner", date_field="name")
        self.assertTrue(err)
        err, text = self._tool(access, "suggest_questions")
        self.assertFalse(err, text)
        self.assertIn("questions", json.loads(text))

    def test_access_rights_and_safety(self):
        _cid, tokens, _c, _v = self._oauth_token("mcp_basic", "mcp_basic_pw_123")
        access = tokens["access_token"]
        # hard-blocked and sensitive
        err, text = self._tool(access, "search_records", model="ir.config_parameter")
        self.assertTrue(err)
        err, text = self._tool(access, "search_records", model="res.users", domain=[["id", "=", self.basic.id]],
                               fields=["name", "password"])
        self.assertFalse(err, text)
        self.assertNotIn("password", json.loads(text)["records"][0])
        # the user's own rights apply: a basic user cannot read server actions
        err, text = self._tool(access, "search_records", model="ir.actions.server")
        self.assertTrue(err)
        # lite has no write tools, even when someone sets the old paid-edition parameters
        set_param(self.icp, "mcp_lite.allow_write", "True")
        names = {t["name"] for t in self._rpc(access, "tools/list")["result"]["tools"]}
        self.assertEqual(names, {"whoami", "list_models", "get_fields", "search_records", "count_records", "aggregate_records",
                                 "search_by_name", "period_report", "suggest_questions"})
        for tool in ("create_record", "update_record", "delete_records", "run_action", "post_message"):
            err, text = self._tool(access, tool, model="res.partner", values={"name": "X"})
            self.assertTrue(err, tool)
        self.assertFalse(self.env["res.partner"].search([("name", "=", "X")]))
        # hidden models
        set_param(self.icp, "mcp_lite.blocked_models", "res.partner")
        err, text = self._tool(access, "search_records", model="res.partner")
        self.assertTrue(err)
        err, text = self._tool(access, "list_models", query="partner")
        self.assertNotIn('"res.partner"', text)

    def test_hidden_fields_cannot_leak_through_filters(self):
        """A sensitive field must not be readable, filterable, sortable or groupable, however it is reached."""
        _cid, tokens, _c, _v = self._oauth_token("mcp_basic", "mcp_basic_pw_123")
        access = tokens["access_token"]
        attacks = [
            ("search_records", dict(model="res.users", domain=[["password", "=", "x"]])),
            ("count_records", dict(model="res.users", domain=[["password", "!=", False]])),
            ("search_records", dict(model="res.users", order="password")),
            ("aggregate_records", dict(model="res.users", groupby=["password"])),
            ("aggregate_records", dict(model="res.users", measures=["password:count_distinct"])),
            ("aggregate_records", dict(model="res.users", groupby=["id"], order="password")),
            # through a relation (partner -> users -> password)
            ("count_records", dict(model="res.partner", domain=[["user_ids.password", "!=", False]])),
            ("search_records", dict(model="res.partner", order="user_ids.password")),
            # through 'any' sub-domains
            ("count_records", dict(model="res.partner", domain=[["user_ids", "any", [["password", "=", "x"]]]])),
            ("count_records", dict(model="res.partner", domain=[["user_ids", "not any", [["api_key_ids.key", "=", "x"]]]])),
            ("count_records", dict(model="res.partner", domain=[["user_ids", "any", [["id", "=", 1]]], ["bogus_field", "=", 1]])),
        ]
        for tool, args in attacks:
            err, text = self._tool(access, tool, **args)
            self.assertTrue(err, f"{tool} {args} was allowed: {text}")
        # a relation into a blocked model is refused too
        set_param(self.icp, "mcp_lite.blocked_models", "res.users")
        err, text = self._tool(access, "count_records", model="res.partner", domain=[["user_ids.login", "=", "admin"]])
        self.assertTrue(err, text)
        set_param(self.icp, "mcp_lite.blocked_models", "")
        # normal paths still work
        err, text = self._tool(access, "count_records", model="res.partner", domain=[["user_ids.login", "=", "mcp_basic"]])
        self.assertFalse(err, text)
        self.assertEqual(json.loads(text)["count"], 1)
        err, text = self._tool(access, "count_records", model="res.partner",
                               domain=["|", ["name", "ilike", "Azure"], ["user_ids", "any", [["login", "=", "mcp_basic"]]]])
        self.assertFalse(err, text)
        err, text = self._tool(access, "aggregate_records", model="res.partner", groupby=["is_company"], order="__count desc")
        self.assertFalse(err, text)
        # oversized domains are refused
        err, text = self._tool(access, "count_records", model="res.partner", domain=[["id", ">", 0]] * 60)
        self.assertTrue(err)

    def test_prompts_and_resources_are_empty(self):
        _cid, tokens, _c, _v = self._oauth_token("mcp_basic", "mcp_basic_pw_123")
        access = tokens["access_token"]
        init = self._rpc(access, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t"}})
        self.assertNotIn("prompts", init["result"]["capabilities"])
        res = self._post_json("/mcp", {"jsonrpc": "2.0", "id": 9, "method": "prompts/list"}, access).json()
        self.assertEqual(res["error"]["code"], -32601)

    def test_log_keeps_no_arguments(self):
        _cid, tokens, _c, _v = self._oauth_token("mcp_basic", "mcp_basic_pw_123")
        self._tool(tokens["access_token"], "search_records", model="res.partner", domain=[["name", "=", "Azure MCP Interior"]])
        log = self.env["mcp_lite.log"].search([("user_id", "=", self.basic.id), ("tool", "=", "search_records")], limit=1)
        self.assertEqual(log.model, "res.partner")
        self.assertNotIn("arguments", log._fields)
        self.assertFalse(log.message)

    def test_outsider_cannot_connect(self):
        client_id = self._register()
        self.authenticate("mcp_outsider", "mcp_outsider_pw_123")
        page = self.url_open(f"/mcp/oauth/authorize?response_type=code&client_id={client_id}&redirect_uri={REDIRECT}"
                             f"&code_challenge={_challenge('v' * 50)}&code_challenge_method=S256")
        self.assertIn("not allowed", page.text)
        self.assertNotIn('value="allow"', page.text)

    def test_api_key_auth(self):
        apikeys = self.env["res.users.apikeys"].with_user(self.basic).sudo()
        try:
            key = apikeys._generate("rpc", "claude code", None)
        except TypeError:  # Odoo 17 has no expiration argument
            key = apikeys._generate("rpc", "claude code")
        result = self._rpc(key, "tools/list")["result"]
        self.assertTrue(result["tools"])
        err, text = self._tool(key, "whoami")
        self.assertEqual(json.loads(text)["login"], "mcp_basic")

    def test_rate_limit_and_kill_switch(self):
        _cid, tokens, _c, _v = self._oauth_token("mcp_basic", "mcp_basic_pw_123")
        access = tokens["access_token"]
        set_param(self.icp, "mcp_lite.rate_limit", "3")
        calls = [self._tool(access, "whoami") for _ in range(3)]
        self.assertFalse(any(err for err, _t in calls))
        err, text = self._tool(access, "whoami")
        self.assertTrue(err)
        self.assertIn("Rate limit", text)
        self.assertTrue(self.env["mcp_lite.log"].search([("user_id", "=", self.basic.id), ("state", "=", "limited")]))
        set_param(self.icp, "mcp_lite.rate_limit", "0")
        err, text = self._tool(access, "whoami")
        self.assertFalse(err, text)
        set_param(self.icp, "mcp_lite.kill_switch", "True")
        res = self._post_json("/mcp", {"jsonrpc": "2.0", "id": 1, "method": "ping"}, access)
        self.assertEqual(res.status_code, 503)
        set_param(self.icp, "mcp_lite.kill_switch", "False")
        self.assertEqual(self._rpc(access, "ping")["result"], {})
