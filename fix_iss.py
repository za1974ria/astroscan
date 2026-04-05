import requests
import time

ISS_CACHE = {
    "data": {"latitude": "0.0", "longitude": "0.0", "timestamp": int(time.time())},
    "last_update": 0
}

def get_iss_location_safe():
    global ISS_CACHE
    current_time = time.time()
    if current_time - ISS_CACHE["last_update"] < 30:
        return ISS_CACHE["data"]
    try:
        r = requests.get("http://api.open-notify.org/iss-now.json", timeout=2.5)
        r.raise_for_status()
        ISS_CACHE["data"] = r.json()
        ISS_CACHE["last_update"] = current_time
        return ISS_CACHE["data"]
    except Exception:
        return ISS_CACHE["data"]
