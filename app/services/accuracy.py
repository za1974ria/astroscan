def compute_iss_accuracy(local_lat, local_lon):
    """
    Compare position locale ISS avec source externe (open-notify API).
    Retourne distance approximative en km + statut.
    """
    import math
    import requests

    if local_lat in (None, 0.0) or local_lon in (None, 0.0):
        return {
            "distance_km": None,
            "status": "skipped",
            "source": "internal",
            "method": "sgp4_vs_external_reference",
            "note": "no valid coordinates for comparison",
        }

    try:
        r = requests.get("http://api.open-notify.org/iss-now.json", timeout=3)
        data = r.json()

        ext_lat = float(data["iss_position"]["latitude"])
        ext_lon = float(data["iss_position"]["longitude"])

        # Approx distance (Haversine simplifie)
        def haversine(lat1, lon1, lat2, lon2):
            radius_km = 6371
            dlat = math.radians(lat2 - lat1)
            dlon = math.radians(lon2 - lon1)
            a = (
                math.sin(dlat / 2) ** 2
                + math.cos(math.radians(lat1))
                * math.cos(math.radians(lat2))
                * math.sin(dlon / 2) ** 2
            )
            return 2 * radius_km * math.asin(math.sqrt(a))

        distance_km = haversine(local_lat, local_lon, ext_lat, ext_lon)

        return {
            "distance_km": round(distance_km, 2),
            "status": "ok",
            "source": "open-notify",
            "method": "sgp4_vs_external_reference",
        }
    except Exception:
        return {
            "distance_km": None,
            "status": "no_reference",
            "source": "fallback",
            "method": "sgp4_vs_external_reference",
            "note": "external reference not available",
        }
