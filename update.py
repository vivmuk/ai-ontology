#!/usr/bin/env python3
"""Weekly updater for the emerging-AI-concepts ontology.

Takes a repo checkout that contains ontology.yaml, discovers concepts that
emerged in the last N days via the Venice API (web search on), merges them
into the ontology, writes ontology.json for the viewer, and optionally commits
and pushes.

Usage:
  .venv/bin/python update.py                       # apply, commit, no push
  .venv/bin/python update.py --dry-run             # print proposed diff only
  .venv/bin/python update.py --repo /path/to/repo  # operate on another checkout
  .venv/bin/python update.py --push                # also push to origin

Venice key resolution: --key, $VENICE_API_KEY, then ~/.config/ai-ontology/venice.key
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

import yaml

VENICE_CHAT_URL = "https://api.venice.ai/api/v1/chat/completions"
DEFAULT_MODEL = "gemini-3-5-flash"
CATEGORIES = {
    "reasoning", "agents", "architecture", "training", "retrieval",
    "multimodal", "infrastructure", "interaction-protocols", "evaluation",
    "safety",
}
RELATION_TYPES = {"enables", "derives_from", "supersedes", "extends",
                  "used_with", "contrasts_with"}
STATUSES = {"emerging", "established", "absorbed"}
KEY_PATHS = [os.path.expanduser("~/.config/ai-ontology/venice.key")]


def log(msg: str) -> None:
    print(msg, flush=True)


def load_key(args) -> str:
    if args.key:
        return args.key.strip()
    env = os.environ.get("VENICE_API_KEY", "").strip()
    if env:
        return env
    for p in KEY_PATHS:
        if os.path.exists(p):
            return open(p).read().strip()
    sys.exit("no Venice API key: pass --key, set VENICE_API_KEY, or write "
             "~/.config/ai-ontology/venice.key")


def month_str(d: dt.date) -> str:
    return d.strftime("%Y-%m")


def slugify(label: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
    return re.sub(r"-{2,}", "-", s)[:64].rstrip("-")


def extract_json(text: str):
    """Best-effort JSON extraction: fences, then every balanced {...} span."""
    if not text or not text.strip():
        return None
    t = re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.I).strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", t, re.I)
    if m:
        t = m.group(1).strip()
    try:
        return json.loads(t)
    except Exception:
        pass
    # scan for balanced objects, skipping braces inside strings
    for start in range(len(t)):
        if t[start] != "{":
            continue
        depth, i, in_str, esc = 0, start, False, False
        for i in range(start, len(t)):
            ch = t[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(t[start:i + 1])
                    except Exception:
                        break  # try next '{'
    return None


def venice_json(key: str, model: str, system: str, user: str,
               max_tokens: int = 4000, timeout: int = 120, retries: int = 2):
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.3,
        "max_tokens": max_tokens,
        "venice_parameters": {
            "enable_web_search": "on",  # string! boolean is a 400
            "strip_thinking_response": True,
        },
    }
    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                VENICE_CHAT_URL,
                data=json.dumps(body).encode(),
                headers={"Authorization": "Bearer " + key,
                         "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.loads(r.read())
            content = data["choices"][0]["message"].get("content", "")
            parsed = extract_json(content)
            if parsed is not None:
                return parsed
            last_err = f"unparseable response: {content[:200]!r}"
        except urllib.error.HTTPError as e:
            last_err = f"HTTP {e.code}: {e.read()[:200]!r}"
        except Exception as e:  # noqa: BLE001
            last_err = f"{type(e).__name__}: {e}"
        log(f"  attempt {attempt + 1}/{retries} failed: {last_err}")
    return None


def discover(key: str, model: str, ontology: dict, lookback_days: int) -> list:
    today = dt.date.today()
    since = today - dt.timedelta(days=lookback_days)
    known = ",".join(sorted(c["id"] for c in ontology["concepts"]))
    cats = "|".join(sorted(CATEGORIES))
    rtypes = "|".join(sorted(RELATION_TYPES))
    prompt = f"""Today is {today.isoformat()}. Search the web for AI concepts that EMERGED or reached broad traction in the last {lookback_days} days (since {since.isoformat()}): new techniques, model capabilities, training methods, agent protocols, or architectures. Papers, frontier model releases, adopted tools only — no product news, no funding news.

Already known (never repeat any of these): {known}

Answer with ONLY this JSON object, nothing before or after it:
{{"concepts":[{{"label":"name","category":"{cats}","first_seen":"YYYY-MM","summary":"1-2 sentences, graduate level","aliases":["optional"],"sources":[{{"title":"t","url":"https://..."}}],"status":"emerging","relations":[{{"to":"known or new concept label","type":"{rtypes}"}}]}}]}}

