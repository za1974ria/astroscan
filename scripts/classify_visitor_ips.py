#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Classe les IP visiteurs (public / privé / CGNAT / …) et estime un type
d'institution à partir du champ isp (heuristique, pas ASN réel).
Sortie CSV : exports/visiteurs_ip_classification_mondiale.csv
"""
from __future__ import annotations

import csv
import ipaddress
import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "data" / "archive_stellaire.db"
OUT = Path(__file__).resolve().parent.parent / "exports" / "visiteurs_ip_classification_mondiale.csv"

# Mots-clés ISP / org (minuscules) — heuristique, à affiner avec le temps
_CLOUD = (
    "amazon", "aws", "google", "gcp", "microsoft", "azure", "oracle cloud",
    "alibaba", "tencent", "digitalocean", "linode", "akamai", "cloudflare",
    "fastly", "ovh", "hetzner", "scaleway", "vultr", "contabo", "choopa",
    "leaseweb", "online.net", "hostinger", "godaddy", "namecheap",
    "m247", "packet", "equinix", "colo", "datacenter", "data center",
    "hosting", "servers", "llc",  # LLC seul = faible signal ; combiné ailleurs
)
_MOBILE = (
    "mobile", "cellular", "wireless", "4g", "5g", "lte", "gsm", "umts",
    "orange", "vodafone", "t-mobile", "verizon", "at&t", "att ", "sprint",
    "wataniya", "mobilis", "djezzy", "ooredoo", "turk telekom",
)
_TELECOM = (
    "telecom", "télécom", "fibre", "fiber", "broadband", "cable", "dsl",
    "adsl", "ftth", "isp", "internet", "communications", "communcations",
    "algerie telecom", "algérie télécom", "free sas", "sfr", "bouygues",
    "proximus", "swisscom", "deutsche telekom", "telefonica", "tim ",
    "reliance", "jio", "airtel", "mtn ", "ethio telecom",
)
_EDU = (
    "universit", "university", "univ.", "school", "college", "academy",
    "institute of", "research center", "cnrs", "inria", "cern", ".edu",
    "ecole", "école", "polytechn",
)
_GOV = (
    "government", "gouvernement", "ministry", "ministère", "state of",
    "federal", "national agency", "defense", "défense", "military",
    "army", "navy", "air force", "police", "gendarmerie", "prefecture",
)


def classify_ip_scope(ip: str) -> tuple[str, str]:
    """
    Retourne (catégorie courte, détail).
    DOMESTIQUE = RFC1918 LAN / ULA IPv6 (pas la même chose que « résidentiel FAI »).
    Les plages TEST-NET RFC5737 sont « private » en Python mais ne sont pas du LAN : on les isole.
    """
    s = (ip or "").strip()
    if not s:
        return "VIDE", "IP absente"
    # X-Forwarded-For parfois concaténé : prendre le premier hop (client le plus proche du proxy)
    first = s.split(",")[0].strip()
    try:
        addr = ipaddress.ip_address(first)
    except ValueError:
        return "NON_PARSEABLE", f"Format invalide: {first[:80]!r}"

    if addr.version == 4:
        for net in (
            ipaddress.ip_network("192.0.2.0/24"),
            ipaddress.ip_network("198.51.100.0/24"),
            ipaddress.ip_network("203.0.113.0/24"),
            ipaddress.ip_network("198.18.0.0/15"),  # benchmark / perf testing
        ):
            if addr in net:
                return "TEST_DOC_BENCHMARK", f"Plage spéciale {net} (RFC5737 / bench — pas une IP production client)"

    if addr.version == 6:
        if addr.is_loopback:
            return "BOUCLE_IPV6", "::1 / loopback"
        if addr.is_link_local:
            return "LIEN_LOCAL_IPV6", "fe80::/10"
        if addr.is_multicast:
            return "MULTICAST_IPV6", str(addr)
        if addr.is_private:  # includes Unique Local fc00::/7 in Python
            return "DOMESTIQUE_IPV6", "ULA / privée IPv6 (RFC4193)"
        if addr.is_global:
            return "PUBLIC_IPV6", "Globale routable"
        return "IPV6_AUTRE", str(addr)

    # IPv4
    if addr.is_loopback:
        return "BOUCLE_IPV4", "127.0.0.0/8"
    if addr.is_link_local:
        return "LIEN_LOCAL_IPV4", "169.254.0.0/16"
    if addr.is_multicast:
        return "MULTICAST_IPV4", str(addr)
    if addr.is_private:
        return "DOMESTIQUE_IPV4", "RFC1918 (10/8, 172.16/12, 192.168/16)"
    if addr.is_reserved:
        return "RESERVE_IPV4", "Espace réservé IANA"
    # CGNAT partagé opérateur (distinct du LAN domestique)
    if addr in ipaddress.ip_network("100.64.0.0/10"):
        return "CGNAT_OPERATEUR", "100.64.0.0/10 (RFC6598 — sortie partagée FAI, pas LAN client)"

    if addr.is_global:
        return "PUBLIC_IPV4", "Routable Internet (IPv4)"

    return "IPV4_AUTRE", str(addr)


def guess_institution(isp: str) -> str:
    t = (isp or "").strip().lower()
    if not t:
        return "INCONNU_SANS_ISP"
    if any(k in t for k in _GOV):
        return "INSTITUTION_PUBLIQUE_GOUVERNEMENTALE_PROBABLE"
    if any(k in t for k in _EDU):
        return "RECHERCHE_ENSEIGNEMENT_SUPERIEUR_PROBABLE"
    if any(k in t for k in _CLOUD):
        # LLC seul = trop faible
        if t.endswith(" llc") and not any(k in t for k in ("google", "amazon", "microsoft", "oracle")):
            pass
        else:
            if any(k in t for k in _CLOUD):
                return "CLOUD_HEBERGEUR_CDN_PROBABLE"
    if any(k in t for k in _MOBILE):
        return "OPERATEUR_MOBILE_PROBABLE"
    if any(k in t for k in _TELECOM):
        return "FAISCEAU_RESIDENTIEL_ENTREPRISE_PROBABLE"
    # Hébergeur générique
    if "host" in t or "server" in t or "vps" in t or "dedi" in t:
        return "HEBERGEUR_GENERIC_PROBABLE"
    return "AUTRE_OU_ENTREPRISE_NON_CLASSEE"


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    rows = cur.execute(
        """
        SELECT vl1.ip, vl1.country, vl1.country_code, vl1.city, vl1.region,
               vl1.isp, vl1.is_bot, vl1.human_score, vl1.visited_at AS last_seen
        FROM visitor_log vl1
        WHERE vl1.id = (
            SELECT MAX(vl2.id) FROM visitor_log vl2 WHERE vl2.ip = vl1.ip
        )
        ORDER BY vl1.country_code, vl1.ip
        """
    ).fetchall()
    conn.close()

    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "ip",
            "country",
            "country_code",
            "city",
            "region",
            "isp_en_base",
            "portee_ip",
            "detail_portee_ip",
            "type_institution_estime",
            "is_bot",
            "human_score",
            "last_seen",
            "note_methodologie",
        ])
        note = (
            "portee_ip=classification mathématique de l'adresse; "
            "type_institution_estime=heuristique sur libellé ISP (pas ASN); "
            "CGNAT≠LAN domestique client."
        )
        for r in rows:
            scope, scope_detail = classify_ip_scope(r["ip"])
            inst = guess_institution(r["isp"] or "")
            w.writerow([
                r["ip"],
                r["country"],
                r["country_code"],
                r["city"],
                r["region"],
                r["isp"],
                scope,
                scope_detail,
                inst,
                r["is_bot"],
                r["human_score"],
                r["last_seen"],
                note,
            ])

    print(f"OK {len(rows)} IPs -> {OUT}")


if __name__ == "__main__":
    main()
