#!/usr/bin/env bash
# Run the module tests in Docker against a given Odoo version: scripts/test.sh 19 (or 18, 17).
# Starts its own throwaway PostgreSQL on a private network and removes everything afterwards.
set -euo pipefail
V="${1:-19}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
RUN="mcp-lite-test-$V-$$"
ADDONS="$(mktemp -d)"
trap 'docker rm -fv "$RUN-db" >/dev/null 2>&1 || true; docker network rm "$RUN" >/dev/null 2>&1 || true; rm -rf "$ADDONS"' EXIT

cp -R "$HERE/mcp_lite" "$ADDONS/mcp_lite"
if [ "$V" = "17" ]; then
  # Odoo 17 calls list views "tree"; everything else is identical
  sed -i.bak -e 's/<list /<tree /g; s/<\/list>/<\/tree>/g; s/>list</>tree</g; s/"list,form"/"tree,form"/g; s/<list>/<tree>/g' "$ADDONS/mcp_lite/views/"*.xml
  sed -i.bak -e 's/>list</>tree</g' "$ADDONS/mcp_lite/views/mcp_views.xml"
  find "$ADDONS" -name '*.bak' -delete
fi
if [ "$V" = "20" ]; then
  # Odoo 20 has a different access-rights file format; port20.py converts it (see its docstring)
  python3 "$HERE/scripts/port20.py" "$ADDONS/mcp_lite"
fi
sed -i.bak "s/\"version\": \"[0-9.]*\"/\"version\": \"$V.0.1.0.0\"/" "$ADDONS/mcp_lite/__manifest__.py"; rm -f "$ADDONS/mcp_lite/__manifest__.py.bak"

docker network create "$RUN" >/dev/null
docker run -d --name "$RUN-db" --network "$RUN" -e POSTGRES_USER=odoo -e POSTGRES_PASSWORD=odoo -e POSTGRES_DB=postgres \
  postgres:16-alpine >/dev/null
until docker exec "$RUN-db" pg_isready -U odoo >/dev/null 2>&1; do sleep 1; done

LOG="$(mktemp)"
set +e
docker run --rm --network "$RUN" -e HOST="$RUN-db" -e USER=odoo -e PASSWORD=odoo \
  -v "$ADDONS:/mnt/extra-addons:ro" "odoo:$V" \
  odoo -d "t$V" \
  --addons-path=/usr/lib/python3/dist-packages/odoo/addons,/mnt/extra-addons \
  -i mcp_lite --test-tags /mcp_lite --stop-after-init --without-demo=all --log-level=test > "$LOG" 2>&1
set -e
[ -n "${TEST_LOG:-}" ] && cp "$LOG" "$TEST_LOG"
grep -E "ERROR|FAIL|Traceback|tests in|failed, " "$LOG" | tail -60 || true
# Odoo exits 0 even when tests fail, so read the verdict from its log.
if grep -qE "^[0-9-]+ [0-9:,]+ [0-9]+ (ERROR|CRITICAL)" "$LOG" || ! grep -qE " 0 failed, 0 error\(s\) of [1-9][0-9]* tests" "$LOG"; then
  echo "TESTS FAILED on odoo:$V"; exit 1
fi
echo "TESTS PASSED on odoo:$V: $(grep -oE '[0-9]+ failed, [0-9]+ error\(s\) of [0-9]+ tests' "$LOG" | tail -1)"
