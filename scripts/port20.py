"""Odoo 20 replaced security/ir.model.access.csv with ir.access.csv (columns model_id as a
technical name, operation as letters). Usage: python3 port20.py <path to mcp_lite folder>.
Writes security/ir.access.csv, removes the old file and updates __manifest__.py."""
import csv, pathlib, re, sys

root = pathlib.Path(sys.argv[1])
old = root / "security" / "ir.model.access.csv"
new = root / "security" / "ir.access.csv"
rows = list(csv.DictReader(old.open()))
with new.open("w", newline="") as fh:
    out = csv.writer(fh)
    out.writerow(["id", "name", "model_id", "group_id/id", "operation", "domain"])
    for r in rows:
        # model_mcp_lite_client -> mcp_lite.client (first underscore after the module name)
        model = "mcp_lite." + re.sub(r"^mcp\.lite\.|^mcp_lite_", "", re.sub(r"^model_", "", r["model_id:id"]))
        ops = "".join(l for l, k in (("c", "perm_create"), ("r", "perm_read"), ("u", "perm_write"), ("d", "perm_unlink")) if r[k] == "1")
        out.writerow([r["id"], r["name"], model, r["group_id:id"], ops, ""])
old.unlink()
manifest = root / "__manifest__.py"
manifest.write_text(manifest.read_text().replace("security/ir.model.access.csv", "security/ir.access.csv"))
