# -*- coding: utf-8 -*-
"""
Moteur d'intelligence spatiale : analyse passages satellites,
activité solaire, anomalies orbitales → alertes, événements, niveau de risque.
"""


def detect_space_event(data):
    """
    Analyse les données spatiales et produit alertes, événements, risk_level.
    data: dict avec clés optionnelles (passages, solar, voyager, iss, sdr, ...)
    """
    alerts = []
    events = []
    risk_level = "low"

    if not isinstance(data, dict):
        return {"alerts": ["Données invalides"], "events": [], "risk_level": "medium"}

    # Activité solaire
    solar = data.get("solar") or data.get("solar_weather") or {}
    kp = solar.get("kp_index") or solar.get("kp") or 0
    if isinstance(kp, (int, float)):
        if kp >= 7:
            alerts.append("Tempête géomagnétique forte (KP ≥ 7)")
            risk_level = "high"
        elif kp >= 5:
            alerts.append("Activité géomagnétique élevée (KP ≥ 5)")
            if risk_level != "high":
                risk_level = "medium"
    statut = (solar.get("statut_magnetosphere") or "").upper()
    if "ROUGE" in statut or "ORANGE" in statut:
        alerts.append("Magnetosphère perturbée")
        if risk_level != "high":
            risk_level = "medium"

    # Passages satellites
    passages = data.get("passages") or data.get("passes") or []
    if len(passages) > 10:
        events.append("Plusieurs passages orbitaux imminents")
    for p in passages[:5]:
        if isinstance(p, dict) and p.get("elevation", 0) > 70:
            events.append("Passage à haute élévation: " + str(p.get("satellite", p.get("name", "?"))))

    # ISS
    iss = data.get("iss") or {}
    if iss.get("ok") and iss.get("lat") is not None:
        events.append("ISS en suivi — lat %.1f, lon %.1f" % (iss.get("lat", 0), iss.get("lon", 0)))

    # Voyager
    voyager = data.get("voyager") or data.get("voyager_live") or {}
    if voyager.get("statut") and voyager.get("statut") != "Indisponible":
        events.append("Télémétrie Voyager disponible")

    # Anomalies orbitales (ex. données SDR)
    sdr = data.get("sdr") or data.get("sdr_status") or {}
    if isinstance(sdr, dict) and sdr.get("status") == "error":
        alerts.append("SDR en erreur")
        risk_level = "medium"

    return {
        "alerts": alerts,
        "events": events[:20],
        "risk_level": risk_level,
    }
