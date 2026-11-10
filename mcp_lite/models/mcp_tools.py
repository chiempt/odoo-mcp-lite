"""The tools an AI assistant can call (read only). Every tool runs as the
connected user, so Odoo access rights and record rules decide what it can see."""
import re
from datetime import date, datetime

from odoo import api, models
from odoo.exceptions import AccessError, UserError

PARAM = "mcp_lite."
MAX_LIMIT = 200
DEFAULT_LIMIT = 40
MAX_DOMAIN_TERMS = 50
SENSITIVE_FIELD = re.compile(r"(password|passwd|secret|token|api_?key|totp|private_key|signature_key|oauth_access)", re.I)
# Never exposed, whatever the settings say.
HARD_BLOCKED = {
    "res.users.apikeys", "res.users.apikeys.description", "res.users.identitycheck",
    "mcp_lite.client", "mcp_lite.code", "mcp_lite.token",
    "bro3b.mcp.client", "bro3b.mcp.code", "bro3b.mcp.token",
    "ir.config_parameter", "auth_totp.device", "ir.cron", "ir.rule", "ir.model.access",
}


class McpToolError(Exception):
    """An error message meant for the AI assistant (shown as a tool error)."""


def _json_safe(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, bytes):
        return "<binary omitted>"
    if isinstance(value, models.BaseModel):
        return [value.id, value.display_name] if len(value) == 1 else value.ids
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


def _user_has_groups(user, groups):
    if hasattr(user, "has_groups"):  # Odoo 18+
        return user.has_groups(groups)
    return user.user_has_groups(groups)