Max 6 genuinely new concepts. No new concepts = {{"concepts":[]}}."""
    system = "You answer only with raw JSON. No thinking, no markdown, no commentary."
    raw = venice_json(key, model, system, prompt, max_tokens=8000)
    if not raw or not isinstance(raw, dict):
        return []
    return raw.get("concepts") or []


def normalize_concept(raw: dict, known_ids: set, categories: set) -> dict | None:
    if not isinstance(raw, dict):
        return None
    label = str(raw.get("label", "")).strip()
    if len(label) < 3:
        return None
    cid = slugify(str(raw.get("id") or label))
    if not cid or cid in known_ids:
        return None
    category = str(raw.get("category", "")).strip()
    if category not in categories:
        category = "architecture"
    summary = str(raw.get("summary", "")).strip()
    if len(summary) < 20:
        return None
    first_seen = str(raw.get("first_seen", "")).strip()
    if not re.fullmatch(r"\d{4}-\d{2}", first_seen):
        first_seen = month_str(dt.date.today())
    status = raw.get("status", "emerging")
    if status not in STATUSES:
        status = "emerging"
    sources = []
    for s in raw.get("sources") or []:
        if isinstance(s, dict) and str(s.get("url", "")).startswith("http"):
            sources.append({"title": str(s.get("title", ""))[:180],
                            "url": s["url"][:300]})
    aliases = [str(a)[:60] for a in (raw.get("aliases") or []) if str(a).strip()][:6]
    return {
        "id": cid,
        "label": label[:80],
        "category": category,
        "first_seen": first_seen,
        "summary": summary[:600],
        **({"aliases": aliases} if aliases else {}),
        **({"sources": sources} if sources else {}),
        "status": status,
    }


def normalize_relations(raw: list, all_ids: set, id_by_label: dict) -> list:
    out = []
    for r in raw or []:
        if not isinstance(r, dict):
            continue
        src = slugify(str(r.get("from", "")))
        dst_raw = str(r.get("to", "")).strip()
        dst = slugify(dst_raw)
        if dst not in all_ids:
            dst = id_by_label.get(dst_raw.lower(), "")
            dst = dst if dst else slugify(dst_raw)
        rtype = r.get("type", "")
        if rtype not in RELATION_TYPES:
            continue
        since = str(r.get("since", "")).strip()
        if not re.fullmatch(r"\d{4}-\d{2}", since):
            since = month_str(dt.date.today())
        if src in all_ids and dst in all_ids and src != dst:
            out.append({"from": src, "to": dst, "type": rtype, "since": since})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=os.path.dirname(os.path.abspath(__file__)),
                    help="checkout containing ontology.yaml")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--push", action="store_true")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--lookback-days", type=int, default=7)
    ap.add_argument("--key", default=None)
    args = ap.parse_args()

    repo = os.path.abspath(args.repo)
    onto_path = os.path.join(repo, "ontology.yaml")
    if not os.path.exists(onto_path):
        sys.exit(f"no ontology.yaml in {repo}")
    ontology = yaml.safe_load(open(onto_path))
    key = load_key(args)

    log(f"discovering (lookback {args.lookback_days}d, model {args.model})...")
    raw = discover(key, args.model, ontology, args.lookback_days)
    known_ids = {c["id"] for c in ontology["concepts"]}
    id_by_label = {c.get("label", "").lower(): c["id"] for c in ontology["concepts"]}

    new_concepts, new_relations = [], []
    for rc in raw:
        c = normalize_concept(rc, known_ids, CATEGORIES)
        if not c:
            continue
        known_ids.add(c["id"])
        id_by_label[c["label"].lower()] = c["id"]
        new_concepts.append(c)
        new_relations.extend(normalize_relations(rc.get("relations"), known_ids, id_by_label))

    if not new_concepts:
        log("nothing new emerged; ontology unchanged")
        return 0

    # existing relation keys, to dedupe
    existing_rel = {(r["from"], r["to"], r["type"]) for r in ontology["relations"]}
    new_relations = [r for r in new_relations
                     if (r["from"], r["to"], r["type"]) not in existing_rel]

    if args.dry_run:
        log(json.dumps({"concepts": [c["id"] for c in new_concepts],
                        "relations": new_relations}, indent=2))
        return 0

    today = dt.date.today().isoformat()
    ontology["concepts"].extend(new_concepts)
    ontology["relations"].extend(new_relations)
    ontology["meta"]["updated"] = today

    with open(onto_path, "w") as f:
        yaml.safe_dump(ontology, f, sort_keys=False, allow_unicode=True, width=100)
    with open(os.path.join(repo, "ontology.json"), "w") as f:
        json.dump(ontology, f, indent=1, ensure_ascii=False)

    # changelog
    cl_path = os.path.join(repo, "CHANGELOG.md")
    entry = [f"\n## {today} (+{len(new_concepts)} concepts, +{len(new_relations)} relations)\n"]
    for c in new_concepts:
        src = f" — {c['sources'][0]['url']}" if c.get("sources") else ""
        entry.append(f"- **{c['label']}** ({c['category']}, {c['first_seen']}): "
                     f"{c['summary'][:180]}{src}\n")
    with open(cl_path, "a") as f:
        f.writelines(entry)

    log(f"merged {len(new_concepts)} concepts, {len(new_relations)} relations")

    if subprocess.call(["git", "-C", repo, "diff", "--quiet"]) == 0:
        log("no file changes detected; skipping commit")
        return 0
    msg = f"ontology: weekly update {today} (+{len(new_concepts)} concepts)"
    subprocess.run(["git", "-C", repo, "add", "ontology.yaml", "ontology.json",
                    "CHANGELOG.md"], check=True)
    subprocess.run(["git", "-C", repo, "commit", "-q", "-m", msg], check=True)
    log("committed: " + msg)
    if args.push:
        r = subprocess.run(["git", "-C", repo, "push", "-q", "origin",
                            "HEAD"], capture_output=True, text=True)
        if r.returncode != 0:
            log("push failed: " + r.stderr.strip()[:300])
            return 2
        log("pushed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
