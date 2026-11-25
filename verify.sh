#!/usr/bin/env bash
# Verify the ontology artifact and tool before shipping.
set -euo pipefail
cd "$(dirname "$0")"

echo "== syntax =="
.venv/bin/python -m py_compile update.py && echo "update.py compiles"

echo "== ontology invariants =="
.venv/bin/python - <<'EOF'
import re, sys, yaml
o = yaml.safe_load(open("ontology.yaml"))
errs = []
cats = set(o["meta"]["categories"])
ids = [c["id"] for c in o["concepts"]]
if len(ids) != len(set(ids)):
    errs.append("duplicate concept ids")
idset = set(ids)
statuses = {"emerging","established","absorbed"}
rtypes = {"enables","derives_from","supersedes","extends","used_with","contrasts_with"}
for c in o["concepts"]:
    if c["category"] not in cats: errs.append(f"bad category: {c['id']}")
    if not re.fullmatch(r"\d{4}-\d{2}", c.get("first_seen","")): errs.append(f"bad first_seen: {c['id']}")
    if c.get("status","emerging") not in statuses: errs.append(f"bad status: {c['id']}")
    if len(c.get("summary","")) < 20: errs.append(f"summary too short: {c['id']}")
seen = set()
for r in o["relations"]:
    if r["from"] not in idset or r["to"] not in idset: errs.append(f"dangling relation: {r}")
    if r["type"] not in rtypes: errs.append(f"bad relation type: {r}")
    k = (r["from"], r["to"], r["type"])
    if k in seen: errs.append(f"duplicate relation: {k}")
    seen.add(k)
    if not re.fullmatch(r"\d{4}-\d{2}", r.get("since","")): errs.append(f"bad since: {r}")
if errs:
    print("\n".join(errs)); sys.exit(1)
print(f"OK: {len(ids)} concepts, {len(o['relations'])} relations, all invariants hold")
EOF

echo "== viewer data =="
.venv/bin/python - <<'EOF'
import json, yaml
o = yaml.safe_load(open("ontology.yaml"))
json.dump(o, open("ontology.json","w"), indent=1, ensure_ascii=False)
print("ontology.json written:", len(o["concepts"]), "concepts")
EOF
echo "ALL CHECKS PASS"
