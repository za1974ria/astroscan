#!/usr/bin/env python3
"""Audit GET routes (Flask test_client) — sans POST pour éviter effets de bord."""
from __future__ import annotations

import sys
from collections import Counter

# Exécuter depuis la racine du projet : python3 scripts/audit_routes_get_only.py
sys.path.insert(0, ".")

SAMPLES = {
    "obj_id": "M31",
    "target_id": "m31",
    "nom_fichier": "placeholder.png",
    "filename": "dummy.jpg",
    "name": "orbital_map",
}

SKIP_SUBSTR = (
    "/api/iss/stream",
    "/api/telescope/stream",
)


def build_url(rule_path: str) -> tuple[str | None, str | None]:
    if "<" not in rule_path:
        return rule_path, None
    parts: list[str] = []
    for segment in rule_path.split("/"):
        if not segment:
            continue
        if segment.startswith("<") and segment.endswith(">"):
            inner = segment[1:-1]
            name = inner.split(":")[-1]
            if name not in SAMPLES:
                return None, f"pas d’échantillon pour <{name}>"
            parts.append(SAMPLES[name])
        else:
            parts.append(segment)
    url = "/" + "/".join(parts)
    return url, None


def main() -> int:
    from station_web import app

    client = app.test_client()
    rows: list[tuple[str, int, str, str, str]] = []

    with app.app_context():
        rules = sorted(app.url_map.iter_rules(), key=lambda r: r.rule)

    for rule in rules:
        if rule.endpoint == "static":
            continue
        if "GET" not in (rule.methods or set()):
            continue
        path = rule.rule
        if any(s in path for s in SKIP_SUBSTR):
            rows.append((path, 0, "SKIP", "stream SSE", rule.endpoint))
            continue
        url, err = build_url(path)
        if err:
            rows.append((path, 0, "SKIP", err, rule.endpoint))
            continue
        try:
            r = client.get(url, follow_redirects=False)
            ct = (r.headers.get("Content-Type") or "").split(";")[0][:40]
            note = ""
            if "json" in (r.headers.get("Content-Type") or ""):
                j = r.get_json(silent=True)
                if isinstance(j, list):
                    note = "list[%d]" % len(j)
                elif isinstance(j, dict):
                    note = "keys:%s" % ",".join(list(j.keys())[:6])
                else:
                    note = str(type(j))
            elif "html" in (r.headers.get("Content-Type") or ""):
                note = "html %dB" % len(r.data or b"")
            else:
                note = "%dB" % len(r.data or b"")
            rows.append((path, r.status_code, ct, note, rule.endpoint))
        except Exception as e:
            rows.append((path, 0, "ERR", str(e)[:100], rule.endpoint))

    st = Counter()
    for _, code, kind, _, _ in rows:
        if isinstance(code, int) and code > 0:
            st["%dxx" % (code // 100)] += 1
            if code >= 400:
                st["fail"] += 1
        elif kind == "SKIP":
            st["SKIP"] += 1
        elif kind == "ERR":
            st["ERR"] += 1

    print("=== Audit GET uniquement ===")
    for k in sorted(st.keys()):
        print(f"  {k}: {st[k]}")
    print(f"  routes testées: {len(rows)}")

    print("\n=== Échecs HTTP (status >= 400) ===")
    for path, code, ct, note, ep in rows:
        if isinstance(code, int) and code >= 400:
            print(f"  {code} {path} [{ep}] {note}")

    print("\n=== SKIP / ERR ===")
    for path, code, ct, note, ep in rows:
        if ct == "SKIP" or ct == "ERR":
            print(f"  {ct} {path} [{ep}] {note}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
