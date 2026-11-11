"""Calls a running MCP Lite endpoint with an Odoo API key and saves request/response pairs.
Real responses, not edited; the renderer only truncates long ones for display."""
import json, sys, urllib.request

url, key, out = sys.argv[1:4]


def rpc(method, params=None, i=[0]):
    i[0] += 1
    req = urllib.request.Request(url, data=json.dumps({"jsonrpc": "2.0", "id": i[0], "method": method, "params": params or {}}).encode(),
                                 headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
                                          "Authorization": "Bearer " + key})
    return json.load(urllib.request.urlopen(req))["result"]


def tool(tool_name, **args):
    res = rpc("tools/call", {"name": tool_name, "arguments": args})
    text = res["content"][0]["text"]
    try:
        body = json.loads(text)
    except ValueError:  # errors come back as plain text
        body = text
    return {"tool": tool_name, "arguments": args, "is_error": res.get("isError", False), "result": body}


rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "demo"}})
steps = [
    tool("whoami"),
    tool("search_by_name", model="res.partner", name="azure"),
    tool("period_report", model="sale.order", date_field="date_order", measure="amount_total", period="month"),
    tool("aggregate_records", model="sale.order", groupby=["partner_id"], measures=["amount_total:sum"], limit=3, order="amount_total:sum desc"),
    # a hidden-field probe: refused
    tool("search_records", model="res.partner", domain=[["user_ids.password", "!=", False]], fields=["name"]),
]
json.dump(steps, open(out, "w"), indent=1)
print("saved", out, [s["tool"] + (" (refused)" if s["is_error"] else "") for s in steps])
