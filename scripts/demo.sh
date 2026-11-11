#!/usr/bin/env bash
# Records REAL tool calls against a throwaway Odoo (demo data) running MCP Lite.
# Usage: scripts/demo.sh [19]   -> writes docs/demo/transcript.json
# It only talks to a local container; nothing leaves your machine.
set -euo pipefail
V="${1:-19}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
RUN="mcp-lite-demo-$V-$$"
PORT="${PORT:-18069}"
trap 'docker rm -fv "$RUN-odoo" "$RUN-db" >/dev/null 2>&1 || true; docker network rm "$RUN" >/dev/null 2>&1 || true' EXIT
docker network create "$RUN" >/dev/null
docker run -d --name "$RUN-db" --network "$RUN" -e POSTGRES_USER=odoo -e POSTGRES_PASSWORD=odoo -e POSTGRES_DB=postgres postgres:16-alpine >/dev/null
until docker exec "$RUN-db" pg_isready -U odoo >/dev/null 2>&1; do sleep 1; done
COMMON=(--network "$RUN" -e HOST="$RUN-db" -e USER=odoo -e PASSWORD=odoo -v "$HERE/mcp_lite:/mnt/extra-addons/mcp_lite:ro")
ADDONS=--addons-path=/usr/lib/python3/dist-packages/odoo/addons,/mnt/extra-addons
docker run --rm "${COMMON[@]}" "odoo:$V" odoo -d demo $ADDONS -i sale_management,mcp_lite --stop-after-init --log-level=warn >/dev/null 2>&1
docker run -d --name "$RUN-odoo" "${COMMON[@]}" -p "$PORT:8069" "odoo:$V" odoo -d demo $ADDONS --log-level=warn >/dev/null
until curl -fs "http://localhost:$PORT/web/login" >/dev/null 2>&1; do sleep 2; done
KEY=$(docker run --rm -i "${COMMON[@]}" "odoo:$V" odoo shell -d demo $ADDONS --no-http --log-level=error 2>/tmp/mcp-lite-demo-shell.err <<'PY' | grep '^KEY=' | cut -d= -f2 || true
admin = env.ref("base.user_admin")
apikeys = env["res.users.apikeys"].with_user(admin).sudo()
try:
    key = apikeys._generate("rpc", "mcp-lite-demo", None)
except TypeError:
    key = apikeys._generate("rpc", "mcp-lite-demo")
# sample data (this image has no demo data): 4 customers, 24 confirmed orders over 8 months
import random, datetime
random.seed(7)
names = ["Azure Interior", "Deco Addict", "Gemini Furniture", "Lumber Inc"]
partners = [env["res.partner"].create({"name": n}) for n in names]
product = env["product.product"].create({"name": "Consulting day", "type": "service", "list_price": 480})
for i in range(24):
    when = datetime.datetime(2026, 3, 1) + datetime.timedelta(days=random.randint(0, 230))
    order = env["sale.order"].create({"partner_id": random.choice(partners).id, "date_order": when,
        "order_line": [(0, 0, {"product_id": product.id, "product_uom_qty": random.randint(1, 6), "price_unit": random.choice([480, 520, 610])})]})
    order.action_confirm()
    order.date_order = when
env.cr.commit()
print("KEY=" + key)
PY
)
[ -n "$KEY" ] || { echo "no API key; see /tmp/mcp-lite-demo-shell.err"; tail -5 /tmp/mcp-lite-demo-shell.err; exit 1; }
python3 -I "$HERE/scripts/demo_calls.py" "http://localhost:$PORT/mcp" "$KEY" "$HERE/docs/demo/transcript.json"