class McpServer(models.AbstractModel):
    _name = "mcp_lite.server"
    _description = "MCP Lite: tools"

    # ------------------------------------------------------------------ settings
    @api.model
    def _blocked_patterns(self):
        raw = self.env["ir.config_parameter"].sudo().get_param(PARAM + "blocked_models", "")
        return [p.strip() for p in (raw or "").replace("\n", ",").split(",") if p.strip()]

    @staticmethod
    def _matches(model_name, patterns):
        for pattern in patterns:
            if pattern.endswith("*") and model_name.startswith(pattern[:-1]):
                return True
            if model_name == pattern:
                return True
        return False

    # ------------------------------------------------------------------ catalogue
    @api.model
    def _tool_specs(self):
        domain_help = (
            "Odoo domain as a JSON list, e.g. [[\"state\",\"=\",\"sale\"],[\"amount_total\",\">\",1000]]. "
            "Use [] for all records."
        )
        return [
            {
                "name": "whoami",
                "description": "Who you are connected as: user, companies, language and timezone. This connector is read-only.",
                "inputSchema": {"type": "object", "properties": {}},
                "annotations": {"readOnlyHint": True},
            },
            {
                "name": "list_models",
                "description": "Find models (tables) the user can read. Search by technical name or label, "
                               "e.g. 'sale', 'invoice', 'partner'. Call this first when you do not know the model name.",
                "inputSchema": {"type": "object", "properties": {
                    "query": {"type": "string", "description": "Part of the model name or label. Empty lists the common business models."},
                    "limit": {"type": "integer", "default": 30},
                }},
                "annotations": {"readOnlyHint": True},
            },
            {
                "name": "get_fields",
                "description": "List the fields of a model with type, label and relation. Call before search_records "
                               "so you use real field names.",
                "inputSchema": {"type": "object", "required": ["model"], "properties": {
                    "model": {"type": "string", "description": "Technical model name, e.g. sale.order"},
                    "query": {"type": "string", "description": "Optional filter on field name or label."},
                }},
                "annotations": {"readOnlyHint": True},
            },
            {
                "name": "search_records",
                "description": "Search and read records. Returns the requested fields (or a short default set).",
                "inputSchema": {"type": "object", "required": ["model"], "properties": {
                    "model": {"type": "string"},
                    "domain": {"type": "array", "description": domain_help, "default": []},
                    "fields": {"type": "array", "items": {"type": "string"}, "description": "Field names to return. Empty returns display_name and a few key fields."},
                    "limit": {"type": "integer", "default": DEFAULT_LIMIT, "maximum": MAX_LIMIT},
                    "offset": {"type": "integer", "default": 0},
                    "order": {"type": "string", "description": "e.g. 'date_order desc'"},
                }},
                "annotations": {"readOnlyHint": True},
            },
            {
                "name": "count_records",
                "description": "Count records matching a domain.",
                "inputSchema": {"type": "object", "required": ["model"], "properties": {
                    "model": {"type": "string"},
                    "domain": {"type": "array", "description": domain_help, "default": []},
                }},
                "annotations": {"readOnlyHint": True},
            },
            {
                "name": "aggregate_records",
                "description": "Group and total records, like a pivot table. Example: revenue per month = "
                               "model sale.order, groupby ['date_order:month'], measures ['amount_total:sum'].",
                "inputSchema": {"type": "object", "required": ["model"], "properties": {
                    "model": {"type": "string"},
                    "domain": {"type": "array", "description": domain_help, "default": []},
                    "groupby": {"type": "array", "items": {"type": "string"}, "description": "Fields to group by; dates accept :day :week :month :quarter :year."},
                    "measures": {"type": "array", "items": {"type": "string"}, "description": "field:sum, field:avg, field:max, field:min. A record count is always included."},
                    "limit": {"type": "integer", "default": 100, "maximum": 1000},
                    "order": {"type": "string", "description": "e.g. 'amount_total:sum desc'"},
                }},
                "annotations": {"readOnlyHint": True},
            },
        ]

    # ------------------------------------------------------------------ dispatch
    @api.model
    def _call_tool(self, name, arguments):
        if name not in {spec["name"] for spec in self._tool_specs()}:
            raise McpToolError(f"Unknown or disabled tool: {name}")
        arguments = arguments or {}
        if not isinstance(arguments, dict):
            raise McpToolError("arguments must be an object.")
        return _json_safe(getattr(self, "_tool_" + name)(**arguments))

    # ------------------------------------------------------------------ helpers
    def _model_blocked(self, model, patterns=None):
        patterns = self._blocked_patterns() if patterns is None else patterns
        return model in HARD_BLOCKED or self._matches(model, patterns)

    def _mcp_model(self, model):
        if not isinstance(model, str) or model not in self.env:
            raise McpToolError(f"Model '{model}' does not exist. Use list_models to find the right name.")
        if self._model_blocked(model):
            raise McpToolError(f"Model '{model}' is blocked for AI access by the administrator.")
        records = self.env[model]
        if records._abstract or records._transient:
            raise McpToolError(f"'{model}' is not a data model.")
        if not self._can(records, "read"):
            raise AccessError(f"You are not allowed to read '{model}'.")
        return records

    @staticmethod
    def _can(records, operation):
        if hasattr(records, "has_access"):  # Odoo 18+
            return records.has_access(operation)
        return records.check_access_rights(operation, raise_exception=False)

    @staticmethod
    def _field_visible(records, name):
        """Whether the assistant may see this field at all (read, filter, group, sort)."""
        field = records._fields.get(name)
        if not field:
            raise McpToolError(f"Field '{name}' does not exist on {records._name}. Use get_fields.")
        if SENSITIVE_FIELD.search(name) or field.type == "binary":
            return False
        if field.groups and not _user_has_groups(records.env.user, field.groups):
            return False
        return True

    def _readable_fields(self, records, requested=None):
        return [n for n in (requested or list(records._fields)) if self._field_visible(records, n)]

    @staticmethod
    def _default_fields(records):
        preferred = ["display_name", "name", "state", "partner_id", "date", "date_order", "invoice_date",
                     "amount_total", "amount_residual", "email", "phone", "user_id", "stage_id", "company_id"]
        return [name for name in preferred if name in records._fields]

    def _assert_path(self, records, path):
        """Every hop of a dotted field path ('partner_id.user_ids.login') must be visible
        and lead only to models the assistant may use. Filtering or sorting on a hidden
        field would leak it one yes/no answer at a time, so the whole path is checked."""
        current = records
        parts = path.split(".")
        for index, part in enumerate(parts):
            part = part.split(":")[0]
            if part == "id" and index == len(parts) - 1:
                return current._fields["id"]
            if not self._field_visible(current, part):
                raise McpToolError(f"Field '{part}' is not available to AI assistants on {current._name}.")
            field = current._fields[part]
            if index < len(parts) - 1:
                if not field.relational:
                    raise McpToolError(f"Field '{part}' on {current._name} is not a relation.")
                if self._model_blocked(field.comodel_name) or not self._can(self.env[field.comodel_name], "read"):
                    raise McpToolError(f"Model '{field.comodel_name}' is not available to AI assistants.")
                current = self.env[field.comodel_name]
        return field

    def _assert_fields(self, records, names):
        for name in names:
            if name:
                self._assert_path(records, name)

    def _check_domain(self, records, domain):
        if len(domain) > MAX_DOMAIN_TERMS:
            raise McpToolError(f"The domain has too many terms (maximum {MAX_DOMAIN_TERMS}).")
        for term in domain:
            if isinstance(term, (tuple, list)):
                if len(term) != 3 or not isinstance(term[0], str):
                    raise McpToolError("Each domain term must be [field, operator, value].")
                field = self._assert_path(records, term[0])
                if term[1] in ("any", "not any"):
                    # a sub-domain on the related model: check it with the same rules
                    if not field.relational or not isinstance(term[2], (list, tuple)):
                        raise McpToolError("'any' needs a relation and a domain list.")
                    self._check_domain(self.env[field.comodel_name], self._mcp_domain(list(term[2])))
            elif term not in ("&", "|", "!"):
                raise McpToolError("Domain operators must be '&', '|' or '!'.")
        return domain

    @staticmethod
    def _mcp_domain(domain):
        if domain in (None, ""):
            return []
        if not isinstance(domain, list):
            raise McpToolError("domain must be a JSON list, e.g. [[\"name\",\"ilike\",\"acme\"]].")
        return [tuple(term) if isinstance(term, list) else term for term in domain]

    def _check_order(self, records, order, allow=()):
        for part in (order or "").split(","):
            if part.strip() and part.split()[0] not in allow:
                self._assert_path(records, part.split()[0])

    # ------------------------------------------------------------------ read tools
    def _tool_whoami(self):
        user = self.env.user
        return {
            "user": user.name, "login": user.login, "user_id": user.id,
            "company": self.env.company.name, "currency": self.env.company.currency_id.name,
            "companies": user.company_ids.mapped("name"),
            "lang": user.lang, "tz": user.tz,
            "can_change_data": False,
            "edition": "MCP Lite (read-only)",
        }

    def _tool_list_models(self, query="", limit=30):
        limit = max(1, min(int(limit or 30), 200))
        domain = [("transient", "=", False)]
        if query:
            domain += ["|", ("model", "ilike", query), ("name", "ilike", query)]
        else:
            domain += [("model", "in", [
                "res.partner", "sale.order", "sale.order.line", "purchase.order", "account.move",
                "account.move.line", "account.payment", "product.product", "product.template",
                "stock.picking", "stock.quant", "crm.lead", "project.project", "project.task",
                "hr.employee", "mrp.production", "pos.order", "helpdesk.ticket",
            ])]
        patterns = self._blocked_patterns()
        out = []
        for rec in self.env["ir.model"].sudo().search(domain, order="model"):
            name = rec.model
            if name not in self.env or self._model_blocked(name, patterns):
                continue
            records = self.env[name]
            if records._abstract or not self._can(records, "read"):
                continue
            out.append({"model": name, "label": rec.name})
            if len(out) >= limit:
                break
        return {"models": out, "hint": "Call get_fields next to see the columns of a model."}

    def _tool_get_fields(self, model, query=""):
        records = self._mcp_model(model)
        info = records.fields_get(attributes=["string", "type", "relation", "required", "readonly", "selection", "help"])
        out = []
        for name, attrs in sorted(info.items()):
            if not self._field_visible(records, name):
                continue
            if query and query.lower() not in name.lower() and query.lower() not in (attrs.get("string") or "").lower():
                continue
            item = {"name": name, "label": attrs.get("string"), "type": attrs.get("type")}
            for key in ("relation", "required", "readonly"):
                if attrs.get(key):
                    item[key] = attrs[key]
            if attrs.get("selection") and isinstance(attrs["selection"], list):
                item["selection"] = [s[0] for s in attrs["selection"]][:30]
            if attrs.get("help"):
                item["help"] = attrs["help"][:200]
            out.append(item)
        return {"model": model, "fields": out}

    def _tool_search_records(self, model, domain=None, fields=None, limit=DEFAULT_LIMIT, offset=0, order=None):
        records = self._mcp_model(model)
        limit = max(1, min(int(limit or DEFAULT_LIMIT), MAX_LIMIT))
        names = self._readable_fields(records, fields or self._default_fields(records))
        domain = self._check_domain(records, self._mcp_domain(domain))
        self._check_order(records, order)
        found = records.search(domain, limit=limit, offset=int(offset or 0), order=order or None)
        rows = found.read([n for n in names if n != "display_name"]) if names else [{"id": r.id} for r in found]
        if "display_name" in names:
            for row, rec in zip(rows, found):
                row["display_name"] = rec.display_name
        total = records.search_count(domain) if len(found) == limit or offset else len(found)
        return {"model": model, "count": len(rows), "total": total, "records": rows}

    def _tool_count_records(self, model, domain=None):
        records = self._mcp_model(model)
        domain = self._check_domain(records, self._mcp_domain(domain))
        return {"model": model, "count": records.search_count(domain)}

    def _tool_aggregate_records(self, model, domain=None, groupby=None, measures=None, limit=100, order=None):
        records = self._mcp_model(model)
        groupby = list(groupby or [])
        aggregates = []
        for measure in measures or []:
            field_name, _, func = measure.partition(":")
            if "." in field_name or field_name not in records._fields:
                raise McpToolError(f"Field '{field_name}' does not exist on {model}.")
            aggregates.append(f"{field_name}:{func or 'sum'}")
        for spec in groupby:
            if spec.split(":")[0] not in records._fields:
                raise McpToolError(f"Field '{spec.split(':')[0]}' does not exist on {model}.")
        # visibility first, so a hidden field is refused before anything is computed
        self._assert_fields(records, [g.split(":")[0] for g in groupby] + [a.split(":")[0] for a in aggregates])
        domain = self._check_domain(records, self._mcp_domain(domain))
        self._check_order(records, order, allow=("count", "__count"))
        rows = records._read_group(
            domain, groupby, aggregates + ["__count"],
            limit=max(1, min(int(limit or 100), 1000)), order=order or None,
        )
        keys = groupby + aggregates + ["count"]
        return {"model": model, "groups": [dict(zip(keys, row)) for row in rows]}


def tool_error_message(exc):
    if isinstance(exc, (McpToolError, UserError, AccessError)):
        return str(exc.args[0] if exc.args else exc)
    if isinstance(exc, (ValueError, TypeError, KeyError)):
        return f"Invalid arguments: {exc}"
    return f"{type(exc).__name__}: {exc}"
